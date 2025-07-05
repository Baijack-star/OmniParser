import requests
import json
from typing import Any, Optional, Dict, Literal, Tuple

# Assuming mcp_server.py is running and accessible at this URL
DEFAULT_MCP_SERVICE_URL = "http://localhost:8001"

class MCPServiceError(Exception):
    """Custom exception for MCPServiceClient errors."""
    def __init__(self, message, status_code=None, response_text=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class MCPServiceClient:
    def __init__(self, base_url: str = DEFAULT_MCP_SERVICE_URL):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=90, **kwargs) # Increased timeout
            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
            if response.content:
                return response.json()
            return None # Handle cases with no content (e.g., 204 No Content)
        except requests.exceptions.HTTPError as e:
            error_message = f"HTTP error occurred: {e.response.status_code} - {e.response.reason}"
            try: # Try to get more details from response
                error_details = e.response.json().get("detail", e.response.text)
                error_message += f". Detail: {error_details}"
            except json.JSONDecodeError:
                error_message += f". Response: {e.response.text}"
            raise MCPServiceError(error_message, status_code=e.response.status_code, response_text=e.response.text) from e
        except requests.exceptions.RequestException as e:
            raise MCPServiceError(f"Request failed: {e}") from e

    def probe(self) -> Dict[str, Any]:
        """Probes the MCP service."""
        return self._request("GET", "probe")

    def get_screen_analysis(self, use_scaled_coords_for_screenshot_dimensions: Optional[bool] = False) -> Dict[str, Any]:
        """Gets screen analysis from the MCP service."""
        params = {"use_scaled_coords_for_screenshot_dimensions": use_scaled_coords_for_screenshot_dimensions}
        response_json = self._request("GET", "get_screen_analysis", params=params)
        # Ensure the response matches ScreenAnalysisResponse structure, or handle variations
        if not isinstance(response_json, dict): # Basic check
             raise MCPServiceError(f"Unexpected response format for screen analysis: {type(response_json)}")
        return response_json


    def execute_action(
        self,
        action_type: Literal[
            "mouse_move", "click", "drag_to", "type_text", "press_key",
            "key_down", "key_up", "scroll", "get_cursor_position",
            "get_screen_dimensions", "take_screenshot", "wait"
        ],
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Executes a desktop action via the MCP service."""
        payload = {"action_type": action_type}
        if parameters:
            payload["parameters"] = parameters

        response_json = self._request("POST", "execute_action", json=payload)
        if not isinstance(response_json, dict): # Basic check
             raise MCPServiceError(f"Unexpected response format for action execution: {type(response_json)}")
        return response_json

# Example Usage (can be run if mcp_server.py is active)
if __name__ == "__main__":
    client = MCPServiceClient()

    try:
        print("Probing MCP service...")
        probe_result = client.probe()
        print(f"Probe result: {probe_result}")

        if probe_result.get("status") in ["success", "partial"]:
            print("\nGetting screen analysis...")
            analysis = client.get_screen_analysis()
            print(f"Screen analysis received. Width: {analysis.get('screen_width')}, Height: {analysis.get('screen_height')}")
            if analysis.get("parsed_content_list"):
                print(f"Number of parsed elements: {len(analysis['parsed_content_list'])}")

            # Example: Get cursor position
            print("\nGetting cursor position (actual coords)...")
            pos_actual = client.execute_action("get_cursor_position", {"use_scaled_coords": False})
            print(f"Actual cursor position: {pos_actual.get('data')}")

            print("\nGetting cursor position (scaled coords)...")
            pos_scaled = client.execute_action("get_cursor_position", {"use_scaled_coords": True})
            print(f"Scaled cursor position: {pos_scaled.get('data')}")

            # Example: Move mouse (use with caution!)
            # print("\nMoving mouse to (10, 10) actual coordinates...")
            # move_result = client.execute_action("mouse_move", {"x": 10, "y": 10, "use_scaled_coords": False})
            # print(f"Move result: {move_result}")
            # time.sleep(1)
            # client.execute_action("mouse_move", pos_actual['data']) # Move back

            print("\nTaking a screenshot (base64)...")
            screenshot_result = client.execute_action("take_screenshot")
            if screenshot_result.get("data", {}).get("base64_image"):
                print("Screenshot (base64) received successfully.")
            else:
                print(f"Failed to get screenshot base64: {screenshot_result}")

        else:
            print("MCP service not fully initialized, skipping further tests.")

    except MCPServiceError as e:
        print(f"Error interacting with MCP Service: {e}")
        if e.status_code:
            print(f"Status Code: {e.status_code}")
        if e.response_text:
            print(f"Response Text: {e.response_text}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
