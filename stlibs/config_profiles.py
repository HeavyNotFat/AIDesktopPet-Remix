import json
import os


KINDS = ('live2d', 'static', 'emote')
SIZE_RATIOS = {'live2d': 1.0, 'static': 0.70, 'emote': 0.25}


def profile_root() -> str:
    from . import CONFIG_PATH

    return os.path.join(os.path.dirname(CONFIG_PATH), 'config')


def profile_path(kind: str) -> str:
    return os.path.join(profile_root(), f'{kind}.json')


def load(kind: str) -> dict:
    try:
        with open(profile_path(kind), 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(kind: str, model: str, opacity, size, rotate) -> dict:
    root = profile_root()
    os.makedirs(root, exist_ok=True)
    data = {
        'model': str(model or ''),
        'opacity': opacity,
        'size': int(size),
        'rotate': int(rotate),
    }
    path = profile_path(kind)
    temp = f'{path}.tmp'
    with open(temp, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp, path)
    return data


def kind_from(data: dict) -> str:
    if str((data or {}).get('model_emote') or '').strip():
        return 'emote'
    if str((data or {}).get('model_live2d') or '').strip():
        return 'live2d'
    if str((data or {}).get('static_model') or '').strip():
        return 'static'
    return 'live2d'


def clamp_size(value) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        value = 100
    return max(10, min(110, value))


def default_size(kind: str, base_size=110) -> int:
    base = clamp_size(base_size)
    return max(10, min(110, int(round(base * SIZE_RATIOS.get(kind, 1.0)))))


def live2d_size(fallback=110) -> int:
    value = load('live2d').get('size')
    return clamp_size(value if value is not None else fallback)


__all__ = [
    'KINDS', 'SIZE_RATIOS', 'clamp_size', 'default_size', 'kind_from', 'live2d_size',
    'load', 'profile_path', 'profile_root', 'save',
]
