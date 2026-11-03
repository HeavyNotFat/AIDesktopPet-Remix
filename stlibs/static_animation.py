import json
import os
import shutil

from dataclasses import dataclass

from .character import IMAGE_EXTENSIONS, natural_key


ROOT = "./resources/character/static"
CONFIG_PATH = "./resources/static.json"


@dataclass(frozen=True, slots=True)
class StaticAnimation:
    model: str
    name: str
    frames: tuple[str, ...]
    fps: int = 12
    loop: bool = True
    op: str | None = None

    def public(self) -> dict:
        return {
            "model": self.model,
            "name": self.name,
            "frames": list(self.frames),
            "fps": self.fps,
            "loop": self.loop,
            "op": self.op,
        }


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_config(data: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    temp = f"{CONFIG_PATH}.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temp, CONFIG_PATH)


def _safe_name(value: str, label: str = "名字") -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError(f"{label}不能为空")
    if value in (".", "..") or any(ch in value for ch in '\\/:*?"<>|'):
        raise ValueError(f"{label}不能包含路径字符")
    return value


def list_models() -> list[str]:
    try:
        names = os.listdir(ROOT)
    except OSError:
        return []
    result = []
    for name in sorted(names, key=natural_key):
        if name.startswith("."):
            continue
        if not os.path.isdir(os.path.join(ROOT, name)):
            continue
        if _has_images(os.path.join(ROOT, name)):
            result.append(name)
    return result


def _has_images(path: str) -> bool:
    for _root, _dirs, files in os.walk(path):
        if any(os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS for name in files):
            return True
    return False


def _frame_paths(model: str, animation: str, entry: dict) -> tuple[str, ...]:
    folder = os.path.join(ROOT, model, animation)
    frames = entry.get("frames") if isinstance(entry, dict) else None
    if not isinstance(frames, list) or not frames:
        return ()

    explicit = any(os.path.splitext(str(item))[1].lower() in IMAGE_EXTENSIONS for item in frames)
    result = []
    if explicit:
        for item in frames:
            path = os.path.join(folder, str(item))
            if os.path.isfile(path):
                result.append(path)
        return tuple(result)

    for prefix in frames:
        prefix = str(prefix)
        matched = []
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for filename in names:
            name, ext = os.path.splitext(filename)
            if ext.lower() not in IMAGE_EXTENSIONS or not name.startswith(prefix):
                continue
            tail = name[len(prefix):]
            if tail.isdigit():
                matched.append((int(tail), filename))
        matched.sort(key=lambda item: item[0])
        result.extend(os.path.join(folder, filename) for _index, filename in matched)
    return tuple(result)


def list_animations(model: str) -> list[StaticAnimation]:
    config = _load_config().get(model) or {}
    result = []
    if not isinstance(config, dict):
        return result
    for name, entry in config.items():
        if not isinstance(entry, dict):
            continue
        frames = _frame_paths(model, name, entry)
        if not frames:
            continue
        fps = entry.get("fps", 12)
        try:
            fps = max(1, int(fps))
        except (TypeError, ValueError):
            fps = 12
        result.append(StaticAnimation(model, name, frames, fps, bool(entry.get("loop", True)),
                                      entry.get("op")))
    return result


def find_animation(model: str, name: str) -> StaticAnimation | None:
    for animation in list_animations(model):
        if animation.name == name:
            return animation
    return None


def sort_paths(paths: list[str]) -> list[str]:
    return sorted((str(path) for path in paths), key=natural_key)


def _unique_filename(used: set[str], filename: str) -> str:
    stem, ext = os.path.splitext(os.path.basename(filename))
    candidate = f"{stem}{ext}"
    index = 2
    while candidate.casefold() in used:
        candidate = f"{stem}_{index}{ext}"
        index += 1
    used.add(candidate.casefold())
    return candidate


def import_images(model: str, animation: str, paths: list[str], fps: int = 12,
                  loop: bool = True, overwrite: bool = False) -> StaticAnimation:
    """按文件名排序复制一组图片，并登记成一个动画。"""
    model = _safe_name(model, "形象名")
    animation = _safe_name(animation, "动画名")
    fps = max(1, int(fps))

    source_paths = sort_paths(paths)
    if not source_paths:
        raise ValueError("没有选择图片")
    for path in source_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        if os.path.splitext(path)[1].lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"不支持的图片格式：{path}")

    folder = os.path.join(ROOT, model, animation)
    if os.path.isdir(folder):
        if not overwrite:
            raise FileExistsError(f"动画已存在：{model}/{animation}")
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)

    used: set[str] = set()
    copied = []
    for path in source_paths:
        filename = _unique_filename(used, path)
        shutil.copy2(path, os.path.join(folder, filename))
        copied.append(filename)

    config = _load_config()
    model_config = config.get(model)
    if not isinstance(model_config, dict):
        model_config = {}
        config[model] = model_config
    model_config[animation] = {
        "frames": copied,
        "op": None,
        "fps": fps,
        "loop": bool(loop),
    }
    _save_config(config)
    return StaticAnimation(model, animation, tuple(os.path.join(folder, name) for name in copied),
                           fps, bool(loop), None)


def remove_animation(model: str, animation: str) -> bool:
    model = _safe_name(model, "形象名")
    animation = _safe_name(animation, "动画名")
    config = _load_config()
    model_config = config.get(model)
    removed = False
    if isinstance(model_config, dict) and animation in model_config:
        model_config.pop(animation, None)
        if not model_config:
            config.pop(model, None)
        _save_config(config)
        removed = True

    folder = os.path.join(ROOT, model, animation)
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
        removed = True
    return removed


def rename_animation(model: str, old: str, new: str) -> StaticAnimation:
    model = _safe_name(model, "形象名")
    old = _safe_name(old, "旧动画名")
    new = _safe_name(new, "新动画名")
    if old == new:
        animation = find_animation(model, old)
        if animation is None:
            raise KeyError(old)
        return animation

    config = _load_config()
    model_config = config.get(model)
    if not isinstance(model_config, dict) or old not in model_config:
        raise KeyError(old)
    if new in model_config or os.path.exists(os.path.join(ROOT, model, new)):
        raise FileExistsError(new)

    old_folder = os.path.join(ROOT, model, old)
    new_folder = os.path.join(ROOT, model, new)
    if os.path.isdir(old_folder):
        os.rename(old_folder, new_folder)

    model_config[new] = model_config.pop(old)
    _save_config(config)
    animation = find_animation(model, new)
    if animation is None:
        raise KeyError(new)
    return animation


def create_model(name: str) -> str:
    name = _safe_name(name, "形象名")
    os.makedirs(os.path.join(ROOT, name), exist_ok=True)
    return name


def refresh_sharing_data():
    """重新读 static.json，让运行中的静态形象拿到新动画。"""
    try:
        from . import SharingData, Config, reload_static_models

        reload_static_models()
        ui = getattr(SharingData, "mainloop_ui", None)
        if ui is not None and hasattr(ui, "reload_animations"):
            ui.reload_animations(Config.static_model)
    except Exception:  # noqa: BLE001 - 设置页刷新失败不该崩
        pass


__all__ = [
    "CONFIG_PATH",
    "ROOT",
    "StaticAnimation",
    "create_model",
    "find_animation",
    "import_images",
    "list_animations",
    "list_models",
    "refresh_sharing_data",
    "remove_animation",
    "rename_animation",
    "sort_paths",
]
