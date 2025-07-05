import pyautogui
import time
import platform
import subprocess
import re
from typing import Literal, TypedDict, Union


class Resolution(TypedDict):
    width: int
    height: int

# For now, keeping screen scaling constants here. Might move to a config file later.
MAX_SCALING_TARGETS: dict[str, Resolution] = {
    "XGA": Resolution(width=1024, height=768),  # 4:3
    "WXGA": Resolution(width=1280, height=800),  # 16:10
    "FWXGA": Resolution(width=1366, height=768),  # ~16:9
}

class DesktopAutomationError(Exception):
    """Custom exception for DesktopAutomation errors."""
    pass

class DesktopAutomation:
    """
    Provides cross-platform desktop automation capabilities (mouse, keyboard, screen).
    """
    def __init__(self, enable_scaling: bool = False):
        self.enable_scaling = enable_scaling
        self.screen_width, self.screen_height = self._get_screen_size_platform()
        self.target_dimension: Union[Resolution, None] = None

        # Configure pyautogui
        pyautogui.FAILSAFE = False  # Disables the fail-safe check
        pyautogui.MINIMUM_DURATION = 0  # No delay after each pyautogui call
        pyautogui.MINIMUM_SLEEP = 0 # No sleep after each pyautogui call
        pyautogui.PAUSE = 0 # No pause after each pyautogui call


        self.key_conversion = {
            "Page_Down": "pagedown",
            "Page_Up": "pageup",
            "Super_L": "win" if platform.system() == "Windows" else "command",
            "Escape": "esc",
            "Enter": "enter",
            "Backspace": "backspace",
            "Delete": "delete",
            "Tab": "tab",
            "Up": "up",
            "Down": "down",
            "Left": "left",
            "Right": "right",
            "Home": "home",
            "End": "end",
            "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4",
            "F5": "f5", "F6": "f6", "F7": "f7", "F8": "f8",
            "F9": "f9", "F10": "f10", "F11": "f11", "F12": "f12",
        }
        self._initialize_scaling()

    def _initialize_scaling(self):
        if self.enable_scaling:
            ratio = self.screen_width / self.screen_height
            for _, dimension in MAX_SCALING_TARGETS.items():
                if abs(dimension["width"] / dimension["height"] - ratio) < 0.02:
                    if dimension["width"] < self.screen_width : # only scale down
                        self.target_dimension = dimension
                        break
            if self.target_dimension is None:
                # Default if no close match or if screen is smaller than all targets
                self.target_dimension = MAX_SCALING_TARGETS["WXGA"]


    def _get_screen_size_platform(self) -> tuple[int, int]:
        """Gets screen size using pyautogui."""
        try:
            return pyautogui.size()
        except Exception as e:
            # Fallback for specific environments if pyautogui.size() fails (e.g., some CI environments)
            if platform.system() == "Linux":
                try:
                    cmd = "xrandr | grep '*' | head -n 1 | awk '{print $1}'"
                    output = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
                    if "x" in output:
                        width, height = map(int, output.split("x"))
                        return width, height
                except Exception as e_linux:
                    raise DesktopAutomationError(f"Failed to get screen size on Linux: {e_linux}") from e_linux
            raise DesktopAutomationError(f"pyautogui.size() failed: {e}. Consider installing platform-specific libraries if on a headless server (e.g., python3-tk and scrot on Linux).") from e


    def scale_coordinates_to_screen(self, x: int, y: int) -> tuple[int, int]:
        """Scales coordinates from a normalized/target resolution to actual screen coordinates."""
        if not self.enable_scaling or self.target_dimension is None:
            return x, y

        # Scale up from target to actual screen
        x_scaling_factor = self.screen_width / self.target_dimension["width"]
        y_scaling_factor = self.screen_height / self.target_dimension["height"]

        screen_x = round(x * x_scaling_factor)
        screen_y = round(y * y_scaling_factor)
        return screen_x, screen_y

    def scale_coordinates_from_screen(self, x: int, y: int) -> tuple[int, int]:
        """Scales actual screen coordinates to a normalized/target resolution."""
        if not self.enable_scaling or self.target_dimension is None:
            return x, y

        # Scale down from actual screen to target
        x_scaling_factor = self.target_dimension["width"] / self.screen_width
        y_scaling_factor = self.target_dimension["height"] / self.screen_height

        target_x = round(x * x_scaling_factor)
        target_y = round(y * y_scaling_factor)
        return target_x, target_y

    def mouse_move(self, x: int, y: int, use_scaled_coords: bool = False):
        """
        Moves the mouse to the specified coordinates.
        If use_scaled_coords is True, x and y are assumed to be in the target_dimension space.
        Otherwise, they are assumed to be actual screen coordinates.
        """
        screen_x, screen_y = (self.scale_coordinates_to_screen(x, y)
                              if use_scaled_coords and self.enable_scaling
                              else (x,y))

        if not (0 <= screen_x <= self.screen_width and 0 <= screen_y <= self.screen_height):
            # Optional: Clamp or raise error if out of bounds
            # print(f"Warning: Mouse move ({screen_x},{screen_y}) is out of screen bounds ({self.screen_width},{self.screen_height}). Clamping.")
            screen_x = max(0, min(screen_x, self.screen_width))
            screen_y = max(0, min(screen_y, self.screen_height))
            # raise DesktopAutomationError(f"Mouse move ({screen_x},{screen_y}) is out of screen bounds ({self.screen_width},{self.screen_height})")

        pyautogui.moveTo(screen_x, screen_y)

    def click(self, x: int | None = None, y: int | None = None, button: Literal["left", "right", "middle"] = "left", clicks: int = 1, interval: float = 0.0, use_scaled_coords: bool = False):
        """
        Performs a mouse click.
        If x and y are provided, moves to that position before clicking.
        If use_scaled_coords is True, x and y are assumed to be in the target_dimension space.
        """
        current_pos = None
        if x is not None and y is not None:
            current_pos = pyautogui.position()
            self.mouse_move(x, y, use_scaled_coords=use_scaled_coords)

        pyautogui.click(button=button, clicks=clicks, interval=interval)

        # Optional: move mouse back to original position if it was moved
        # if current_pos and (x is not None and y is not None):
        #     pyautogui.moveTo(current_pos.x, current_pos.y)


    def drag_to(self, x: int, y: int, button: Literal["left", "right", "middle"] = "left", duration: float = 0.5, use_scaled_coords: bool = False):
        """
        Drags the mouse to the specified coordinates.
        If use_scaled_coords is True, x and y are assumed to be in the target_dimension space.
        """
        screen_x, screen_y = (self.scale_coordinates_to_screen(x, y)
                              if use_scaled_coords and self.enable_scaling
                              else (x,y))

        if not (0 <= screen_x <= self.screen_width and 0 <= screen_y <= self.screen_height):
            screen_x = max(0, min(screen_x, self.screen_width))
            screen_y = max(0, min(screen_y, self.screen_height))

        pyautogui.dragTo(screen_x, screen_y, duration=duration, button=button)

    def type_text(self, text: str, interval: float = 0.0):
        """Types the given text. Simulates keystrokes."""
        # Sanitize text for pyautogui special characters if necessary,
        # or handle them explicitly. For now, assume text is mostly standard.
        pyautogui.typewrite(text, interval=interval)

    def press_key(self, key_name: str):
        """
        Presses a special key (e.g., 'enter', 'esc').
        Handles single keys and combinations like 'ctrl+c'.
        """
        key_name = key_name.lower()
        if '+' in key_name:
            keys_to_press = key_name.split('+')
            processed_keys = [self.key_conversion.get(k.strip(), k.strip()) for k in keys_to_press]
            pyautogui.hotkey(*processed_keys)
        else:
            processed_key = self.key_conversion.get(key_name.strip(), key_name.strip())
            pyautogui.press(processed_key)

    def key_down(self, key_name: str):
        """Holds a key down."""
        processed_key = self.key_conversion.get(key_name.strip().lower(), key_name.strip().lower())
        pyautogui.keyDown(processed_key)

    def key_up(self, key_name: str):
        """Releases a key."""
        processed_key = self.key_conversion.get(key_name.strip().lower(), key_name.strip().lower())
        pyautogui.keyUp(processed_key)

    def scroll(self, amount: int, x: int | None = None, y: int | None = None, use_scaled_coords: bool = False):
        """
        Scrolls the mouse wheel. Positive amount scrolls up, negative scrolls down.
        If x and y are given, moves mouse there before scrolling.
        """
        if x is not None and y is not None:
            self.mouse_move(x, y, use_scaled_coords=use_scaled_coords)
        pyautogui.scroll(amount)

    def get_cursor_position(self, use_scaled_coords: bool = False) -> tuple[int, int]:
        """
        Returns the current mouse cursor position (x, y).
        If use_scaled_coords is True, returns coordinates in the target_dimension space.
        """
        x, y = pyautogui.position()
        if use_scaled_coords and self.enable_scaling:
            return self.scale_coordinates_from_screen(x, y)
        return x, y

    def get_screen_dimensions(self, use_scaled_coords: bool = False) -> tuple[int, int]:
        """
        Returns the screen dimensions (width, height).
        If use_scaled_coords is True and scaling is enabled, returns the target_dimension.
        """
        if use_scaled_coords and self.enable_scaling and self.target_dimension:
            return self.target_dimension["width"], self.target_dimension["height"]
        return self.screen_width, self.screen_height

    def take_screenshot(self, region: tuple[int, int, int, int] | None = None, use_scaled_coords_for_region: bool = False) -> pyautogui.Image:
        """
        Takes a screenshot.
        Region is (left, top, width, height).
        If use_scaled_coords_for_region is True, region coordinates are assumed to be in target_dimension space.
        Returns a PIL Image object.
        """
        actual_region = None
        if region:
            l, t, w, h = region
            if use_scaled_coords_for_region and self.enable_scaling and self.target_dimension:
                # Scale region from target to screen
                # Top-left corner
                screen_l, screen_t = self.scale_coordinates_to_screen(l, t)
                # Bottom-right corner (to calculate width and height on screen)
                screen_r, screen_b = self.scale_coordinates_to_screen(l + w, t + h)
                screen_w = screen_r - screen_l
                screen_h = screen_b - screen_t
                actual_region = (screen_l, screen_t, screen_w, screen_h)
            else:
                actual_region = region

        # Ensure pyautogui takes screenshot of the correct screen if multiple monitors
        # This might require platform-specific handling or ensuring primary monitor.
        # For now, default behavior of pyautogui.screenshot() is used.
        try:
            return pyautogui.screenshot(region=actual_region)
        except Exception as e:
            # Attempt to handle common Linux screenshot issue (needs scrot)
            if platform.system() == "Linux" and "scrot" in str(e).lower():
                 raise DesktopAutomationError(
                    "Screenshot failed. On Linux, 'scrot' is required. "
                    "Please install it (e.g., 'sudo apt-get install scrot') and ensure it's in PATH."
                ) from e
            raise DesktopAutomationError(f"Screenshot failed: {e}") from e

    def wait(self, seconds: float):
        """Pauses execution for a specified number of seconds."""
        if seconds < 0:
            raise ValueError("Wait duration cannot be negative.")
        time.sleep(seconds)

