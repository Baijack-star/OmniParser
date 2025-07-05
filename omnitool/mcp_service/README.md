# OmniTool - Multimodal Cybernetic Peripheral (MCP) Service

The MCP Service provides a unified API for AI agents to perceive and interact with a computer's graphical user interface. It combines screen analysis capabilities (using OmniParser) with desktop automation (mouse, keyboard, screen control).

## Running the MCP Service

The MCP Service is a FastAPI application located in `omnitool/mcp_service/mcp_server.py`.

**Prerequisites:**
1.  Ensure all dependencies from the main `requirements.txt` of the OmniParser project are installed.
2.  OmniParser model weights should be downloaded and correctly placed in the `weights/` directory as per the main project's README. The default paths in `mcp_server.py` point to:
    *   `weights/icon_detect/model.pt`
    *   `weights/icon_caption_florence`
    These paths and other OmniParser configurations can be adjusted in the `OMNIPARSER_CONFIG` dictionary within `mcp_server.py`.
3.  The machine running the MCP service needs a desktop environment for `pyautogui` to function correctly (e.g., X11 server on Linux). For screenshots on Linux, `scrot` is usually required (`sudo apt-get install scrot`).

**To run the server:**
Navigate to the `omnitool/mcp_service/` directory and run:
```bash
python mcp_server.py
```
By default, it starts on `http://0.0.0.0:8001`. You can change the host and port in the `uvicorn.run` command at the end of `mcp_server.py`.

