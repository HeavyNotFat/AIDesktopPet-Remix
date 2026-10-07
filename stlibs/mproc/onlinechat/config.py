import os
from pathlib import Path

from ... import Config, get_model_lists

HOST = os.getenv('ONLINECHAT_HOST', '127.0.0.1')
PORT = int(os.getenv('ONLINECHAT_PORT', '52493'))

WEB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resources/web/onlinechat"

ASSISTANT_NAME = Config.name if Config.name else Config.model_live2d

# 兼容旧接口：本地（Ollama）模型名快照。
# 新的调用方请用 ``registry.snapshot()``，它带 TTL、还包含云端模型。
MODELS = get_model_lists()

LLM_TIMEOUT = float(os.getenv('LLM_TIMEOUT', '120'))

# 一个会话空闲多久后被回收（秒）；<=0 表示不按时间回收
SESSION_TTL = float(os.getenv('WEBCHAT_SESSION_TTL', '1800'))
# 同时保留多少个会话实例（LRU 淘汰）
MAX_SESSIONS = int(os.getenv('WEBCHAT_MAX_SESSIONS', '8'))
# 模型列表缓存时间（秒）。刷新会跑一次 ``ollama list``（子进程），
# 所以别设太小：每次刷新都发生在请求线程里。
MODEL_LIST_TTL = float(os.getenv('WEBCHAT_MODEL_TTL', '30'))
# 单个请求最长处理时间（秒），用于反向代理/前端提示
REQUEST_TIMEOUT = float(os.getenv('WEBCHAT_REQUEST_TIMEOUT', str(LLM_TIMEOUT)))

# 附件：前端按 base64 上传，所以这里限的是 base64 字符数（约等于原始大小的 4/3）
MAX_ATTACHMENTS = int(os.getenv('WEBCHAT_MAX_ATTACHMENTS', '6'))
MAX_ATTACHMENT_CHARS = int(os.getenv('WEBCHAT_MAX_ATTACHMENT_CHARS', str(12 * 1024 * 1024)))
