import uuid
import pyotp
try:
    #  DO NOT REMOVE THIS IMPORT, IT IS REQUIRED FOR THE LOGS TO BE SENT TO SUMO
    import log_utils
except ImportError:
    pass
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.interaction import POINTER_TOUCH
from selenium.webdriver.common.actions.mouse_button import MouseButton
from selenium.webdriver.common.action_chains import ActionChains
from typing import Dict, Optional, List, Tuple
import json, time, traceback, re, base64, requests, os, math, random, string, calendar
from xml.etree import ElementTree
from lxml import etree
from urllib.parse import urlparse
from typing import Any, Dict, Mapping, Sequence, Union
import unicodedata

################# Main Methods to handle operations meta data #########################
# operation meta data file
operation_file_path = 'operations_meta_data.json'
#root_meta_data will be used to store all the meta data including all modules and main flow
root_meta_data = {}
#operations_meta_data will be used to store the meta data of the current flow,let it be module or main flow
operations_meta_data = {}

# helper to get operation meta data
def get_operations_meta_data():
    return operations_meta_data

# Load operation meta data once using the function
def set_operations_meta_data(file_path: str):
    global operations_meta_data, operation_file_path, root_meta_data
    operation_file_path = file_path
    print("operation_file_path: ", operation_file_path)
    with open(operation_file_path, 'r') as f:
        root_meta_data = json.load(f) 
    print(f"Operations meta data loaded from: {root_meta_data}")

if os.getenv("HYPER") == "true":
    folder_name = os.path.abspath(__file__).split("/")[-2]
    operation_file_path = f"extracted_hye_files/{folder_name}/operations_meta_data.json"

set_operations_meta_data(operation_file_path)
user_variables = root_meta_data.get('variables', {})
# this function is used to change the operations_meta_data according to the switch_root given , which can be main_flow or module
def reload_metadata_root(switch_root="main_flow"):
    global operations_meta_data
    print(f"Reloading operations meta data for root: {switch_root}")
    # Ensure that we reload just the 'main_flow' part of the data
    operations_meta_data = root_meta_data.get(switch_root, {})
    print(f"Updated operations meta data: {operations_meta_data}")

# Update operation meta data
def update_operation_meta_data(operation_index, value):
    if operation_index in operations_meta_data:
        operations_meta_data[operation_index].update(value)
        print(f"Updated operation meta data for index {operation_index}: {operations_meta_data[operation_index]}")
    else:
        print(f"Operation index {operation_index} not found in the metadata")

#######################################################################################



