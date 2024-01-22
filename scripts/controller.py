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
from model import ask_gpt4v, parse_explore_rsp, parse_reflect_rsp, ask_gpt4v_azure
from utils import print_with_color, draw_bbox_multi, encode_image


def get_controller(controller_type):
    # Get the controller for the target app
    if controller_type == 'android':
        device_list = list_all_devices()
        if not device_list:
            print_with_color("ERROR: No device found!", "red")
            sys.exit()
        print_with_color(f"List of devices attached:\n{str(device_list)}", "yellow")
        if len(device_list) == 1:
            device = device_list[0]
            print_with_color(f"Device selected: {device}", "yellow")
        else:
            print_with_color("Please choose the Android device to start demo by entering its ID:", "blue")
            device = input()
        controller = AndroidController(device)
        width, height = controller.get_device_size()
        if not width and not height:
            print_with_color("ERROR: Invalid device size!", "red")
            sys.exit()
        print_with_color(f"Screen resolution of {device}: {width}x{height}", "yellow")
        return controller, width, height

    elif controller_type == 'chrome':
        controller = ChromeController()
        width, height = controller.get_device_size()
        return controller, width, height
