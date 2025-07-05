"""
Agentic sampling loop that calls the Anthropic API and local implenmentation of anthropic-defined computer use tools.
"""
import asyncio
import platform
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from anthropic import Anthropic, AnthropicBedrock, AnthropicVertex, APIResponse
from anthropic.types import (
    ToolResultBlockParam,
)
from anthropic.types.beta import (
    BetaContentBlock,
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
)
from anthropic.types import TextBlock
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock

# ComputerTool and ToolCollection are removed as part of the refactor.
# The agent will interact with a new MCP service instead of directly using these tools.
# from tools import ComputerTool, ToolCollection
# ToolResult might still be needed if it's a generic class for tool outputs.
# For now, let's assume it's available or will be handled.
# Placeholder for ToolResult if it's not found elsewhere by the linter/compiler
try:
    from tools import ToolResult # If tools/__init__.py or tools/base.py defines it
except ImportError:
    print("Warning: ToolResult definition not found in anthropic_agent.py, using a placeholder. This might cause issues.")
    class ToolResult: # Basic placeholder
        def __init__(self, output=None, error=None, base64_image=None):
            self.output = output
            self.error = error
            self.base64_image = base64_image

from PIL import Image
from io import BytesIO
import gradio as gr
from typing import Dict

BETA_FLAG = "computer-use-2024-10-22"

