import json
import os

from dataclasses import dataclass


LIVE2D = "live2d"
STATIC = "static"
EMOTE = "emote"

LIVE2D_ROOT = "./resources/character/model"
STATIC_ROOT = "./resources/character/static"
EMOTE_ROOT = "./resources/character/emote"

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


@dataclass(frozen=True, slots=True)
class Character:
    kind: str
    name: str
    path: str
    label: str


def natural_key(value: str):
    """文件名自然排序键：2 排在 10 前面。"""
    import re

    parts = re.split(r"(\d+)", os.path.basename(str(value)))
    return [int(part) if part.isdigit() else part.casefold() for part in parts]


def _listdir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path), key=natural_key)
    except OSError:
        return []


def _has_live2d(path: str) -> bool:
    if os.path.isdir(os.path.join(path, "2")) or os.path.isdir(os.path.join(path, "3")):
        return True
    for name in _listdir(path):
        lowered = name.lower()
        if lowered.endswith(".model3.json") or lowered.endswith(".model.json"):
            return True
    return False


def _has_static(path: str) -> bool:
    for root, _dirs, files in os.walk(path):
        if any(os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS for name in files):
            return True
        if os.path.relpath(root, path).count(os.sep) >= 1:
            break
    for name in _listdir(path):
        sub = os.path.join(path, name)
        if not os.path.isdir(sub):
            continue
        if any(os.path.splitext(item)[1].lower() in IMAGE_EXTENSIONS for item in _listdir(sub)):
            return True
    return False


def _live2d_models() -> list[Character]:
    result = []
    for name in _listdir(LIVE2D_ROOT):
        path = os.path.join(LIVE2D_ROOT, name)
        if os.path.isdir(path) and _has_live2d(path):
            result.append(Character(LIVE2D, name, path, name))
    return result


def _static_models() -> list[Character]:
    result = []
    for name in _listdir(STATIC_ROOT):
        path = os.path.join(STATIC_ROOT, name)
        if os.path.isdir(path) and _has_static(path):
            result.append(Character(STATIC, name, path, name))
    return result


def _emote_models() -> list[Character]:
    try:
        from . import emote
    except Exception:  # noqa: BLE001 - 资源目录坏掉时只显示别的形象
        return []

    result = []
    for model in emote.discover_models():
        result.append(Character(EMOTE, model.name, model.directory, f"{model.name} · Emote"))
    return result


def discover() -> list[Character]:
    """列出三种形象；重名时给标签补类型。"""
    live2d = _live2d_models()
    static = _static_models()
    emote_models = _emote_models()

    names = [item.name for item in live2d + static]
    result = []
    for item in live2d + static:
        label = item.label
        if names.count(item.name) > 1:
            label = f"{item.name} · {'Live2D' if item.kind == LIVE2D else '静态'}"
        result.append(Character(item.kind, item.name, item.path, label))
    result.extend(emote_models)
    return result


def kind() -> str:
    """当前配置里的形象类型。"""
    from . import Config

    if str(getattr(Config, "model_emote", "") or "").strip():
        return EMOTE
    if str(getattr(Config, "model_live2d", "") or "").strip():
        return LIVE2D
    if str(getattr(Config, "static_model", "") or "").strip():
        return STATIC
    return LIVE2D


def current() -> Character | None:
    current_kind = kind()
    name = _name_for_kind(current_kind)
    if not name:
        return None
    for item in discover():
        if item.kind == current_kind and item.name == name:
            return item
    return Character(current_kind, name, _path_for_kind(current_kind, name), name)


def _name_for_kind(current_kind: str) -> str:
    from . import Config

    if current_kind == EMOTE:
        return str(getattr(Config, "model_emote", "") or "").strip()
    if current_kind == LIVE2D:
        return str(getattr(Config, "model_live2d", "") or "").strip()
    return str(getattr(Config, "static_model", "") or "").strip()


def _path_for_kind(current_kind: str, name: str) -> str:
    if current_kind == EMOTE:
        return os.path.join(EMOTE_ROOT, name)
    if current_kind == LIVE2D:
        return os.path.join(LIVE2D_ROOT, name)
    return os.path.join(STATIC_ROOT, name)


def resolve(label: str) -> Character | None:
    label = str(label or "").strip()
    if not label:
        return None
    for item in discover():
        if item.label == label or item.name == label:
            return item
    return None


def _set_model_fields(item: Character):
    from . import Config

    Config.model_live2d = item.name if item.kind == LIVE2D else ""
    Config.static_model = item.name if item.kind == STATIC else ""
    Config.model_emote = item.name if item.kind == EMOTE else ""


def select(label_or_name: str) -> Character | None:
    """按标签或名字切换形象并落盘。"""
    from . import Config, ConfigLoader, config_profiles

    item = resolve(label_or_name)
    if item is None:
        return None

    previous = kind()
    if previous != item.kind:
        ConfigLoader.save_config()

    _set_model_fields(item)
    profile = config_profiles.load(item.kind)
    base = config_profiles.live2d_size(Config.size)
    if profile:
        Config.opacity = profile.get('opacity', Config.opacity)
        Config.size = config_profiles.clamp_size(profile.get('size', config_profiles.default_size(item.kind, base)))
        Config.rotate = profile.get('rotate', Config.rotate)
    else:
        Config.size = config_profiles.default_size(item.kind, base)
    ConfigLoader.save_config()
    return item


def animation_path(current_kind: str | None = None) -> str:
    from . import ANIMATION_EMOTE_PATH, ANIMATION_LIVE2D_PATH, ANIMATION_STATIC_PATH

    current_kind = current_kind or kind()
    if current_kind == EMOTE:
        return ANIMATION_EMOTE_PATH
    if current_kind == STATIC:
        return ANIMATION_STATIC_PATH
    return ANIMATION_LIVE2D_PATH


def same_kind(label_or_name: str) -> bool:
    item = resolve(label_or_name)
    return item is not None and item.kind == kind()


def read_static_models() -> dict:
    try:
        with open("./resources/static.json", "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


__all__ = [
    "Character",
    "EMOTE",
    "EMOTE_ROOT",
    "IMAGE_EXTENSIONS",
    "LIVE2D",
    "LIVE2D_ROOT",
    "STATIC",
    "STATIC_ROOT",
    "animation_path",
    "current",
    "discover",
    "kind",
    "natural_key",
    "read_static_models",
    "resolve",
    "same_kind",
    "select",
]
