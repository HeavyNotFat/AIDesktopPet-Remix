import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest

import stlibs
from stlibs.plugins import PluginManager
from stlibs.plugins.manager.js_plugin import find_node

NODE = find_node()
needs_node = pytest.mark.skipif(NODE is None, reason="需要 node 才能跑 JavaScript 插件")
PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugins" / "ugc_hub"
CHECK_SCRIPT = Path(__file__).resolve().parent / "ugc_client_check.js"
PAGE_KEY = "ugc"
PAGE_TITLE = "UGC 素材站"
SECTIONS = ["素材站", "账号", "查找素材", "下载", "上传", "维护"]
DEFAULT_SERVER = "https://adp.cqjszx.cn"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """别把测试用的开关与插件数据写进仓库。"""
    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    monkeypatch.setattr(stlibs.Config, "plugins", {
        "enable": True, "directory": str(tmp_path / "plugins"),
        "disabled": [], "settings": {}, "timeout": 5.0,
    }, raising=False)
    return stlibs.Config


@pytest.fixture
def sandbox(tmp_path):
    """把仓库里真实的 ugc_hub 插件拷到临时目录再加载。"""
    directory = tmp_path / "plugins"
    directory.mkdir()
    shutil.copytree(PLUGIN_DIR, directory / "ugc_hub")
    return directory


@pytest.fixture
def manager(sandbox):
    instance = PluginManager(directory=str(sandbox))
    instance.discover()
    return instance


def page_map(manager):
    return {page["key"]: page for page in manager.settings_pages()}


def flat_rows(manager, key):
    """页面里的行（含 section 里的子行），拉平成一个列表。"""
    rows = []
    for row in page_map(manager)[key]["form"]:
        if row["type"] == "section":
            rows.extend(row["rows"])
        else:
            rows.append(row)
    return rows


def rows_of(manager, key):
    return {row["key"] or row["action"]: row for row in flat_rows(manager, key)}


def controls(manager, key, kind="button"):
    return sorted(row["action"] for row in flat_rows(manager, key) if row["type"] == kind)


def maps_of(manager, key):
    """页面里的 map 行，拉平成 {行标题: {名称: 值}}。"""
    result = {}
    for row in page_map(manager)[key]["form"]:
        if row["type"] == "map":
            result[row["label"] or row["text"]] = {item["key"]: item["value"] for item in row["items"]}
    return result


def sections_of(manager, key):
    return {row["label"] or row["text"]: row for row in page_map(manager)[key]["form"] if row["type"] == "section"}


def write_task(sandbox, payload):
    data_dir = sandbox / ".data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "ugc_hub-task.json").write_text(json.dumps(payload), encoding="utf-8")


@needs_node
def test_one_page_is_the_only_ui_entry(manager):
    """按要求：不注入右键菜单、不注册聊天命令，导航栏里只有一页。"""
    infos = manager.load_all()
    info = [item for item in infos if item.manifest.id == "ugc_hub"][0]
    assert info.loaded, info.error
    assert manager.menu_items() == []
    assert manager.commands() == {}
    pages = page_map(manager)
    assert list(pages) == [PAGE_KEY], "一个插件只占导航栏一条"
    assert pages[PAGE_KEY]["title"] == PAGE_TITLE, "标题里已经带插件名，不再加前缀"


@needs_node
def test_page_is_sections_in_order_with_a_status_map(manager):
    manager.load_all()
    page = page_map(manager)[PAGE_KEY]
    kinds = [row["type"] for row in page["form"]]
    assert kinds[0] == "map", "第一块是状态映射"
    assert kinds[1:7] == ["section"] * 6, "其余是六个分区"
    assert [row["label"] for row in page["form"] if row["type"] == "section"] == SECTIONS
    assert all(row["type"] != "hint" or row["text"] for row in page["form"])

    status = maps_of(manager, PAGE_KEY)["状态"]
    assert status["素材站"] == DEFAULT_SERVER, "默认地址就是 https://adp.cqjszx.cn"
    assert status["账号"] is None and status["本次任务"] == "还没跑过任务"

    sections = sections_of(manager, PAGE_KEY)
    assert sections["素材站"]["columns"] == 2
    assert sections["查找素材"]["columns"] == 3
    assert sections["下载"]["columns"] == 2
    assert sections["维护"]["columns"] == 3


