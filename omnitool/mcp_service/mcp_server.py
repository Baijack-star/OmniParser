import sys
import os
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Any, Literal, Tuple, Optional, Dict
import base64
from io import BytesIO

# Add project root to sys.path to allow importing from omnitool.mcp and util
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

from omnitool.mcp.desktop_automation import DesktopAutomation, DesktopAutomationError
from util.omniparser import Omniparser # Assuming direct use for now

# --- Configuration ---
# OmniParser configuration (example, adjust as needed)
OMNIPARSER_CONFIG = {
    'som_model_path': os.path.join(root_dir, 'weights/icon_detect/model.pt'),
    'caption_model_name': 'florence2',
    'caption_model_path': os.path.join(root_dir, 'weights/icon_caption_florence'),
    'device': 'cpu',  # Change to 'cuda' if GPU is available and desired
    'BOX_TRESHOLD': 0.05
}

# --- Pydantic Models for API requests and responses ---
class ActionParameter(BaseModel):
    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[Literal["left", "right", "middle"]] = "left"
    clicks: Optional[int] = 1
    interval: Optional[float] = 0.0
    text: Optional[str] = None
    key_name: Optional[str] = None
    amount: Optional[int] = None # For scrolling
    duration: Optional[float] = 0.5 # For dragging
    region: Optional[Tuple[int, int, int, int]] = None # For screenshot region
    use_scaled_coords: Optional[bool] = Field(default=False, description="Whether x,y,region are in scaled coordinates")
    path: Optional[str] = None # For saving screenshot

class ExecuteActionRequest(BaseModel):
    action_type: Literal[
        "mouse_move", "click", "drag_to", "type_text", "press_key",
        "key_down", "key_up", "scroll", "get_cursor_position",
        "get_screen_dimensions", "take_screenshot", "wait"
    ]
    parameters: Optional[ActionParameter] = None

class ScreenAnalysisResponse(BaseModel):
    screen_width: int
    screen_height: int
    scaled_screen_width: Optional[int] = None
    scaled_screen_height: Optional[int] = None
    original_screenshot_base64: str
    som_image_base64: Optional[str] = None # From OmniParser
    parsed_content_list: Optional[list] = None # From OmniParser
    latency_omniparser: Optional[float] = None
    message: Optional[str] = None

class SimpleResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[Any] = None

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Multimodal Cybernetic Peripheral (MCP) Service",
    description="Provides screen analysis and desktop automation capabilities.",
)

# --- Global Instances ---
# Initialize DesktopAutomation. enable_scaling can be a config option.
desktop_auto: Optional[DesktopAutomation] = None
omni_parser_instance: Optional[Omniparser] = None

@app.on_event("startup")
async def startup_event():
    global desktop_auto, omni_parser_instance
    try:
        desktop_auto = DesktopAutomation(enable_scaling=True) # Example: enable scaling
        # Initialize OmniParser
        # Option 1: Run OmniParser server separately and use a client (like OmniParserClient in loop.py)
        # Option 2: Initialize OmniParser directly here (chosen for this example)
        # Ensure OMNIPARSER_CONFIG paths are correct relative to where this server runs
        # This might be slow if models are large and loaded on CPU at startup
        omni_parser_instance = Omniparser(OMNIPARSER_CONFIG)
        print("DesktopAutomation and OmniParser initialized.")
    except Exception as e:
        print(f"Error during startup initialization: {e}")
        # You might want to prevent the app from starting or handle this more gracefully
        desktop_auto = None
        omni_parser_instance = None


# --- API Endpoints ---
@app.get("/probe", response_model=SimpleResponse)
async def probe_server():
    if desktop_auto is not None and omni_parser_instance is not None:
        return {"status": "success", "message": "MCP Service is running and initialized."}
    elif desktop_auto is not None:
        return {"status": "partial", "message": "MCP Service is running, DesktopAutomation initialized, OmniParser FAILED."}
    else:
        return {"status": "error", "message": "MCP Service is running, but DesktopAutomation FAILED to initialize."}

