import unittest
import os, json
from appium import webdriver
from appium.options.ios import XCUITestOptions
from UIActions import ui_action, lambda_hooks, query, vision_query, perform_assertion, string_to_float, execute_lambda_hooks, get_test_case_name, lambda_test_case_start, lambda_test_case_end, execute_api_action, set_operations_meta_data, reload_metadata_root, user_variables, initialize_network_throttle

import argparse, requests
from requests.auth import HTTPBasicAuth
from utils import build_caps
import sys

username = os.getenv("LT_USERNAME")
access_key = os.getenv("LT_ACCESS_KEY")
hub_url = os.getenv("LT_HUB_URL", "mobile-hub.lambdatest.com")
metadata_url = "https://manual-api.lambdatest.com/app/"

# caps options
options = XCUITestOptions()

# driver settings
driver_settings = {}

def app_metadata(metaData_url, username, access_key, platform_name):
    try:
        response = requests.get(metaData_url, auth=HTTPBasicAuth(username, access_key))
        response.raise_for_status()  

        try:
            data = response.json().get("data", {})
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to decode JSON: {e}")

        if not data:
            raise KeyError("Missing 'data' in the response")

        os.environ["app"] = data.get("name", "unknown-app")

        metadata_str = data.get("metadata", "{}")
        try:
            metadata = json.loads(metadata_str)
        except json.JSONDecodeError:
            metadata = {}
            print("Warning: Failed to parse metadata. Defaulting version.")

        if platform_name.lower() == "android":
            os.environ["appVersion"] = metadata.get("versionName", "0.0.1")
        else:
            os.environ["appVersion"] = metadata.get("version", "0.0.1")

    except requests.RequestException as e:
        os.environ["app"] = "unknown-app"
        os.environ["appVersion"] = "0.0.1"
    except Exception as e:
        os.environ["app"] = "unknown-app"
        os.environ["appVersion"] = "0.0.1"

        
class FirstSampleTest(unittest.TestCase):
    driver = None

    def setUp(self):
        self.driver = webdriver.Remote(
            command_executor="https://{}:{}@{}/wd/hub".format(
                username, access_key, hub_url
            ),
            options=options,
        )
        # update driver settings if any
        if driver_settings and len(driver_settings) > 0:
            print(f"Updating driver settings: {driver_settings}")
            self.driver.update_settings(driver_settings)

    def test_demo_site(self):
        driver = self.driver
        status = "failed"
        
        try:    
            driver.implicitly_wait(10)
            reload_metadata_root()

            initialize_network_throttle(driver)

            # click on 'Colour' button
            lambda_hooks(driver, "click on 'Colour' button")
            ui_action(driver = driver, operation_index = str(0))

            # click on Home button
            lambda_hooks(driver, "click on Home button")
            ui_action(driver = driver, operation_index = str(1))

            # get the value of 3rd button
            lambda_hooks(driver, "get the value of 3rd button")
            third_button_value = vision_query(driver = driver, operation_index = str(2))
            user_variables["third_button_value"] =  third_button_value
            print("third_button_value:", third_button_value)

            # assert {{third_button_value}} is equal to 'cOLOUR'
            lambda_hooks(driver, "assert {{third_button_value}} is equal to 'cOLOUR'")
            perform_assertion(driver, "3", str(third_button_value).lower().strip(), "==", """colour""",{"assert {{third_button_value}} is equal to 'cOLOUR'"})

            # Update the status to passed
            status = "passed"
        
        except Exception as e:
            print(f"An error occurred: {e}")
        
        finally:
            # Update the status at the end
            if driver is not None:
                driver.execute_script(f"lambda-status={status}")

    # tearDown runs after each test case
    def tearDown(self):
        if self.driver is not None:
            self.driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Custom argument demo for unittest.")
    
    parser.add_argument("--test-config", type=str,
                        help="Test config file path")

    parser.add_argument("--test-instance-id", type=str,
                        help="Test Instance to be picked from the test config file")
    parser.add_argument("--operations-meta-data", type=str, default="operations_meta_data.json",
                        help="Operation meta data to be picked from the file")

    args, unittest_args = parser.parse_known_args()
    set_operations_meta_data(args.operations_meta_data)
    
    # set fixed caps and settings
    fixed_caps = {'tms.tc_id': 'TC-1808', 'platformName': 'ios', 'autoAcceptAlerts': True, 'autoDismissAlerts': False}
    fixed_driver_settings = {'respectSystemAlerts': True}
    
    # fetch caps
    lt_options = build_caps(args.test_instance_id, args.test_config)
    
    # fetch and set driver settings
    driver_settings = lt_options.get("driver_settings", {})
    driver_settings.update(fixed_driver_settings) # override fixed driver settings
    
    # del driver settings from lt_options
    lt_options.pop("driver_settings", None)
    
    # override fixed caps
    lt_options.update(fixed_caps)
    
    os.environ["deviceName"] = lt_options.get("deviceName", "")
    os.environ["platformVersion"] = lt_options.get("platformVersion", "")
    os.environ["platformName"] = lt_options.get("platformName", "")

    metaData_url = metadata_url + lt_options.get("app").removeprefix("lt://") + "/metadata"
    app_metadata(metaData_url, username, access_key,lt_options.get("platformName"))

    # set final caps in options
    print(f"Test capabilities: {lt_options}")
    options.set_capability("LT:Options", lt_options)
    
    unittest.main(argv=[sys.argv[0]] + unittest_args)
