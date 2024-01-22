import time
from io import BytesIO

from PIL import Image
from playwright.sync_api import sync_playwright

import os
import subprocess
import xml.etree.ElementTree as ET

from config import load_config
from utils import print_with_color


configs = load_config()

vimium_path = "./vimium-master"


from controller_abs import Controller
class ChromeController(Controller):
    def __init__(self, ):
        headless = configs['CHROME_HEADLESS']
        self.context = (
            sync_playwright()
            .start()
            .chromium.launch_persistent_context(
                "",
                headless=headless,
                args=[
                    f"--disable-extensions-except={vimium_path}",
                    f"--load-extension={vimium_path}",
                ],
                ignore_https_errors=True,
            )
        )

        self.size = {"width": 1080, "height": 720}
        self.page = self.context.new_page()
        self.page.set_viewport_size(self.size)
        
        self.screenshot_dir = configs["ANDROID_SCREENSHOT_DIR"]
        self.xml_dir = configs["ANDROID_XML_DIR"]
        self.navigate("https://www.google.com")
        
    def get_device_size(self):
        return self.size["width"], self.size["height"]

    def get_screenshot(self, prefix, save_dir, return_before=True):
        save_path = os.path.join(save_dir, prefix + ".png")
        image = self.capture(return_before=return_before)
        image.save(save_path)
        return save_path

    def capture(self, return_before=False):
        if return_before:
            screenshot_before = Image.open(BytesIO(self.page.screenshot())).convert("RGB")
            return screenshot_before
        # capture a screenshot with vim bindings on the screen
        self.page.keyboard.press("Escape")
        self.page.keyboard.type("f")

        screenshot = Image.open(BytesIO(self.page.screenshot())).convert("RGB")
        return screenshot

    def perform_action(self, action):
        if "done" in action:
            return True
        if "click" in action and "type" in action:
            self.click(action["click"])
            self.type(action["type"])
        if "navigate" in action:
            self.navigate(action["navigate"])
        elif "type" in action:
            self.type(action["type"])
        elif "click" in action:
            self.click(action["click"])

    def navigate(self, url):
        self.page.goto(url=url if "://" in url else "https://" + url, timeout=60000)

    def type(self, text):
        time.sleep(1)
        self.page.keyboard.type(text)
        self.page.keyboard.press("Enter")
        
    def scroll(self, direction):
        self.page.keyboard.press("Escape")
        self.page.keyboard.press("Escape")

    def click(self, text):
        self.page.keyboard.type(text)
        
