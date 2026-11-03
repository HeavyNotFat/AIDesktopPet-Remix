import json
import os
import shutil
import zipfile

from dataclasses import dataclass, field
from pathlib import Path

from ..character import natural_key


ROOT = "./resources/character/emote"
SOUNDS_ROOT = os.path.join(ROOT, "sounds")
RUNTIME_ROOT = "./resources/emote/runtime"
MODEL_SUFFIXES = (".psb.zip", ".psb", ".zip")
CONFIG_NAMES = ("config.js", "emote.json")


@dataclass(frozen=True, slots=True)
class EmoteModel:
    name: str
    directory: str
    model_file: str
    config_file: str = ""
    entry_url: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def model_name(self) -> str:
        return os.path.basename(self.model_file)

    @property
    def is_zip(self) -> bool:
        return self.model_file.lower().endswith(".zip")

    @property
    def config_url(self) -> str:
        return "config.js" if self.config_file else ""

    @property
    def sounds_dir(self) -> str:
        return os.path.join(self.directory, "sounds")

    def public(self) -> dict:
        return {
            "name": self.name,
            "model": self.model_name,
            "config": bool(self.config_file),
            "metadata": self.metadata,
        }


def read_metadata(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _find_model(directory: str, metadata: dict) -> str:
    wanted = str(metadata.get("model") or "").strip()
    if wanted:
        path = os.path.join(directory, wanted)
        if os.path.isfile(path):
            return path

    files = []
    try:
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if os.path.isfile(path) and name.lower().endswith(MODEL_SUFFIXES):
                files.append(path)
    except OSError:
        return ""
    files.sort(key=natural_key)
    return files[0] if files else ""


def _find_config(directory: str, metadata: dict) -> str:
    wanted = str(metadata.get("config") or "").strip()
    if wanted:
        path = os.path.join(directory, wanted)
        if os.path.isfile(path):
            return path
    for name in CONFIG_NAMES:
        path = os.path.join(directory, name)
        if os.path.isfile(path) and name != "emote.json":
            return path
    return ""


def load_model(directory: str) -> EmoteModel | None:
    name = os.path.basename(os.path.normpath(directory))
    metadata = read_metadata(os.path.join(directory, "emote.json"))
    model_file = _find_model(directory, metadata)
    if not model_file:
        return None
    config_file = _find_config(directory, metadata)
    return EmoteModel(name=name, directory=directory, model_file=model_file,
                      config_file=config_file, metadata=metadata)


def discover_models() -> list[EmoteModel]:
    result = []
    try:
        names = sorted(os.listdir(ROOT), key=natural_key)
    except OSError:
        return result

    for name in names:
        if name.startswith(".") or name == "sounds":
            continue
        directory = os.path.join(ROOT, name)
        if not os.path.isdir(directory):
            continue
        model = load_model(directory)
        if model is not None:
            result.append(model)
    return result


def find_model(name: str) -> EmoteModel | None:
    name = str(name or "").strip()
    if not name:
        return None
    for model in discover_models():
        if model.name == name:
            return model
    return None


def _unique_dir(name: str) -> str:
    base = os.path.join(ROOT, name)
    if not os.path.exists(base):
        return base
    index = 2
    while os.path.exists(f"{base}-{index}"):
        index += 1
    return f"{base}-{index}"


def _extract_companions(archive: str, target: str):
    try:
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                name = info.filename.replace("\\", "/")
                if info.is_dir():
                    continue
                if name.endswith("/"):
                    continue
                if os.path.basename(name) not in ("config.js", "emote.json"):
                    continue
                destination = os.path.join(target, os.path.basename(name))
                with bundle.open(info) as source, open(destination, "wb") as output:
                    shutil.copyfileobj(source, output)
    except (OSError, zipfile.BadZipFile):
        return


def import_model(source: str, name: str | None = None) -> EmoteModel:
    """把一个 .psb / .psb.zip 复制进形象目录。"""
    source = os.path.abspath(os.path.expanduser(str(source or "")))
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    if not source.lower().endswith(MODEL_SUFFIXES):
        raise ValueError("只支持 .psb / .psb.zip / .zip")

    stem = str(name or "").strip()
    if not stem:
        stem = Path(source).name
        for suffix in MODEL_SUFFIXES:
            if stem.lower().endswith(suffix):
                stem = stem[: -len(suffix)]
                break
    stem = "".join(ch for ch in stem if ch not in '\\/:*?"<>|').strip() or "emote"

    target = _unique_dir(stem)
    os.makedirs(target, exist_ok=True)
    destination = os.path.join(target, os.path.basename(source))
    shutil.copy2(source, destination)

    if source.lower().endswith(".zip"):
        _extract_companions(source, target)

    metadata = read_metadata(os.path.join(target, "emote.json"))
    if not metadata:
        metadata = {"model": os.path.basename(destination)}
        with open(os.path.join(target, "emote.json"), "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)

    model = load_model(target)
    if model is None:
        raise ValueError("导入后没有找到可用的 PSB 文件")
    return model


def remove_model(name: str) -> bool:
    model = find_model(name)
    if model is None:
        return False
    shutil.rmtree(model.directory, ignore_errors=True)
    return True


def ensure_directories():
    os.makedirs(ROOT, exist_ok=True)
    os.makedirs(SOUNDS_ROOT, exist_ok=True)
    os.makedirs(RUNTIME_ROOT, exist_ok=True)


def runtime_file(name: str) -> str:
    return os.path.join(RUNTIME_ROOT, name)


def model_url(name: str, filename: str | None = None) -> str:
    model = find_model(name)
    if model is None:
        return ""
    filename = filename or model.model_name
    return f"model/{model.name}/{filename}"


def sounds_url(path: str) -> str:
    return f"sounds/{path.lstrip('./')}"


def bootstrap(model: EmoteModel, size: int, opacity: float, rotate: int, render_ratio: float,
              tracking_interval: int) -> dict:
    metadata = model.metadata or {}
    scale = metadata.get("scale", 1.0)
    try:
        scale = float(scale)
    except (TypeError, ValueError):
        scale = 1.0
    return {
        "name": model.name,
        "modelUrl": model_url(model.name, model.model_name),
        "configUrl": f"model/{model.name}/config.js" if model.config_file else "",
        "renderRatio": max(0.5, min(3.0, float(render_ratio or 1.0))),
        "trackingInterval": max(20, int(tracking_interval or 50)),
        "scale": max(0.05, min(3.0, scale)),
        "sizePercent": max(10, min(200, int(size or 100))),
        "opacity": max(0.0, min(1.0, float(opacity or 1.0))),
        "rotation": float(rotate or 0),
        "offset": metadata.get("offset") or [0, 0],
        "audioRoot": "sounds/",
        "hasConfig": bool(model.config_file),
    }


__all__ = [
    "CONFIG_NAMES",
    "EmoteModel",
    "MODEL_SUFFIXES",
    "ROOT",
    "RUNTIME_ROOT",
    "SOUNDS_ROOT",
    "bootstrap",
    "discover_models",
    "ensure_directories",
    "find_model",
    "import_model",
    "load_model",
    "model_url",
    "read_metadata",
    "remove_model",
    "runtime_file",
    "sounds_url",
]
