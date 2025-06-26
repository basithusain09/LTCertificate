import json, os

def get_device_name_regex(device_name: str, platform_name: str) -> str:
    if device_name:
        return device_name

    if platform_name.lower() == "android":
        device_name =  "^(?!.*(Tab|Fold|Xiaomi|Redmi|Oppo|Moto|OnePlus|Vivo|Huawei|Realme)).*"
    elif platform_name.lower() == "ios":
        device_name = "iPhone.*"

    return device_name

# get appium version
def get_appium_version(appium_version: str, platform_name: str, platform_version: str) -> str:
    if appium_version:
        return appium_version
    
    if platform_name.lower() == "ios":
        try: 
            platform_version_float = float(platform_version)
            
            if platform_version_float < 15:
                return "2.2.1-kane-ai"
            
            return  "2.11.4-kane-ai"
        except:
            return "2.11.4-kane-ai"
    
    return "2.11.2"

# helper to parse config value
def parse_config_value(config: dict) -> str|None:
    if not config:
        return None
    
    value = config.get("value", None)
    is_secret = config.get("isSecretValue", False)
    
    if not value:
        return None
    
    if is_secret:
        value = os.environ.get(value, None)
        if not value:
            return None
        
    return str(value)
        

# get playstore login caps
def parse_playstore_login_caps(playstore_login_config: dict, platform_name: str) -> dict|None:
    if platform_name.lower() != "android":
        return None
    
    email = parse_config_value(playstore_login_config.get("email", {}))
    password = parse_config_value(playstore_login_config.get("password", {}))
    if not (email and password):
        return None
    
    return {
        "email": email,
        "password": password
    }

def get_env_bool(key: str, default: bool) -> bool:
    """Fetches an environment variable and converts it to a boolean.
    
    - If the key exists and is "true" (case-insensitive), returns True.
    - If the key exists and is "false" (case-insensitive), returns False.
    - If the key is not found, returns the provided default value.
    """
    value = os.getenv(key, str(default)).lower()
    return value == "true"

# get test name and build name
def get_test_name_and_build_name(test_instance: dict) -> tuple:
    runName = "[PYTHON RUN] "
    project_name = test_instance.get("project_name", 'Untitled Project')
    folder_name = test_instance.get("folder_name", '')
    og_test_name = test_instance.get("test_name", '')
    tc_internal_id = test_instance.get("tms.tc_id", '')
    code_req_name = test_instance.get("code_req_name", '')
    
    build_name = "[Kane AI Code Gen]"  + " | " + project_name + f" [{tc_internal_id}]"
    test_name = runName + folder_name + " | " + og_test_name + f" [{code_req_name}]"
    
    if test_instance.get("is_test_run", False): # for test run, run all tests under 1 build
        build_name = "[Kane AI Test Run]" + " | " + test_instance.get("test_run_name") + " | " + project_name
        test_name = runName + folder_name + " | " + og_test_name + " | " + f" [{tc_internal_id}]"
        
    return test_name, build_name


# main function to build caps
def build_caps(test_instance_id: str, test_config_file_path: str):
    with open(test_config_file_path, 'r') as file:
        test_config = json.load(file)
    test_instances = test_config.get("linux", [])
    test_instance = {}
    for x_test_instance in test_instances:
        x_test_instance_id = x_test_instance.get("test_instance_id")

        if x_test_instance_id == test_instance_id:
            test_instance = x_test_instance
            break

    if not test_instance:
        raise Exception("Test instance not found")
    
    device_name = test_instance.get("device_name", "")
    platform_name = test_instance.get("platform_name", "")
    platform_version = test_instance.get("platform_version", "")
    appium_version = test_instance.get("appium_version", "")
    
    # form test name and build name
    test_name, build_name = get_test_name_and_build_name(test_instance)
        
    
    lt_options = {}
    lt_options["appiumVersion"] = get_appium_version(appium_version, platform_name, platform_version)
    lt_options["appiumPlugins"] = test_instance.get("appium_plugins", [])
    lt_options["app"] = test_instance.get("app", '')
    lt_options["deviceName"] = get_device_name_regex(device_name, platform_name)
    lt_options["tms.tc_id"] = test_instance.get("tms.tc_id", '')
    lt_options["name"] = test_name
    lt_options["build"] = os.getenv("BUILD", build_name)
    lt_options["platformName"] = platform_name
    lt_options["privateCloud"] = test_instance.get("private_cloud", False)
    lt_options["platformVersion"] = test_instance.get("platform_version", '')
    
    if platform_name == "android":
        lt_options["unicodeKeyboard"] = test_instance.get("unicode_keyboard", True)
        lt_options["autoGrantPermissions"] = test_instance.get("auto_grant_permissions", False)
        lt_options["allowInvisibleElements"] = True
    else:
        lt_options["waitForQuiescence"] = False
        lt_options["useJSONSource"] = test_instance.get("use_json_source", False)
        lt_options["pageSourceExcludedAttributes"] = "frame,enabled,focused"
        lt_options["autoAcceptAlerts"] = test_instance.get("auto_accept_alerts", False)
        lt_options["autoDismissAlerts"] = test_instance.get("auto_dismiss_alerts", False)
        # check for enterprise apps
        if test_instance.get("disable_app_resigning", False):
            lt_options["resignApp"] = False
    
    
    if str(test_instance.get("tunnel", False)).lower() == "true":
        lt_options["tunnel"] = True
        lt_options["tunnelName"] = test_instance.get("tunnel_name", '')
    
    if str(test_instance.get("dedicated_proxy", False)).lower() == "true":
        lt_options["dedicatedProxy"] = True
    
    if test_instance.get("geo_location", ''):
        lt_options["geoLocation"] = test_instance.get("geo_location")
        
    # check for playstore login caps
    playstore_login_caps = parse_playstore_login_caps(test_instance.get("google_login_config", {}), platform_name)
    if playstore_login_caps:
        lt_options["playStoreLogin"] = playstore_login_caps
        
    # check for region caps
    regionCap = os.getenv("DEVICE_REGION", "")
    if not regionCap:
        regionCap = test_instance.get("region", "")
    if regionCap:
        lt_options["region"] = regionCap.lower()
        

    lt_options["newCommandTimeout"] = 86400
    lt_options["idleTimeout"] = int(os.getenv("IDLE_TIMEOUT", 1500))
    lt_options["queueTimeout"] = int(os.getenv("QUEUE_TIMEOUT", 900))

    lt_options["visual"] = get_env_bool("VISUAL", True)
    lt_options["video"] = get_env_bool("VIDEO", True)
    lt_options["screenshot"] = get_env_bool("SCREENSHOT", True)
    lt_options["network"] = get_env_bool("NETWORK", False)
    lt_options["mitmProxy"] = get_env_bool("MITM_PROXY", False)

    lt_options["networkProfile"] = "default"
    lt_options["devicelog"] = get_env_bool("DEVICE_LOG", True)
    
    lt_options["isRealMobile"] = True
    lt_options["w3c"] = True

    if os.getenv("TIMEZONE", False):
        lt_options["timeZone"] = os.getenv("TIMEZONE")
    
    if os.getenv("APP_PACKAGE", False):
        lt_options["appPackage"] = os.getenv("APP_PACKAGE")
    
    if os.getenv("APP_ACTIVITY", False):
        lt_options["appActivity"] = os.getenv("APP_ACTIVITY")
    
    if os.getenv("UDID", False):
        lt_options["udid"] = os.getenv("UDID")
    
    # check for driver settings
    lt_options["driver_settings"] = test_instance.get("driver_settings", {})
    
    return lt_options
    
