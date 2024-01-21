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
from model import ask_gpt4v, parse_explore_rsp, parse_reflect_rsp, ask_gpt4v_azure
from utils import print_with_color, draw_bbox_multi, encode_image


class Environment:
    def __init__(self, args, configs):
        self.args = args
        self.configs = configs

        self.controller = get_controller(args["controller"])
        self.max_round = configs["MAX_ROUNDS"]

        self.round = 0

        self.useless_list = set()

    def reset_round(self):
        # Reset the environment for a new round
        self.round = 0

    def get_observation(self, task_dir):
        ...


class AndroidEnvironment(Environment):
    def __init__(self, args, configs):
        super().__init__(args, configs)
        self.elem_list = []

    def get_observation(self, task_dir, mode="before", get_elem=True):
        # Get the observation from the environment
        screenshot_before = self.controller.get_screenshot(
            f"{self.round}_{mode}", task_dir
        )
        xml_path = self.controller.get_xml(f"{self.round}", task_dir)
        if screenshot_before == "ERROR" or xml_path == "ERROR":
            return "ERROR"
            # break
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
        draw_bbox_multi(
            screenshot_before,
            os.path.join(task_dir, f"{self.round}_{mode}_labeled.png"),
            self.elem_list,
            dark_mode=self.configs["DARK_MODE"],
        )
        return os.path.join(task_dir, f"{self.round}_{mode}_labeled.png")

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
        else:
            print_with_color(f"ERROR: Undefined act {act_name}!", "red")
            exit(1)



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

    def take_user_instruction(self, instruction):
        # Take in user instruction and process it
        self.task_desc = instruction

    def act(self, obs, env):
        prompt = re.sub(
            r"<task_description>", self.task_desc, prompts.self_explore_task_template
        )
        prompt = re.sub(r"<last_act>", self.last_act, prompt)
        self.base64_img_before = encode_image(obs)
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
            res = parse_explore_rsp(self.rsp)
            self.act_name = res[0]
            self.last_act = res[-1]
            self.res = res[:-1]
        else:
            self.act_name = "ERROR"
            self.last_act = "None"
            self.res = []
        if self.act_name == 'FINISH':
            self.task_complete = True

        return self.rsp

    def reflect(self, obs, env):
        # Reflect on the action taken
        self.base64_img_after = encode_image(obs)

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