######################### Custom appium driver class ##################################
class CustomAppiumDriver:
    UiAutomator2 = 'uiautomator2'
    System_Popup_Packages = ['com.apple.springboard', 'com.google.android.permissioncontroller', 'com.android.permissioncontroller', 'com.samsung.android.permissioncontroller', 'com.miui.securitycenter', 'com.android.systemui']
    Blocked_Packages_For_Termination = ["com.apple.springboard", "com.sec.android.app.launcher", "com.google.android.apps.nexuslauncher", "com.android.launcher", "com.miui.home", "net.oneplus.launcher", "com.huawei.android.launcher", "com.motorola.launcher3", "com.oppo.launcher", "com.realme.launcher"]

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.automation_name = str(driver.capabilities.get('automationName', 'Unknown')).lower()
        self.device_os = str(driver.capabilities.get('platformName', 'Unknown')).lower()
        self.appium_driver_window_size = {"width": 0, "height": 0}
        self.iOS_device_screen_size = {
            "statusBarSize": {
                "width": 0,
                "height": 0
            },
            "scale": 1,
            "screenSize": {
                "width": 0,
                "height": 0
            }
        }

    # get device os from capabilities
    def get_test_device_os(self) -> str:
        return self.device_os

    # get automation name from capabilities
    def get_automation_name(self) -> str:
        return self.automation_name
    
    # get ios native screen info
    def get_ios_device_screen_size(self) -> Tuple[int, int]:
        if self.automation_name == self.UiAutomator2:
            raise RuntimeError("Method not implemented for Android")
        if self.iOS_device_screen_size['screenSize']['width'] == 0:
            self.iOS_device_screen_size = self.driver.execute_script("mobile: deviceScreenInfo")
        return self.iOS_device_screen_size['screenSize']['width'], self.iOS_device_screen_size['screenSize']['height']

    # get appium driver screen info
    def get_appium_driver_window_size(self) -> Tuple[int, int]:
        if self.appium_driver_window_size['width'] == 0:
            self.appium_driver_window_size = self.driver.get_window_size()
        return self.appium_driver_window_size['width'], self.appium_driver_window_size['height']

    # get screen dimensions: [width, height]
    def get_device_screen_dimensions(self) -> Tuple[int, int]:
        driver_window_size = self.get_appium_driver_window_size()
        if self.automation_name == self.UiAutomator2:
            return driver_window_size
        else:
            return self.get_ios_device_screen_size()
        
    # update driver setting
    def update_driver_settings(self, settings: dict):
        print(f"Updating driver settings: {settings}")
        self.driver.update_settings(settings)
        
    # is keyboard shown
    def is_keyboard_shown(self) -> bool:
        return self.driver.is_keyboard_shown()
    
    # get page source
    def get_page_source(self) -> str:
        return self.driver.page_source.replace('\r\n', '')
    
    # check if webview is loaded or not
    def is_webview_loaded(self, root):
        if self.automation_name != self.UiAutomator2:
            return True
        
        node = root.find(".//android.webkit.WebView")
        if node is None:
            return True
        
        if len(node) > 0:
            return True
        
        return False
    
    # returns page_src with webview loaded timeout
    def get_page_source_with_webview_wait(self):
        if self.automation_name != self.UiAutomator2:
            return self.get_page_source() # Return the page source directly for non-UIAutomator2 drivers
        
        page_src = self.get_page_source()
        is_webview_loaded = False
        retry = 3
        while retry > 0 and not is_webview_loaded:
            root = ElementTree.fromstring(page_src)
            is_webview_loaded = self.is_webview_loaded(root)
            if not is_webview_loaded:
               page_src = self.get_page_source()
            retry -= 1
            
        return page_src

    # get screenshot
    def get_base64_screenshot(self) -> Optional[str]:
        try:
            return self.driver.get_screenshot_as_base64()
        except Exception as e:
            print(f"Error getting screenshot: {e}")
            return None
    
    
    # get current package
    def get_current_package(self) -> Optional[str]:
        if self.automation_name == self.UiAutomator2:
            return self.driver.current_package
        else:
            app_info = self.driver.execute_script("mobile: activeAppInfo")
            return app_info['bundleId']
    
    # check is system popup
    def is_system_popup_package(self, package_name) -> bool:
        if not package_name:
            return False
        return package_name in self.System_Popup_Packages
    
    def is_package_allowed_for_termination(self, package_name: str) -> bool:
        return package_name not in self.Blocked_Packages_For_Termination
    
    # check element is clickable
    def is_element_clickable(self, element: any) -> bool:
        if element is None:
            raise ValueError("Element not found")
        
        # for ios, return true always
        if self.automation_name != self.UiAutomator2:
            return 'true'
        
        is_clickable = element.get_attribute('clickable')
        return is_clickable == 'true'
    
    # get element class
    def get_element_class(self, element: any) -> Optional[str]:
        if not element:
            return None
        
        if self.automation_name != self.UiAutomator2:
            return element.get_attribute('type')
        
        return element.get_attribute('class')
    
    # get element bounds
    def get_element_bounds(self, element: any) -> List[int]:
        if element is None:
            raise ValueError("Element not found")
        
        curr_bounds = [0,0,0,0]
        
        # check for iOS
        if self.automation_name != self.UiAutomator2:
            rect = element.rect
            x = rect['x']
            y = rect['y']
            width = rect['width']
            height = rect['height']
            
            curr_bounds = [x, y, x+width, y+height]
        
        else:
            bounds = element.get_attribute('bounds')
            if bounds:
                match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    curr_bounds = [x1, y1, x2, y2]
                else:
                    raise ValueError("Bounds coordinates not found")
            else:
                raise ValueError("Element bounds not found")
        
        # clamp bounds to ensure they are within the window size
        scr_width, scr_height = self.get_device_screen_dimensions()
        x1, y1, x2, y2 = curr_bounds
        x1 = max(0, min(x1, scr_width))
        y1 = max(0, min(y1, scr_height))
        x2 = max(0, min(x2, scr_width))
        y2 = max(0, min(y2, scr_height))
        return [x1, y1, x2, y2]


    
    # get scroll screen bounds based on element centre coordinates
    def get_element_scroll_screen_bounds_from_coordinates(self, element_coordinates: list) -> List[int]:
        width, height = self.get_device_screen_dimensions()
        cx = element_coordinates[0]
        cy = element_coordinates[1]

        left_x_distance, right_x_distance = cx, width - cx
        top_y_distance, bottom_y_distance = cy,  height - cy 

        x1, x2, y1, y2 = 0, width, 0, height

        # align screen bounds such that element_coordinates is at the centre
        if left_x_distance < right_x_distance:
            x2 = cx + left_x_distance
        elif left_x_distance > right_x_distance:
            x1 = cx - right_x_distance

        if top_y_distance < bottom_y_distance:
            y2 = cy + top_y_distance
        elif top_y_distance > bottom_y_distance:
            y1 = cy - bottom_y_distance

        return [x1, y1, x2, y2]
    
    
    # get element coordinates from ratio
    def get_element_coordinates_from_ratio(self, element_coordinates_ratio: list) -> list:
        width, height = self.get_device_screen_dimensions()
        element_coordinates = [int(element_coordinates_ratio[0] * width), int(element_coordinates_ratio[1] * height)]
        return element_coordinates
    
    
    # perform close app
    def perform_terminate_app_action(self, package_name: str, kill_timeout_ms: int = 3000, max_attempts: int = 2):
        if not self.is_package_allowed_for_termination(package_name):
            print(f"Skipping termination for blocked package: {package_name}")
            return
        
        current_attempt = 1
        while current_attempt <= max_attempts:
            try:
                self.driver.execute_script("mobile: terminateApp", {"bundleId": package_name, "appId": package_name, "timeout": kill_timeout_ms})
                return
            except:
                if current_attempt >= max_attempts:
                    print(f"Tried Killing the {package_name} but possible that some of its background processes are still running.")
                pass
            current_attempt += 1
    
    
    # driver navigate
    def navigate(self, direction: str):
        direction = direction.lower()
        if direction == 'back':
            self.driver.back()
        elif direction == 'forward':
            self.driver.forward()
        elif direction == 'home':
            self.perform_keyevent("HOME")
        else:
            raise ValueError("Invalid navigation direction: " + direction)
        
    # switch to active element
    def switch_to_active_element(self):
        return self.driver.switch_to.active_element
    
    # perform click
    def perform_click_action(self, element: any, element_class: str|None = "", is_coordinates_used_for_interaction: bool = False, element_coordinates: list = []):
        if is_coordinates_used_for_interaction:
            self.driver.tap([(element_coordinates[0], element_coordinates[1])])
            return
    
        if element is None:
            raise ValueError("Element not found")
        
        x1, y1, x2, y2 = self.get_element_bounds(element)
        w = x2 - x1
        cx = (x2 + x1) // 2
        cy = (y2 + y1) // 2
        
        # set tap coordinates to center by default
        tx = cx
        ty = cy
        
        # check if interactable element class
        non_interactable_classes = ['android.widget.TextView', 'XCUIElementTypeStaticText']
        is_interactable = not (element_class and element_class in non_interactable_classes)
        
        if not is_interactable:
            bounds_scale_ratio = 1
            if self.automation_name != self.UiAutomator2:
                bounds_scale_ratio = 0.36
            
            offset = int(85 * bounds_scale_ratio)
            tx = cx + offset
            
            max_width = int(400 * bounds_scale_ratio)
            if w <= max_width:
                offset = int(50 * bounds_scale_ratio)
                tx = max(cx, x2 - offset)

        self.driver.tap([(tx, ty)])
    
    # perform native type for android
    def perform_native_type_action(self, input_text: str):
        if self.automation_name != self.UiAutomator2:
            return

        # for android: type via mobile type shell cmd: this is independent of unicode keyboard
        shell_command = "mobile: type"
        args = { 'text': input_text }
        self.driver.execute_script(shell_command, args)
        
    
    # perform type action with delay
    def perform_type_action_with_delay(self, input_text: str, delay_ms: int = 0):
        delay_sec = delay_ms / 1000
        
        actions = ActionBuilder(driver=self.driver)
        action_chain = actions.add_key_input("keyboard")

        for char in input_text:
            if self.automation_name == self.UiAutomator2:
                self.perform_native_type_action(char)
            else:
                action_chain.create_key_down(char) # Press key
                action_chain.create_key_up(char)   # Release key
                actions.perform()
                
            time.sleep(delay_sec)
            
        
    # perform type
    def perform_type_action(self, input_text: str, delay_ms: int = 0):
        if delay_ms > 0:
            self.perform_type_action_with_delay(input_text, delay_ms)
            return
        
        if self.automation_name == self.UiAutomator2:
            self.perform_native_type_action(input_text)
            return
    
        actions = ActionBuilder(driver=self.driver)
        action_chain = actions.add_key_input("keyboard")

        for char in input_text:
            action_chain.create_key_down(char) # Press key
            action_chain.create_key_up(char)   # Release key

        actions.perform()
    
    
    # perform clear action
    def perform_clear_action(self, element: any, is_coordinates_used_for_interaction: bool = False):
        if is_coordinates_used_for_interaction:
            try: 
                active_element = self.switch_to_active_element()
                active_element.clear()
            except:
                if self.automation_name != self.UiAutomator2:
                    self.perform_type_action(input_text="\b"*50, delay_ms=0)
                else:
                    for _ in range(50):
                        self.perform_keyevent(keyevent="DEL")
                
            return
        
        if element is None:
            raise ValueError("Element not found")
        
        element.clear()
    
    
    # perform selector elements set value action and return true else false
    def perform_selector_element_set_value_action(self, element: any, element_class: str, desired_value: str) -> bool:
        android_selector_element_classes = ["android.widget.NumberPicker", "android.widget.SeekBar"]
        ios_selector_elements_classes = ["XCUIElementTypePickerWheel", "XCUIElementTypePicker", "XCUIElementTypeDatePicker", "XCUIElementTypeSlider"]
        is_ios = self.automation_name != self.UiAutomator2
        
        # decide if selector elements instead of editable fields
        if not element_class:
            return False
        elif is_ios and (element_class not in ios_selector_elements_classes):
            return False
        elif (not is_ios) and (element_class not in android_selector_element_classes):
            return False
        
        if element is None:
            raise ValueError("Element not found")
        
        if not desired_value:
            raise ValueError("Desired value not found")
            
        if is_ios:
            element.send_keys(desired_value)
        elif element_class == 'android.widget.NumberPicker':
            self.set_number_picker_value(element, desired_value)          
        elif element_class == 'android.widget.SeekBar':
            self.set_seekbar_value(element, desired_value)
        
        return True
    
    # perform keyevent
    def perform_keyevent(self, keyevent: str):
        keyevent = keyevent.upper()
        if self.automation_name == self.UiAutomator2:
            keycode_map = {
                "HOME": 3,
                "BACK": 4,
                "TAB": 61,
                "SPACE": 62,
                "DEL": 67,
                "RECENT": 187,
                "ENTER": 66
            }
            keycode = keycode_map.get(keyevent)
            if keycode:
                self.driver.press_keycode(keycode)
            else:
                raise ValueError(f"{keyevent} is Unsupported in Android.")
        else:
            # check driver command
            if keyevent == "BACK":
                self.driver.back()
                return
            
            # check if script command
            keycode_script = {"HOME": "home"}.get(keyevent)
            if keycode_script:
                self.driver.execute_script(f"mobile: pressButton", {"name": keycode_script})
                return
            
            # check if send keys command
            keycode_input = {"TAB": "\t", "SPACE": " ", "DEL": "\b", "ENTER": "\n"}.get(keyevent)
            if keycode_input:
                self.perform_type_action(input_text=keycode_input, delay_ms=0)
                return
            else:
                raise ValueError(f"{keyevent} is Unsupported in iOS.")
    
    
    # perform keyboard actions
    def perform_keyboard_action(self, action: str):
        action = action.upper()
        if self.automation_name == self.UiAutomator2:
            if action == 'HIDE':
                if self.is_keyboard_shown():
                    self.driver.hide_keyboard()
            else:
                raise ValueError("Invalid keyboard action: {}".format(action))
        else:
            raise ValueError("Unsupported operation for iOS")
        
        
    # open notifications
    def open_notifications(self):
        if self.automation_name == self.UiAutomator2:
            self.driver.open_notifications()
            time.sleep(0.5) # Add a delay to allow time for notifications to be visible
        else:
            # for ios: open using scroll from top to bottom
            _, screen_height = self.get_device_screen_dimensions()
            self.perform_scroll_action(0, 0, 0, screen_height-1, 1100)
        
    # hide notifications
    def hide_notifications(self):
        if self.automation_name == self.UiAutomator2:
            self.navigate('back')
        else:
            self.perform_keyevent("HOME")
    
            
    # send app to background
    def send_app_to_background(self, seconds: int):
        self.driver.background_app(seconds)
        
    # activate app
    def activate_app_with_fallback(self, package_name: str):
        self.driver.activate_app(package_name)
        
    # get largest scrollable element
    def get_largest_scrollable_element_bounds(self) -> List[int]:
        """
        Get coordinates of scrollable elements based on direction or device dimensions if none are found.

        Returns:
            List[int]: List containing coordinates [x1, y1, x2, y2].
        """
        
        # get windlow screen dimensions
        window_width, window_height = self.get_device_screen_dimensions()        
        return [0, 0, window_width, window_height]
        
    
    # helper function to perform scroll
    def perform_scroll_action(self, start_x, start_y, end_x, end_y, duration=250):
        """
        Perform a scroll gesture using ActionBuilder (W3C-compliant).
        
        :param start_x: Starting X coordinate
        :param start_y: Starting Y coordinate
        :param end_x: Ending X coordinate
        :param end_y: Ending Y coordinate
        :param duration: Duration of the scroll in milliseconds
        """
        
        # Build the actions sequence
        actions = ActionBuilder(self.driver)
        action_chain = actions.add_pointer_input(POINTER_TOUCH, "touch")

        # Scroll action sequence
        action_chain.create_pointer_move(duration=0, x=start_x, y=start_y)  # Move to start point
        action_chain.create_pointer_down()                # Press down
        action_chain.create_pointer_move(duration=duration, x=end_x, y=end_y)  # Scroll gesture
        action_chain.create_pointer_up(MouseButton.LEFT)                  # Release: comment it if performing extra scroll
        action_chain.create_pause(0.5)      # Pause
        
        # Perform the gesture
        actions.perform()

    # helper function to move number picker
    def set_number_picker_value(self, element: any, desired_value: str):
        if element is None:
            raise ValueError("Element not found")
        
        if not desired_value:
            raise ValueError("Desired value not provided")
        
        child_elements = element.find_elements(By.XPATH, ".//*")
        if not child_elements or len(child_elements) < 2:
            raise ValueError("No child elements found in the number picker")
        
        # to decide cycle completion
        cycle_completed = False
        initial_valid_val: str = ""
        curr_traversed_val: str = ""
        
        # to decide scroll direction
        scroll_direction = -1
        desired_val_int = int(desired_value) if desired_value.isdigit() else None
        set_scroll_direction = desired_val_int is not None
        
        child_height = child_elements[1].size['height']
        max_attempts = 100
        
        while max_attempts > 0 and not cycle_completed:
            curr_traversed_val = ""
            for child in child_elements:
                curr_val = str(child.text)
                if curr_val == desired_value:
                    child.click()
                    return
                curr_traversed_val += f"{curr_val}-"
                
                # decide scroll direction to reach the desired value faster
                try:
                    if set_scroll_direction and curr_val.isdigit():
                        curr_val_int = int(curr_val)
                        if desired_val_int < curr_val_int:
                            scroll_direction = 1
                            
                        # update scroll direction only once
                        set_scroll_direction = False
                except:
                    print("Error in parsing integer value")

            if initial_valid_val != "" and curr_traversed_val == initial_valid_val:
                cycle_completed = True # Cycle completed without finding the desired value, so no need to continue after the current iteration
            elif initial_valid_val == "" and curr_traversed_val != "":
                initial_valid_val = curr_traversed_val
            
            if not cycle_completed:
                action = ActionChains(self.driver)
                action.click_and_hold(element).move_by_offset(0, scroll_direction * child_height).release().perform()
            
            max_attempts -= 1
        
        raise ValueError(f"Desired value '{desired_value}' not found in the number picker")

    # helper function to move seekbar
    def set_seekbar_value(self, element: any, target_value: str):
        if element is None:
            raise ValueError("Element not found")
        
        if not target_value:
            raise ValueError("Target value not provided")
        
        desired_value = target_value.lower()
        aspect_ratio_tolerance = 0.1
        location = element.location
        seekbar_size = element.size
        
        width = seekbar_size['width']
        height = seekbar_size['height']
        
        if element.get_attribute('scrollable') == 'true':
            scroll_step = -50
            max_attempts = 100
            while max_attempts > 0:
                content_desc = element.get_attribute("content-desc").lower()
                text_value = element.get_attribute("text").lower()
                
                if desired_value in content_desc or desired_value in text_value:
                    break
                action = ActionChains(self.driver)
                action.click_and_hold(element).move_by_offset(0, scroll_step).release().perform()
                max_attempts -= 1
        elif abs(width - height) / max(width, height) < aspect_ratio_tolerance:
            try:
                desired_value = float(desired_value)
            except ValueError:
                raise ValueError("Target value must be a numeric string.")
            min_val, max_val = 0, 12
            angle = 360 * (desired_value - min_val) / (max_val - min_val)
            element.send_keys(angle)
        else:
            try:
                desired_value = float(desired_value)
            except ValueError:
                raise ValueError("Target value must be a numeric string.")
            min_val, max_val = 0, 100
            start_x = location.get('x')
            proportion = (desired_value - min_val) / (max_val - min_val)
            target_x = start_x + proportion * width
            y = location.get('y') + height // 2

            action = ActionChains(self.driver)
            action.click_and_hold(element).move_to_element_with_offset(element, target_x, y).release().perform()


    # dismiss dialog
    def perform_dismiss_dialog_action(self):
        if self.automation_name == self.UiAutomator2:
            self.navigate('back')
        else:
            self.driver.tap([(10, 75)])
        
