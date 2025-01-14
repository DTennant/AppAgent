import re
import json
import requests
from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential


client = AzureOpenAI(
    azure_endpoint="https://openai-vlaa-westus.openai.azure.com/",  # west us
    # api_key="70c5b839665e4e6a8cd27876e1aa6d51",  # east us 2
    api_key="0276e5b9e7fe497294c347fafaa6ad4b",  # west us
    api_version="2023-05-15",
)
def _log_when_fail(retry_state):
    print(
        "Request failed. Current retry attempts:{}. Sleep for {:.2f}. Exception: {}".format(
            retry_state.attempt_number, retry_state.idle_for, repr(
                retry_state.outcome.exception())
        )
    )


generate_with_retry = retry(
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_attempt(15),
    before_sleep=_log_when_fail
)(client.chat.completions.create)


from config import load_config
from utils import print_with_color

configs = load_config()

def ask_gpt4v_azure(content):
    temp = configs['TEMPERATURE']
    max_tokens = configs['MAX_TOKENS']
    # response = client.chat.completions.create(
    response = generate_with_retry(
        model="gpt-4-vision-preview",
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        max_tokens=max_tokens,
        temperature=temp,
    )
    response_json = json.loads(response.json())
    if "error" not in response_json:
        usage = response_json["usage"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        print_with_color(
            f"Request cost is "
            f"${'{0:.2f}'.format(prompt_tokens / 1000 * 0.01 + completion_tokens / 1000 * 0.03)}",
            "yellow",
        )
    return response_json

def ask_gpt4v(content):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {configs['OPENAI_API_KEY']}",
    }
    payload = {
        "model": configs["OPENAI_API_MODEL"],
        "messages": [{"role": "user", "content": content}],
        "temperature": configs["TEMPERATURE"],
        "max_tokens": configs["MAX_TOKENS"],
    }
    response = requests.post(configs["OPENAI_API_BASE"], headers=headers, json=payload)
    if "error" not in response.json():
        usage = response.json()["usage"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        print_with_color(
            f"Request cost is "
            f"${'{0:.2f}'.format(prompt_tokens / 1000 * 0.01 + completion_tokens / 1000 * 0.03)}",
            "yellow",
        )
    return response.json()


def parse_explore_rsp(rsp):
    try:
        msg = rsp["choices"][0]["message"]["content"]
        observation = re.findall(r"Observation: (.*?)$", msg, re.MULTILINE)[0]
        think = re.findall(r"Thought: (.*?)$", msg, re.MULTILINE)[0]
        act = re.findall(r"Action: (.*?)$", msg, re.MULTILINE)[0]
        last_act = re.findall(r"Summary: (.*?)$", msg, re.MULTILINE)[0]
        print_with_color("Observation:", "yellow")
        print_with_color(observation, "magenta")
        print_with_color("Thought:", "yellow")
        print_with_color(think, "magenta")
        print_with_color("Action:", "yellow")
        print_with_color(act, "magenta")
        print_with_color("Summary:", "yellow")
        print_with_color(last_act, "magenta")
        if "FINISH" in act:
            return ["FINISH"]
        act_name = act.split("(")[0]
        if act_name == "tap":
            area = int(re.findall(r"tap\((.*?)\)", act)[0])
            return [act_name, area, last_act]
        elif act_name == "text":
            input_str = re.findall(r"text\((.*?)\)", act)[0][1:-1]
            return [act_name, input_str, last_act]
        elif act_name == "long_press":
            area = int(re.findall(r"long_press\((.*?)\)", act)[0])
            return [act_name, area, last_act]
        elif act_name == "swipe":
            params = re.findall(r"swipe\((.*?)\)", act)[0]
            area, swipe_dir, dist = params.split(",")
            area = int(area)
            swipe_dir = swipe_dir.strip()[1:-1]
            dist = dist.strip()[1:-1]
            return [act_name, area, swipe_dir, dist, last_act]
        elif act_name == "grid":
            return [act_name]
        else:
            print_with_color(f"ERROR: Undefined act {act_name}!", "red")
            return ["ERROR"]
    except Exception as e:
        print_with_color(
            f"ERROR: an exception occurs while parsing the model response: {e}", "red"
        )
        print_with_color(rsp, "red")
        return ["ERROR"]
    
def parse_chrome_rsp(rsp):
    try:
        msg = rsp["choices"][0]["message"]["content"]
        observation = re.findall(r"Observation: (.*?)$", msg, re.MULTILINE)[0]
        think = re.findall(r"Thought: (.*?)$", msg, re.MULTILINE)[0]
        act = re.findall(r"Action: (.*?)$", msg, re.MULTILINE)[0]
        last_act = re.findall(r"Summary: (.*?)$", msg, re.MULTILINE)[0]
        print_with_color("Observation:", "yellow")
        print_with_color(observation, "magenta")
        print_with_color("Thought:", "yellow")
        print_with_color(think, "magenta")
        print_with_color("Action:", "yellow")
        print_with_color(act, "magenta")
        print_with_color("Summary:", "yellow")
        print_with_color(last_act, "magenta")
        
        if 'FINISH' in act:
            return ['FINISH']
        act_name = act.split('(')[0]
        if act_name == 'navigate':
            url = re.findall(r"navigate\((.*?)\)", act)[0][1:-1]
            return [act_name, url, last_act]
        elif act_name == 'click':
            area = str(re.findall(r"click\((.*?)\)", act)[0])
            return [act_name, area, last_act]
        elif act_name == 'click_type':
            __import__("ipdb").set_trace()
            area, input_str = re.findall(r"click_type\((.*?),\s*\"(.*?)\"\)", act)[0]
            return [act_name, area, input_str, last_act]
        elif act_name == 'enter':
            return [act_name, last_act]
        elif act_name == 'scroll':
            direction = re.findall(r"scroll\((.*?)\)", act)[0]
            return [act_name, direction, last_act]
        else:
            print_with_color(f"ERROR: Undefined act {act_name}!", "red")
            return ['ERROR']

    except Exception as e:
        print_with_color(
            f"ERROR: an exception occurs while parsing the model response: {e}", "red"
        )
        print_with_color(rsp, "red")
        return ["ERROR"]


def parse_grid_rsp(rsp):
    try:
        msg = rsp["choices"][0]["message"]["content"]
        observation = re.findall(r"Observation: (.*?)$", msg, re.MULTILINE)[0]
        think = re.findall(r"Thought: (.*?)$", msg, re.MULTILINE)[0]
        act = re.findall(r"Action: (.*?)$", msg, re.MULTILINE)[0]
        last_act = re.findall(r"Summary: (.*?)$", msg, re.MULTILINE)[0]
        print_with_color("Observation:", "yellow")
        print_with_color(observation, "magenta")
        print_with_color("Thought:", "yellow")
        print_with_color(think, "magenta")
        print_with_color("Action:", "yellow")
        print_with_color(act, "magenta")
        print_with_color("Summary:", "yellow")
        print_with_color(last_act, "magenta")
        if "FINISH" in act:
            return ["FINISH"]
        act_name = act.split("(")[0]
        if act_name == "tap":
            params = re.findall(r"tap\((.*?)\)", act)[0].split(",")
            area = int(params[0].strip())
            subarea = params[1].strip()[1:-1]
            return [act_name + "_grid", area, subarea, last_act]
        elif act_name == "long_press":
            params = re.findall(r"long_press\((.*?)\)", act)[0].split(",")
            area = int(params[0].strip())
            subarea = params[1].strip()[1:-1]
            return [act_name + "_grid", area, subarea, last_act]
        elif act_name == "swipe":
            params = re.findall(r"swipe\((.*?)\)", act)[0].split(",")
            start_area = int(params[0].strip())
            start_subarea = params[1].strip()[1:-1]
            end_area = int(params[2].strip())
            end_subarea = params[3].strip()[1:-1]
            return [
                act_name + "_grid",
                start_area,
                start_subarea,
                end_area,
                end_subarea,
                last_act,
            ]
        elif act_name == "grid":
            return [act_name]
        else:
            print_with_color(f"ERROR: Undefined act {act_name}!", "red")
            return ["ERROR"]
    except Exception as e:
        print_with_color(
            f"ERROR: an exception occurs while parsing the model response: {e}", "red"
        )
        print_with_color(rsp, "red")
        return ["ERROR"]


def parse_reflect_rsp(rsp):
    try:
        msg = rsp["choices"][0]["message"]["content"]
        decision = re.findall(r"Decision: (.*?)$", msg, re.MULTILINE)[0]
        think = re.findall(r"Thought: (.*?)$", msg, re.MULTILINE)[0]
        print_with_color("Decision:", "yellow")
        print_with_color(decision, "magenta")
        print_with_color("Thought:", "yellow")
        print_with_color(think, "magenta")
        if decision == "INEFFECTIVE":
            return [decision, think]
        elif decision == "BACK" or decision == "CONTINUE" or decision == "SUCCESS":
            doc = re.findall(r"Documentation: (.*?)$", msg, re.MULTILINE)[0]
            print_with_color("Documentation:", "yellow")
            print_with_color(doc, "magenta")
            return [decision, think, doc]
        else:
            print_with_color(f"ERROR: Undefined decision {decision}!", "red")
            return ["ERROR"]
    except Exception as e:
        print_with_color(
            f"ERROR: an exception occurs while parsing the model response: {e}", "red"
        )
        print_with_color(rsp, "red")
        return ["ERROR"]
