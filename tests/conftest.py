from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from tools.ci import Report, run  # noqa: E402
from tools.ci.core import Severity  # noqa: E402

# 迷你仓库放点开头的目录下：CI 扫描会跳过点目录，样例文件不会污染真实仓库
WORK_ROOT = ROOT / ".ci-tmp"
# pytest 的 --basetemp 指向 .ci-tmp/pytest，而它只创建最后一级目录，
# 父目录得先有，否则单独跑某个用例会 FileNotFoundError
WORK_ROOT.mkdir(parents=True, exist_ok=True)
WORK_ROOT.mkdir(parents=True, exist_ok=True)

# 迷你仓库里可用的最小主题契约（与 stlibs/__init__.py 的 Protocol 保持一致）
MAPPING_NAMES = (
    "Window",
    "Button",
    "Label",
    "Menu",
    "Action",
    "ScrollArea",
    "TextEdit",
    "LineEdit",
    "Slider",
    "ComboBox",
    "CardWidget",
    "ChatWidget",
    "ChatBubble",
    "ModelChat",
)

PROTOCOL_SRC = (
    "from typing import Protocol, Callable\n"
    "from types import ModuleType\n"
    "\n"
    "\n"
    "class _ThemeTypingProtocol(Protocol):\n"
    "    theme: ModuleType\n"
    "    general: ModuleType\n"
    "    llm: ModuleType\n"
    "    tts: ModuleType\n"
    "    settings: ModuleType\n"
    "    animation: ModuleType\n"
    "\n"
    + "".join(f"    {name}: Callable\n" for name in MAPPING_NAMES)
    + "    IconList: object\n"
)

BASE_SRC = '''\
from abc import ABCMeta, abstractmethod
class ModelChatABS(metaclass=ABCMeta):
    """模型聊天"""
    @staticmethod
    @abstractmethod
    def return_llm_class(model): pass
class MainWindowABS(metaclass=ABCMeta):
    """UI主窗口"""
    @abstractmethod
    def addNavigation(self, text: str, widget, shortcut_keys=None, position: str = "top", category=None): pass
    @abstractmethod
    def removeNavigation(self, widget): pass
    @abstractmethod
    def create_category(self, category: str, position: str = "top"): pass
    @abstractmethod
    def setTitle(self, title: str): pass
class IconListABS(metaclass=ABCMeta):
    @property
    @abstractmethod
    def SETTING(self): pass
    @property
    @abstractmethod
    def CHAT(self): pass
    @property
    @abstractmethod
    def SHUTDOWN(self): pass
class MenuWidgetABS(metaclass=ABCMeta):
    @abstractmethod
    def addSeparator(self): pass
    @abstractmethod
    def addAction(self, action): pass
class SwitchWidgetABS(metaclass=ABCMeta):
    @abstractmethod
    def setChecked(self, checked: bool): pass
    @abstractmethod
    def isChecked(self): pass
'''

THEME_SUBMODULES = {
    "general": "class GeneralPage: pass\n",
    "llm": "class LLMPage: pass\n",
    "tts": "class TTSPage: pass\n",
    "settings": "class SettingsPage: pass\n",
    "animation": "class AnimationPage: pass\n",
}


def write_mini_repo(root: Path, files: dict[str, str], *, contract: bool = False) -> Path:
    """在 ``root`` 下按 ``{相对路径: 内容}`` 建一个迷你仓库。"""
    root.mkdir(parents=True, exist_ok=True)
    if contract:
        files = {
            "stlibs/__init__.py": PROTOCOL_SRC,
            "stlibs/themes/base.py": BASE_SRC,
            **files,
        }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def run_checks(root: Path, only: list[str] | None = None) -> Report:
    return run(root=root, only=only)


def findings_of(root: Path, check: str) -> list:
    report = run_checks(root, [check])
    assert not report.crashes, [r.crash for r in report.crashes]
    return report.findings


def checks_of(report: Report, check: str) -> list:
    return [item for item in report.findings if item.check == check]


@pytest.fixture
def work_root(request) -> Path:
    """每个测试一个干净的目录（位于被 CI 忽略的 ``.ci-tmp`` 下）。"""
    name = request.node.name.replace("[", "_").replace("]", "_").replace("/", "_")
    target = WORK_ROOT / name
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    yield target
    shutil.rmtree(target, ignore_errors=True)


@pytest.fixture
def mini_repo(work_root: Path):
    def factory(files: dict[str, str], *, contract: bool = False) -> Path:
        return write_mini_repo(work_root / "repo", files, contract=contract)

    return factory


@pytest.fixture(scope="session", autouse=True)
def _cleanup_work_root():
    yield
    shutil.rmtree(WORK_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def severity():
    return Severity