#######################################################################################



######################### Autohealer class #############################################
class AutoHealer:
    def __init__(self, driver: WebDriver):
        self.driver = CustomAppiumDriver(driver)
        self.automind_url = os.getenv('AUTOMIND_URL', 'https://kaneai-api.lambdatest.com')
        self.username = os.getenv('LT_USERNAME', 'dummy')
        self.accesskey = os.getenv('LT_ACCESS_KEY', 'dummy')
        self.org_id = int(os.getenv('ORG_ID', '0'))
        self.test_id = os.getenv('TEST_ID', '')
        self.commit_id = os.getenv('COMMIT_ID', '')
        self.session_id = driver.session_id

    class AutoHealerPayload(BaseModel):
        code_export_id: str
        username: str
        accesskey: str
        org_id: int
        test_id: str
        commit_id: str
        session_id: str
        current_action: dict

        prev_actions: Optional[List[dict]] = []
        xpath_mapping: Optional[dict] = {}
        tagified_image: Optional[str] = ""
        tags_description: Optional[dict] = {}
        page_source: Optional[str] = ""

        # specific for mobile
        is_mobile: Optional[bool] = False
        device_os: Optional[str] = ""
        untagged_image_base64: Optional[str] = None
        height: Optional[int] = 0
        width: Optional[int] = 0
        use_query_v2: Optional[bool] = False

    # make healer API call
    def make_healer_api_call(self, operation_index: str, api_endpoint: str, api_method: str, skip_page_source: bool = False) -> requests.Response:
        # generate api url
        url = f'{self.automind_url}/{api_endpoint.lstrip("/")}'

        # generate headers
        headers = {'Content-Type': 'application/json','Authorization' : f"Basic {base64.b64encode(f'{self.username}:{self.accesskey}'.encode()).decode()}"}

        # generate payload
        req_id = uuid.uuid4().hex[:16]
        width, height = self.driver.get_appium_driver_window_size()
        untagged_screenshot = self.driver.get_base64_screenshot() # added after hierarchy to make sure webview is loaded if required
        
        hierarchy = ""
        if not skip_page_source:
            hierarchy = self.driver.get_page_source_with_webview_wait()
    
        payload = self.AutoHealerPayload(
            # required fields
            code_export_id=req_id,
            username=self.username,
            accesskey=self.accesskey,
            org_id=self.org_id,
            test_id=self.test_id,
            commit_id=self.commit_id,
            session_id=self.session_id,

            # optional fields
            prev_actions=[],
            xpath_mapping={},
            tagified_image="",
            tags_description={},

            # operation specific required fields
            is_mobile=True,
            device_os=self.driver.get_test_device_os(),
            width=width,
            height=height,
            page_source=hierarchy,
            untagged_image_base64=untagged_screenshot,
            current_action=operations_meta_data[operation_index],
            use_query_v2=operations_meta_data[operation_index].get('use_query_v2', False)
        )

        # make API call
        print(f"Making Healer API call to [{api_method} {url}], reqId: {req_id}, testId: {self.test_id}, commitId: {self.commit_id}")
        start_time = time.time()  # Record the start time
        response = requests.request(api_method, url, headers=headers, json=payload.model_dump(), timeout=120)
        end_time = time.time()  # Record the end time
        elapsed_time = end_time - start_time  # Calculate elapsed time
        print(f"Healer Request completed in {elapsed_time:.2f} seconds")  # Log the time taken by request to complete
        return response
    
    # heal xpaths
    def get_healed_xpaths(self, operation_index: str) -> list[str]:
        response = self.make_healer_api_call(operation_index, 'v1/heal/xpaths', 'POST')

        # Check if the response is successful
        if response.status_code == 200:
            # Parse JSON response body
            json_data = response.json()

            if 'error' in json_data:
                print(f"get_healed_xpaths :: response error: {json_data['error']}")
                return []

            # Extract the 'xpaths' key, Default to an empty list if 'xpaths' is not present
            xpaths = json_data.get('xpaths', [])

            # Ensure xpaths is a list
            if isinstance(xpaths, list):
                print("get_healed_xpaths :: xpaths: ", xpaths)
                return xpaths
            else:
                print("get_healed_xpaths :: returned 'xpaths' is not a list, response: ", json_data)
        else:
            print(f"get_healed_xpaths :: Request failed with status code: {response.status_code}, body: {response.text}")

        return []
    
    # heal vision query
    def get_healed_vision_query(self, operation_index: str):
        response = self.make_healer_api_call(operation_index, 'v1/heal/vision', 'POST')

        # Check if the response is successful
        if response.status_code == 200:
            # Parse JSON response body
            json_data = response.json()

            if 'error' in json_data:
                print(f"get_healed_vision_query :: response error: {json_data['error']}")
                return None

            # Extract the 'vision_query' key, Default to None if 'vision_query' is not present
            query_content = json_data.get('vision_query', None)

            # Ensure query_content is present
            if query_content is not None:
                return query_content
            else:
                print("get_healed_vision_query :: returned 'vision_query' is not valid, response: ", json_data)
        else:
            print(f"get_healed_vision_query :: Request failed with status code: {response.status_code}, body: {response.text}")

        return None
    
    # resolve operation
    def resolve_operation(self, operation_index: str):
        response = self.make_healer_api_call(operation_index, 'v1/heal/resolve', 'POST')

        # Check if the response is successful
        if response.status_code == 200:
            # Parse JSON response body
            json_data = response.json()

            if 'error' in json_data:
                print(f"resolve_operation :: response error: {json_data['error']}")
                return None
            
            print(f"resolve_operation :: resolved operation: {json_data}")
            return json_data
        
        else:
            print(f"resolve_operation :: Request failed with status code: {response.status_code}, body: {response.text}")
        
        return None
    
    
    # resolve coordinates
    def resolve_coordinates(self, operation_index: str):
        response = self.make_healer_api_call(operation_index, 'v1/heal/coordinates', 'POST', True)

        # Check if the response is successful
        if response.status_code == 200:
            # Parse JSON response body
            json_data = response.json()

            if 'error' in json_data:
                print(f"resolve_coordinates :: response error: {json_data['error']}")
                return None
            
            # Extract the 'element_coordinates_ratio' key, Default to None if 'element_coordinates_ratio' is not present
            element_coordinates_ratio = json_data.get('element_coordinates_ratio', None)

            # Ensure query_content is present
            if element_coordinates_ratio is not None:
                return element_coordinates_ratio
            else:
                print("resolve_coordinates :: returned 'element_coordinates_ratio' is not valid, response: ", json_data)
        
        else:
            print(f"resolve_coordinates :: Request failed with status code: {response.status_code}, body: {response.text}")
        
        return None
    
    
    
