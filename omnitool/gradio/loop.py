"""
Agentic sampling loop that calls the Anthropic API and local implenmentation of anthropic-defined computer use tools.
"""
from collections.abc import Callable
from enum import StrEnum

from anthropic import APIResponse
from anthropic.types import (
    TextBlock,
)
from anthropic.types.beta import (
    BetaContentBlock,
    BetaMessage,
    BetaMessageParam
)
# from tools import ToolResult # ToolResult might be defined elsewhere or needs adjustment
# ComputerTool is removed, its functionality will be part of a new MCP service.
# For now, direct computer interaction from here is disabled.

# from agent.llm_utils.omniparserclient import OmniParserClient # Replaced by MCPServiceClient
from .mcp_client import MCPServiceClient, MCPServiceError # New client for MCP service

# Assuming ToolResult is still needed by AnthropicExecutor or other parts.
# If it was defined in the old tools.py, we might need to redefine it or import from a new location.
# For now, let's assume it's available or will be handled.
# Placeholder for ToolResult if it's not found elsewhere by the linter/compiler
try:
    from tools import ToolResult # If tools/__init__.py or tools/base.py defines it
except ImportError:
    print("Warning: ToolResult definition not found, using a placeholder. This might cause issues.")
    class ToolResult: # Basic placeholder
        def __init__(self, output=None, error=None, base64_image=None):
            self.output = output
            self.error = error
            self.base64_image = base64_image

from agent.anthropic_agent import AnthropicActor
from agent.vlm_agent import VLMAgent
from agent.vlm_agent_with_orchestrator import VLMOrchestratedAgent
from executor.anthropic_executor import AnthropicExecutor

BETA_FLAG = "computer-use-2024-10-22"