@app.post("/execute_action", response_model=SimpleResponse)
async def execute_action(request: ExecuteActionRequest = Body(...)):
    if desktop_auto is None:
        raise HTTPException(status_code=503, detail="DesktopAutomation not initialized.")

    action_type = request.action_type
    params = request.parameters if request.parameters else ActionParameter()

    try:
        result = None
        if action_type == "mouse_move":
            if params.x is None or params.y is None:
                raise HTTPException(status_code=400, detail="x and y are required for mouse_move")
            desktop_auto.mouse_move(params.x, params.y, use_scaled_coords=params.use_scaled_coords)
            result = f"Moved mouse to ({params.x}, {params.y})"
        elif action_type == "click":
            desktop_auto.click(params.x, params.y, button=params.button, clicks=params.clicks, interval=params.interval, use_scaled_coords=params.use_scaled_coords)
            result = f"Clicked {params.button} button {params.clicks} times"
        elif action_type == "drag_to":
            if params.x is None or params.y is None:
                raise HTTPException(status_code=400, detail="x and y are required for drag_to")
            desktop_auto.drag_to(params.x, params.y, button=params.button, duration=params.duration, use_scaled_coords=params.use_scaled_coords)
            result = f"Dragged mouse to ({params.x}, {params.y})"
        elif action_type == "type_text":
            if params.text is None:
                raise HTTPException(status_code=400, detail="text is required for type_text")
            desktop_auto.type_text(params.text, interval=params.interval)
            result = f"Typed text: {params.text}"
        elif action_type == "press_key":
            if params.key_name is None:
                raise HTTPException(status_code=400, detail="key_name is required for press_key")
            desktop_auto.press_key(params.key_name)
            result = f"Pressed key: {params.key_name}"
        elif action_type == "key_down":
            if params.key_name is None:
                raise HTTPException(status_code=400, detail="key_name is required for key_down")
            desktop_auto.key_down(params.key_name)
            result = f"Key down: {params.key_name}"
        elif action_type == "key_up":
            if params.key_name is None:
                raise HTTPException(status_code=400, detail="key_name is required for key_up")
            desktop_auto.key_up(params.key_name)
            result = f"Key up: {params.key_name}"
        elif action_type == "scroll":
            if params.amount is None:
                raise HTTPException(status_code=400, detail="amount is required for scroll")
            desktop_auto.scroll(params.amount, params.x, params.y, use_scaled_coords=params.use_scaled_coords)
            result = f"Scrolled by {params.amount}"
        elif action_type == "get_cursor_position":
            pos = desktop_auto.get_cursor_position(use_scaled_coords=params.use_scaled_coords)
            result = {"x": pos[0], "y": pos[1]}
        elif action_type == "get_screen_dimensions":
            dims = desktop_auto.get_screen_dimensions(use_scaled_coords=params.use_scaled_coords)
            result = {"width": dims[0], "height": dims[1]}
        elif action_type == "take_screenshot":
            pil_image = desktop_auto.take_screenshot(region=params.region, use_scaled_coords_for_region=params.use_scaled_coords)
            if params.path:
                pil_image.save(params.path)
                result = f"Screenshot saved to {params.path}"
            else:
                buffered = BytesIO()
                pil_image.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                result = {"base64_image": img_str}
        elif action_type == "wait":
            if params.interval is None: # Using interval for wait duration
                raise HTTPException(status_code=400, detail="interval (duration) is required for wait")
            desktop_auto.wait(params.interval)
            result = f"Waited for {params.interval} seconds"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action_type: {action_type}")

        return {"status": "success", "message": f"Action '{action_type}' executed.", "data": result}

    except DesktopAutomationError as e:
        raise HTTPException(status_code=500, detail=f"Desktop automation error: {str(e)}")
    except HTTPException: # Re-raise HTTPExceptions
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

@app.get("/get_screen_analysis", response_model=ScreenAnalysisResponse)
async def get_screen_analysis(use_scaled_coords_for_screenshot_dimensions: Optional[bool] = False):
    if desktop_auto is None or omni_parser_instance is None:
        raise HTTPException(status_code=503, detail="DesktopAutomation or OmniParser not initialized.")

    try:
        # 1. Take screenshot
        pil_image = desktop_auto.take_screenshot()
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        screenshot_base64 = base64.b64encode(buffered.getvalue()).decode()

        # 2. Get screen dimensions
        actual_width, actual_height = desktop_auto.get_screen_dimensions(use_scaled_coords=False)
        scaled_width, scaled_height = None, None
        if desktop_auto.enable_scaling:
            scaled_dims = desktop_auto.get_screen_dimensions(use_scaled_coords=True)
            scaled_width, scaled_height = scaled_dims[0], scaled_dims[1]

        # 3. Parse with OmniParser
        # This is a blocking call. For a production server, consider running OmniParser
        # in a separate thread or process pool if it's CPU/GPU intensive.
        import time # For latency measurement
        start_time = time.time()
        som_image_base64_str, parsed_content = omni_parser_instance.parse(screenshot_base64)
        latency = time.time() - start_time

        return ScreenAnalysisResponse(
            screen_width=actual_width,
            screen_height=actual_height,
            scaled_screen_width=scaled_width,
            scaled_screen_height=scaled_height,
            original_screenshot_base64=screenshot_base64,
            som_image_base64=som_image_base64_str,
            parsed_content_list=parsed_content,
            latency_omniparser=latency
        )

    except DesktopAutomationError as e:
        raise HTTPException(status_code=500, detail=f"Desktop automation error during screen analysis: {str(e)}")
    except Exception as e:
        # Log the full error for debugging
        print(f"Error in /get_screen_analysis: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during screen analysis: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Ensure OMNIPARSER_CONFIG paths are correct if running this directly
    # The startup event will handle initialization.
    print(f"OMNIPARSER_CONFIG used by server: {OMNIPARSER_CONFIG}")
    uvicorn.run(app, host="0.0.0.0", port=8001) # Using a different port from OmniParserServer if it runs separately