########################################################################################



################################## Helper methods ######################################

def resolve_mathematical_operand(node, driver):
    node_name, node_type = next(iter(node.items()))
    value = None
    if node_type == "runtime_variable":
        value = string_to_float(access_value(user_variables, node_name, driver))
    elif node_type == "numeric_literal" or node_type == "parameter":
        value = string_to_float(node_name)
    elif node_type == "predefined_variable":
        predefined_variable = re.findall(r'\{\{(.*?)\}\}', node_name)[0]
        value = string_to_float(access_value(user_variables, predefined_variable, driver))
    else:
        return 0

    if value is None:
        return 0
    return value

def eval_math(node, driver):
    # Leaf
    if isinstance(node, (int, float)):
        return float(node)
    if isinstance(node, dict) and not "op" in node:
        return resolve_mathematical_operand(node, driver)

    # Branch
    op = node["op"]
    vals = [eval_math(child, driver) for child in node["operands"]]
    ops = {
        "add":       lambda a,b: a+b,
        "subtract":  lambda a,b: a-b,
        "multiply":  lambda a,b: a*b,
        "divide":    lambda a,b: a/b,
        "mod":       lambda a,b: a%b,
        "pow":       lambda a,b: a**b,
        "negate":    lambda a: -a,
        "abs":       lambda a: abs(a),
    }
    fn = ops[op]
    return fn(*vals) if len(vals)>1 else fn(vals[0])


def resolve_assertion_operand(node, driver):
    node_name, node_type = next(iter(node.items()))
    if node_type == "runtime_variable":
        value = access_value(user_variables, node_name, driver)
    elif node_type == "parameter":
        value = node_name
    elif node_type == "predefined_variable":
        predefined_variable = re.findall(r'\{\{(.*?)\}\}', node_name)[0]
        value = access_value(user_variables, predefined_variable, driver)
    print("value in resolve_assertion_operand: ", value, " node_name: ", node_name, " node_type: ", node_type)
    return value

def evaluate_assertion(tree: Mapping[str, Any], driver) -> bool:
    op = tree["operator"]

    # ----- logical nodes -----
    if op in {"AND", "OR", "NOT"}:
        ops = tree["operands"]
        if op == "AND":
            result = all(evaluate_assertion(t, driver) for t in ops)
            # if not result:
            #     raise AssertionError("AND condition failed - not all conditions were true")
            return result
        if op == "OR":
            result = any(evaluate_assertion(t, driver) for t in ops)
            # if not result:
            #     raise AssertionError("OR condition failed - none of the conditions were true")
            return result
        result = not evaluate_assertion(ops[0], driver)  # NOT
        # if not result:
        #     raise AssertionError("NOT condition failed")
        return result

    # ----- atomic nodes -----
    left = resolve_assertion_operand(tree["left_operand"], driver)
    right = None
    if tree.get("right_operand", None):
        right = resolve_assertion_operand(tree["right_operand"], driver)
    #  apply transforms if present
    if "transform_operands" in tree:
        if op in ["greater_than", "less_than", "greater_than_or_equal", "less_than_or_equal"]:
            if "string_to_float" not in tree["transform_operands"]:
                tree["transform_operands"].append("string_to_float")
        left = _apply_transform(left, tree["transform_operands"])
        if right is not None:
            right = _apply_transform(right, tree["transform_operands"])

    result = _compare_atomic(op, left, right)
    # if not result:
    #     raise AssertionError(f"Assertion failed for operation '{op}' with values {left} and {right}")
    return result

def _compare_atomic(op: str, a: Any, b: Any) -> bool:
    if op in {"equals", "equal"}  : return a == b
    if op in {"not_equal", "not_equals"}  : return a != b
    if op == "greater_than"   : return a >  b
    if op == "less_than"   : return a <  b
    if op == "greater_than_or_equal"  : return a >= b
    if op == "less_than_or_equal"  : return a <= b
    if op in {"start_with", "starts_with"}: return str(a).lower().startswith(str(b).lower())
    if op in {"end_with",   "ends_with"}  : return str(a).lower().endswith(str(b).lower())
    if op in {"contain", "contains"}      : return str(b).lower() in str(a).lower()
    if op == "lower_case": return str(a) == str(a).lower()
    if op == "upper_case": return str(a) == str(a).upper()
    if op == "length_equals": return len(a) == len(b)
    if op == "type_equals": return type(a).__name__ == str(b)
    if op == "json_key_exists": return str(b) in _json_obj(a)
    if op == "json_keys_count": return len(_json_obj(a).keys()) == int(b)
    if op == "json_array_length_equals": return len(_json_arr(a)) == int(b)
    if op == "json_array_contains": return b in _json_arr(a)

    raise ValueError(f"Unsupported operator {op}")

def _json_obj(x: Any) -> Mapping[str, Any]:
    if isinstance(x, str):
        x = json.loads(x)
    return x

def _json_arr(x: Any) -> Sequence[Any]:
    if isinstance(x, str):
        x = json.loads(x)
    return x

def _apply_transform(val: Any, transform_name: list) -> Any:
    for transform in transform_name:
        if transform == "string_to_float":
            val = string_to_float(val)
    return val

def sanitize_visible_text(raw: str) -> str:
    """
    - Convert non-breaking spaces to a normal space.
    - Remove control / format characters (zero-width, bidi marks, etc.).
    - Collapse any run of whitespace (space, tab, newline) to a single space.
    - Trim leading / trailing whitespace.
    
    Feel free to extend the 'category' filter or add specific
    character replacements for your domain.
    """
    if not raw:
        return ""

    # &nbsp; → space
    cleaned = raw.replace("\u00A0", " ")

    # Strip control/format chars (Unicode categories Cc = control, Cf = format)
    cleaned = "".join(
        ch for ch in cleaned
        if unicodedata.category(ch) not in {"Cf", "Cc"}
    )

    # Collapse runs of whitespace to a single space
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()

def safe_value(element, driver, timeout: float = 2.0) -> str:
    element_text = element.text if hasattr(element, 'text') else ""
    return sanitize_visible_text(element_text)

def get_attribute(element, driver, selected_attribute: str):
    try:
        if selected_attribute == "text":
            value = safe_value(element, driver)
            return value
    except Exception as e:
        print(f"Error getting attribute: {e}")
        return None

# get current time helper
def get_current_utc_time():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

# get prev operation wait time
def get_prev_operation_wait_time(operation_index: str) -> float:
    wait_time = 0
    try:
        prev_op_index = str(int(operation_index) - 1)
        prev_op_end_time = operations_meta_data.get(prev_op_index, {}).get('operation_end', '')
        curr_op_start_time = operations_meta_data[operation_index].get('operation_start', '')
        
        if prev_op_end_time and curr_op_start_time:
            # Define the datetime format
            format = "%Y-%m-%d %H:%M:%S.%f"
            
            # Convert strings to datetime objects
            datetime1 = datetime.strptime(prev_op_end_time, format)
            datetime2 = datetime.strptime(curr_op_start_time, format)
            
            # Calculate the difference in seconds
            wait_time =  (datetime2 - datetime1).total_seconds()
    except Exception as e:
        print(f"Error getting prev operation wait time: {e}")
    
    return wait_time

# get operation wait time
def get_operation_wait_time(operation_index: str, default_wait_time: float = 5, max_additional_wait_time: float = 5 ) -> float:
    wait_time: float = 0
    try:
        explicit_wait = float(operations_meta_data[operation_index].get('explicit_wait', 0))
        wait_time = explicit_wait
        
        # get additional wait time depending on prev operation end time: to avoid delay in screen loading or slow internet issues
        additional_wait = default_wait_time
        prev_op_wait_time = get_prev_operation_wait_time(operation_index)
        if prev_op_wait_time > additional_wait:
            additional_wait = prev_op_wait_time
            
        # limit additional wait time in order to avoid false negatives or long waiting time
        additional_wait = min(additional_wait, max_additional_wait_time)
        
        wait_time += additional_wait
    except Exception as e:
        print(f"Error getting wait time: {e}")
        wait_time += default_wait_time # add default wait time
    
    return wait_time


