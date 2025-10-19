import os
import glob
import time
import json
import signal
import random
import pyodbc
import traceback
import importlib.util
from datetime import datetime, timedelta
from colorama import Fore, Style, init

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

init(autoreset=True)
class Logger:
    COLORS = {
        "DEBUG": Fore.LIGHTBLACK_EX ,
        "INFO": Fore.WHITE,
        "WARNING": Fore.YELLOW + Style.BRIGHT,
        "ERROR": Fore.RED + Style.BRIGHT,
        "CRITICAL": Fore.BLUE  + Style.BRIGHT,
        "SUCCESS": Fore.GREEN + Style.BRIGHT
    }

    def __init__(self, logfile=None):
        logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
        if logfile is None:
            log_filename = os.path.splitext(os.path.basename(__file__))[0] + ".log"
            self.logfile = os.path.join(logs_dir, log_filename)
        else:
            self.logfile = os.path.join(logs_dir, logfile) if not os.path.isabs(logfile) else logfile

    def log(self, level, msg):
        timestamp = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        log_line = f"{timestamp} [{level}] {msg}"
        print(f"{self.COLORS.get(level, Fore.WHITE)}{log_line}{Style.RESET_ALL}")
        with open(self.logfile, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")

    def __getattr__(self, level):
        return lambda msg: self.log(level.upper(), msg)

class WhatsAppBot:
    def __init__(self, user_data_dir: str = None, session_timeout: int = 60, default_timeout: int = 30):
        self.log = Logger()
        self.log.info("Initializing WhatsApp Bot")
        self.default_timeout = default_timeout
        self.session_timeout = session_timeout
        self._load_config()
        effective_user_data_dir = os.path.join(os.getcwd(), "cookies", user_data_dir or self.config.get("userdata_dir", ""))
        self.log.debug(f"Using user data directory: {effective_user_data_dir}")
        self.options = Options()
        
        if self.config.get("headless", False):
            self.options.add_argument("--headless")
            self.options.add_argument("--window-size=1920,1080")
            self.log.info("Running in headless mode")
        else:
            self.options.add_argument("--start-maximized")
            self.log.info("Running in visible mode")
        
        self.options.add_argument(rf"user-data-dir={effective_user_data_dir}")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-popup-blocking")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--detach")
        self.options.add_argument("--disable-logging")
        self.options.add_argument("--log-level=3")
        self.options.add_argument("--silent")
        self.options.add_argument("--disable-extensions")
        self.options.add_argument("--disable-plugins")
        self.options.add_argument("--disable-default-apps")
        self.options.add_argument("--disable-sync")
        self.options.add_argument("--disable-background-timer-throttling")
        self.options.add_argument("--disable-backgrounding-occluded-windows")
        self.options.add_argument("--disable-renderer-backgrounding")
        self.options.add_argument("--disable-features=TranslateUI")
        self.options.add_argument("--disable-ipc-flooding-protection")
        self.log.info("Starting Chrome WebDriver")
        self.driver = webdriver.Chrome(options=self.options)
        self.pid = self.driver.service.process.pid
        self.log.info(f"Chrome PID: {self.pid}")
        self.driver.get("https://web.whatsapp.com")
        self.log.info("Navigating to WhatsApp Web")
        self.latest_messages = None
        self.latest_sender = None
        self.latest_hour = None
        self.session_caller = None
        self.last_activity_time = None
        self.last_scheduler_time = None
        self.last_scheduler_task = list()
        self.interactive_mode = False
        self.scheduler_mode = False
        self.module_found = False
        try:
            self.log.debug("Waiting for WhatsApp Web to load")
            self.wait_for_presence('//div[@contenteditable="true"][@data-tab="3"]', timeout=120)
            self.log.success("WhatsApp Web loaded successfully")
        except TimeoutException:
            self.log.warning("Timeout waiting for WhatsApp Web to load")
            pass
        self.log.info(f"Opening group: {self.config['groupname']}")
        self.open_group(self.config["groupname"])

    def _load_config(self):
        with open("config.json", "r", encoding="utf-8") as file:
            self.config = json.load(file)
        self.affirmative_keywords = self.config["affirmative_keywords"]
        self.negative_keywords = self.config["negative_keywords"]
        self.messages = self.config["messages"]
        self.help_text = self.config["help_text"]
        self.keyword = self.config["reporting_service"]
        self.keyword_sql = self.config["sql_service"]
        self.keyword_py = self.config["python_service"]
        self.schedule = self.config["scheduler_service"]
        self.max_consecutive_errors = self.config.get("max_consecutive_errors", 5)
        self.restart_delay = self.config.get("restart_delay", 5)

    def wait_for_presence(self, xpath, timeout: int = None):
        t = timeout or self.default_timeout
        return WebDriverWait(self.driver, t).until(EC.presence_of_element_located((By.XPATH, xpath)))

    def wait_for_visibility(self, xpath, timeout: int = None):
        t = timeout or self.default_timeout
        return WebDriverWait(self.driver, t).until(EC.visibility_of_element_located((By.XPATH, xpath)))

    def wait_for_clickable(self, xpath, timeout: int = None):
        t = timeout or self.default_timeout
        return WebDriverWait(self.driver, t).until(EC.element_to_be_clickable((By.XPATH, xpath)))

    def human_type(self, element, text: str):
        words = text.split(' ')
        for i, word in enumerate(words):
            element.send_keys(word)
            if i < len(words) - 1:
                element.send_keys(' ')
            time.sleep(random.uniform(0.05, 0.15))

    def open_group(self, group_name: str):
        self.log.debug(f"Opening group: {group_name}")
        search_box = self.wait_for_visibility('//div[@contenteditable="true"][@data-tab="3"]')
        search_box.click()
        try:
            search_box.clear()
        except Exception:
            search_box.send_keys(Keys.CONTROL + "a")
            search_box.send_keys(Keys.DELETE)
        self.human_type(search_box, group_name)
        self.wait_for_clickable(f'//span[@title="{group_name}"]').click()
        self.wait_for_clickable(f'//div[@contenteditable="true"][@data-tab="10"]').click()
        self.log.success(f"Successfully opened group: {group_name}")

    def get_message(self):
        self.wait_for_presence('//div[contains(@class,"message-in")]')
        messages = self.driver.find_elements(By.XPATH, '//div[contains(@class,"message-in")]')[-1]
        parts = messages.text.split("\n")
        last_sender = parts[0] if len(parts) == 3 else 'Bapak/Ibu'
        last_messages = parts[1] if len(parts) == 3 else parts[0]
        last_hour = parts[2] if len(parts) == 3 else parts[1]
        return last_sender, last_messages, last_hour

    def send_message(self, message, is_multiline: bool = False):
        self.log.debug(f"Sending message: {'[MULTILINE]' if is_multiline else message}")
        input_box = self.wait_for_visibility(f'//div[@contenteditable="true"][@data-tab="10"]')
        input_box.click()
        if is_multiline:
            for row in message:
                input_box.send_keys(row)
                input_box.send_keys(Keys.SHIFT, Keys.ENTER)
            input_box.send_keys(Keys.ENTER)
        else:
            self.human_type(input_box, message)
            input_box.send_keys(Keys.ENTER)
        self.log.success("Message sent successfully")

    def image_to_base64(self, image_path: str) -> str:
        self.log.debug(f"Converting image to base64: {image_path}")
        with open(image_path, "rb") as image_file:
            import base64
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string

    def enable_hd_quality(self):
        try:
            photo_quality_button = self.wait_for_clickable(f'//div[@title="Photo quality"][@role="button"]', timeout=5)
            photo_quality_button.click()
            hd_quality_option = self.wait_for_clickable(f"//div[text()='HD quality']", timeout=5)
            hd_quality_option.click()
            self.log.debug("HD quality enabled successfully")
        except TimeoutException:
            self.log.debug("HD quality option not available, skipping")
            pass
        except Exception as e:
            self.log.debug(f"Error enabling HD quality: {str(e)}, skipping")
            pass

    def send_image(self, image_path: str, caption: str):
        self.log.debug(f"Sending image: {image_path} with caption: {caption}")
        encoded_string = self.image_to_base64(image_path)
        input_box = self.wait_for_visibility(f'//div[@contenteditable="true"][@data-tab="10"]')
        input_box.click()
        
        js_script = f"""
        var dataTransfer = new DataTransfer();
        var blob = new Blob([Uint8Array.from(atob('{encoded_string}'), c => c.charCodeAt(0))], {{type: 'image/png'}});
        var file = new File([blob], '{os.path.basename(image_path)}', {{type: 'image/png'}});
        dataTransfer.items.add(file);
        
        var pasteEvent = new ClipboardEvent('paste', {{
            clipboardData: dataTransfer,
            bubbles: true,
            cancelable: true
        }});
        
        var element = arguments[0];
        element.dispatchEvent(pasteEvent);
        """
        
        self.log.debug(f"Executing JavaScript paste event for {image_path}")
        self.driver.execute_script(js_script, input_box)
        time.sleep(3)
        caption_box = self.wait_for_clickable(f'//div[@contenteditable="true"][@role="textbox"]')
        caption_box.click()
        for row in caption:
            self.log.debug(f"Send {row}")
            caption_box.send_keys(row)
            caption_box.send_keys(Keys.SHIFT, Keys.ENTER)
        self.enable_hd_quality()
        caption_box.send_keys(Keys.ENTER)
        self.log.success("Image sent successfully")

    def open_new_tab(self, url=None):
        self.log.debug(f"Open url in new tab: {url}")
        self.driver.execute_script("window.open('');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        if url:
            self.driver.get(url)
        return self.driver.window_handles[-1]

    def switch_tab(self, tab_handle):
        self.log.debug(f"Switch tab to: {tab_handle}")
        self.driver.switch_to.window(tab_handle)

    def close_current_tab(self):
        self.log.debug(f"Closing new tab")
        self.driver.close()
        if len(self.driver.window_handles) > 0:
            self.driver.switch_to.window(self.driver.window_handles[0])

    def getdate(self):
        self.log.debug(f"Generating current date")
        now = datetime.now()
        if 7 <= now.hour <= 23:
            return now.strftime("%Y-%m-%d")
        previous_day = now - timedelta(days=1)
        return previous_day.strftime("%Y-%m-%d")

    def input_parameter(self, last_messages):
        self.log.debug(f"Input parameter to: {last_messages}")
        for param in self.keyword[last_messages]["parameter"]:
            if param["type"] == "text_input":
                self.log.debug(f"Input parameter to: {param['name']}")
                input_box = self.wait_for_visibility(param['xpath'])
                input_box.click()
                input_box.send_keys(Keys.CONTROL + "a")
                input_box.send_keys(Keys.DELETE)
                value = param['value']
                if value == "getdate":
                    value = self.getdate()
                input_box.send_keys(value)
            elif param["type"] == "select":
                self.log.debug(f"Input parameter to: {param['name']}")
                select_box = self.wait_for_clickable(param['xpath'])
                select_box.click()

    def take_screenshot(self, last_messages):
        element = self.wait_for_visibility(self.keyword[last_messages]["body"])
        self.log.debug(f"Resizing windows")
        self.driver.set_window_size(self.keyword[last_messages]["width"], self.keyword[last_messages]["height"])
        time.sleep(5)
        picture_name = self.driver.current_window_handle + '.png'
        self.log.debug(f"Taking Screenshot: {picture_name}")
        element.screenshot(picture_name)
        if not self.config.get("headless", False):
            self.driver.maximize_window()
        else:
            self.driver.set_window_size(1920, 1080)        
        return picture_name
    
    def _load_sql(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
        
    def _connect(self, server, database, timeout):
        conn_str = (
            "Driver={SQL Server};"
            f"Server={server};"
            f"Database={database};"
            "Trusted_Connection=yes;")
        return pyodbc.connect(conn_str, timeout=timeout)
    
    def execute_sql(self, command_key, values, timeout=120):
        cfg = self.config["sql_service"][command_key]
        param_names = cfg.get("params", [])
        self.log.debug(f"Checking parameters for command '{command_key}': expected {param_names}, got {values}")
        if len(param_names) != len(values):
            return [f"Maaf parameter yang anda cari tidak ditemukan/salah. Command ini membutuhkan {len(param_names)} parameter, sedangkan anda memberikan {len(values)} parameter"]

        params = dict(zip(param_names, values))
        query = self._load_sql(cfg["sql_file"]).format(**params)
        with self._connect(cfg["server"], cfg["database"], timeout) as conn:
            with conn.cursor() as cursor:
                self.log.debug(f"Executing SQL command: {command_key} with params: {params}")
                cursor.execute(query)
                row = cursor.fetchone()
                self.log.success(f"Successfully executed SQL command: {command_key}")
                if row and row[0] and row[0].strip():
                    return [item.strip() for item in row[0].split(';') if item.strip()]
                self.log.warning(f"No data found for command '{command_key}' with params {params}")
                return ["Maaf parameter yang anda cari tidak ditemukan/salah"]
    
    def execute_python(self, command_key):
        svc = self.keyword_py.get(command_key)
        if not svc:
            self.send_message(f"Service '{command_key}' not found in config")
            return None

        module_path = os.path.abspath(svc["python_path"])
        module_name = os.path.splitext(os.path.basename(module_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class_name = svc.get("class_name", None)
        method_name = svc.get("method", None)
        if not class_name or not method_name:
            self.send_message(f"Service '{command_key}' must define 'class_name' and 'method'")
            return None
        
        cls = getattr(module, class_name)
        instance = cls(**svc["parameter"])
        method = getattr(instance, method_name)
        self.module_found = True
        return method()

    def scheduler(self):
        now = datetime.now()
        for schedule_time, commands in self.schedule.items():
            schedule_dt = datetime.strptime(schedule_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            if schedule_dt <= now <= schedule_dt + timedelta(minutes=10):
                self.scheduler_mode = True
                if self.last_scheduler_time == schedule_time:
                    self.last_scheduler_task = list()
                    self.scheduler_mode = False
                    return None, None, None, self.scheduler_mode
                self.log.debug(f"Listing tasks for time: {schedule_time}")
                remain_task = [cmd for cmd in commands if cmd not in self.last_scheduler_task]
                if len(remain_task) == 0:
                    self.log.debug(f"All Job done for time: {schedule_time}, resetting")
                    self.last_scheduler_time = schedule_time
                    self.scheduler_mode = False
                    self.interactive_mode = False
                    return None, None, None, self.scheduler_mode
                self.log.debug(f"Generating message for scheduler task: {remain_task[0]}")
                scheduler_messages = remain_task[0]
                scheduler_sender = 'system_scheduler'
                scheduler_hour = schedule_time
                self.last_scheduler_task.append(remain_task[0])
                return scheduler_messages, scheduler_sender, scheduler_hour, self.scheduler_mode
        self.scheduler_mode = False
        return None, None, None, self.scheduler_mode
    
    def health_check(self):
        try:
            current_url = self.driver.current_url
            if "web.whatsapp.com" not in current_url:
                self.log.warning("WhatsApp Web is no longer loaded")
                return False
            
            self.driver.find_element(By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')
            return True
        except Exception as e:
            self.log.warning(f"Health check failed: {str(e)}")
            return False

    def restart_driver(self):
        self.log.warning("Restarting WebDriver due to connection issues")
        try:
            self.driver.quit()
        except Exception:
            pass
        
        self.driver = webdriver.Chrome(options=self.options)
        self.driver.get("https://web.whatsapp.com")
        try:
            self.wait_for_presence('//div[@contenteditable="true"][@data-tab="3"]', timeout=120)
        except TimeoutException:
            pass
        self.open_group(self.config["groupname"])
        self.log.success("WebDriver restarted successfully")

    def run(self):
        self.log.info("Starting WhatsApp Bot main loop")
        consecutive_errors = 0
        max_consecutive_errors = self.max_consecutive_errors
        
        while True:
            self._load_config()
            scheduler_messages, scheduler_sender, scheduler_hour, self.scheduler_mode = self.scheduler()
            try:
                last_sender, last_messages, last_hour = self.get_message()
                if self.scheduler_mode:
                    self.log.debug(f"Entering scheduler mode..")
                    self.interactive_mode = True
                    self.session_caller = scheduler_sender
                    self.last_activity_time = time.time()
                    last_sender = scheduler_sender
                    last_messages = scheduler_messages
                    last_hour = scheduler_hour
                consecutive_errors = 0 
            except Exception as e:
                consecutive_errors += 1
                self.log.error(f"Error getting message (consecutive errors: {consecutive_errors}): {str(e)}")
                
                if consecutive_errors >= max_consecutive_errors:
                    self.log.critical(f"Too many consecutive errors ({consecutive_errors}). Raising exception for main handler.")
                    raise Exception(f"Too many consecutive errors in message retrieval: {str(e)}")
                
                self.restart_driver()
                time.sleep(5)
                continue
            if self.interactive_mode and self.last_activity_time and (time.time() - self.last_activity_time > self.session_timeout):
                self.log.warning(f"Session timeout for user: {self.session_caller}")
                self.send_message(self.messages["no_response"].format(user=self.session_caller))
                self.last_activity_time = None
                self.interactive_mode = False
                self.session_caller = None
                time.sleep(2)
                continue
            if last_messages == self.latest_messages and last_hour == self.latest_hour:
                time.sleep(2)
                continue
            last_messages = last_messages.lower()
            self.latest_messages = last_messages
            self.latest_hour = last_hour
            if last_sender != 'Bapak/Ibu':
                self.latest_sender = last_sender
            try:
                if self.interactive_mode:
                    if last_sender != self.session_caller and (last_messages in list(self.keyword.keys()) 
                                                            or last_messages in self.keyword_sql.keys() 
                                                            or last_messages.split()[0] in self.keyword_sql.keys()
                                                            or 'bot mio' in last_messages):
                        self.log.debug(f"Message from {last_sender} while session with {self.session_caller} is active")
                        self.send_message(self.messages["wait"].format(user=self.session_caller))
                        time.sleep(2)
                        continue
                    self.last_activity_time = time.time()
                    if last_messages in self.affirmative_keywords:
                        self.log.debug("User responded affirmatively")
                        self.send_message(self.messages["ask_help"])
                        time.sleep(2)
                        continue
                    if last_messages == "help":
                        self.log.debug("User requested help")
                        self.send_message(self.help_text, is_multiline=True)
                        time.sleep(2)
                        continue
                    if last_messages in self.negative_keywords:
                        self.log.info(f"Session ended by user: {self.session_caller}")
                        self.interactive_mode = False
                        self.session_caller = None
                        self.last_activity_time = None
                        self.send_message(self.messages["session_end"])
                        time.sleep(2)
                        continue
                    if last_messages in list(self.keyword.keys()):
                        self.log.info(f"Processing request: {last_messages}")
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["processing"].format(command=last_messages))
                        new_tab = self.open_new_tab(self.keyword[last_messages]["url"])
                        self.switch_tab(new_tab)
                        self.input_parameter(last_messages)
                        time.sleep(5)
                        detection = self.wait_for_visibility(self.keyword[last_messages]["detection"], 120)
                        detection.click()
                        if self.keyword[last_messages]["caption"] == "xpath":
                            caption_text = self.wait_for_visibility("//*[contains(text(), 'captionbox')]")
                            caption = caption_text.text.strip()
                        else:
                            caption = self.keyword[last_messages]["caption"] + self.getdate()
                        caption_list = [line for line in caption.splitlines() if "captionbox" not in line.lower()]
                        filename = self.take_screenshot(last_messages)
                        self.close_current_tab()
                        self.open_group(self.config["groupname"])
                        self.send_image(filename, caption_list)
                        os.remove(filename)
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["confirmation"])
                        self.last_activity_time = time.time()
                        self.log.success(f"Successfully processed request: {last_messages}")
                        time.sleep(2)
                        continue
                    if last_messages in self.keyword_sql.keys():
                        self.log.info(f"Processing SQL request: {last_messages}")
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["processing"].format(command=last_messages))
                        self.command_key = last_messages
                        self.values = []
                        self.result = self.execute_sql(self.command_key, self.values, timeout=60)
                        self.send_message(self.result, is_multiline=True)
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["confirmation"])
                        self.log.success(f"Successfully processed request: {last_messages}")
                        time.sleep(2)
                        continue
                    if last_messages.split()[0] in self.keyword_sql.keys():
                        self.log.info(f"Processing SQL request: {last_messages}")
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["processing"].format(command=last_messages))
                        parts = last_messages.split()
                        self.command_key = parts[0]
                        self.values = parts[1:]
                        self.result = self.execute_sql(self.command_key, self.values, timeout=60)
                        self.send_message(self.result, is_multiline=True)
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["confirmation"])
                        self.log.success(f"Successfully processed request: {last_messages}")
                        time.sleep(2)
                        continue
                    if last_messages in self.keyword_py.keys() and self.keyword_py.get(last_messages, {}).get("output_type") == "image":
                        self.log.info(f"Executing Python request: {last_messages}")
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["processing"].format(command=last_messages))
                        image_path, caption = self.execute_python(last_messages)
                        if not self.module_found:
                            self.send_message(f"Maaf module untuk service '{last_messages}' tidak ditemukan/salah")
                            continue
                        self.send_image(image_path, caption)
                        os.remove(image_path)
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["confirmation"])
                        self.log.success(f"Successfully processed request: {last_messages}")
                        self.last_activity_time = time.time()
                        time.sleep(2)
                        continue
                    if last_messages in self.keyword_py.keys() and self.keyword_py.get(last_messages, {}).get("output_type") == "html":
                        self.log.info(f"Executing Python request: {last_messages}")
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["processing"].format(command=last_messages))
                        html_path, caption = self.execute_python(last_messages)
                        if not self.module_found:
                            self.send_message(f"Maaf module untuk service '{last_messages}' tidak ditemukan/salah")
                            continue
                        self.driver.set_window_size(self.keyword_py[last_messages]["width"], self.keyword_py[last_messages]["height"])
                        self.log.debug(f"Opening HTML file in new tab: {html_path}")
                        new_tab = self.open_new_tab(f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}")
                        self.switch_tab(new_tab)
                        time.sleep(5)
                        picture_name = self.driver.current_window_handle + '.png'
                        element = self.wait_for_visibility("/html/body")
                        element.screenshot(picture_name)
                        if not self.config.get("headless", False):
                            self.driver.maximize_window()
                        else:
                            self.driver.set_window_size(1920, 1080)
                        self.close_current_tab()
                        self.open_group(self.config["groupname"])
                        self.send_image(picture_name, caption)
                        os.remove(picture_name)
                        os.remove(html_path)
                        [os.remove(f) for f in glob.glob("templates/asset/*") if os.path.isfile(f)]
                        if self.session_caller != "system_scheduler": self.send_message(self.messages["confirmation"])
                        self.log.success(f"Successfully processed request: {last_messages}")
                        self.module_found = False
                        self.last_activity_time = time.time()
                        time.sleep(2)
                        continue
                    self.log.warning(f"Unknown command received: {last_messages}")
                    self.send_message(self.messages["unknown"])
                    time.sleep(2)
                    continue

                if 'bot mio' in last_messages and self.interactive_mode == False:
                    self.log.info(f"Bot activated by user: {self.latest_sender}")
                    self.interactive_mode = True
                    self.session_caller = self.latest_sender
                    self.send_message(self.messages["activation"].format(user=self.session_caller))
                    self.last_activity_time = time.time()
                    continue
                time.sleep(2)
            except Exception as e:
                error_details = traceback.format_exc()
                self.log.error(f"Failed to process command '{last_messages}' from {last_sender}: {e}")
                self.log.debug(f"Traceback details:\n{error_details}")
                self.send_message(f"Gagal memproses perintah '{last_messages}'. Silakan coba lagi nanti.")
                if self.session_caller != "system_scheduler": self.send_message(self.messages["confirmation"])
                self.last_activity_time = time.time()
                time.sleep(2)
                continue