@needs_node
def test_rows_and_buttons_live_in_their_sections(manager):
    manager.load_all()
    rows = rows_of(manager, PAGE_KEY)

    assert rows["server_url"]["type"] == "text" and rows["server_url"]["span"] == 2
    assert rows["download_dir"]["type"] == "text" and rows["download_dir"]["span"] == 2
    assert rows["keyword"]["type"] == "text" and rows["keyword"]["span"] == 2
    assert rows["browse_kind"]["type"] == "select"
    assert rows["sort"]["type"] == "select"
    assert rows["page_size"]["type"] == "number"
    assert rows["pick"]["type"] == "select"
    assert [option["value"] for option in rows["pick"]["options"]] == [""], "没有列表时给一个占位项"
    assert rows["username"]["type"] == "text" and rows["password"]["type"] == "password"
    for key in ("threads", "timeout_seconds"):
        assert rows[key]["type"] == "number", key
    for key in ("overwrite", "verify_sha256", "unzip_after_download", "keep_zip", "notify_when_done"):
        assert rows[key]["type"] == "switch", key
    assert rows["upload_kind"]["type"] == "select" and rows["upload_license"]["type"] == "select"
    assert rows["upload_path"]["span"] == 2

    assert controls(manager, PAGE_KEY) == [
        "clear_items", "clear_password", "clear_status", "download", "login",
        "logout", "open_dir", "ping", "refresh", "register", "search", "status", "upload",
    ]
    node_hint = [row for row in sections_of(manager, PAGE_KEY)["维护"]["rows"] if row["type"] == "hint"][0]
    assert "node" in node_hint["text"] and node_hint["span"] == 3


@needs_node
def test_actions_without_input_only_answer(manager):
    """没填地址 / 没选素材 / 没填路径时，按钮只给提示，不发请求。"""
    manager.load_all()
    assert manager.settings_action("ugc_hub", PAGE_KEY, "download") == "先在「下载」分区选一个素材"
    assert manager.settings_action("ugc_hub", PAGE_KEY, "upload") == "先填要上传的文件完整路径"
    assert manager.settings_action("ugc_hub", PAGE_KEY, "login") == "用户名和密码都要填"
    assert manager.settings_action("ugc_hub", PAGE_KEY, "clear_password") == "密码框已清空"
    assert manager.settings_action("ugc_hub", PAGE_KEY, "clear_status") == "任务状态已清空"
    assert "http" not in str(manager.settings_action("ugc_hub", PAGE_KEY, "open_dir"))


@needs_node
def test_upload_guards_on_missing_file_and_logout_clears_token(manager, sandbox):
    manager.load_all()
    manager.set_setting("ugc_hub", "upload_path", "D:/肯定不存在的文件.zip")
    assert manager.settings_action("ugc_hub", PAGE_KEY, "upload").startswith("找不到文件：")
    data = sandbox / ".data"
    data.mkdir(exist_ok=True)
    (data / "ugc_hub.json").write_text(json.dumps({"token": "t" * 30, "username": "alice"}), encoding="utf-8")
    manager.settings_action("ugc_hub", PAGE_KEY, "logout")
    stored = json.loads((data / "ugc_hub.json").read_text(encoding="utf-8"))
    assert stored["token"] == "" and stored["username"] == ""


@needs_node
def test_finished_list_job_shows_up_in_the_page(manager, sandbox):
    """后台任务写完状态文件后，页面（含下拉框）要能看到素材列表。"""
    manager.load_all()
    write_task(sandbox, {
        "action": "list",
        "task_id": "t1",
        "state": "done",
        "message": "共 2 条，取回 2 条",
        "progress": {"done": 2, "total": 2},
        "result": {
            "total": 2,
            "items": [
                {"id": "7", "name": "日和", "kind": "live2d", "size": 1363149, "downloads": 3},
                {"id": "8", "name": "猫猫", "kind": "static", "size": 20480, "downloads": 0},
            ],
        },
        "updated_at": int(time.time()),
    })
    assert manager.emit_event("chat_finished") is None

    status = maps_of(manager, PAGE_KEY)["状态"]
    assert status["本次任务"] == "共 2 条，取回 2 条"
    assert status["素材列表"].startswith("2 条（共 2 条）")
    assert status["预览"][0].endswith("#7 日和（live2d，1.3 MB，下载 3）")
    pick = rows_of(manager, PAGE_KEY)["pick"]
    assert [option["value"] for option in pick["options"]] == ["7", "8"]
    assert "日和" in pick["options"][0]["label"]


