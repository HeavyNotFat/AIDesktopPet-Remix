import os
from pathlib import Path

from ... import Config, get_model_lists

HOST = '127.0.0.1'
PORT = 52493

WEB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resources/web/onlinechat"

ASSISTANT_NAME = Config.name if Config.name else Config.model_live2d
MODELS = get_model_lists()

LLM_BASE_URL = os.getenv('LLM_BASE_URL', 'http://127.0.0.1:11434/v1')
LLM_TIMEOUT = float(os.getenv('LLM_TIMEOUT', '120'))