def signal_handler(signum, frame):
    print(f"\n{Fore.YELLOW}Signal {signum} received. Initiating graceful shutdown...{Style.RESET_ALL}")
    raise KeyboardInterrupt("Received termination signal")

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    log = Logger()
    log.info("Starting WhatsApp Bot Application with auto-restart capability")
    log.info("Press Ctrl+C to stop the application gracefully")
    restart_count = 0
    max_restarts = 5

    while True:
        try:
            log.info(f"Initializing bot (attempt {restart_count + 1})")
            bot = WhatsAppBot()
            log.success("Bot initialized successfully, starting main loop")
            bot.run()
            
        except KeyboardInterrupt:
            log.warning("KeyboardInterrupt detected. Closing Chrome and exiting safely...")
            try:
                if 'bot' in locals():
                    bot.driver.quit()
            except Exception:
                pass
            log.info("Application terminated gracefully by user")
            break
            
        except Exception as e:
            restart_count += 1
            log.error(f"Unexpected error (attempt {restart_count}): {str(e)}")
            
            try:
                if 'bot' in locals():
                    bot.driver.quit()
            except Exception:
                pass
            
            if restart_count >= max_restarts:
                log.critical(f"Maximum restart attempts ({max_restarts}) reached. Exiting...")
                break
            
            wait_time = min(30, 5 * restart_count) 
            log.warning(f"Restarting in {wait_time} seconds... (attempt {restart_count}/{max_restarts})")
            
            for i in range(wait_time, 0, -1):
                if i % 10 == 0 or i <= 5: 
                    log.info(f"Restarting in {i} seconds...")
                time.sleep(1)
            log.info("Attempting to restart the bot...")

if __name__ == "__main__":
    main()