# throttle network
def execute_network_throttle(driver, is_mobile_offline: bool, network_throttle: dict):
    value = network_throttle.get("value")

    try:
        if value != "custom":
            driver.execute_script(f"updateNetworkProfile={value}")
            print(f"Throttling Successfully Applied With Network Profile: {value}")
        else:
            download_speed = network_throttle.get("download_speed", 0)
            upload_speed = network_throttle.get("upload_speed", 0)
            latency = network_throttle.get("latency", 0)
            driver.execute_script(f"customNetworkProfile:{{ \\\"downloadSpeed\\\": {download_speed},\\\"uploadSpeed\\\" : {upload_speed}, \\\"latency\\\": {latency} }}")
            print(f"Throttling Successfully Applied With Custom Network Profile: downloadSpeed: {download_speed}, uploadSpeed: {upload_speed}, latency: {latency}")
        
        time.sleep(2) # wait for 2 seconds to apply the network throttle
    except Exception as e:
        raise Exception(f"Error executing network throttle: {e}")


# initialize network throttle
def initialize_network_throttle(driver):
    
    value = os.getenv("NETWORK_PROFILE", "default")

    if value != "default":
        network_throttle = {
            "value": value,
            "download_speed": int(os.getenv("DOWNLOAD_SPEED", 0)),
            "upload_speed": int(os.getenv("UPLOAD_SPEED", 0)),
            "latency": int(os.getenv("LATENCY", 0))
        }
        
        execute_network_throttle(driver, is_mobile_offline=False, network_throttle=network_throttle)
        
# lambda hooks execution support
def execute_lambda_hooks(driver, hook, argument):
    print(f"*********** [{get_current_utc_time()}]:: Executing hook: '{hook}' = '{argument}'")
    driver.execute_script(f"{hook}={argument}")

# lambda test case start
def lambda_test_case_start(driver, test_case_name):
    try:
        execute_lambda_hooks(driver, "lambda-testCase-start", test_case_name)
    except Exception as e:
        print(f"Failed to update lambda-testCase-start={test_case_name} due to error: {e}")

# lambda test case end    
def lambda_test_case_end(driver, test_case_name):
    try:
        execute_lambda_hooks(driver, "lambda-testCase-end", test_case_name)
    except Exception as e:
        print(f"Failed to update lambda-testCase-end={test_case_name} due to error: {e}")

# get test case name
def get_test_case_name(operation_index):
    default_test_case_name = f"[{operation_index}]: "
    
    op_intent = str(operations_meta_data[operation_index].get("operation_intent", ""))
    op_type = str(operations_meta_data[operation_index].get("operation_type", ""))
    
    test_case_name = f"{default_test_case_name} '{op_intent}'"
    if not op_intent or len(test_case_name) > 255: 
        test_case_name = f"{default_test_case_name} '{op_type}'"
        
    if len(test_case_name) > 255:
        test_case_name = default_test_case_name

    return test_case_name

# scroll helper to get coordinates
def get_scroll_coordinates(
    screen_coordinates: List[int],
    direction: str, 
    value: int,
    is_percent_value: bool = False
) -> tuple[int, List[int]]:
    """
    Calculate the start and end coordinates for scrolling based on direction and value.

    Args:
        screen_coordinates (List[int]): Scrollable Section bounds.
        direction (str): Direction to scroll ('up', 'down', 'left', 'right').
        value (int): Distance to scroll in pixels.
        is_percent_value (bool): If True, value is a percentage of the screen size.

    Returns:
        tuple[int, List[int]]: (loop_range, [start_x, start_y, end_x, end_y])
    """
    direction = direction.lower()
    start_screen_x, start_screen_y, end_screen_x, end_screen_y = screen_coordinates
    
    # Sort coordinates to ensure proper order
    min_x = min(start_screen_x, end_screen_x)
    max_x = max(start_screen_x, end_screen_x)
    min_y = min(start_screen_y, end_screen_y)
    max_y = max(start_screen_y, end_screen_y)
    
    # Calculate screen width and height
    screen_width = abs(max_x - min_x)
    screen_height = abs(max_y - min_y)
    
    # Default scroll distance if no value provided
    single_scroll_distance_percent = 50 if direction in ['up', 'down'] else 70
    if value <= 0:
        value = single_scroll_distance_percent
        is_percent_value = True
    
    if is_percent_value:
        value = int(screen_height * value / 100) if direction in ['up', 'down'] else int(screen_width * value / 100)
        
    value = int(value)

    # Fix start coordinates to middle of the element
    start_x = (min_x + max_x) // 2
    start_y = (min_y + max_y) // 2
    
    scroll_val = int(screen_height * single_scroll_distance_percent / 100) if direction in ['up', 'down'] else int(screen_width * single_scroll_distance_percent / 100)
    scroll_val = min(value, scroll_val) # in case value is less than scroll_val
    
    # Determine end coordinates based on the direction
    end_x, end_y = start_x, start_y
    if direction == 'up':
        end_y = start_y + scroll_val
    elif direction == 'down':
        end_y = start_y - scroll_val
    elif direction == 'left':
        start_x = min(min_x + 65, start_x)
        end_x = start_x + scroll_val
    elif direction == 'right':
        start_x = max(max_x - 65, start_x)
        end_x = start_x - scroll_val
    else:
        raise ValueError("Invalid direction. Use 'up', 'down', 'left', or 'right'.")

    # Ensure start and end points are within bounds
    start_x = max(min_x, min(start_x, max_x - 1))
    start_y = max(min_y, min(start_y, max_y - 1))
    end_x = max(min_x, min(end_x, max_x - 1))
    end_y = max(min_y, min(end_y, max_y - 1))
    
    # Calculate loop range based on the scroll value
    single_scroll_distance_covered = abs(start_y - end_y) if direction in ['up', 'down'] else abs(start_x - end_x)
    loop_range = math.ceil(value / single_scroll_distance_covered)
    
    return (loop_range , [start_x, start_y, end_x, end_y])

# returns element and corresponding locator
def find_element(driver: WebDriver, locators: list, operation_idx: str, max_retries: int = 2, current_retry: int = 0) -> tuple[str, str]:
    wait_times = [10, 5, 3]
    for i, locator in enumerate(locators):
        if not locator:
            continue
        try:
            driver.implicitly_wait(wait_times[i%3]) # set implicit wait time
            element = driver.find_element(By.XPATH, locator)
            if element:
                print(f"Element found with locator: {locator}")
                return element, locator
        except:
            pass

    if current_retry >= max_retries:
        print("MAX RETRIES EXCEEDED")
        return None, None

    # retry healing xpaths
    time.sleep(1.5) # add delay to avoid false negatives like loading screen or slow network
    print("Trying autoheal.. Unable to find element in locators: ", locators)
    locators = AutoHealer(driver).get_healed_xpaths(operation_idx)
    return find_element(driver, locators, operation_idx, max_retries, current_retry + 1) # Recursively retry with healed locators

# handle unresolved operations
def handle_unresolved_operations(operations_meta_data, operation_index, driver) -> bool:
    unresolved_operation = operations_meta_data[operation_index]
    
    action = operations_meta_data[operation_index]['operation_type']
    sub_instruction_obj = operations_meta_data[operation_index].get('sub_instruction_obj', {})
    if isinstance(sub_instruction_obj, str):
        sub_instruction_obj = json.loads(sub_instruction_obj)

    # check is operation is unresolved
    is_unresolved = ('unresolved' in unresolved_operation) and (isinstance(unresolved_operation['unresolved'], bool)) and (unresolved_operation['unresolved']) or is_action_unresolved(action, sub_instruction_obj)
    if not is_unresolved:
        return False
    
    # replace variable in operations
    updates = {}
    if 'variable' in sub_instruction_obj and 'operation_intent' in sub_instruction_obj['variable']:
        updates['operation_intent'] = get_variable_value(sub_instruction_obj['variable']['operation_intent'], driver)
        sub_instruction_obj['operation'] = updates['operation_intent']
        updates['sub_instruction_obj'] = json.dumps(sub_instruction_obj)

    if 'agent' in sub_instruction_obj:
        updates['agent'] = sub_instruction_obj['agent']

    if updates:
        update_operation_meta_data(operation_index, updates)

    print("Resolving unresolved operation, Operation Intent:", operations_meta_data[operation_index]['operation_intent']) # To Do: currently, it works correctly if resolved result is a single operation, may fail if resolve case result in multiple operations
    
    agent = unresolved_operation['agent']
    if agent == "Vision Agent":
        response = AutoHealer(driver).resolve_operation(operation_index)

        if response is None:
            raise RuntimeError("Error in resolving operation: response is None")
        
        # add resolved xpath to locator key
        if response.get('xpath', None):
            response['locator'] = [response.get('xpath')]
        
        # add alternate xpaths to locator key
        alternate_xpaths = response.get('alternative_xpaths', [])
        if alternate_xpaths is not None and isinstance(alternate_xpaths, list) and len(alternate_xpaths) > 0:
            response['locator'].extend(alternate_xpaths)
        
        
        update_operation_meta_data(operation_index, response)
        
    # return true by default
    return True