if __name__ == '__main__':
    # Example Usage
    auto = DesktopAutomation(enable_scaling=True) # Try with enable_scaling=True and False

    print(f"Actual Screen dimensions: {auto.get_screen_dimensions(use_scaled_coords=False)}")
    if auto.enable_scaling and auto.target_dimension:
        print(f"Scaled Target dimensions: {auto.get_screen_dimensions(use_scaled_coords=True)}")

    print("Moving mouse to (100, 100) in scaled coordinates (if enabled, else actual)")
    auto.mouse_move(100, 100, use_scaled_coords=True)
    auto.wait(1)

    # Get cursor position in both coordinate systems
    actual_x, actual_y = auto.get_cursor_position(use_scaled_coords=False)
    print(f"Cursor position (actual): {actual_x}, {actual_y}")

    if auto.enable_scaling:
        scaled_x, scaled_y = auto.get_cursor_position(use_scaled_coords=True)
        print(f"Cursor position (scaled): {scaled_x}, {scaled_y}")

    # Click at current position
    print("Clicking left mouse button")
    auto.click()
    auto.wait(1)

    # Type some text (e.g., if a text editor is open)
    # print("Typing 'Hello, Desktop Automation!'")
    # auto.type_text("Hello, Desktop Automation!")
    # auto.wait(1)
    # auto.press_key("enter")
    # auto.wait(1)

    # Press a hotkey (e.g., Ctrl+A to select all, if applicable)
    # print("Pressing Ctrl+A")
    # auto.press_key("ctrl+a") # Use 'command+a' on macOS
    # auto.wait(1)

    # Take a screenshot
    print("Taking a screenshot (full_screenshot.png)")
    try:
        img = auto.take_screenshot()
        img.save("full_screenshot.png")
        print("Screenshot saved.")
    except DesktopAutomationError as e:
        print(f"Error taking screenshot: {e}")

    if auto.enable_scaling and auto.target_dimension:
        print(f"Taking a screenshot of region (0,0, 200,200) in scaled coordinates (scaled_region_screenshot.png)")
        try:
            # Define region in scaled coordinates
            scaled_region = (0, 0, 200, 200) # Top-left 200x200 pixels of the scaled view
            img_region_scaled = auto.take_screenshot(region=scaled_region, use_scaled_coords_for_region=True)
            img_region_scaled.save("scaled_region_screenshot.png")
            print("Scaled region screenshot saved.")
        except DesktopAutomationError as e:
            print(f"Error taking scaled region screenshot: {e}")

    print("Example finished.")
