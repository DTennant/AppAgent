import argparse
import json
import ast
import os, re, sys
import time

import prompts
from config import load_config
from and_controller import list_all_devices, AndroidController, traverse_tree
from model import ask_gpt4v, parse_explore_rsp, parse_reflect_rsp, ask_gpt4v_azure
from utils import print_with_color, draw_bbox_multi, encode_image
from task_agent import TaskAgent, AndroidEnvironment, ChromeEnvironment

arg_desc = "AppAgent - Autonomous Exploration"
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=arg_desc)
parser.add_argument("--app")
parser.add_argument("--controller", default="android")
parser.add_argument("--use_grid", action='store_true')
parser.add_argument("--self-explore", default=True, type=ast.literal_eval)
parser.add_argument("--root_dir", default="./")
args = vars(parser.parse_args())

__import__("ipdb").set_trace()
configs = load_config()

agent = TaskAgent(args, configs)
if args['controller'] == 'android':
    env = AndroidEnvironment(args, configs)
elif args['controller'] == 'chrome':
    env = ChromeEnvironment(args, configs)
else:
    raise NotImplementedError

print_with_color("Please enter the description of the task you want me to complete in a few sentences:", "blue")
task_desc = 'find the weather report of london in the next week. Also please call grid() on the first call.'
agent.take_user_instruction(task_desc)


while env.round < env.max_round:
    env.round += 1
    print_with_color(f"Round {env.round}", "yellow")

    # observe env
    screenshot_before = env.get_observation(agent.task_dir)

    rsp = agent.act(screenshot_before, env)
    if agent.act_name == "ERROR":
        print_with_color(rsp["error"]["message"], "red")
        break
    if agent.act_name == 'FINISH':
        break
    
    env.perform_action(agent.act_name, agent.res)
    
    screenshot_after = env.get_observation(agent.task_dir, mode='after', get_elem=False)
    agent.reflect(screenshot_after, env)

    time.sleep(configs["REQUEST_INTERVAL"])

if agent.task_complete:
    print_with_color(f"Autonomous exploration completed successfully. {agent.doc_count} docs generated.", "yellow")
elif env.round == env.max_round:
    print_with_color(f"Autonomous exploration finished due to reaching max rounds. {agent.doc_count} docs generated.",
                     "yellow")
else:
    print_with_color(f"Autonomous exploration finished unexpectedly. {agent.doc_count} docs generated.", "red")