# handle coordinates
def get_new_coordinates_ratio_for_operation(operation_index, driver) -> list:
    response = AutoHealer(driver).resolve_coordinates(operation_index)
    if response is None:
        raise RuntimeError("Error in resolving new coordinates: response is None")
    return response
    


# finds element and returns xml if exist
def fetch_element_xml(page_source, xpath: str):
    try:
        # Convert the page source to bytes if it contains an encoding declaration
        if isinstance(page_source, str):
            page_source = page_source.encode('utf-8')

        root = etree.fromstring(page_source)
        xml_elements = root.xpath(xpath)

        if len(xml_elements) == 0:
            return None
        else:
            return etree.tostring(xml_elements[0], pretty_print=True, encoding='unicode')
    except Exception as e:
        print(f"Error: {e}")
        return None

def access_value(mapping, path, driver):
    try:
        keys = path.split('.')
        if keys[0] == 'smart' and len(keys) == 2:
            smart_variables = smart_variables_init()
            smart_variables["device_orientation"]=driver.orientation
            return smart_variables.get(keys[1]) if keys[1] in smart_variables else path
        value = mapping
        for key in keys:
            while '[' in key and ']' in key:
                base_key, index = key.split('[', 1)
                index = int(index.split(']')[0])
                value = value[base_key] if base_key else value
                value = value[index]
                key = key[key.index(']') + 1:] 
            if key: 
                value = value[key]

        return str(value)
    except (KeyError, IndexError, ValueError, TypeError):
        return path

def smart_variables_init():
    smart_object={}
    varDateTime = datetime.now()
    smart_object['current_date']=varDateTime.strftime("%Y-%m-%d")
    smart_object['current_day']=varDateTime.strftime("%d")
    smart_object['current_month_number']=varDateTime.strftime("%m")
    smart_object['current_year']=varDateTime.strftime("%Y")
    smart_object['current_month']=varDateTime.strftime("%B")
    smart_object['current_hour']=varDateTime.strftime("%H")
    smart_object['current_minute']=varDateTime.strftime("%M")
    smart_object['current_timestamp']=varDateTime.strftime("%Y-%m-%d %H:%M:%S")
    smart_object['current_timezone']=time.strftime("%Z")
    smart_object['next_day']=(varDateTime+timedelta(days=1)).strftime("%Y-%m-%d")
    smart_object['previous_day']=(varDateTime-timedelta(days=1)).strftime("%Y-%m-%d")
    smart_object['start_of_week']=(varDateTime-timedelta(days=varDateTime.weekday())).strftime("%Y-%m-%d")
    smart_object['end_of_week']=(varDateTime+timedelta(days=6-varDateTime.weekday())).strftime("%Y-%m-%d")
    smart_object['start_of_month']=(varDateTime.replace(day=1)).strftime("%Y-%m-%d")
    smart_object['end_of_month']=(varDateTime.replace(day=calendar.monthrange(varDateTime.year, varDateTime.month)[1])).strftime("%Y-%m-%d")
    smart_object['latitude'] = "13.2257"
    smart_object['longitude'] =  "77.5750"
    smart_object['country'] =  "India"
    smart_object['city'] = "Doddaballapura"
    smart_object['ip_address'] = "143.110.182.88"
    smart_object['random_int'] = str(random.randint(100, 999))
    smart_object['random_float'] = str(round(random.uniform(1, 100), 2))
    smart_object['random_string_8'] = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    smart_object['random_string_56'] = ''.join(random.choices(string.ascii_letters + string.digits, k=56))
    smart_object['random_email'] = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + "@example.com"
    smart_object['random_phone'] = f"{random.randint(1000000000,9999999999)}"
    smart_object['user_name']=os.getenv('LT_USERNAME','')
    smart_object['device_name']=os.getenv('deviceName',"")
    smart_object['app_package_name']=os.getenv("app","")
    smart_object['app_version']=os.getenv("appVersion","")
    smart_object['device_os']=os.getenv("platformName","")
    smart_object['device_os_version']=os.getenv("platformVersion","")

    return smart_object

def generate_totp_code(secret):
    try:
        # Clean the secret by removing spaces, hyphens and converting to uppercase
        cleaned_secret = secret.replace('-', '').replace(' ', '').upper()
        
        # Validate the secret is not empty
        if not cleaned_secret:
            print("Error: Invalid TOTP secret",secret)
            return None
            
        # Generate TOTP code
        totp = pyotp.TOTP(cleaned_secret)
        code = totp.now()
            
        return code
    except Exception as e:
        print(f"Error generating TOTP code: {e}")
        return secret
    
def handle_totp_variable(match: str) -> str:
    name = match.split(".")[1]
    key = user_variables.get(f"{name}", "")
    if key.startswith('{{secrets.'):
        key = key.replace("}}", "")
        key = key.replace("{{", "")
        key = os.getenv(key.split('.')[2], '')
    return generate_totp_code(key)        


def get_variable_value(value: str, driver) -> str:
    matches = re.findall(r'\{\{(.*?)\}\}', value)
    new_value = value
    if matches:
        for match in matches:
            if match.split(".")[0] == 'smart' and match.split(".")[1].startswith('totp_'):
                new_value = new_value.replace("{{"+match+"}}", str(handle_totp_variable(match)))
                continue
            if match.split(".")[0] == "secrets" and len(match.split(".")) == 3:
                new_value = new_value.replace("{{"+match+"}}", os.getenv(match.split('.')[2], ''))
                continue
            new_value = new_value.replace("{{"+match+"}}", access_value(user_variables, match, driver))
    return new_value

def replace_apivar(request_args, driver):
    for (key,value) in request_args.items():
        if isinstance(value, str):
            request_args[key]=get_variable_value(request_args[key], driver)
        elif isinstance(value, dict):
            for (key2,value2) in value.items():
                if isinstance(value2, str):
                    request_args[key][key2]=get_variable_value(request_args[key][key2], driver)
    return request_args    

#########################################################################################################



############################# Main Methods used in test.py #################################################

# string to float execution
def string_to_float(input_string):
    if isinstance(input_string, float):
        return input_string
    if isinstance(input_string, int):
        return float(input_string)
    if not isinstance(input_string, str):
        input_string = str(input_string)
        
    filtered_input = ''.join(filter(lambda x: x.isdigit() or x == '.', input_string))
    
    # Check if the result is empty, return 0
    if not filtered_input:
        return 0
    
    return float(filtered_input)

# prints the argument: just for debugging, main method is 'execute_lambda_hooks': use if required
def lambda_hooks(driver, argument):
    print(argument)
    
# perform assertion based on operator
def perform_assertion(driver, operation_index, operand1, operator, operand2, assertion = ""):
    # execute test case start
    sub_instruction_obj = operations_meta_data[str(operation_index)].get('sub_instruction_obj', {})
    if isinstance(sub_instruction_obj, str):
        sub_instruction_obj = json.loads(sub_instruction_obj)
    is_string_to_float = operations_meta_data[str(operation_index)].get('string_to_float', False)
    if isinstance(sub_instruction_obj, dict) and 'json' not in operator:
        if 'params' in sub_instruction_obj:
            if 'operand1' in sub_instruction_obj['params']:
                new_value = str(operations_meta_data[str(operation_index)]['queried_value'])
                if is_string_to_float:
                    operand1 = string_to_float(new_value)
                else:
                    operand1 = new_value.lower()
            if 'operand2' in sub_instruction_obj['params']:
                new_value = str(operations_meta_data[str(operation_index)]['expected_value'])
                if is_string_to_float:
                    operand2 = string_to_float(new_value)
                else:
                    operand2 = new_value.lower()
        if 'variable' in sub_instruction_obj:
            if 'operand1' in sub_instruction_obj['variable']:
                new_value = get_variable_value(sub_instruction_obj['variable']['operand1'], driver)
                if is_string_to_float:
                    operand1 = string_to_float(new_value)
                else:
                    operand1 = new_value.lower()
            if 'operand2' in sub_instruction_obj['variable']:
                new_value = get_variable_value(sub_instruction_obj['variable']['operand2'], driver)
                if is_string_to_float:
                    operand2 = string_to_float(new_value)
                else:
                    operand2 = new_value.lower()
    curr_test_case_name = f"""[{operation_index}]: Asserting [({operand1})  {operator}  ({operand2})]"""
    if len(curr_test_case_name) > 255:
        curr_test_case_name = f"""[{operation_index}]: Asserting [{operator}] operation"""
        
    lambda_test_case_start(driver, curr_test_case_name)

    print(f"""\n***** Executing Assertion operation: [({operand1}) {operator} ({operand2})]: """)
    hard_assertion = operations_meta_data[str(operation_index)].get('hard_assertion', False)
    try:
        if operator == "json_key_exists":
            assert operand2 in operand1.keys(), f"Key '{operand2}' does not exist in the JSON object."
        elif operator == "json_keys_count":
            assert len(operand1.keys()) == int(operand2), f"Expected {operand2} keys, but found {len(operand1.keys())}."
        elif operator == "json_array_length":
            assert len(operand1) == int(operand2), f"Expected array length {operand2}, but found {len(operand1)}."
        elif operator == "json_array_contains":
            assert operand2 in operand1, f"Array does not contain the value '{operand2}'."
        elif operator == "json_value_equals":
            assert operand1 == operand2, f"Expected value '{operand2}', but found '{operand1}'."
        elif operator == "==":
            assert operand1 == operand2, f"Expected {operand1} to equal {operand2}"
        elif operator == "!=":
            assert operand1 != operand2, f"Expected {operand1} to not equal {operand2}"
        elif operator == "true":
            assert operand1, f"Expected true, got {operand1}"
        elif operator == "false":
            assert not operand1, f"Expected false, got {operand1}"
        elif operator == "is_null":
            assert operand1 is None, "Expected operand to be None"
        elif operator == "not_null":
            assert operand1 is not None, "Expected operand to be not None"
        elif operator == "contains":
            assert operand2 in operand1, f"Expected {operand2} to be in {operand1}"
        elif operator == "not_contains":
            assert operand2 not in operand1, f"Expected {operand2} to not be in {operand1}"
        elif operator == ">":
            assert operand1 > operand2, f"Expected {operand1} to be greater than {operand2}"
        elif operator == "<":
            assert operand1 < operand2, f"Expected {operand1} to be less than {operand2}"
        elif operator == ">=":
            assert operand1 >= operand2, f"Expected {operand1} to be greater than or equal to {operand2}"
        elif operator == "<=":
            assert operand1 <= operand2, f"Expected {operand1} to be less than or equal to {operand2}"
        print("Assertion passed\n")
        
    except AssertionError as e:
        print(f"Assertion [{assertion}] failed :: {str(e)} \n")
        if hard_assertion:
            # execute test case end lambda hook
            lambda_test_case_end(driver, curr_test_case_name)
            raise e

    # execute test case end lambda hook
    lambda_test_case_end(driver, curr_test_case_name)