The server initializes `DesktopAutomation` (for controlling the computer it's running on) and `Omniparser` (for screen analysis) at startup.

## API Endpoints

The service exposes the following HTTP endpoints:

### 1. `GET /probe`

Checks the status of the MCP Service.

*   **Response (`200 OK`)**:
    ```json
    {
        "status": "success" | "partial" | "error",
        "message": "Descriptive message about the service status."
    }
    ```
    *   `"success"`: All components initialized correctly.
    *   `"partial"`: Service is running, but one or more components (e.g., OmniParser) failed to initialize. Check the message for details.
    *   `"error"`: Critical component (e.g., DesktopAutomation) failed to initialize.

### 2. `POST /execute_action`

Executes a specified desktop automation action.

*   **Request Body**:
    ```json
    {
        "action_type": "action_name",
        "parameters": {
            // Parameters vary based on action_type
            // See omnitool.mcp_service.mcp_server.ActionParameter for all possible fields
            "x": 100, // Optional: integer
            "y": 200, // Optional: integer
            "button": "left", // Optional: "left" | "right" | "middle", default "left"
            "clicks": 1, // Optional: integer, default 1
            "interval": 0.0, // Optional: float, default 0.0 (used for click interval, type interval, wait duration)
            "text": "hello world", // Optional: string (for type_text)
            "key_name": "enter", // Optional: string (for press_key, key_down, key_up)
            "amount": 100, // Optional: integer (for scroll)
            "duration": 0.5, // Optional: float (for drag_to)
            "region": [0, 0, 800, 600], // Optional: tuple[int, int, int, int] (for take_screenshot)
            "use_scaled_coords": false, // Optional: boolean, default false
            "path": "/path/to/save/screenshot.png" // Optional: string (for take_screenshot)
        }
    }
    ```
    **`action_type` can be one of:**
    `"mouse_move"`, `"click"`, `"drag_to"`, `"type_text"`, `"press_key"`, `"key_down"`, `"key_up"`, `"scroll"`, `"get_cursor_position"`, `"get_screen_dimensions"`, `"take_screenshot"`, `"wait"`.

    **`parameters` object:**
    *   `x`, `y`: Coordinates for mouse actions.
    *   `button`: Mouse button (`"left"`, `"right"`, `"middle"`).
    *   `clicks`: Number of clicks.
    *   `interval`: Time interval for actions (e.g., between clicks, between characters typed, duration for `wait`).
    *   `text`: String to be typed.
    *   `key_name`: Key to be pressed (e.g., `"enter"`, `"esc"`, `"ctrl+c"`).
    *   `amount`: Scroll amount (positive for up, negative for down).
    *   `duration`: Time duration for drag actions.
    *   `region`: A tuple `(left, top, width, height)` for regional screenshots.
    *   `use_scaled_coords`: If `true`, `x`, `y`, and `region` are interpreted as coordinates in a scaled/normalized display space. If `false` (default), they are actual screen pixel coordinates. The scaling behavior is defined by `DesktopAutomation`'s `MAX_SCALING_TARGETS`.
    *   `path`: If provided for `take_screenshot`, the image is saved to this path on the server running MCP. Otherwise, the image is returned as base64.

*   **Response (`200 OK`)**:
    ```json
    {
        "status": "success",
        "message": "Action 'action_name' executed.",
        "data": { /* Action-specific result, e.g., cursor position, screenshot data */ }
    }
    ```
    *   For `get_cursor_position`: `data` is `{"x": int, "y": int}`.
    *   For `get_screen_dimensions`: `data` is `{"width": int, "height": int}`.
    *   For `take_screenshot` (no path): `data` is `{"base64_image": "base64_encoded_png_string"}`.
    *   For `take_screenshot` (with path): `data` is a confirmation message.
    *   Other actions usually return a confirmation message in `data` or `message`.

*   **Error Responses**: `400 Bad Request` for invalid parameters, `500 Internal Server Error` or `503 Service Unavailable` for execution errors or uninitialized components.

### 3. `GET /get_screen_analysis`

Captures the current screen, analyzes it using OmniParser, and returns the results.

*   **Query Parameters**:
    *   `use_scaled_coords_for_screenshot_dimensions` (boolean, optional, default `false`): If `true`, the `scaled_screen_width` and `scaled_screen_height` in the response will reflect the target scaled dimensions. The main `screen_width` and `screen_height` are always actual pixel dimensions.

*   **Response (`200 OK`)**:
    ```json
    {
        "screen_width": 1920, // Actual screen width in pixels
        "screen_height": 1080, // Actual screen height in pixels
        "scaled_screen_width": 1280, // Optional: Scaled width if scaling is enabled
        "scaled_screen_height": 800, // Optional: Scaled height if scaling is enabled
        "original_screenshot_base64": "base64_encoded_png_string_of_full_screenshot",
        "som_image_base64": "base64_encoded_png_string_of_omniparser_visualization", // Optional
        "parsed_content_list": [ /* List of UI elements detected by OmniParser */ ], // Optional
        "latency_omniparser": 0.5, // Optional: Time taken for OmniParser processing in seconds
        "message": null // Optional: Additional messages
    }
    ```
    The structure of `parsed_content_list` items is defined by OmniParser's output.

*   **Error Responses**: `500 Internal Server Error` or `503 Service Unavailable` if errors occur during screenshotting or parsing.


## Example Python Client Interaction

This example demonstrates how to interact with the MCP Service from a Python script using the `requests` library. For a more robust client, see `omnitool/gradio/mcp_client.py`.

```python
import requests
import base64
from io import BytesIO
from PIL import Image
import time

MCP_SERVICE_URL = "http://localhost:8001" # Adjust if your service runs elsewhere

def get_screen_analysis():
    try:
        response = requests.get(f"{MCP_SERVICE_URL}/get_screen_analysis")
        response.raise_for_status()
        analysis_data = response.json()
        print("Screen Analysis:")
        print(f"  Dimensions: {analysis_data['screen_width']}x{analysis_data['screen_height']}")
        if analysis_data.get('scaled_screen_width'):
            print(f"  Scaled Dimensions: {analysis_data['scaled_screen_width']}x{analysis_data['scaled_screen_height']}")

        # To display the screenshot (optional)
        # img_data = base64.b64decode(analysis_data['original_screenshot_base64'])
        # img = Image.open(BytesIO(img_data))
        # img.show()

        if analysis_data.get('parsed_content_list'):
            print(f"  Parsed elements: {len(analysis_data['parsed_content_list'])}")
            # print(analysis_data['parsed_content_list'][0] if analysis_data['parsed_content_list'] else "No elements")
        print(f"  OmniParser Latency: {analysis_data.get('latency_omniparser', 'N/A')}s")
        return analysis_data
    except requests.exceptions.RequestException as e:
        print(f"Error getting screen analysis: {e}")
        return None

def execute_mcp_action(action_type: str, parameters: dict = None):
    payload = {"action_type": action_type}
    if parameters:
        payload["parameters"] = parameters

    try:
        response = requests.post(f"{MCP_SERVICE_URL}/execute_action", json=payload)
        response.raise_for_status()
        result = response.json()
        print(f"Action '{action_type}' result: {result.get('message', '')} Data: {result.get('data')}")
        return result
    except requests.exceptions.RequestException as e:
        print(f"Error executing action '{action_type}': {e}")
        if e.response is not None:
            print(f"Response content: {e.response.text}")
        return None

if __name__ == "__main__":
    # 1. Probe the server
    try:
        probe_response = requests.get(f"{MCP_SERVICE_URL}/probe")
        probe_response.raise_for_status()
        print(f"MCP Service Probe: {probe_response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"MCP Service not responding or error during probe: {e}")
        exit()

    # 2. Get screen analysis
    screen_data = get_screen_analysis()

    if screen_data:
        # Example: Get current cursor position (using actual screen coordinates)
        execute_mcp_action("get_cursor_position", {"use_scaled_coords": False})

        # Example: Move mouse to (100,100) actual screen coordinates (Use with caution!)
        # print("\nMoving mouse to (100,100)...")
        # execute_mcp_action("mouse_move", {"x": 100, "y": 100, "use_scaled_coords": False})
        # time.sleep(1)

        # Example: Click at the current mouse position
        # print("Clicking left button...")
        # execute_mcp_action("click", {"button": "left"})
        # time.sleep(1)

        # Example: Type text (ensure a text field is focused on the target machine)
        # print("Typing 'Hello from MCP Client!'...")
        # execute_mcp_action("type_text", {"text": "Hello from MCP Client!"})
        # execute_mcp_action("press_key", {"key_name": "enter"})

        # Example: Take a screenshot and save it (server-side) or get base64
        print("\nTaking a screenshot (returned as base64)...")
        screenshot_action_result = execute_mcp_action("take_screenshot")
        if screenshot_action_result and screenshot_action_result.get('data', {}).get('base64_image'):
            print("Base64 screenshot received.")
            # To save it:
            # b64_data = screenshot_action_result['data']['base64_image']
            # img_bytes = base64.b64decode(b64_data)
            # with open("mcp_screenshot.png", "wb") as f:
            #     f.write(img_bytes)
            # print("Screenshot saved as mcp_screenshot.png")

        # print("\nTaking a screenshot and saving to server_screenshot.png on the server...")
        # execute_mcp_action("take_screenshot", {"path": "server_screenshot.png"})

```

This README provides a good starting point for users to understand and interact with the MCP Service.
