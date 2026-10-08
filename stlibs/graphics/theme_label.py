
from __future__ import annotations

from .. import Config, SharingData

# 主题包名 → 中文名；主题里写了 THEME_LABEL 就优先用它的
FALLBACK_LABELS = {
    "hacker": "黑客",
    "breeze": "轻风",
}


def theme_name() -> str:
    """当前主题包名（配置里写什么用什么，取不到就 hacker）。"""
    return (getattr(Config, "theme", "") or "hacker").strip() or "hacker"


def theme_label() -> str:
    """给窗口标题用的主题说明：``轻风(breeze)``。"""
    name = theme_name()
    theme = getattr(SharingData, "theme", None)
    label = getattr(theme, "THEME_LABEL", "") if theme is not None else ""
    label = label or FALLBACK_LABELS.get(name, name)
    return f"{label}({name})"


__all__ = ["FALLBACK_LABELS", "theme_label", "theme_name"]
