from __future__ import annotations

import inspect
import json
import re
import threading
import weakref
from dataclasses import dataclass, field

from .errors import PluginError

# 插件页面统一挂在设置窗的这个分类下，插件改不了
PLUGIN_CATEGORY = "插件"

# 声明式表单支持的控件类型
FORM_TYPES = ("label", "hint", "text", "password", "number", "switch", "select", "button", "section", "map")
VALUE_TYPES = ("text", "password", "number", "switch", "select")
MAX_ROWS = 64
MAX_OPTIONS = 64
MAX_COLUMNS = 4
MAX_NESTED_ROWS = 32

_SLUG_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def jsonable(value):
    """能塞进 JSON 就原样返回，不能就转成字符串。"""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def page_key(title: str, fallback: str = "page") -> str:
    """由标题生成一个稳定的页面 key（插件没写 key 时用）。"""
    slug = _SLUG_RE.sub("_", str(title or "").strip()).strip("_")
    return slug or fallback


def _text(value, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text or default


def _number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _clamp_int(value, low: int, high: int, fallback: int) -> int:
    number = _number(value)
    if number is None:
        return fallback
    return max(low, min(high, int(number)))


def _options(raw) -> tuple:
    """下拉项：接受 "文本" / (值, 文本) / {"value", "label"} 三种写法。"""
    if not isinstance(raw, (list, tuple)):
        return ()

    items = []
    for item in list(raw)[:MAX_OPTIONS]:
        if isinstance(item, dict):
            value = item.get("value", item.get("label"))
            label = item.get("label", value)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            value, label = item[0], item[1]
        else:
            value = label = item
        if value is None:
            continue
        items.append({"value": jsonable(value), "label": str(label if label is not None else value)})
    return tuple(items)


@dataclass(slots=True)
class FormRow:
    """声明式表单的一行：插件给 dict，宿主渲染成控件。

    `section` 是一块栅格卡片（`columns` 列，子行用 `span` 跨列）；
    `map` 是一组「名称 → 值」的只读展示，用来显示状态。
    """

    type: str = "text"
    key: str = ""
    label: str = ""
    text: str = ""
    hint: str = ""
    placeholder: str = ""
    action: str = ""
    default: object = None
    options: tuple = ()
    minimum: object = None
    maximum: object = None
    step: object = None
    columns: int = 1
    span: int = 1
    rows: tuple = ()
    items: tuple = ()

    @property
    def title(self) -> str:
        """这一行显示的主文字（控件行用 label，纯文字行用 text）。"""
        return self.label or self.text or self.key

    def public(self) -> dict:
        return {
            "type": self.type,
            "key": self.key,
            "label": self.label,
            "text": self.text,
            "hint": self.hint,
            "action": self.action,
            "default": jsonable(self.default),
            "options": [dict(item) for item in self.options],
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "columns": self.columns,
            "span": self.span,
            "rows": [row.public() for row in self.rows],
            "items": [dict(item) for item in self.items],
        }


def _map_items(raw) -> tuple:
    """状态映射：接受 {"键": 值} / [[键, 值]] / [{"key", "value"}] 三种写法。"""
    items = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        pairs = []
        for item in raw:
            if isinstance(item, dict):
                pairs.append((item.get("key", item.get("label")), item.get("value")))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                pairs.append((item[0], item[1]))
            else:
                pairs.append((item, ""))
    else:
        return ()

    for key, value in pairs[:MAX_OPTIONS]:
        name = _text(key)
        if not name:
            continue
        items.append({"key": name, "value": jsonable(value)})
    return tuple(items)


def make_row(raw) -> FormRow | None:
    """把一行声明变成 FormRow；看不懂的行返回 None（跳过，不影响别的行）。"""
    if isinstance(raw, FormRow):
        return raw
    if not isinstance(raw, dict):
        return None

    kind = _text(raw.get("type"), "text").lower()
    if kind not in FORM_TYPES:
        return None

    label = _text(raw.get("label") or raw.get("title"))
    text = _text(raw.get("text")) or label
    key = _text(raw.get("key"))
    action = _text(raw.get("action"))
    hint = _text(raw.get("hint") or raw.get("description"))

    if kind == "section":
        children = tuple(
            row for row in (make_row(item) for item in raw.get("rows") or [])
            if row is not None and row.type != "section"
        )[:MAX_NESTED_ROWS]
        if not children:
            return None
        return FormRow(
            type="section",
            label=label or text,
            text=text,
            hint=hint,
            columns=_clamp_int(raw.get("columns"), 1, MAX_COLUMNS, 1),
            rows=children,
        )

    if kind == "map":
        items = _map_items(raw.get("items") or raw.get("values") or raw.get("map"))
        if not items:
            return None
        return FormRow(type="map", label=label or text, text=text, hint=hint, items=items)

    if kind in VALUE_TYPES and not key:
        return None
    if kind == "button" and not (action or key):
        return None
    if kind in ("label", "hint") and not text:
        return None

    default = raw.get("default")
    if kind == "switch":
        default = bool(default)
    elif kind == "number":
        default = _number(default)

    return FormRow(
        type=kind,
        key=key,
        label=label or text,
        text=text,
        hint=hint,
        placeholder=_text(raw.get("placeholder")),
        action=action,
        default=default,
        options=_options(raw.get("options") or raw.get("choices")),
        minimum=_number(raw.get("min")),
        maximum=_number(raw.get("max")),
        step=_number(raw.get("step")),
        span=_clamp_int(raw.get("span"), 1, MAX_COLUMNS, 1),
    )


def normalize_form(raw) -> tuple:
    """把插件给的表单声明整理成 FormRow 元组；结构不对就报错。"""
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
        raise PluginError("form 必须是行列表：form=[{'type': 'text', 'key': 'suffix', ...}]")

    rows = []
    for item in list(raw)[:MAX_ROWS]:
        row = make_row(item)
        if row is not None:
            rows.append(row)
    return tuple(rows)


def rows_from_manifest(settings) -> tuple:
    """按 plugin.json 里声明的 settings 生成表单行（插件不写 form 时的默认页）。"""
    rows = []
    for item in list(settings or ())[:MAX_ROWS]:
        if not isinstance(item, dict):
            continue
        kind = _text(item.get("type"), "text").lower()
        row = make_row({
            "type": kind if kind in VALUE_TYPES else "text",
            "key": item.get("key"),
            "label": item.get("label"),
            "default": item.get("default"),
        })
        if row is not None:
            rows.append(row)
    return tuple(rows)


@dataclass
class SettingsPageSpec:
    """插件注册的一个设置页；generation 变了表示要重建控件。"""

    plugin: str
    key: str
    title: str
    hint: str = ""
    order: int = 100
    builder: object = None
    rows: tuple = ()
    generation: int = 0

    @property
    def id(self) -> str:
        return f"{self.plugin}:{self.key}"

    def public(self) -> dict:
        return {
            "plugin": self.plugin,
            "key": self.key,
            "id": self.id,
            "title": self.title,
            "hint": self.hint,
            "order": self.order,
            "builder": callable(self.builder),
            "form": [row.public() for row in self.rows],
        }


def weak_callback(target):
    """给回调做弱引用：窗口被销毁后不该再收到通知。"""
    if target is None:
        return None
    try:
        return weakref.WeakMethod(target) if inspect.ismethod(target) else weakref.ref(target)
    except TypeError:
        return None


@dataclass
class PluginPages:
    """插件设置页注册表：不依赖 Qt，只记账；挂载与摘除由设置窗执行。"""
    manager: object = None
    _items: dict = field(default_factory=dict)
    _listeners: list = field(default_factory=list)
    _strong: list = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def add(self, plugin_id, title, form=None, builder=None, key=None, order=100, hint="") -> SettingsPageSpec:
        """注册/覆盖一个页面，返回它的 spec（key 在插件内唯一）。"""
        plugin_id = _text(plugin_id)
        if not plugin_id:
            raise PluginError("插件 id 不能为空")

        title = _text(title)
        if not title:
            raise PluginError("设置页标题不能为空")
        if builder is not None and not callable(builder):
            raise PluginError("builder 必须是可调用对象（调用后返回一个 QWidget）")

        rows = normalize_form(form)
        if not rows and builder is None:
            raise PluginError("页面没有任何内容：form 是空的，也没有 builder")

        page = _text(key) or page_key(title)
        try:
            spec = SettingsPageSpec(
                plugin=plugin_id,
                key=page,
                title=title,
                hint=_text(hint),
                order=int(order),
                builder=builder,
                rows=rows,
            )
        except (TypeError, ValueError) as exc:
            raise PluginError(f"order 必须是数字：{exc}") from exc

        with self._lock:
            items = list(self._items.get(plugin_id) or ())
            index = next((position for position, item in enumerate(items) if item.key == page), -1)
            if index >= 0:
                spec.generation = items[index].generation + 1
                items[index] = spec
            else:
                items.append(spec)
            self._items[plugin_id] = items

        self.changed(rebuild=True)
        return spec

    def remove(self, plugin_id: str, key: str | None = None) -> int:
        """摘掉某个页面（key 为空就摘掉这个插件的全部页面）。"""
        plugin_id = _text(plugin_id)
        with self._lock:
            items = list(self._items.get(plugin_id) or ())
            if key is None:
                removed = len(items)
                self._items.pop(plugin_id, None)
            else:
                page = _text(key)
                kept = [item for item in items if item.key != page]
                removed = len(items) - len(kept)
                if kept:
                    self._items[plugin_id] = kept
                else:
                    self._items.pop(plugin_id, None)

        if removed:
            self.changed(rebuild=True)
        return removed

    def remove_plugin(self, plugin_id: str) -> int:
        return self.remove(plugin_id)

    def refresh(self, plugin_id: str | None = None, key: str | None = None) -> int:
        """重建页面控件让它们重读设置值，返回被刷新的页数。"""
        if plugin_id is None:
            wanted = self.pages()
        else:
            found = self.find(plugin_id, key)
            wanted = [item for item in (found if isinstance(found, list) else [found]) if item is not None]

        with self._lock:
            for spec in wanted:
                spec.generation += 1
        if wanted:
            self.changed(rebuild=True)
        return len(wanted)

    def find(self, plugin_id: str, key: str | None = None):
        """按插件（可选 key）取页面：key 为空返回列表，否则返回单个或 None。"""
        plugin_id = _text(plugin_id)
        with self._lock:
            items = list(self._items.get(plugin_id) or ())
        if key is None:
            return items
        page = _text(key)
        return next((item for item in items if item.key == page), None)

    def pages(self, plugin_id: str | None = None) -> list:
        """全部页面，按（插件 order、页面 order、标题）排好序。"""
        with self._lock:
            groups = {key: list(value) for key, value in self._items.items()}

        result = []
        for owner, items in groups.items():
            if plugin_id is not None and owner != _text(plugin_id):
                continue
            result.extend(items)
        result.sort(key=lambda item: (self.plugin_order(item.plugin), item.order, item.title))
        return result

    def public(self) -> list:
        return [spec.public() for spec in self.pages()]

    def plugin_order(self, plugin_id: str) -> int:
        infos = getattr(self.manager, "infos", None) or {}
        info = infos.get(plugin_id)
        order = getattr(getattr(info, "manifest", None), "order", 100)
        return order if isinstance(order, int) else 100

    def bind(self, callback) -> bool:
        """登记页面变更的回调（设置窗用），绑定方法用弱引用。"""
        if not callable(callback):
            raise PluginError("监听者必须可调用")

        reference = weak_callback(callback) if inspect.ismethod(callback) else None
        with self._lock:
            if reference is None:
                # 普通函数/闭包拿不到弱引用，按强引用留着
                if callback not in self._strong:
                    self._strong.append(callback)
                return True
            self._listeners = [item for item in self._listeners if item() is not None]
            self._listeners.append(reference)
        return True

    def changed(self, rebuild: bool = False):
        """通知监听者：页面注册表变了（rebuild=True 表示挂载中的控件要重建）。"""
        for callback in self._live():
            if self.manager is not None:
                self.manager.run_on_ui(callback, rebuild)
            else:
                callback(rebuild)

    def _live(self) -> list:
        with self._lock:
            alive = []
            for item in self._listeners:
                target = item()
                if target is not None:
                    alive.append(target)
            self._listeners = [item for item in self._listeners if item() is not None]
            alive.extend(self._strong)
        return alive


__all__ = [
    "FORM_TYPES",
    "FormRow",
    "MAX_OPTIONS",
    "MAX_ROWS",
    "PLUGIN_CATEGORY",
    "PluginPages",
    "SettingsPageSpec",
    "VALUE_TYPES",
    "jsonable",
    "make_row",
    "normalize_form",
    "page_key",
    "rows_from_manifest",
    "weak_callback",
]
