import json
import os
import re


SECRETS_DIR = './.env'
SECRETS_FILE = 'secrets.json'


def _path():
    return os.path.join(SECRETS_DIR, SECRETS_FILE)


def _env_name(alias: str) -> str:
    return 'ADP_API_KEY_' + re.sub(r'[^A-Za-z0-9]+', '_', str(alias)).strip('_').upper()


def load() -> dict:
    try:
        with open(_path(), 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {'models': {}}
    if not isinstance(data, dict):
        return {'models': {}}
    models = data.get('models')
    data['models'] = models if isinstance(models, dict) else {}
    return data


def _write(data: dict):
    os.makedirs(SECRETS_DIR, exist_ok=True)
    path = _path()
    temp = f'{path}.tmp'
    with open(temp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def model_keys() -> dict:
    keys = {}
    for alias, value in (load().get('models') or {}).items():
        if isinstance(value, str) and value.strip():
            keys[str(alias)] = value.strip()
    return keys


def sync_model_keys(keys: dict) -> bool:
    """把当前模型密钥写进 .env；失败时保留旧文件并返回 False。"""
    data = load()
    data['models'] = {str(alias): str(value) for alias, value in (keys or {}).items() if value}
    try:
        _write(data)
    except OSError as exc:
        print(f'[secrets] 写入 .env 失败：{exc}')
        return False
    return True


def _key_for(alias: str, keys: dict) -> str:
    value = keys.get(str(alias)) or os.getenv(_env_name(alias), '')
    return str(value).strip() if value else ''


def merge_models(models) -> dict:
    """把 .env / 环境变量里的 key 合并进模型表。"""
    keys = model_keys()
    result = {}
    for alias, parameters in (models or {}).items():
        item = dict(parameters) if isinstance(parameters, dict) else {}
        key = _key_for(alias, keys)
        if key:
            item['apikey'] = key
        result[alias] = item
    return result


def strip_models(models) -> dict:
    result = {}
    for alias, parameters in (models or {}).items():
        item = dict(parameters) if isinstance(parameters, dict) else {}
        item.pop('apikey', None)
        item.pop('api_key', None)
        result[alias] = item
    return result


__all__ = [
    'SECRETS_DIR', 'SECRETS_FILE', 'load', 'merge_models', 'model_keys', 'strip_models',
    'sync_model_keys',
]