class APIProvider(StrEnum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    VERTEX = "vertex"

SYSTEM_PROMPT = f"""<SYSTEM_CAPABILITY>
* You are utilizing a Windows system with internet access.
* The current date is {datetime.today().strftime('%A, %B %d, %Y')}.
</SYSTEM_CAPABILITY>
"""

class AnthropicActor:
    def __init__(
        self, 
        model: str, 
        provider: APIProvider,
        api_key: str,
        api_response_callback: Callable[[APIResponse[BetaMessage]], None],
        max_tokens: int = 4096,
        only_n_most_recent_images: int | None = None,
        print_usage: bool = True,
    ):
        self.model = model
        self.provider = provider
        self.api_key = api_key
        self.api_response_callback = api_response_callback
        self.max_tokens = max_tokens
        self.only_n_most_recent_images = only_n_most_recent_images
        
        # self.tool_collection = ToolCollection(ComputerTool()) # Removed: Tools will be managed by the MCP service
        self.tool_collection_params = [self.get_mcp_computer_tool_schema()]

        self.system = SYSTEM_PROMPT
        
        self.total_token_usage = 0
        self.total_cost = 0
        self.print_usage = print_usage

        # Instantiate the appropriate API client based on the provider
        if provider == APIProvider.ANTHROPIC:
            self.client = Anthropic(api_key=api_key)
        elif provider == APIProvider.VERTEX:
            self.client = AnthropicVertex()
        elif provider == APIProvider.BEDROCK:
            self.client = AnthropicBedrock()

    def __call__(
        self, 
        *,
        messages: list[BetaMessageParam]
    ):
        """
        Generate a response given history messages.
        """
        if self.only_n_most_recent_images:
            _maybe_filter_to_n_most_recent_images(messages, self.only_n_most_recent_images)

        # Call the API synchronously
        raw_response = self.client.beta.messages.with_raw_response.create(
            max_tokens=self.max_tokens,
            messages=messages,
            model=self.model,
            system=self.system,
            # tools=self.tool_collection.to_params(), # Tools will be handled differently via MCP service
            tools=self.tool_collection_params, # Use the placeholder
            betas=["computer-use-2024-10-22"], # This beta flag might relate to specific tool schemas.
                                               # We'll need to ensure the MCP service provides tools in a compatible way,
                                               # or this part of the API call might need to change.
        )

        self.api_response_callback(cast(APIResponse[BetaMessage], raw_response))

        response = raw_response.parse()
        print(f"AnthropicActor response: {response}")

        self.total_token_usage += response.usage.input_tokens + response.usage.output_tokens
        self.total_cost += (response.usage.input_tokens * 3 / 1000000 + response.usage.output_tokens * 15 / 1000000)
        
        if self.print_usage:
            print(f"Claude total token usage so far: {self.total_token_usage}, total cost so far: $USD{self.total_cost}")
        
        return response


def _maybe_filter_to_n_most_recent_images(
    messages: list[BetaMessageParam],
    images_to_keep: int,
    min_removal_threshold: int = 10,
):
    """
    With the assumption that images are screenshots that are of diminishing value as
    the conversation progresses, remove all but the final `images_to_keep` tool_result
    images in place, with a chunk of min_removal_threshold to reduce the amount we
    break the implicit prompt cache.
    """
    if images_to_keep is None:
        return messages

    tool_result_blocks = cast(
        list[ToolResultBlockParam],
        [
            item
            for message in messages
            for item in (
                message["content"] if isinstance(message["content"], list) else []
            )
            if isinstance(item, dict) and item.get("type") == "tool_result"
        ],
    )

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get("content", [])
        if isinstance(content, dict) and content.get("type") == "image"
    )

    images_to_remove = total_images - images_to_keep
    # for better cache behavior, we want to remove in chunks
    images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get("content"), list):
            new_content = []
            for content in tool_result.get("content", []):
                if isinstance(content, dict) and content.get("type") == "image":
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result["content"] = new_content

    def get_mcp_computer_tool_schema(self) -> Dict[str, Any]:
        """
        Returns the JSON schema for the 'computer' tool, reflecting MCP service capabilities.
        This schema should align with what mcp_server.py's ExecuteActionRequest expects.
        """
        # Based on ActionParameter and ExecuteActionRequest in mcp_server.py
        parameter_properties = {
            "x": {"type": "integer", "description": "X-coordinate for mouse actions."},
            "y": {"type": "integer", "description": "Y-coordinate for mouse actions."},
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "default": "left",
                "description": "Mouse button to be used."
            },
            "clicks": {"type": "integer", "default": 1, "description": "Number of clicks."},
            "interval": {"type": "number", "default": 0.0, "description": "Interval between clicks or for typing. Also used as duration for wait."},
            "text": {"type": "string", "description": "Text to type."},
            "key_name": {"type": "string", "description": "Name of the key to press (e.g., 'enter', 'ctrl+c')."},
            "amount": {"type": "integer", "description": "Scroll amount (positive up, negative down)."},
            "duration": {"type": "number", "default": 0.5, "description": "Duration for drag actions."},
            "region": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Region for screenshot (left, top, width, height)."
            },
            "use_scaled_coords": {
                "type": "boolean",
                "default": False,
                "description": "Whether x, y, region coordinates are in scaled space (normalized to a target resolution) rather than actual screen pixels."
            },
            "path": {"type": "string", "description": "File path to save a screenshot."}
        }

        action_types = [
            "mouse_move", "click", "drag_to", "type_text", "press_key",
            "key_down", "key_up", "scroll", "get_cursor_position",
            "get_screen_dimensions", "take_screenshot", "wait"
        ]

        return {
            "name": "computer",
            "description": (
                "Allows interaction with the computer's screen, mouse, and keyboard. "
                "All coordinates (x, y, region) are assumed to be actual screen pixel values unless 'use_scaled_coords' is true. "
                "If 'use_scaled_coords' is true, coordinates are relative to a scaled logical display area."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": action_types,
                        "description": "The type of computer action to perform."
                    },
                    # Include all parameters from ActionParameter, making them optional
                    # as specific actions only need a subset.
                    # The 'required' field at the object level can list parameters
                    # that are always required for any action, if any (e.g., 'action' itself).
                    **parameter_properties
                },
                "required": ["action"] # Only 'action' is universally required for the tool call.
                                       # Specific actions will have their own parameter requirements,
                                       # handled by the MCP service.
            }
        }