from __future__ import annotations

import hashlib
import os
import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap

DEFAULT_ICON_SIZE = 64
BADGE_FONT_POINT = 0.52  # 徽章字号比例
BADGE_RADIUS_RATIO = 0.26  # 圆角半径比例
BADGE_BORDER_RATIO = 0.06  # 描边宽度比例

BADGE_COLORS = (
    (0x2E, 0x7D, 0x32),  # 绿
    (0x00, 0x69, 0x5C),  # 青
    (0x02, 0x77, 0xBD),  # 蓝
    (0x45, 0x27, 0xA0),  # 紫
    (0xAD, 0x14, 0x57),  # 品红
    (0xC6, 0x28, 0x28),  # 红
    (0xEF, 0x6C, 0x00),  # 橙
    (0x6D, 0x4C, 0x41),  # 棕
)

_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff]")
_LATIN_RE = re.compile(r"[0-9A-Za-z]")

# 中文字符要有这些字形的字体，否则徽章会画成空白方块
FONT_FAMILIES = "Microsoft YaHei, SimHei, Noto Sans CJK SC, PingFang SC, sans-serif"

_cache: dict = {}
_MISS = object()  # 解码失败也缓存


def has_gui() -> bool:
    """能不能安全地构造 QPixmap：没有 QGuiApplication 时构造它会直接终止进程。"""
    return QGuiApplication.instance() is not None


def badge_color(seed: str) -> QColor:
    """由插件 id 稳定地挑一个颜色（同一插件每次跑都是同一个色）。"""
    digest = hashlib.sha1(str(seed or "").encode("utf-8")).digest()
    red, green, blue = BADGE_COLORS[digest[0] % len(BADGE_COLORS)]
    return QColor(red, green, blue)


def initials(name: str, plugin_id: str = "") -> str:
    """取徽章上的字：优先中文首字，其次首个字母/数字，都没有就退回 id 的首字符。"""
    text = str(name or "").strip()
    match = _CJK_RE.search(text)
    if match:
        return match.group(0)

    match = _LATIN_RE.search(text)
    if match:
        return match.group(0).upper()

    for candidate in (text, str(plugin_id or "").strip()):
        if candidate:
            return candidate[0].upper()
    return "?"


def _paint_badge(text: str, color: QColor, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    radius = max(2.0, size * BADGE_RADIUS_RATIO)
    inset = max(1.0, size * BADGE_BORDER_RATIO)
    body = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)

    painter.setPen(QPen(color.lighter(165), max(1.0, size * 0.035)))
    painter.setBrush(color)
    painter.drawRoundedRect(body, radius, radius)

    font = QFont(FONT_FAMILIES, -1)
    font.setPixelSize(max(8, int(size * BADGE_FONT_POINT)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 235))
    painter.drawText(body, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()

    return pixmap


def badge_icon(name: str, plugin_id: str = "", size: int = DEFAULT_ICON_SIZE) -> QIcon:
    """按插件名生成的字母/汉字徽章（颜色由 id 决定，稳定可区分）。"""
    pixmap = badge_pixmap(name, plugin_id, size)
    return QIcon() if pixmap is None else QIcon(pixmap)


def badge_pixmap(name: str, plugin_id: str = "", size: int = DEFAULT_ICON_SIZE):
    """徽章位图；没有 QGuiApplication 时返回 None（见 has_gui 的说明）。"""
    if not has_gui():
        return None

    key = ("badge", initials(name, plugin_id), str(plugin_id or name or ""), int(size))
    cached = _cache.get(key)
    if isinstance(cached, QPixmap):
        return cached

    pixmap = _paint_badge(key[1], badge_color(key[2]), int(size))
    _cache[key] = pixmap
    return pixmap


def custom_icon_path(manifest):
    """清单里那枚自定义图标的路径（没有/文件不在就是 None）。"""
    return getattr(manifest, "icon_path", None)


def _file_key(path, size: int) -> tuple:
    """把修改时间编进缓存键：插件作者换了图，不重启也能立刻看到新图。"""
    try:
        return ("file", str(path), int(size), os.stat(path).st_mtime_ns)
    except OSError:
        return ("file", str(path), int(size), None)


def plugin_icon(manifest, size: int = DEFAULT_ICON_SIZE) -> QIcon:
    """插件图标：有自定义图就解码它，否则回退到字母徽章。"""
    if not has_gui():
        return QIcon()

    plugin_id = str(getattr(manifest, "id", "") or "")
    name = str(getattr(manifest, "name", "") or plugin_id)

    path = custom_icon_path(manifest)
    if path is not None:
        key = _file_key(path, size)
        cached = _cache.get(key, _MISS)
        if cached is _MISS:
            pixmap = QPixmap(str(path))
            cached = None if pixmap.isNull() else pixmap.scaled(
                int(size),
                int(size),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            _cache[key] = cached
        if cached is not None:
            return QIcon(cached)

    return badge_icon(name, plugin_id, size)


def plugin_pixmap(manifest, size: int = DEFAULT_ICON_SIZE):
    """plugin_icon 的 QPixmap 版本（自绘菜单要 drawPixmap）。"""
    if not has_gui():
        return None

    size = int(size)
    pixmap = plugin_icon(manifest, size).pixmap(size, size)
    if pixmap.isNull():
        # 极少数情况（svg 解码失败等）：退回徽章，保证菜单里不会出现空洞
        pixmap = badge_pixmap(
            str(getattr(manifest, "name", "") or getattr(manifest, "id", "")),
            str(getattr(manifest, "id", "") or ""),
            size,
        )
    return pixmap


def clear_cache():
    """测试用：换掉插件目录后清一下，免得拿到上一份插件的图。"""
    _cache.clear()


__all__ = [
    "BADGE_COLORS",
    "DEFAULT_ICON_SIZE",
    "badge_color",
    "badge_icon",
    "badge_pixmap",
    "clear_cache",
    "custom_icon_path",
    "has_gui",
    "initials",
    "plugin_icon",
    "plugin_pixmap",
]
