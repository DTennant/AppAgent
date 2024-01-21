import time
from io import BytesIO

from PIL import Image
from playwright.sync_api import sync_playwright

vimium_path = "./vimium-master"


from controller_abs import Controller
class ChromeController(Controller):
    def __init__(self, headless=False):
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
        
    def get_screenshot(self, prefix, save_dir):
        image = self.capture(return_before=True)


    def capture(self, return_before=False):
        if return_before:
            screenshot_before = Image.open(BytesIO(self.page.screenshot())).convert("RGB")
            return screenshot_before
        # capture a screenshot with vim bindings on the screen
        self.page.keyboard.press("Escape")
        self.page.keyboard.type("f")

        screenshot = Image.open(BytesIO(self.page.screenshot())).convert("RGB")
        return screenshot
