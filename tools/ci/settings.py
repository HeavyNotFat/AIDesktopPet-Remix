from __future__ import annotations

import fnmatch
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from .core import Finding, Severity

# 默认不扫描的目录/文件（glob，相对仓库根）
DEFAULT_EXCLUDE: tuple[str, ...] = (
    ".git/*",
    ".venv/*",
    "venv/*",
    ".idea/*",
    "build/*",
    "dist/*",
    "__pycache__/*",
    "*/__pycache__/*",
    "*/*/__pycache__/*",
    ".mypy_cache/*",
    ".ruff_cache/*",
    ".pytest_cache/*",
    "node_modules/*",
    "test/*",          # 该目录在 .gitignore 里，属于本地试验代码
    "tools/ci/tests/fixtures/*",
)

# 内联忽略：``# ci: ignore`` / ``# ci: ignore=ui/x,ui/y``
INLINE_MARKER = "ci: ignore"


@dataclass(slots=True)
class Settings:

    root: Path
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE
    ignore: tuple[str, ...] = ()
    disable: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    fail_on: Severity = Severity.ERROR
    _inline_cache: dict[str, tuple[bool, set[str]]] = field(default_factory=dict, repr=False)

    # -- 载入 -------------------------------------------------------------
    @classmethod
    def load(cls, root: Path) -> "Settings":
        data: Mapping = {}
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            with pyproject.open("rb") as handle:
                data = tomllib.load(handle).get("tool", {}).get("adpci", {}) or {}

        # pyproject 里的 exclude 是**追加**在默认排除项之后，而不是替换：
        # 否则很容易不小心把 __pycache__ 之类的默认项丢掉。
        exclude = (*DEFAULT_EXCLUDE, *tuple(data.get("exclude", ())))
        env_fail = os.getenv("ADPCI_FAIL_ON")
        fail_on = Severity.parse(env_fail) if env_fail else Severity.parse(str(data.get("fail-on", "error")))

        return cls(
            root=root,
            exclude=exclude,
            ignore=tuple(data.get("ignore", ())),
            disable=tuple(data.get("disable", ())),
            allow=tuple(data.get("allow", ())),
            fail_on=fail_on,
        )

    # -- 过滤 -------------------------------------------------------------
    def is_excluded(self, rel_path: str) -> bool:
        rel = rel_path.replace("\\", "/")
        # 点开头的目录一律不看：.venv/.git/.idea/.PluginDevOld 这类本地残留
        for part in rel.split("/"):
            if part.startswith(".") and part not in {".", ".."}:
                return True
        for pattern in self.exclude:
            pattern = pattern.replace("\\", "/")
            if fnmatch.fnmatch(rel, pattern):
                return True
            if pattern.endswith("/*") and rel.startswith(pattern[:-1]):
                return True
        return False

    def is_disabled(self, check_id: str) -> bool:
        """完全不跑的检查（``disable``）。``ignore`` 走 suppression。"""
        return check_id in self.disable

    def allow_tokens(self, check_id: str) -> set[str]:
        """``allow = ["ui/xxx:Token"]`` → ``{"Token"}``。"""
        tokens: set[str] = set()
        for entry in self.allow:
            head, _, tail = entry.partition(":")
            if head.strip() == check_id and tail.strip():
                tokens.add(tail.strip())
        return tokens

    def suppression(self, item: Finding, sources) -> str | None:
        """返回抑制原因；``None`` 表示这条问题应该保留。"""
        if item.check in self.ignore:
            return "ignored"
        allowed, checks = self._inline(sources, item.location)
        if allowed and (not checks or item.check in checks):
            return "inline"
        return None

    def _inline(self, sources, location) -> tuple[bool, set[str]]:
        key = f"{location.path}:{location.line}"
        cached = self._inline_cache.get(key)
        if cached is not None:
            return cached

        result: tuple[bool, set[str]] = (False, set())
        line = sources.line(location.path, location.line)
        if INLINE_MARKER in line:
            tail = line.split(INLINE_MARKER, 1)[1].lstrip()
            if tail.startswith("="):
                names = {part.strip() for part in tail[1:].split(",") if part.strip()}
                result = (True, names)
            else:
                result = (True, set())

        self._inline_cache[key] = result
        return result

    # -- 输出 -------------------------------------------------------------
    def describe(self) -> Sequence[str]:
        return (
            f"root            = {self.root}",
            f"fail-on         = {self.fail_on.value}",
            f"exclude         = {len(self.exclude)} pattern(s)",
            f"ignore          = {', '.join(self.ignore) or '-'}",
            f"disable         = {', '.join(self.disable) or '-'}",
            f"allow           = {', '.join(self.allow) or '-'}",
        )
