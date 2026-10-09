import os
from pathlib import Path

from ... import Config, get_model_lists

HOST = os.getenv('ONLINECHAT_HOST', '127.0.0.1')
PORT = int(os.getenv('ONLINECHAT_PORT', '52493'))

WEB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resources/web/onlinechat"

ASSISTANT_NAME = Config.name if Config.name else Config.model_live2d

# 兼容旧接口的本地模型名快照；新代码用 ``registry.snapshot()``
MODELS = get_model_lists()

LLM_TIMEOUT = float(os.getenv('LLM_TIMEOUT', '120'))

# 会话空闲多久回收（秒），<=0 表示不按时间回收
SESSION_TTL = float(os.getenv('WEBCHAT_SESSION_TTL', '1800'))
# 同时保留多少会话（LRU 淘汰）
MAX_SESSIONS = int(os.getenv('WEBCHAT_MAX_SESSIONS', '8'))
# 模型列表缓存秒数（刷新要跑一次 ``ollama list``，别设太小）
MODEL_LIST_TTL = float(os.getenv('WEBCHAT_MODEL_TTL', '30'))
# 单个请求最长处理时间（秒）
REQUEST_TIMEOUT = float(os.getenv('WEBCHAT_REQUEST_TIMEOUT', str(LLM_TIMEOUT)))

# 附件上限：前端按 base64 上传，限的是 base64 字符数
MAX_ATTACHMENTS = int(os.getenv('WEBCHAT_MAX_ATTACHMENTS', '6'))
MAX_ATTACHMENT_CHARS = int(os.getenv('WEBCHAT_MAX_ATTACHMENT_CHARS', str(12 * 1024 * 1024)))
