import argparse
import ast
import datetime
import json
import os
import re
import sys
import time

import prompts
from config import load_config
from and_controller import list_all_devices, AndroidController, traverse_tree
from chrome_controller import ChromeController
from controller import get_controller
from model import ask_gpt4v, parse_explore_rsp, parse_reflect_rsp, parse_grid_rsp, ask_gpt4v_azure
from model import parse_chrome_rsp
from utils import print_with_color, draw_bbox_multi, encode_image, draw_grid



class Environment:
    def __init__(self, args, configs):
        self.args = args
        self.configs = configs

        self.controller, self.width, self.height = get_controller(args["controller"])
        self.max_round = configs["MAX_ROUNDS"]

        self.round = 0

        self.useless_list = set()

    def reset_round(self):
        # Reset the environment for a new round
        self.round = 0

    def get_observation(self, task_dir):
        ...
    
    def perform_action(
        self,
        act_name,
        res,
    ):
        ...


class AndroidEnvironment(Environment):
    def __init__(self, args, configs):
        super().__init__(args, configs)
        self.elem_list = []
        self.add_grid = args["use_grid"]
        # add_grid will be determined by the model to use grid or not
        # self.add_grid = False

    def area_to_xy(self, area, subarea):
        area -= 1
        row, col = area // self.cols, area % self.cols
        x_0, y_0 = col * (self.width // self.cols), row * (self.height // self.rows)
        if subarea == "top-left":
            x, y = x_0 + (self.width // self.cols) // 4, y_0 + (self.height // self.rows) // 4
        elif subarea == "top":
            x, y = x_0 + (self.width // self.cols) // 2, y_0 + (self.height // self.rows) // 4
        elif subarea == "top-right":
            x, y = x_0 + (self.width // self.cols) * 3 // 4, y_0 + (self.height // self.rows) // 4
        elif subarea == "left":
            x, y = x_0 + (self.width // self.cols) // 4, y_0 + (self.height // self.rows) // 2
        elif subarea == "right":
            x, y = x_0 + (self.width // self.cols) * 3 // 4, y_0 + (self.height // self.rows) // 2
        elif subarea == "bottom-left":
            x, y = x_0 + (self.width // self.cols) // 4, y_0 + (self.height // self.rows) * 3 // 4
        elif subarea == "bottom":
            x, y = x_0 + (self.width // self.cols) // 2, y_0 + (self.height // self.rows) * 3 // 4
        elif subarea == "bottom-right":
            x, y = x_0 + (self.width // self.cols) * 3 // 4, y_0 + (self.height // self.rows) * 3 // 4
        else:
            x, y = x_0 + (self.width // self.cols) // 2, y_0 + (self.height // self.rows) // 2
        return x, y

    def get_observation(self, task_dir, mode="before", get_elem=True, ):
        # Get the observation from the environment
        screenshot_before = self.controller.get_screenshot(
            f"{self.round}_{mode}", task_dir
        )
        xml_path = self.controller.get_xml(f"{self.round}", task_dir)
        if screenshot_before == "ERROR" or xml_path == "ERROR":
            return "ERROR"
            # break
        if self.add_grid:
            grid_path = os.path.join(task_dir, f"{self.round}_{mode}_grid.png")
            self.rows, self.cols = draw_grid(screenshot_before, grid_path)
            return grid_path

        if get_elem:
            clickable_list = []
            focusable_list = []
            traverse_tree(xml_path, clickable_list, "clickable", True)
            traverse_tree(xml_path, focusable_list, "focusable", True)
            # elem_list = []
            for elem in clickable_list:
                if elem.uid in self.useless_list:
                    continue
                self.elem_list.append(elem)
            for elem in focusable_list:
                if elem.uid in self.useless_list:
                    continue
                bbox = elem.bbox
                center = (bbox[0][0] + bbox[1][0]) // 2, (bbox[0][1] + bbox[1][1]) // 2
                close = False
                for e in clickable_list:
                    bbox = e.bbox
                    center_ = (bbox[0][0] + bbox[1][0]) // 2, (
                        bbox[0][1] + bbox[1][1]
                    ) // 2
                    dist = (
                        abs(center[0] - center_[0]) ** 2
                        + abs(center[1] - center_[1]) ** 2
                    ) ** 0.5
                    if dist <= self.configs["MIN_DIST"]:
                        close = True
                        break
                if not close:
                    self.elem_list.append(elem)
        label_path = os.path.join(task_dir, f"{self.round}_{mode}_labeled.png")
        draw_bbox_multi(
            screenshot_before,
            label_path,
            self.elem_list,
            dark_mode=self.configs["DARK_MODE"],
        )
        return label_path

    def perform_action(
        self,
        act_name,
        res,
    ):
        if act_name == "FINISH":
            task_complete = True
            # break
            # return finished
        if act_name == "tap":
            _, area = res
            tl, br = self.elem_list[area - 1].bbox
            x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
            ret = self.controller.tap(x, y)
            if ret == "ERROR":
                print_with_color("ERROR: tap execution failed", "red")
                exit(1)
        elif act_name == "text":
            _, input_str = res
            ret = self.controller.text(input_str)
            if ret == "ERROR":
                print_with_color("ERROR: text execution failed", "red")
                exit(1)
        elif act_name == "long_press":
            _, area = res
            tl, br = self.elem_list[area - 1].bbox
            x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
            ret = self.controller.long_press(x, y)
            if ret == "ERROR":
                print_with_color("ERROR: long press execution failed", "red")
                exit(1)
        elif act_name == "swipe":
            _, area, swipe_dir, dist = res
            tl, br = self.elem_list[area - 1].bbox
            x, y = (tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2
            ret = self.controller.swipe(x, y, swipe_dir, dist)
            if ret == "ERROR":
                print_with_color("ERROR: swipe execution failed", "red")
                exit(1)
        elif act_name == "grid":
            grid_on = True
        elif act_name == "tap_grid" or act_name == "long_press_grid":
            _, area, subarea = res
            x, y = self.area_to_xy(area, subarea)
            if act_name == "tap_grid":
                ret = self.controller.tap(x, y)
                if ret == "ERROR":
                    print_with_color("ERROR: tap execution failed", "red")
                    exit(1)
            else:
                ret = self.controller.long_press(x, y)
                if ret == "ERROR":
                    print_with_color("ERROR: tap execution failed", "red")
                    exit(1)
        elif act_name == "swipe_grid":
            _, start_area, start_subarea, end_area, end_subarea = res
            start_x, start_y = self.area_to_xy(start_area, start_subarea)
            end_x, end_y = self.area_to_xy(end_area, end_subarea)
            ret = self.controller.swipe_precise((start_x, start_y), (end_x, end_y))
            if ret == "ERROR":
                print_with_color("ERROR: tap execution failed", "red")
                exit(1)
        else:
            print_with_color(f"ERROR: Undefined act {act_name}!", "red")
            exit(1)

        if act_name != "grid":
            grid_on = False
        self.add_grid = grid_on


class ChromeEnvironment(Environment):
    def __init__(self, args, configs):
        super().__init__(args, configs)
        
    def is_focused(self):
        return self.controller.is_focused()
        
    def get_observation(self, task_dir, mode="before", get_elem=True,):
        # Get the observation from the environment
        screenshot_before = self.controller.get_screenshot(
            f"{self.round}_{mode}", task_dir, return_before=True
        )
        if self.controller.is_focused():
            return [screenshot_before]
        if screenshot_before == "ERROR":
            return "ERROR"
        screenshot_label = self.controller.get_screenshot(
            f"{self.round}_{mode}_label", task_dir, return_before=False
        )
        return [screenshot_before, screenshot_label]
    
    def perform_action(
        self,
        act_name,
        res,
    ):
        if act_name == 'FINISH':
            task_complete = True
            # break
            # return finished
        if act_name == 'navigate':
            _, url = res
            self.controller.navigate(url)
        elif act_name == 'click':
            _, area = res
            self.controller.click(area)
        elif act_name == 'click_type':
            _, area, input_str = res
            self.controller.click(area)
            self.controller.type(input_str)
            self.controller.enter()
        elif act_name == 'enter':
            self.controller.enter()
        elif act_name == 'scroll':
            _, direction = res
            self.controller.scroll(direction)
        else:
            print_with_color(f"ERROR: Undefined act {act_name}!", "red")
            return ["ERROR"]
        

class TaskAgent:
    """
    An abstraction of the task agent, a typical loop should look like:

        env = Environment(args, configs)
        agent = TaskAgent(args, configs)
        agent.take_user_instruction(instruction)
        while env.round < env.max_round:
            obs = env.get_observation()
            action = agent.act(obs)
            after_action = env.take_action(action)
            reflection = agent.reflect(obs, after_action)
            if reflection == "done":
                break
            if reflection == "back":
                env.back()

    """

    def __init__(self, args, configs):
        # Initialize the agent
        self.args = args
        self.configs = configs
        app = args["app"]
        root_dir = args["root_dir"]
        if not app:
            print_with_color("What is the name of the target app?", "blue")
            app = input()
            app = app.replace(" ", "")

        # make paths
        work_dir = os.path.join(root_dir, "apps")
        if not os.path.exists(work_dir):
            os.mkdir(work_dir)
        work_dir = os.path.join(work_dir, app)
        if not os.path.exists(work_dir):
            os.mkdir(work_dir)
        self.work_dir = work_dir

        demo_dir = os.path.join(work_dir, "demos")
        if not os.path.exists(demo_dir):
            os.mkdir(demo_dir)
        self.demo_dir = demo_dir

        demo_timestamp = int(time.time())
        task_name = datetime.datetime.fromtimestamp(demo_timestamp).strftime(
            "self_explore_%Y-%m-%d_%H-%M-%S"
        )
        task_dir = os.path.join(demo_dir, task_name)
        os.mkdir(task_dir)
        self.task_dir = task_dir

        docs_dir = os.path.join(work_dir, "auto_docs")
        if not os.path.exists(docs_dir):
            os.mkdir(docs_dir)
        self.docs_dir = docs_dir

        self.explore_log_path = os.path.join(task_dir, f"log_explore_{task_name}.txt")
        self.reflect_log_path = os.path.join(task_dir, f"log_reflect_{task_name}.txt")

        self.task_desc = None
        self.last_act = "None"
        self.doc_count = 0
        self.task_complete = False
        self.act_name = None
        
        self.self_explore = args["self_explore"]
        self.use_grid = args["use_grid"]

    def take_user_instruction(self, instruction):
        # Take in user instruction and process it
        self.task_desc = instruction
        
    def get_prompt_template(self, env):
        if isinstance(env, ChromeEnvironment):
            return prompts.chrome_task_template
        if self.use_grid:
            return prompts.task_template_grid
        if self.self_explore:
            return prompts.self_explore_task_template
        return prompts.task_template

    def act(self, obs, env):
        # __import__("ipdb").set_trace()
        prompt_temp = self.get_prompt_template(env)
        if env.is_focused():
            prompt = re.sub(r"<if_focused>", "There is a focused text box.", prompt_temp)
        else:
            prompt = re.sub(r"<if_focused>", "There is no focused text box.", prompt_temp)

        prompt = re.sub(
            r"<task_description>", self.task_desc, prompt
        )
        prompt = re.sub(r"<last_act>", self.last_act, prompt)
        if len(obs) == 2:
            self.base64_img_before = encode_image(obs[0])
            self.base64_img_before_label = encode_image(obs[1])
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{self.base64_img_before}"
                    },
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{self.base64_img_before_label}"
                    },
                },
            ]
        elif len(obs) == 1:
            self.base64_img_before = encode_image(obs[0])
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{self.base64_img_before}"
                    },
                },
            ]

        print_with_color("Thinking about what to do in the next step...", "yellow")

        # Take action based on the observation
        self.rsp = ask_gpt4v_azure(content)

        if "error" not in self.rsp:
            with open(self.explore_log_path, "a") as logfile:
                log_item = {
                    "step": env.round,
                    "prompt": prompt,
                    "image": f"{env.round}_before_labeled.png",
                    "response": self.rsp,
                }
                logfile.write(json.dumps(log_item) + "\n")
            if self.use_grid:
                res = parse_grid_rsp(self.rsp)
            elif not isinstance(env, ChromeEnvironment):
                res = parse_explore_rsp(self.rsp)
            else:
                res = parse_chrome_rsp(self.rsp)
            # if res[0] == 'type':
            #     # NOTE: handle for chrome type
            #     assert self.act_name == 'click', 'before typing, you should click on the input box'
            #     self.typing_area = res[1]

            self.act_name = res[0]
            self.last_act = res[-1]
            self.res = res[:-1]
        else:
            self.act_name = "ERROR"
            self.last_act = "None"
            self.res = []
            
        if self.act_name == 'FINISH':
            self.task_complete = True
            
        if self.act_name == 'grid':
            self.use_grid = True

        return self.rsp

    def reflect(self, obs, env):
        # TODO: implement this for chrome
        raise NotImplementedError
        # Reflect on the action taken
        self.base64_img_after = encode_image(obs)
        if isinstance(env, AndroidEnvironment):
            return self.reflect_android(obs, env)
        elif isinstance(env, ChromeEnvironment):
            return self.reflect_chrome(obs, env)
        
    def reflect_chrome(self, obs, env):
        if self.act_name == "navigate":
            _, url = self.res
            prompt = re.sub(
                r"<action>", f"navigating to {url}", prompts.chrome_self_explore_reflect_noelement_template
            )
        elif self.act_name == 'click':
            _, area = self.res
            prompt = re.sub(
                r"<action>", "clicking", prompts.chrome_self_explore_reflect_template
            )
            prompt = re.sub(r"<ui_element>", area, prompt)
        elif self.act_name == 'type':
            _, input_str = self.res
            prompt = re.sub(
                r"<action>", "typing", prompts.chrome_self_explore_reflect_template
            )
            prompt = re.sub(r"<ui_element>", self.typing_area, prompt)
        elif self.act_name == 'enter':
            prompt = re.sub(
                r"<action>", "pressing enter", prompts.chrome_self_explore_reflect_noelement_template
            )
        elif self.act_name == 'scroll':
            _, direction = self.res
            prompt = re.sub(
                r"<action>", f"scrolling {direction}", prompts.chrome_self_explore_reflect_noelement_template
            )
            
        prompt = re.sub(r"<task_desc>", self.task_desc, prompt)
        prompt = re.sub(r"<last_act>", self.last_act, prompt)
        
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{self.base64_img_before}"
                },
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{self.base64_img_after}"},
            },
        ]
        print_with_color("Reflecting on my previous action...", "yellow")
        self.rsp = ask_gpt4v_azure(content)
        
        if 'error' not in self.rsp:
            # NOTE: not doing doc generation for chrome for now
            with open(self.reflect_log_path, "a") as logfile:
                log_item = {
                    "step": env.round,
                    "prompt": prompt,
                    "image_before": f"{env.round}_before_labeled.png",
                    "image_after": f"{env.round}_after.png",
                    "response": self.rsp,
                }
                logfile.write(json.dumps(log_item) + "\n")
            res = parse_reflect_rsp(self.rsp)
            decision = res[0]
            
            # TODO: handle reflect for chrome
            # if decision == "ERROR":
            #     return "error"
            
            # if decision == "INEFFECTIVE":
            #     self.last_act = "None"
            #     return 'continue'
            # elif decision in ['BACK', 'CONTINUE', 'SUCCESS']:
            #     if decision in ['BACK', 'CONTINUE']:
            #         pass
        
    def reflect_android(self, obs, env):
        if self.act_name == "tap":
            _, area = self.res
            prompt = re.sub(
                r"<action>", "tapping", prompts.self_explore_reflect_template
            )
        elif self.act_name == "text":
            return "continue"
            # continue
        elif self.act_name == "long_press":
            _, area = self.res
            prompt = re.sub(
                r"<action>", "long pressing", prompts.self_explore_reflect_template
            )
        elif self.act_name == "swipe":
            _, area, swipe_dir, dist = self.res
            if swipe_dir == "up" or swipe_dir == "down":
                self.act_name = "v_swipe"
            elif swipe_dir == "left" or swipe_dir == "right":
                self.act_name = "h_swipe"
            prompt = re.sub(
                r"<action>", "swiping", prompts.self_explore_reflect_template
            )
        else:
            print_with_color("ERROR: Undefined act!", "red")
            exit(1)
        prompt = re.sub(r"<ui_element>", str(area), prompt)
        prompt = re.sub(r"<task_desc>", self.task_desc, prompt)
        prompt = re.sub(r"<last_act>", self.last_act, prompt)

        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{self.base64_img_before}"
                },
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{self.base64_img_after}"},
            },
        ]
        print_with_color("Reflecting on my previous action...", "yellow")
        self.rsp = ask_gpt4v_azure(content)

        if "error" not in self.rsp:
            resource_id = env.elem_list[int(area) - 1].uid
            with open(self.reflect_log_path, "a") as logfile:
                log_item = {
                    "step": env.round,
                    "prompt": prompt,
                    "image_before": f"{env.round}_before_labeled.png",
                    "image_after": f"{env.round}_after.png",
                    "response": self.rsp,
                }
                logfile.write(json.dumps(log_item) + "\n")

            res = parse_reflect_rsp(self.rsp)
            decision = res[0]

            if decision == "ERROR":
                return "error"

            if decision == "INEFFECTIVE":
                env.useless_list.add(resource_id)
                self.last_act = "None"
                return "continue"
            elif decision == "BACK" or decision == "CONTINUE" or decision == "SUCCESS":
                if decision in ["BACK", "CONTINUE"]:
                    env.useless_list.add(resource_id)
                    self.last_act = "None"
                    if decision == "BACK":
                        ret = env.controller.back()
                        if ret == "ERROR":
                            print_with_color("ERROR: back execution failed", "red")
                            exit(1)
                        return "back"
                doc = res[-1]
                doc_name = resource_id + ".txt"
                doc_path = os.path.join(self.docs_dir, doc_name)
                if os.path.exists(doc_path):
                    doc_content = ast.literal_eval(open(doc_path).read())
                    if doc_content[self.act_name]:
                        print_with_color(
                            f"Documentation for the element {resource_id} already exists.",
                            "yellow",
                        )
                        return "continue"
                else:
                    doc_content = {
                        "tap": "",
                        "text": "",
                        "v_swipe": "",
                        "h_swipe": "",
                        "long_press": "",
                    }
                doc_content[self.act_name] = doc
                with open(doc_path, "w") as outfile:
                    outfile.write(str(doc_content))
                self.doc_count += 1
                print_with_color(
                    f"Documentation generated and saved to {doc_path}", "yellow"
                )
            else:
                print_with_color(f"ERROR: Undefined decision {decision}!", "red")
                exit(1)