class APIProvider(StrEnum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    VERTEX = "vertex"
    OPENAI = "openai"


PROVIDER_TO_DEFAULT_MODEL_NAME: dict[APIProvider, str] = {
    APIProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
    APIProvider.BEDROCK: "anthropic.claude-3-5-sonnet-20241022-v2:0",
    APIProvider.VERTEX: "claude-3-5-sonnet-v2@20241022",
    APIProvider.OPENAI: "gpt-4o",
}

def sampling_loop_sync(
    *,
    model: str,
    provider: APIProvider | None,
    messages: list[BetaMessageParam],
    output_callback: Callable[[BetaContentBlock], None],
    tool_output_callback: Callable[[ToolResult, str], None],
    api_response_callback: Callable[[APIResponse[BetaMessage]], None],
    api_key: str,
    only_n_most_recent_images: int | None = 2,
    max_tokens: int = 4096,
    # omniparser_url: str, # Replaced by mcp_service_url
    mcp_service_url: str, # URL for the new MCP service
    save_folder: str = "./uploads"
):
    """
    Synchronous agentic sampling loop for the assistant/tool interaction of computer use.
    Uses MCPServiceClient for screen analysis and action execution.
    """
    print(f'In sampling_loop_sync, model: {model}, MCP Service URL: {mcp_service_url}')
    mcp_client = MCPServiceClient(base_url=mcp_service_url)

    # Initialize actor (agent)
    if model == "claude-3-5-sonnet-20241022":
        actor = AnthropicActor(
            model=model, 
            provider=provider,
            api_key=api_key, 
            api_response_callback=api_response_callback,
            max_tokens=max_tokens,
            only_n_most_recent_images=only_n_most_recent_images
        )
    elif model in set(["omniparser + gpt-4o", "omniparser + o1", "omniparser + o3-mini", "omniparser + R1", "omniparser + qwen2.5vl"]):
        actor = VLMAgent(
            model=model,
            provider=provider,
            api_key=api_key,
            api_response_callback=api_response_callback,
            output_callback=output_callback,
            max_tokens=max_tokens,
            only_n_most_recent_images=only_n_most_recent_images
        )
    elif model in set(["omniparser + gpt-4o-orchestrated", "omniparser + o1-orchestrated", "omniparser + o3-mini-orchestrated", "omniparser + R1-orchestrated", "omniparser + qwen2.5vl-orchestrated"]):
        actor = VLMOrchestratedAgent(
            model=model,
            provider=provider,
            api_key=api_key,
            api_response_callback=api_response_callback,
            output_callback=output_callback,
            max_tokens=max_tokens,
            only_n_most_recent_images=only_n_most_recent_images,
            save_folder=save_folder
        )
    else:
        raise ValueError(f"Model {model} not supported")
    executor = AnthropicExecutor(
        output_callback=output_callback,
        tool_output_callback=tool_output_callback,
    )
    print(f"Model Inited: {model}, Provider: {provider}")
    
    tool_result_content = None
    
    print(f"Start the message loop. User messages: {messages}")

    # Main loop for interacting with agent and MCP service
    while True:
        try:
            # 1. Get screen analysis from MCP Service
            # The `use_scaled_coords_for_screenshot_dimensions` parameter could be configurable
            screen_analysis = mcp_client.get_screen_analysis(use_scaled_coords_for_screenshot_dimensions=True)

            # Prepare screen analysis data for the agent
            # The format of `screen_info_for_agent` might need to match what agents expect.
            # VLM Agents used `parsed_screen['screen_info']` which was a stringified list of dicts.
            # Anthropic agent had a specific TextBlock.
            # For now, let's create a string similar to what VLM agent used.

            # Ensure parsed_content_list is a list of dictionaries before processing
            parsed_content_list = screen_analysis.get("parsed_content_list", [])
            if not isinstance(parsed_content_list, list):
                parsed_content_list = [] # Default to empty list if not a list

            screen_info_str = "Screen elements:\n"
            if parsed_content_list: # Check if list is not empty
                for i, item in enumerate(parsed_content_list):
                    if isinstance(item, dict): # Check if item is a dictionary
                         # Default to 'N/A' if 'label' or 'type' is missing
                        label = item.get('label', 'N/A')
                        type = item.get('type', 'N/A')
                        screen_info_str += f"  ID {i}: Type='{type}', Label='{label}'\n"
                    else: # Handle cases where items are not dictionaries
                        screen_info_str += f"  ID {i}: Malformed item {item}\n"


            # Add screen analysis to messages for the agent
            # This part needs to be compatible with how each agent (Anthropic, VLM) expects screen info
            if model == "claude-3-5-sonnet-20241022":
                # Anthropic agent specific formatting
                # The original prompt mentioned "Note you will still need to take screenshot to get the image"
                # This might need adjustment as MCP now provides the screenshot analysis.
                screen_info_block_text = (
                    "Current UI screen analysis (elements and their IDs):\n"
                    f"{screen_info_str}\n"
                    "The screenshot was taken and analyzed. Use the element IDs for actions."
                )
                # We also need to provide the image itself if the Anthropic agent expects it.
                # The original Anthropic agent loop added a screenshot from ComputerTool.
                # For now, let's assume the text description is the primary input.
                # The `tools_use_needed = actor(messages=messages)` call will happen below.
                current_message_content = [TextBlock(text=screen_info_block_text, type='text')]
                # If the agent also needs the image:
                # image_data = screen_analysis.get("original_screenshot_base64")
                # if image_data:
                #    current_message_content.append(ImageBlockParam(type="image", source={"type": "base64", "media_type": "image/png", "data": image_data}))
                messages.append({"role": "user", "content": current_message_content})

                agent_response = actor(messages=messages) # Anthropic agent call

            elif "omniparser + " in model: # VLM agents
                # VLM agents received `parsed_screen` dict. Let's adapt.
                # The VLM agent's `__call__` method expects `parsed_screen` as a dictionary.
                # It uses `parsed_screen['original_screenshot_base64']`, `['latency']`, `['screen_info']`, etc.
                # We need to reconstruct a similar dict from `screen_analysis`.
                # The VLM agent also saves screenshots to files like `screenshot_{uuid}.png`.
                # This local file saving part might need to be handled differently or skipped if MCP provides all data.

                # For now, let's pass a dictionary mimicking the old `parsed_screen` structure.
                # The VLM agent handles image display and processing based on this.
                # The `screen_info` for VLM agent was a string representation of `parsed_content_list`.
                vlm_parsed_screen_input = {
                    "original_screenshot_base64": screen_analysis.get("original_screenshot_base64"),
                    "som_image_base64": screen_analysis.get("som_image_base64"), # VLM agent uses this for display
                    "parsed_content_list": parsed_content_list, # VLM agent uses this to get bbox for Box ID
                    "screen_info": screen_info_str, # String representation for the prompt
                    "latency": screen_analysis.get("latency_omniparser", 0),
                    "screenshot_uuid": "mcp_generated", # Placeholder UUID
                    "width": screen_analysis.get("screen_width"),
                    "height": screen_analysis.get("screen_height"),
                    # VLM agent might also save images locally using uuid, this behavior needs review.
                }
                agent_response, vlm_response_json = actor(messages=messages, parsed_screen=vlm_parsed_screen_input)
            else:
                raise ValueError(f"Model {model} screen info preparation not implemented.")

            # 2. Process agent response and execute actions via MCP Service
            # The `executor` was used for Anthropic. VLM agents returned JSON directly.

            if model == "claude-3-5-sonnet-20241022":
                # Anthropic agent returns a message object with potential tool_use blocks.
                # The old executor would iterate through these. We need to adapt this.
                tool_results_for_agent = []
                if agent_response.stop_reason == "tool_use":
                    for content_block in agent_response.content:
                        if content_block.type == "text":
                            output_callback(content_block) # Display agent's text
                            yield messages # Update UI
                        elif content_block.type == "tool_use":
                            tool_name = content_block.name
                            tool_input = content_block.input
                            tool_use_id = content_block.id

                            output_callback(content_block) # Display tool use intent
                            yield messages

                            if tool_name == "computer": # Assuming the agent still calls a "computer" tool
                                mcp_action_type = tool_input.get("action")
                                mcp_parameters = {k: v for k, v in tool_input.items() if k != "action"}

                                try:
                                    action_result = mcp_client.execute_action(action_type=mcp_action_type, parameters=mcp_parameters)
                                    tool_output_for_callback = ToolResult(output=str(action_result.get("data", action_result.get("message"))))
                                    # The Anthropic agent expects a ToolResultBlockParam
                                    tool_results_for_agent.append({
                                        "type": "tool_result",
                                        "tool_use_id": tool_use_id,
                                        "content": [TextBlock(text=str(action_result.get("data", action_result.get("message"))), type="text")]
                                        # TODO: Handle image results if agent expects them
                                    })
                                except MCPServiceError as e:
                                    tool_output_for_callback = ToolResult(error=str(e))
                                    tool_results_for_agent.append({
                                        "type": "tool_result",
                                        "tool_use_id": tool_use_id,
                                        "content": [TextBlock(text=f"Error: {str(e)}", type="text")],
                                        "is_error": True
                                    })
                                tool_output_callback(tool_output_for_callback, tool_use_id) # For UI
                                yield messages
                            else:
                                # Handle unknown tool for Anthropic agent
                                error_msg = f"Unknown tool: {tool_name}"
                                tool_output_callback(ToolResult(error=error_msg), tool_use_id)
                                tool_results_for_agent.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": [TextBlock(text=error_msg, type="text")], "is_error": True})
                                yield messages

                    if not tool_results_for_agent: # No tool use, or loop should end
                         messages.append({"role": "assistant", "content": agent_response.content})
                         yield messages # Show final assistant text if any
                         return messages # End loop

                    # Add tool results back to messages for the agent's next turn
                    messages.append({"role": "assistant", "content": agent_response.content}) # Agent's turn
                    messages.append({"role": "user", "content": tool_results_for_agent})      # Tool results

                else: # Stop reason is not tool_use (e.g., end_turn, max_tokens)
                    for content_block in agent_response.content: # Display final text
                        if content_block.type == "text":
                            output_callback(content_block)
                    yield messages
                    return messages # End loop

            elif "omniparser + " in model: # VLM agents
                # VLM agent's `actor` call returns `(response_message, vlm_response_json)`
                # `response_message` is a BetaMessage potentially with tool_use blocks constructed by the VLM agent wrapper
                # `vlm_response_json` is the direct JSON output from the VLM.

                # The VLM agent wrapper already calls output_callback for reasoning, images etc.
                # We need to execute the actions specified in `response_message.content` (if any tool_use)

                action_performed_this_turn = False
                if agent_response and agent_response.content:
                    for content_block in agent_response.content:
                        if content_block.type == "text":
                            # This text is usually the VLM's reasoning, already handled by VLM agent's output_callback
                            # output_callback(content_block) # Display agent's text if not already done
                            pass
                        elif content_block.type == "tool_use":
                            tool_name = content_block.name
                            tool_input = content_block.input
                            # tool_use_id = content_block.id # VLM agent might not use this for callback

                            output_callback(content_block) # Display tool use intent (e.g., "Next I will perform...")
                            yield messages


                            if tool_name == "computer": # VLM agent constructs "computer" tool uses
                                mcp_action_type = tool_input.get("action")
                                # Map VLM agent's 'value' to 'text' for type action, etc.
                                mcp_parameters = {}
                                if "coordinate" in tool_input:
                                    mcp_parameters["x"] = tool_input["coordinate"][0]
                                    mcp_parameters["y"] = tool_input["coordinate"][1]
                                    mcp_parameters["use_scaled_coords"] = False # VLM output coords are actual screen coords
                                if "text" in tool_input: # For 'type' action
                                    mcp_parameters["text"] = tool_input["text"]

                                # Add other parameters if the VLM agent specifies them directly matching MCP
                                for k, v in tool_input.items():
                                    if k not in ["action", "coordinate", "text"] and k in ["button", "clicks", "interval", "key_name", "amount", "duration", "region", "path"]:
                                        mcp_parameters[k] = v

                                try:
                                    action_result = mcp_client.execute_action(action_type=mcp_action_type, parameters=mcp_parameters)
                                    # VLM agent's output_callback already shows rich output.
                                    # We might just log success or pass minimal info.
                                    # The VLM agent loop doesn't typically append tool results to `messages` for next turn,
                                    # it gets fresh screen analysis.
                                    action_summary = str(action_result.get("data", action_result.get("message", "Action executed.")))
                                    output_callback(TextBlock(text=f"Action result: {action_summary}", type="text"))
                                    yield messages

                                    action_performed_this_turn = True
                                    if mcp_action_type == "type": # Typing often implies submission / next step
                                        # VLM agent's `typewrite` includes enter, so screenshot is useful
                                        # Let the loop fetch new screen analysis naturally.
                                        pass


                                except MCPServiceError as e:
                                    output_callback(TextBlock(text=f"MCP Action Error: {str(e)}", type="text"))
                                    yield messages
                                    # Decide if loop should break on error
                                    return messages # End loop on error for now
                            else:
                                output_callback(TextBlock(text=f"VLM Agent: Unknown tool '{tool_name}'", type="text"))
                                yield messages

                # If VLM agent specified "Next Action": "None" or no actions were found, end.
                if vlm_response_json.get("Next Action", "").lower() == "none" and not action_performed_this_turn:
                    output_callback(TextBlock(text="Task marked complete by VLM agent or no action taken.", type="text"))
                    yield messages
                    return messages # End loop

                # VLM loop continues by getting new screen analysis. No explicit message appending here usually.
                # If messages were modified by the actor (e.g. adding its own reasoning), they persist.

            else: # Should not happen if model check at start is correct
                output_callback(TextBlock(text=f"Error: Model type {model} not handled in main loop.", type="text"))
                yield messages
                return messages
        
        except MCPServiceError as e:
            error_text = f"MCP Service Error: {e.status_code} - {e.message}"
            if e.response_text:
                error_text += f" Details: {e.response_text[:200]}" # Truncate long responses
            output_callback(TextBlock(text=error_text, type="text"))
            yield messages # Update UI with error
            return messages # Stop the loop on MCP service error
        except Exception as e:
            import traceback
            error_text = f"An unexpected error occurred in the sampling loop: {type(e).__name__} - {str(e)}"
            output_callback(TextBlock(text=error_text, type="text"))
            output_callback(TextBlock(text=f"Traceback: {traceback.format_exc()[:500]}", type="text")) # Log part of traceback to UI
            print(error_text)
            traceback.print_exc()
            yield messages
            return messages # Stop the loop on unexpected error