import json
import re
import urllib.error
import urllib.request

from . import config


class LLMError(Exception):
    pass


THINK_BLOCK = re.compile(r'<think>.*?</think>', re.DOTALL)


def generate(model: str, question: str) -> str:
    url = config.LLM_BASE_URL.rstrip('/') + '/chat/completions'
    payload = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': question}],
        'stream': False,
    }).encode('utf-8')

    headers = {'Content-Type': 'application/json'}
    if config.LLM_API_KEY:
        headers['Authorization'] = 'Bearer ' + config.LLM_API_KEY

    request = urllib.request.Request(url, data=payload, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(request, timeout=config.LLM_TIMEOUT) as response:
            body = response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:300]
        raise LLMError(f'上游模型服务返回 {e.code}：{detail}')
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f'无法连接上游模型服务 {config.LLM_BASE_URL}：{e}')

    try:
        content = json.loads(body)['choices'][0]['message']['content']
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError('上游模型服务返回了无法识别的格式')

    answer = THINK_BLOCK.sub('', content or '').strip()
    return answer or '（模型返回了空内容）'