@needs_node
def test_login_result_is_kept_and_shown(manager, sandbox):
    manager.load_all()
    write_task(sandbox, {
        "action": "login",
        "task_id": "t2",
        "state": "done",
        "message": "登录成功：alice",
        "result": {"token": "x" * 30, "username": "alice"},
        "updated_at": int(time.time()),
    })
    manager.settings_action("ugc_hub", PAGE_KEY, "status")
    assert maps_of(manager, PAGE_KEY)["状态"]["账号"] == "alice"


@needs_node
def test_failed_job_is_reported_on_the_page(manager, sandbox):
    manager.load_all()
    write_task(sandbox, {
        "action": "download",
        "task_id": "t3",
        "state": "failed",
        "message": "连不上素材站（HTTP 0）",
        "updated_at": int(time.time()),
    })
    assert manager.settings_action("ugc_hub", PAGE_KEY, "status") == "任务：失败 — 连不上素材站（HTTP 0）"
    assert maps_of(manager, PAGE_KEY)["状态"]["本次任务"] == "失败 — 连不上素材站（HTTP 0）"


@needs_node
def test_only_visible_changes_rebuild_the_page(manager):
    """按钮和"会显示在状态映射里"的设置项才重建页面，普通输入框不重建（免得抢焦点）。"""
    manager.load_all()
    spec = manager.pages.find("ugc_hub", PAGE_KEY)
    assert spec is not None

    # 改一个输入框（用户名）：值本身就在输入框里，不需要重画
    manager.settings_action("ugc_hub", PAGE_KEY, "username", "alice", key="username")
    assert manager.pages.find("ugc_hub", PAGE_KEY).generation == spec.generation

    # 改一个会显示在状态映射里的设置项（素材站地址）：要重画
    manager.settings_action("ugc_hub", PAGE_KEY, "server_url", "https://x.example", key="server_url")
    bumped = manager.pages.find("ugc_hub", PAGE_KEY).generation
    assert bumped > spec.generation

    # 按钮一定会重画
    manager.settings_action("ugc_hub", PAGE_KEY, "clear_status")
    assert manager.pages.find("ugc_hub", PAGE_KEY).generation > bumped


@needs_node
def test_unload_removes_all_pages(manager):
    manager.load_all()
    assert len(manager.settings_pages()) == 1
    assert manager.unload("ugc_hub") is True
    assert manager.settings_pages() == []
    assert manager.menu_items() == []


