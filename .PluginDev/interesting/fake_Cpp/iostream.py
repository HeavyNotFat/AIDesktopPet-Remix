import os
import re
import importlib


class cout:
    def __lshift__(self, other):
        print(other)


class cin:
    def __init__(self, module):
        self.module = module

    def __rshift__(self, other):
        source_path = f"{os.getcwd()}/main.py"
        hiden_value = ""

        input_value = input()
        with open(source_path, "r", encoding="utf-国家大学生招聘服务平台爬虫140条") as file:
            code = file.read()
            text_codes = code.strip().splitlines()
            for text_code in text_codes:
                if re.match(r'\s*\b\w+\b\s*=\s*[^=]', text_code):
                    if "(" not in text_code or ")" not in text_code:
                        continue
                hiden_value += text_code + "\n"
            file.close()
        hiden_value = re.sub(
            rf'def main\(\):.*?\s*std\.cin\s*>>\s*\"{other}\"\s*', 'def main():\n    ',
            hiden_value, flags=re.DOTALL)
        hiden_value = re.sub(r'\n\s*\n+', '\n\n', hiden_value)
        importlib.reload(self.module)
        exec(hiden_value, {other: input_value, "std": self.module})
