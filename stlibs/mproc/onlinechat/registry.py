from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Iterable

from ... import Config, get_model_lists
from .config import MODEL_LIST_TTL

#: 云端模型 id 前缀
CLOUD_PREFIX = "api::"

BACKEND_LOCAL = "local"
BACKEND_CLOUD = "cloud"


class UnknownModelError(KeyError):
    """请求的模型不在注册表里。"""

    def __init__(self, value: str, known: Iterable[str] = ()):
        self.value = value
        self.known = list(known)
        super().__init__(value)

    def __str__(self) -> str:
        known = "、".join(self.known) if self.known else "（无可用模型）"
        return f"未知模型：{self.value}；可用模型：{known}"


@dataclass(frozen=True, slots=True)
class ModelTarget:
    """一次网页请求要用到的后端调用描述。"""

    value: str
    label: str
    backend: str
    model: str
    api_key: str | None = None
    base_url: str | None = None

    @property
    def is_cloud(self) -> bool:
        return self.backend == BACKEND_CLOUD

    def public(self) -> dict[str, str]:
        """返回给前端的结构（``api.js`` 的 ``normalizeModel`` 认 label/value）。"""
        return {"value": self.value, "label": self.label, "backend": self.backend}


def load_targets() -> "OrderedDict[str, ModelTarget]":
    """读取当前可用的模型，本地模型在前、云端模型在后。"""
    targets: "OrderedDict[str, ModelTarget]" = OrderedDict()

    for name in get_model_lists():
        if not name:
            continue
        targets[name] = ModelTarget(
            value=name,
            label=name,
            backend=BACKEND_LOCAL,
            model=name,
        )

    for alias, parameters in (Config.models or {}).items():
        if not isinstance(parameters, dict):
            continue
        parameters = dict(parameters)
        value = f"{CLOUD_PREFIX}{alias}"
        actual = parameters.get("name") or alias
        targets[value] = ModelTarget(
            value=value,
            label=f"{alias} (API)",
            backend=BACKEND_CLOUD,
            model=actual,
            api_key=parameters.get("apikey"),
            base_url=parameters.get("baseurl"),
        )

    return targets


class ModelRegistry:
    """带 TTL 的模型注册表，线程安全。"""

    def __init__(self, ttl: float = 5.0, provider: Callable[[], dict] | None = None):
        self._ttl = max(0.0, float(ttl))
        self._provider = provider or load_targets
        self._lock = threading.RLock()
        self._targets: "OrderedDict[str, ModelTarget]" = OrderedDict()
        self._loaded_at = 0.0

    def refresh(self) -> "OrderedDict[str, ModelTarget]":
        targets = OrderedDict(self._provider())
        with self._lock:
            self._targets = targets
            self._loaded_at = time.monotonic()
        return targets

    def snapshot(self) -> "OrderedDict[str, ModelTarget]":
        """返回当前快照，必要时触发一次刷新。"""
        with self._lock:
            stale = not self._targets or (time.monotonic() - self._loaded_at) > self._ttl
        if stale:
            # 刷新失败（例如 Ollama 没起来）不应该让整个接口 500，
            # 保留上一次可用快照即可。
            try:
                self.refresh()
            except Exception:  # noqa: BLE001 - 注册表降级，保留旧快照
                pass
        with self._lock:
            return OrderedDict(self._targets)

    def get(self, value: str) -> ModelTarget | None:
        return self.snapshot().get(value)

    def resolve(self, value: str) -> ModelTarget:
        """解析模型 id，找不到时抛 :class:`UnknownModelError`。"""
        targets = self.snapshot()
        target = targets.get(value)
        if target is None:
            raise UnknownModelError(value, targets.keys())
        return target


#: 进程级默认注册表，路由直接用它
registry = ModelRegistry(ttl=MODEL_LIST_TTL)
