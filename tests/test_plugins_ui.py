import json
import os
import textwrap

import pytest

import stlibs

pytestmark = pytest.mark.ui

QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="插件页测试需要 PySide6")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


PY_PLUGIN = '''
    def on_load(api):
        api.add_menu_item("菜单项", "act")
        api.register_command("cmd")
'''

BROKEN_PLUGIN = 'def on_load(api):\n    raise RuntimeError("坏掉了")\n'


@pytest.fixture
def plugins_dir(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    root.mkdir()

    monkeypatch.setattr(stlibs, "CONFIG_PATH", str(tmp_path / "configure.json"))
    monkeypatch.setattr(stlibs.Config, "plugins", {
        "enable": True, "directory": str(root), "disabled": [], "settings": {}, "timeout": 3.0,
    }, raising=False)

    # 每次都用干净的 manager，别和别的测试共享状态
    from stlibs.plugins import PluginManager
    from stlibs.plugins.manager import core as manager_module
    fresh = PluginManager(directory=str(root))
    monkeypatch.setattr(manager_module, "manager", fresh)
    return root, fresh


def write_plugin(root, plugin_id, code):
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "main.py").write_text(textwrap.dedent(code), encoding="utf-8")
    (directory / "plugin.json").write_text(
        json.dumps({"id": plugin_id, "name": f"插件 {plugin_id}", "language": "python", "entry": "main.py"}),
        encoding="utf-8",
    )


def column(page, title: str) -> int:
    """按表头名找列号：表里加过「图标」列，写死下标会随列变动而错位。"""
    headers = [page.card.table.horizontalHeaderItem(index).text()
               for index in range(page.card.table.columnCount())]
    assert title in headers, f"没有这一列：{title}（现有 {headers}）"
    return headers.index(title)


def cell(page, row: int, title: str) -> str:
    return page.card.table.item(row, column(page, title)).text()


@pytest.fixture
def notify_spy(monkeypatch):
    calls = []

    # 主题页在方法里现取 stlibs.notify，所以补丁打在 stlibs 上
    monkeypatch.setattr(
        stlibs, "notify",
        lambda text, level="info", timeout=2600: calls.append((level, text)),
    )
    return calls


def _page(qapp, plugins_dir):
    from stlibs.themes.hacker.plugins import PluginsPage

    return PluginsPage(None)


def test_page_lists_plugins(qapp, plugins_dir):
    root, _manager = plugins_dir
    write_plugin(root, "alpha", PY_PLUGIN)
    write_plugin(root, "beta", PY_PLUGIN)

    page = _page(qapp, plugins_dir)
    page.refresh()

    assert page.card.table.rowCount() == 2
    assert "alpha" in cell(page, 0, "插件")
    assert "Python" in cell(page, 0, "语言")
    assert cell(page, 0, "图标") == "", "图标画在 item 的 icon 上，不是文字"
    assert not page.card.table.item(0, column(page, "图标")).icon().isNull(), "每个插件都要有图标"


def test_page_shows_manifest_problems(qapp, plugins_dir):
    root, _manager = plugins_dir
    (root / "broken").mkdir()
    (root / "broken" / "plugin.json").write_text("{ 坏的", encoding="utf-8")

    page = _page(qapp, plugins_dir)
    page.refresh()

    assert "有问题" in page.card.detail.text()
    assert "broken" in page.card.detail.text()


def test_page_shows_load_error(qapp, plugins_dir):
    root, manager = plugins_dir
    write_plugin(root, "bad", BROKEN_PLUGIN)
    manager.load_all()

    page = _page(qapp, plugins_dir)
    page.refresh()

    state = page.card.detail.text()
    assert "bad" in state or "坏掉了" in state or page.card.table.rowCount() == 1

    row_text = cell(page, 0, "状态")
    assert "运行出错" in row_text, "模块加载成功但 hook 抛异常也要显示出来"
    assert "坏掉了" in row_text


def test_page_shows_import_error(qapp, plugins_dir):
    root, manager = plugins_dir
    write_plugin(root, "noimport", "import 根本不存在的模块\n")
    manager.load_all()

    page = _page(qapp, plugins_dir)
    page.refresh()

    assert "加载失败" in cell(page, 0, "状态")


def test_toggle_requires_selection(qapp, plugins_dir, notify_spy):
    page = _page(qapp, plugins_dir)
    page.card.table.setCurrentCell(-1, -1)

    page.card.toggle_selected()

    assert notify_spy[-1][0] == "warning"


def test_toggle_disables_and_enables(qapp, plugins_dir, notify_spy):
    root, manager = plugins_dir
    write_plugin(root, "alpha", PY_PLUGIN)
    manager.load_all()

    page = _page(qapp, plugins_dir)
    page.refresh()
    page.card.table.selectRow(0)
    page.card.toggle_selected()

    assert manager.infos["alpha"].manifest.enabled is False
    assert "alpha" in stlibs.Config.plugins["disabled"]
    assert "停用" in notify_spy[-1][1]

    page.card.table.selectRow(0)
    page.card.toggle_selected()

    assert manager.infos["alpha"].manifest.enabled is True
    assert "启用" in notify_spy[-1][1]


def test_reload_selected(qapp, plugins_dir, notify_spy):
    root, manager = plugins_dir
    write_plugin(root, "alpha", PY_PLUGIN)
    manager.load_all()

    page = _page(qapp, plugins_dir)
    page.refresh()
    page.card.table.selectRow(0)
    page.card.reload_selected()

    assert notify_spy[-1][0] == "success"
    assert "已重载" in notify_spy[-1][1]


def test_master_switch_unloads_everything(qapp, plugins_dir, notify_spy):
    root, manager = plugins_dir
    write_plugin(root, "alpha", PY_PLUGIN)
    manager.load_all()

    page = _page(qapp, plugins_dir)
    page.card.enable_switch.setChecked(False)

    assert stlibs.Config.plugins["enable"] is False
    assert manager.infos["alpha"].loaded is False
    assert "已停用" in notify_spy[-1][1]

    page.card.enable_switch.setChecked(True)
    assert manager.infos["alpha"].loaded is True
    assert "已启用" in notify_spy[-1][1]


def test_open_folder_creates_directory(qapp, plugins_dir, monkeypatch):
    opened = []
    monkeypatch.setattr("stlibs.plugins.manager.panel._open_local",
                        lambda path: opened.append(path) or True)
    page = _page(qapp, plugins_dir)

    page.card.open_folder()

    assert opened and opened[0].endswith("plugins")


def test_refresh_reports_empty_state(qapp, plugins_dir):
    page = _page(qapp, plugins_dir)
    page.refresh()

    assert page.card.table.rowCount() == 0
    assert "还没有插件" in page.card.detail.text()