# textual query
def query(driver: WebDriver, operation_index: str):
    # execute test case start
    curr_test_case_name = get_test_case_name(operation_index)
    lambda_test_case_start(driver, curr_test_case_name)
    
    # resolve operation if unresolved
    is_resolved = handle_unresolved_operations(operations_meta_data, operation_index, driver)
    
    custom_driver = CustomAppiumDriver(driver)
    
    locators = operations_meta_data[operation_index]['locator']
    regex_pattern = operations_meta_data[operation_index]['regex_pattern']
    utility = operations_meta_data[operation_index]['string_to_float']
    element, locator = find_element(driver, locators, operation_index, 2, 0)
    
    if element is None and utility:
        # execute test case end lambda hook
        lambda_test_case_end(driver, curr_test_case_name)
        return 0
    elif element is None and not utility:
        # execute test case end lambda hook
        lambda_test_case_end(driver, curr_test_case_name)
        return ""
    
    html = fetch_element_xml(custom_driver.get_page_source_with_webview_wait(), locator)
    html = html.replace('"', "'").replace("\n", "")
    attributes = ['data-node-id' , 'data-auteur-element-id', 'data-original-border-style' , 'data-original-position', 'data-original-padding-top', 'data-original-padding-left', 'data-original-width', 'data-original-height', 'data-original-max-width', 'data-original-max-height', 'data-original-display', 'manual-interaction-id']
    for attribute in attributes:
        html = re.sub(rf'{attribute}=\'.*?\'', '', html)
    
    regex = base64.b64decode(regex_pattern).decode("utf-8")
    match = re.search(fr"{regex}", html)
    if utility:
        # execute test case end lambda hook
        lambda_test_case_end(driver, curr_test_case_name)
        return string_to_float(match.group(1)) if match else 0
    
    # execute test case end lambda hook
    lambda_test_case_end(driver, curr_test_case_name)
    return match.group(1) if match else ""

# visual query
def vision_query(driver: WebDriver, operation_index: str):
    # execute test case start
    curr_test_case_name = get_test_case_name(operation_index)
    lambda_test_case_start(driver, curr_test_case_name)
    
    # wait before performing vision query
    wait_time = get_operation_wait_time(operation_index, 3, 6)
    if wait_time:
        print(f"Waiting '{wait_time} seconds' before performing vision query....")
        time.sleep(wait_time)
    
    autohealer = AutoHealer(driver)
    response = autohealer.get_healed_vision_query(operation_index)
    if response is None:
        raise RuntimeError("Error in vision query: response is None")
    
    # execute test case end lambda hook
    lambda_test_case_end(driver, curr_test_case_name)
    return response

def replace_secrets(text: str) -> str:
    matches = re.findall(r'\{\{(.*?)\}\}', text)
    for match in matches:
        keys = match.split('.')
        if len(keys) == 3 and keys[0] == 'secrets':
            secret_value = os.getenv(keys[2], '')
            text = text.replace(f"{{{{{match}}}}}", secret_value)

    return text

def replace_secrets_in_dict(d: Dict[str, str]) -> Dict[str, str]:
    new_dict = {}
    for k, v in d.items():
        replaced_key = replace_secrets(k)
        replaced_value = replace_secrets(v)
        if replaced_key == 'Authorization' and not replaced_value.startswith('Bearer') and not replaced_value.startswith('AWS'):
            username = replaced_value.split(':')[0]
            access_key = replaced_value.split(':')[1]
            replaced_value = f"Basic {base64.b64encode(f'{username}:{access_key}'.encode()).decode()}"
        new_dict[replaced_key] = replaced_value

    return new_dict


# api testing execution
def execute_api_action(driver: WebDriver, operation_index: str):
    # execute test case start
    curr_test_case_name = get_test_case_name(operation_index)
    lambda_test_case_start(driver, curr_test_case_name)

    original_payload = operations_meta_data[operation_index]
    payload = original_payload.copy()
    payload["headers"] = replace_secrets_in_dict(payload.get("headers", {}))
    
    auth = payload.get("authorization", {})
    if isinstance(auth, dict) and auth and auth.get('data'):
        auth_data = replace_apivar(auth.get("data").copy(), driver)
        auth['data'] = auth_data
        payload["authorization"] = auth

    url, headers, body, params = replace_apivar({'url':payload["url"], 'headers':payload["headers"].copy(), 'body':payload["body"], 'params':payload["params"].copy()},driver).values()
    
    payload["url"]=url
    payload["headers"]=headers
    payload["body"]=body
    payload["params"]=params

    
    # execute via lambda hook
    args = {
            "command": "executeAPI",
            "testId":  driver.session_id,
            "payload": payload
        }
    response = driver.execute_script("lambda-kane-ai", args)
    
    # execute test case end lambda hook
    lambda_test_case_end(driver, curr_test_case_name)
    return response

def is_action_unresolved(action: str, sub_instruction_obj: dict) -> bool:
    valid_actions = ["CLICK", "HOVER", "CLEAR", "ENTER"]
    return action in valid_actions and isinstance(sub_instruction_obj, dict) and len(sub_instruction_obj.get("variable", {})) > 0

