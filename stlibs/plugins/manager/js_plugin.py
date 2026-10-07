from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from ..api import PluginError

RUNTIME_JS = Path(__file__).with_name("runtime.js")
READY_TIMEOUT = 8.0
DEFAULT_TIMEOUT = 3.0


class NodeMissingError(PluginError):
    """找不到 node —— JS 插件直接标记为不可用，而不是静默失效。"""

def find_node() -> str | None:
    env = os.getenv("ADP_NODE") or os.getenv("NODE_EXE")
    if env and Path(env).is_file():
        return env

    found = shutil.which("node") or shutil.which("node.exe")
    if found:
        return found

    for candidate in (r"D:\nodejs\node.exe", "/usr/bin/node", "/usr/local/bin/node"):
        if Path(candidate).is_file():
            return candidate
    return None


class JsPluginProcess:
    """一个 JS 插件 = 一个 node 进程；hook 调用走 request/response。"""
    def __init__(self, manifest, api, timeout: float = DEFAULT_TIMEOUT, node: str | None = None):
        self.manifest = manifest
        self.api = api
        self.timeout = max(0.2, float(timeout))
        self.node = node or find_node()
        if not self.node:
            raise NodeMissingError("没找到 node，可执行文件路径可用环境变量 ADP_NODE 指定")

        self._lock = threading.RLock()
        self._responses: queue.Queue = queue.Queue()
        self._stderr: list[str] = []
        self._seq = 0
        self._closed = False

        env = dict(os.environ)
        env.setdefault("ADP_PLUGIN_ID", manifest.id)

        self.process = subprocess.Popen(
            # 入口要给绝对路径：cwd 已经是插件目录，相对路径会被 node 再拼一次
            [self.node, str(RUNTIME_JS.resolve()), str(manifest.entry_path.resolve())],
            cwd=str(manifest.path),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

        self._reader = threading.Thread(target=self._read_loop, name=f"plugin-js-{manifest.id}", daemon=True)
        self._reader.start()
        self._err_reader = threading.Thread(target=self._err_loop, name=f"plugin-js-err-{manifest.id}", daemon=True)
        self._err_reader.start()

        self._wait_ready()

    @property
    def alive(self) -> bool:
        return self.process.poll() is None and not self._closed

    def _err_loop(self):
        stream = self.process.stderr
        if stream is None:
            return
        for line in stream:
            line = line.rstrip()
            if line:
                self._stderr.append(line)

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr[-10:])

    def _read_loop(self):
        stream = self.process.stdout
        if stream is None:
            return
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            self._responses.put(message)
        self._responses.put({"type": "eof"})

    def _wait_ready(self, timeout: float = READY_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self._responses.get(timeout=0.1)
            except queue.Empty:
                if self.process.poll() is not None:
                    raise PluginError(f"node 进程退出（{self.process.returncode}）：{self.stderr_tail[:400]}")
                continue

            kind = message.get("type")
            if kind == "ready":
                return
            if kind == "fatal":
                raise PluginError(message.get("error") or "插件加载失败")
            if kind == "eof":
                raise PluginError(f"node 进程提前结束：{self.stderr_tail[:400]}")

        raise PluginError("等待插件就绪超时")

    def _send(self, payload: dict):
        if not self.alive:
            raise PluginError("插件进程已退出")
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        try:
            self.process.stdin.write(line)
            self.process.stdin.flush()
        except (BrokenPipeError, ValueError, OSError) as exc:
            raise PluginError(f"写入失败：{exc}") from exc

    def _read_response(self, request_id: int, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PluginError(f"插件 {timeout:.1f}s 没响应（已停用这个进程）")

            try:
                message = self._responses.get(timeout=min(0.2, remaining))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise PluginError(f"插件进程退出（{self.process.returncode}）：{self.stderr_tail[:400]}")
                continue

            kind = message.get("type")
            if kind == "api":
                self._handle_api_call(message)
                continue
            if kind == "eof":
                raise PluginError("插件进程结束了输出")
            if kind == "result" and message.get("id") == request_id:
                if message.get("error"):
                    raise PluginError(str(message["error"]).splitlines()[0][:400])
                return message

    def _handle_api_call(self, message: dict):
        api_id = message.get("id")
        method = str(message.get("method") or "")
        args = message.get("args") or []
        error = None
        result = None
        try:
            result = self.api.call(method, *(args if isinstance(args, list) else [args]))
            result = json.loads(json.dumps(result, ensure_ascii=False, default=str))
        except Exception as exc:  # noqa: BLE001 - 插件调错 API 不该带崩宿主
            error = f"{type(exc).__name__}: {exc}"
        self._send({"type": "api_result", "id": api_id, "result": result, "error": error})

    def call(self, hook: str, payload=None, timeout: float | None = None):
        with self._lock:
            self._seq += 1
            request_id = self._seq
            self._send({"type": "hook", "id": request_id, "hook": hook, "payload": payload})
            response = self._read_response(request_id, timeout or self.timeout)
            return response.get("value")

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if self.alive:
                    self._send({"type": "exit"})
            except PluginError:
                pass

            try:
                self.process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            finally:
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    try:
                        if stream is not None:
                            stream.close()
                    except OSError:
                        pass


class JsHooks:
    """JS 插件的 hook 表（转发给 node 子进程）。"""
    def __init__(self, process: JsPluginProcess):
        self.process = process

    def has(self, hook: str) -> bool:
        # 子进程里有没有实现要跑起来才知道，交给它自己判断（没实现返回 null）
        return True

    def call(self, hook: str, payload=None):
        return self.process.call(hook, payload)

    def close(self):
        self.process.close()


__all__ = ["DEFAULT_TIMEOUT", "JsHooks", "JsPluginProcess", "NodeMissingError", "find_node"]