class _StubSite:
    """够 ugc.js 用的迷你素材站：注册、三步上传、列表、HEAD/GET 下载（含 Range）。"""

    def __init__(self):
        self.items = {}
        self.uploads = {}
        self.next_id = 1
        self.server = None
        self.thread = None

    @staticmethod
    def public(item):
        """对外的 item 结构：去掉只给下载用的原始字节。"""
        return {key: value for key, value in item.items() if key != "bytes"}

    def start(self) -> str:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _json(self, payload, status=200, headers=None):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def _error(self, status, code, message):
                self._json({"error": {"code": code, "message": message}}, status)

            def _read_body(self):
                length = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(length) if length else b""

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/api/health":
                    return self._json({"ok": True, "name": "stub", "version": "1.0.0"})
                if path == "/api/items":
                    kind = ""
                    if "kind=" in self.path:
                        kind = self.path.split("kind=")[1].split("&")[0]
                    items = [item for item in stub.items.values() if not kind or item["kind"] == kind]
                    return self._json({"items": [stub.public(item) for item in items], "total": len(items)})
                if path.startswith("/api/items/") and path.endswith("/download"):
                    return self._download(path.split("/")[3])
                return self._error(404, "no_such_route", "接口不存在")

            def do_HEAD(self):
                path = self.path.split("?")[0]
                if path.startswith("/api/items/") and path.endswith("/download"):
                    return self._download(path.split("/")[3], head_only=True)
                return self._error(404, "no_such_route", "接口不存在")

            def _download(self, item_id, head_only=False):
                item = stub.items.get(str(item_id))
                if item is None:
                    return self._error(404, "no_such_item", "资源不存在")
                data = item["bytes"]
                start, end = 0, len(data) - 1
                status = 200
                range_header = self.headers.get("Range") or ""
                if range_header.startswith("bytes="):
                    raw = range_header[6:].split("-")
                    start = int(raw[0])
                    end = int(raw[1]) if len(raw) > 1 and raw[1] else len(data) - 1
                    status = 206
                chunk = data[start:end + 1]
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("X-Item-SHA256", item["sha256"])
                self.send_header("X-Part-Count", "1")
                self.send_header("X-Part-Size", str(len(data)))
                self.send_header("X-Concurrency-Limit", "4")
                self.send_header("Content-Disposition",
                                 "attachment; filename=\"stub.zip\"; filename*=UTF-8''%s" % quote(item["name"]))
                if status == 206:
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, len(data)))
                self.end_headers()
                if not head_only:
                    self.wfile.write(chunk)

            def do_POST(self):
                path = self.path.split("?")[0]
                body = self._read_body()
                if path == "/api/auth/register":
                    payload = json.loads(body or b"{}")
                    return self._json({
                        "token": "stub-token-" + "x" * 24,
                        "user": {"id": "1", "username": payload.get("username", "stub"), "role": "admin"},
                    }, 201)
                if path == "/api/uploads":
                    payload = json.loads(body or b"{}")
                    upload_id = "up_%d" % stub.next_id
                    stub.next_id += 1
                    stub.uploads[upload_id] = {"expect": payload, "data": b""}
                    return self._json({"upload_id": upload_id, "offset": 0, "chunk_size": 8 * 1024 * 1024}, 201)
                if path.endswith("/chunk"):
                    session = stub.uploads.get(path.split("/")[3])
                    if session is None:
                        return self._error(404, "no_such_upload", "上传会话不存在")
                    session["data"] += body
                    return self._json({"offset": len(session["data"])})
                if path.endswith("/complete"):
                    session = stub.uploads.pop(path.split("/")[3], None)
                    if session is None:
                        return self._error(404, "no_such_upload", "上传会话不存在")
                    payload = json.loads(body or b"{}")
                    data = session["data"]
                    item_id = str(stub.next_id)
                    stub.next_id += 1
                    item = {
                        "id": item_id,
                        "name": payload.get("name", "stub"),
                        "kind": payload.get("kind", "other"),
                        "type": "plugin" if payload.get("kind") == "plugin" else "model",
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "downloads": 0,
                        "status": "published",
                        "author": {"id": "1", "username": "stub"},
                        "meta": {"entry": "Stub/Stub.model3.json"},
                        "bytes": data,
                    }
                    stub.items[item_id] = item
                    return self._json({"item": stub.public(item)}, 201)
                return self._error(404, "no_such_route", "接口不存在")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return "http://127.0.0.1:%d" % self.server.server_address[1]

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture
def stub_site():
    site = _StubSite()
    url = site.start()
    yield url
    site.stop()


@needs_node
def test_client_check_script_covers_download_upload_and_worker(stub_site, tmp_path):
    """把 tests/ugc_client_check.js 指向迷你素材站跑一遍：ugc.js 与 worker 都要过。"""
    fixture = tmp_path / "fixture-live2d.zip"
    with zipfile.ZipFile(fixture, "w") as archive:
        archive.writestr("Stub/Stub.model3.json", '{"Version":3}')
        archive.writestr("Stub/Stub.moc3", b"MOC3" * 32)
        archive.writestr("Stub/textures/tex.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    # node 在 Windows 上要用到 SystemRoot 等环境变量，只传两个自定义变量会让它起不来
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    environment = dict(os.environ)
    environment.update({
        "UGC_BASE_URL": stub_site,
        "UGC_FIXTURE_ZIP": str(fixture),
        "UGC_WORK_DIR": str(work_dir),
    })
    result = subprocess.run(
        [NODE, str(CHECK_SCRIPT)],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert "失败 0 项" in output, output
    assert result.returncode == 0, output
    assert "ok   后台 worker 下载并解包" in output
