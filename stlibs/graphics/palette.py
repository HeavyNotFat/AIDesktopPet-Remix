
from __future__ import annotations

from ..themes.base import ThemePalette

# 默认（黑客主题那种深色终端风）：主题没声明 PALETTE 时用它
DEFAULT_PALETTE = ThemePalette()


def current_theme():
    """当前主题包（没绑主题时返回 None）。"""
    from .. import SharingData

    return getattr(SharingData, "theme", None)


def palette() -> ThemePalette:
    """当前主题的配色；主题没给 PALETTE 就用默认深色那套。"""
    theme = current_theme()
    colors = getattr(theme, "PALETTE", None) if theme is not None else None
    if isinstance(colors, ThemePalette):
        return colors
    return DEFAULT_PALETTE


__all__ = ["DEFAULT_PALETTE", "ThemePalette", "current_theme", "palette"]