# main ui action to handle interactions
def ui_action(driver: WebDriver, operation_index: str):
    # execute test case start
    curr_test_case_name = get_test_case_name(operation_index)
    lambda_test_case_start(driver, curr_test_case_name)
    
    # resolve operation if unresolved
    is_resolved = handle_unresolved_operations(operations_meta_data, operation_index, driver)

    attempts = 1
    max_retries = 2
    custom_driver = CustomAppiumDriver(driver) # helper class to handle custom actions
    action = operations_meta_data[operation_index]['operation_type'].lower()
    locators = operations_meta_data[operation_index].get('locator', None)
    is_coordinates_used_for_interaction = operations_meta_data[operation_index].get('is_coordinates_used_for_interaction', False)
    element_coordinates_ratio = operations_meta_data[operation_index].get('element_coordinates_ratio', [])
    element_coordinates = [0, 0]    
    
    for key, value in operations_meta_data[operation_index].items():
       if isinstance(value, str) and value.startswith("secrets."):
           env_var_name = value.split(".")[1]
           operations_meta_data[operation_index][key] = os.getenv(env_var_name, '')
    sub_instruction_obj = operations_meta_data[operation_index].get('sub_instruction_obj', {})
    if isinstance(sub_instruction_obj, str):
        sub_instruction_obj = json.loads(sub_instruction_obj)

    if isinstance(sub_instruction_obj, dict):
        if 'variable' in sub_instruction_obj:
            for key, value in sub_instruction_obj['variable'].items():
                new_value = get_variable_value(value, driver)
                if new_value != value:
                    if "SCROLL" in  action:
                        operations_meta_data[operation_index]["scroll_value"] = new_value
                    else:
                        operations_meta_data[operation_index][key] = new_value
    # handle implicit wait
    implicit_wait = operations_meta_data[operation_index].get('implicit_wait', 10)
    driver.implicitly_wait(implicit_wait)

    while attempts <= max_retries + 1:
        try:
            # additional wait time
            wait_time = 0
            if "scroll" in  action:
                wait_time = get_operation_wait_time(operation_index, 1, 3)
            elif action != "wait":
                wait_time = get_operation_wait_time(operation_index, 1, 1.5) # wait for 1.5 seconds by default
                
            if wait_time:
                print(f"Waiting '{wait_time} seconds' before performing {action} ....")
                time.sleep(wait_time)

            # check if dismiss dialog required
            if operations_meta_data[operation_index].get('dismiss_dialog', False):
                custom_driver.perform_dismiss_dialog_action()
                break
            
            # determine element
            element = None
            if is_coordinates_used_for_interaction:
                # refresh coordinates ratio data if needed
                if not is_resolved:
                    element_coordinates_ratio = get_new_coordinates_ratio_for_operation(operation_index, driver)
                element_coordinates = custom_driver.get_element_coordinates_from_ratio(element_coordinates_ratio)

            elif locators:
                element, _ = find_element(driver, locators, operation_index, 2, 0)
            
            # fetch element class
            element_class = custom_driver.get_element_class(element)
            
            # perform selector element actions
            if custom_driver.perform_selector_element_set_value_action(element, element_class, operations_meta_data[operation_index].get('value', '')):
                pass

            elif 'click' in action:
                custom_driver.perform_click_action(element, element_class, is_coordinates_used_for_interaction, element_coordinates)
            
            elif action == 'type' or action == 'input' or action == 'search':                           
                input_text = operations_meta_data[operation_index]['value']
                multiple_inputs = operations_meta_data[operation_index].get('multiple_inputs', False)

                # Click to focus on element only if not already focused
                if not multiple_inputs:
                    custom_driver.perform_click_action(element, element_class, is_coordinates_used_for_interaction, element_coordinates)
                else:
                    try:
                        if not custom_driver.is_keyboard_shown():
                            custom_driver.perform_click_action(element, element_class, is_coordinates_used_for_interaction, element_coordinates)
                    except:
                        pass
                
                if not multiple_inputs:
                    try:
                        custom_driver.perform_clear_action(element, is_coordinates_used_for_interaction)
                        if is_coordinates_used_for_interaction and (not custom_driver.is_keyboard_shown()):
                            custom_driver.perform_click_action(element, element_class, is_coordinates_used_for_interaction, element_coordinates)
                    except:
                        pass
                
                if action == 'search':
                    input_text = input_text + "\n"
                
                delay_ms = 0
                if multiple_inputs:
                    delay_ms = 500
                
                time.sleep(0.5) # Add a delay to allow clear/click to complete
                custom_driver.perform_type_action(input_text, delay_ms)

            elif action == 'enter':
                custom_driver.perform_keyevent("ENTER")

            elif action == 'clear':
                if is_coordinates_used_for_interaction:
                    custom_driver.perform_click_action(element, element_class, is_coordinates_used_for_interaction, element_coordinates)
                    
                custom_driver.perform_clear_action(element, is_coordinates_used_for_interaction)

            elif action == 'refresh':
                driver.refresh()
                
            elif action.startswith('scroll'):
                # Retrieve scroll metadata
                direction = operations_meta_data[operation_index]['scroll_direction']
                scroll_value = int(operations_meta_data[operation_index]['scroll_value'])
                
                if not direction or not scroll_value:
                    raise ValueError("Missing required metadata: Scroll direction or value")
                
                # get screen bounds
                screen_bounds: List[int] = [0, 0, 0, 0]
                if action.startswith('scroll_element'):
                    if is_coordinates_used_for_interaction:
                        screen_bounds = custom_driver.get_element_scroll_screen_bounds_from_coordinates(element_coordinates)
                    else:
                        screen_bounds = custom_driver.get_element_bounds(element)
                else:
                    screen_bounds = custom_driver.get_largest_scrollable_element_bounds()
                    
                # check if scroll value is in percentage
                is_percent_value = not action.endswith('pixels')
                
                times_loop_range = 0
                if action.endswith('times'):
                    times_loop_range = scroll_value
                    scroll_value = 0 # use defaults
                    
                # perform scroll
                loop_range, scroll_cords = get_scroll_coordinates(screen_bounds, direction, scroll_value, is_percent_value)
                start_x, start_y, end_x, end_y = scroll_cords
                
                # check if times loop range is set
                if times_loop_range:
                    loop_range = times_loop_range
                    
                for _ in range(loop_range):
                    custom_driver.perform_scroll_action(start_x, start_y, end_x, end_y, duration=300)

            elif action == 'wait':
                time.sleep(int(operations_meta_data[operation_index]['value']))
                
            elif action == 'navigate':
                direction = operations_meta_data[operation_index]['navigation_direction']
                custom_driver.navigate(direction)
                
            elif action == 'open_app' or action == 'switch_app':
                app_info = json.loads(operations_meta_data[operation_index].get('value', '{}'))
                package_name = app_info.get('package_name', app_info.get("packageName", ""))
                if not package_name:
                    raise ValueError("Package name not found")

                custom_driver.activate_app_with_fallback(package_name)

            elif action == 'close_app':
                current_package = custom_driver.get_current_package()
                if custom_driver.is_system_popup_package(current_package):
                    custom_driver.perform_dismiss_dialog_action()
                    current_package = custom_driver.get_current_package()
                    
                app_info = json.loads(operations_meta_data[operation_index].get('value', ''))
                package_name = app_info.get('package_name', app_info.get("packageName", ""))
                if not package_name:
                    package_name = current_package
                    
                custom_driver.perform_terminate_app_action(package_name=package_name, kill_timeout_ms=3000, max_attempts=2)


            elif action == 'orientation':
                setattr(driver, 'orientation', operations_meta_data[operation_index]['value'])
                
            elif action == 'keyboard':
                value = operations_meta_data[operation_index].get('value', 'hide')
                custom_driver.perform_keyboard_action(value)

            elif action == 'notification':
                value = operations_meta_data[operation_index].get('value', '').lower()
                if value == 'show':
                    custom_driver.open_notifications()
                elif value == 'hide':
                    custom_driver.hide_notifications()
                    
            elif action == 'keyevent':
                value = operations_meta_data[operation_index].get('value', '')
                custom_driver.perform_keyevent(value)
                        
            elif action == 'background':
                current_package = custom_driver.get_current_package()
                if custom_driver.is_system_popup_package(current_package):
                    custom_driver.perform_dismiss_dialog_action()
                
                duration = int(operations_meta_data[operation_index].get('value'))
                custom_driver.send_app_to_background(duration)

            elif action.lower() == "mathematical_operation":
                expression_tree = operations_meta_data[operation_index]['expression_tree']
                math_result = eval_math(expression_tree, driver)
                print(f"Mathematical operation result: {math_result}")
                return math_result

            elif action.lower() == "assertion":
                assertion_tree = operations_meta_data[operation_index]['assertion_tree']
                result = evaluate_assertion(assertion_tree, driver)
                print(f"Assertion result: {result}")
                return result
            
            elif action.lower() == "textual_query":
                if operations_meta_data[operation_index]['use_query_v2']:
                    if operations_meta_data[operation_index]['query_info_dict']['custom_data_hook_name']:
                        custom_hook_dict = get_attribute(element, driver, "custom_attributes_dict")
                        result = custom_hook_dict.get(operations_meta_data[operation_index]['query_info_dict']['custom_data_hook_name'], "")
                    else:
                        result = get_attribute(element, driver, operations_meta_data[operation_index]['query_info_dict']['selected_attribute_name'])
                        regex = operations_meta_data[operation_index]['query_info_dict'].get('regex', None)
                        if regex:
                            regex = base64.b64decode(regex).decode("utf-8")
                            result = re.search(fr"{regex}", result)
                            if result:
                                result = result.group(1)
                            else:
                                result = None
                    
                    if result and result != "":
                        return result
                    else:
                        return vision_query(driver, operation_index)
                else:
                    return vision_query(driver, operation_index)
            elif action.lower() == "set_variable":
                if operations_meta_data[operation_index].get("user_variables", "") != "":
                    user_vars_list = json.loads(operations_meta_data[operation_index]["user_variables"])
                    variable_name = user_vars_list[0]["name"]
                    if operations_meta_data[operation_index].get("variable_value", "") != "":
                        variable_value = operations_meta_data[operation_index]["variable_value"]  
                    else:
                        variable_value = user_vars_list[0]["value"]
                    user_variables[variable_name] = variable_value
                    
            elif action == 'network_throttle':
                network_throttle_payload = operations_meta_data[operation_index].get('network_throttle',{})

                if not network_throttle_payload:
                    raise ValueError("Network throttle payload is missing")
                
                is_mobile_offline = operations_meta_data[operation_index].get('is_mobile_offline', False)

                execute_network_throttle(driver, is_mobile_offline = is_mobile_offline, network_throttle = network_throttle_payload)

            else:
                raise ValueError("Invalid action: {}".format(action))
            
            break
            
        except Exception as e:
            attempts += 1
            is_optional = operations_meta_data[operation_index].get('optional_flag', False)
            # handle max retry cases
            if attempts > max_retries:
                if not is_optional:
                    raise RuntimeError(f"Failed to execute action: {action} on locator: {operations_meta_data[operation_index].get('locator', '')}. Error: {e} :: Traceback: {traceback.format_exc()}")
                else:
                    print(f"Failed to execute action: {action} on locator: {operations_meta_data[operation_index].get('locator', '')}. Error: {e} :: Traceback: {traceback.format_exc()}")
                break
            else:
                # wait for retry delay
                retry_delay = operations_meta_data[operation_index].get('retries_delay', 1)
                if not retry_delay:
                    retry_delay = 1
                time.sleep(retry_delay)
                
    # execute test case end lambda hook
    lambda_test_case_end(driver, curr_test_case_name)

#############################################################################################################