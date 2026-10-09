from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback

from ..api import PluginError
from ..manifest import PluginManifest


class PythonHooks:

    def __init__(self, target, module_name: str = "", plugin_api=None, path=None):
        self.target = target
        self.module_name = module_name
        self.api = plugin_api
        self.path = str(path) if path else None

        # 插件目录要一直留在 sys.path 里：入口之外的模块常是懒加载的
        if self.path:
            _keep_path(self.path)

    def has(self, hook: str) -> bool:
        return callable(getattr(self.target, hook, None))

    def call(self, hook: str, payload=None):
        handler = getattr(self.target, hook, None)
        if not callable(handler):
            return None
        return handler(*self._arguments(handler, payload))

    def _arguments(self, handler, payload) -> list:
        try:
            parameters = inspect.signature(handler).parameters.values()
        except (TypeError, ValueError):
            return [self.api, payload]

        wanted = [
            item for item in parameters
            if item.kind in (item.POSITIONAL_ONLY, item.POSITIONAL_OR_KEYWORD)
        ]
        args = []
        if len(wanted) >= 1:
            args.append(self.api)
        if len(wanted) >= 2:
            args.append(payload)
        return args

    def close(self):
        handler = getattr(self.target, "on_close", None)
        if callable(handler):
            try:
                handler()
            except Exception:  # noqa: BLE001 - 关闭钩子出错只记日志
                traceback.print_exc()
        if self.module_name:
            sys.modules.pop(self.module_name, None)
        if self.path:
            _drop_path(self.path)


def _keep_path(path: str):
    if path not in sys.path:
        sys.path.insert(0, path)


def _drop_path(path: str):
    try:
        sys.path.remove(path)
    except ValueError:
        pass


def load_hooks(manifest: PluginManifest, plugin_api) -> PythonHooks:
    """按入口文件导入插件并返回它的 hook 表。"""
    module_name = f"adp_plugin_{manifest.id.replace('-', '_').replace('.', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, manifest.entry_path)
    if spec is None or spec.loader is None:
        raise PluginError(f"无法导入：{manifest.entry_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    # 插件能 import 宿主模块，也能 import 同目录的兄弟模块
    _keep_path(str(manifest.path))
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001
        sys.modules.pop(module_name, None)
        _drop_path(str(manifest.path))
        raise PluginError(f"{type(exc).__name__}: {exc}") from exc

    target = getattr(module, "Plugin", None)
    target = target if target is not None else module
    if isinstance(target, type):
        target = target()
    return PythonHooks(target, module_name, plugin_api, path=manifest.path)


__all__ = ["PythonHooks", "load_hooks"]
