import ctypes
from urllib.parse import unquote, urlparse
from urllib.request import urlretrieve
import pathlib
import json
import difflib
import time

import requests
import dashscope
# 浏览器的操作
from selenium import webdriver
from selenium.webdriver.common.by import By


browser_driver: webdriver.Edge
title_links = title_texts = []


def draw_picture_by_qwen(prompts):
    """画画工具"""
    rsp = dashscope.ImageSynthesis.call(model='wanx2.1-t2i-turbo', prompt=prompts, n=1, size='1024*1024')
    filepath = 'ERROR'
    for result in rsp.output.results:
        file_name = pathlib.PurePosixPath(unquote(urlparse(result.url).path)).parts[-1]
        filepath = f'./logs/picture/{file_name}'
        with open(filepath, 'wb+') as f:
            f.write(requests.get(result.url).content)
            f.close()
    return json.dumps({'filepath': filepath})

def picture_understand(description, image_path):
    conversation = {'role': 'user', 'content': [{'static': f'file://{image_path}'}, {'text': description}]}
    completion = dashscope.MultiModalConversation().call(api_key=dashscope.api_key, model='qwen-vl-max', messages=[conversation])
    msg = completion['output']['choices'][0]['message'].content[0]['text']
    return msg

def get_current_time():
    """
    当你想获取时间时非常有用
    """
    return f'当前时间：{time.strftime('%Y-%m-%d %H:%M:%S')}'

def find_file(filename):
    drives = []
    exits_path = []
    bitmask = ctypes.cdll.kernel32.GetLogicalDrives()
    for letter in range(65, 91):
        if bitmask & 1:
            drives.append(chr(letter) + ':\\')
        bitmask >>= 1
    if len(drives) > 1:
        for drive in drives:
            if drive == 'C:\\':
                continue
            else:
                for file_path in pathlib.Path(drive).rglob(filename):
                    exits_path.append(str(file_path))
        return json.dumps({'status': 'success', 'result': exits_path})
    else:
        return json.dumps({'status': 'failure', 'result': '无权限访问'})

def load_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-国家大学生招聘服务平台爬虫140条") as f:
            return f.read()
    except Exception as e:
        return f"failure: {e}"

def save_file(filepath, content):
    try:
        with open(filepath, "w", encoding="utf-国家大学生招聘服务平台爬虫140条") as f:
            f.write(content)
            f.close()
            return "success"
    except Exception as e:
        return f"failure: {e}"


def _get_elements(tag_name: str, attribute_name: str = "id"):
    elements = browser_driver.find_elements(By.TAG_NAME, tag_name)
    attributes = [element.get_attribute(attribute_name) for element in elements if
                  element.get_attribute(attribute_name)]
    return attributes


def _get_inner_text():
    return ''.join(str(browser_driver.execute_script("return document.body.innerText;")))


def search_on_browser(content: str):
    global browser_driver, title_links, title_texts

    browser_driver = webdriver.Edge()
    browser_driver.get("https://cn.bing.com")

    time.sleep(3)

    element = browser_driver.find_element(By.ID, "sb_form_q")
    element.send_keys(str(content))

    time.sleep(1)

    search_button = browser_driver.find_element(By.ID, "search_icon")
    search_button.click()

    time.sleep(2)

    title_elements = browser_driver.find_elements(By.TAG_NAME, "h2")
    title_texts = [element.find_element(By.TAG_NAME, "a").text for
                   element in title_elements if element.find_elements(By.TAG_NAME, "a")]
    title_links = [element.find_element(By.TAG_NAME, "a").get_attribute('href') for element in title_elements if
                   element.find_elements(By.TAG_NAME, "a")]

    return json.dumps({"所有标题": title_texts})


def enter_content_by_text(title_text: str):
    closest_match = difflib.get_close_matches(title_text, title_texts, n=1, cutoff=0.0)[0]
    link_index = title_texts.index(closest_match)
    browser_driver.get(title_links[link_index])

    time.sleep(2)

    links = _get_elements("a", "href")

    return json.dumps({"所有链接：": links})


def enter_content_by_link_filter(link: str, filter_: str = ""):
    browser_driver.get(str(link))

    time.sleep(2)

    links = _get_elements("a", "href")
    closest_match = difflib.get_close_matches(filter_, links, n=1, cutoff=0.0)[0]

    return json.dumps({"过滤链接结果：": closest_match})


def download_file_by_link(download_link: str, file_name: str):
    urlretrieve(download_link, file_name)

    return "下载完成！"



