from __future__ import annotations

from ..core import register
from . import abstract_api, config_schema, hygiene, imports, resources, theme_mapping, ui_conflict, web_contract


# --- 抽象类 / 抽象方法 -----------------------------------------------------
register(
    "abs/contract",
    "抽象基类的实现必须补齐抽象成员",
    "abstract",
    docs="stlibs/themes/base.py",
)(abstract_api.check_contract)
register(
    "abs/instantiate",
    "禁止构造仍有抽象成员的类",
    "abstract",
)(abstract_api.check_instantiate)
register(
    "abs/decorator-order",
    "@abstractmethod 必须是最内层装饰器",
    "abstract",
)(abstract_api.check_decorator_order)
register(
    "abs/not-enforced",
    "@abstractmethod 必须配合 ABCMeta 才生效",
    "abstract",
)(abstract_api.check_not_enforced)
register(
    "abs/metaclass",
    "Qt + 抽象基类必须显式合并元类",
    "abstract",
)(abstract_api.check_metaclass_conflict)
register(
    "abs/signature",
    "实现签名必须兼容抽象声明",
    "abstract",
)(abstract_api.check_signature)


# --- UI 冲突 ---------------------------------------------------------------
register("ui/duplicate-class", "同名类重复定义", "ui")(ui_conflict.check_duplicate_class)
register("ui/object-name-collision", "objectName 撞车", "ui")(ui_conflict.check_object_name_collision)
register("ui/stylesheet-class", "样式里的类选择器必须存在", "ui")(ui_conflict.check_stylesheet_class)
register("ui/stylesheet-dead-id", "样式里的 #id 必须有对应 setObjectName", "ui")(ui_conflict.check_stylesheet_dead_id)
register("ui/double-parent", "控件被加进多个布局", "ui")(ui_conflict.check_double_parent)
register("ui/layout-vs-geometry", "布局与 setGeometry 冲突", "ui")(ui_conflict.check_layout_vs_geometry)
register("ui/duplicate-setlayout", "重复 setLayout", "ui")(ui_conflict.check_duplicate_setlayout)
register("ui/size-constraint", "固定尺寸与尺寸范围冲突", "ui")(ui_conflict.check_size_constraint)
register("ui/window-flags", "互斥的窗口标志", "ui")(ui_conflict.check_window_flags)
register("ui/signal-clash", "信号名与成员冲突", "ui")(ui_conflict.check_signal_clash)
register("ui/signal-slot", "信号/槽参数个数不匹配", "ui")(ui_conflict.check_signal_slot)
register("ui/style-overwrite", "同一分支重复 setStyleSheet", "ui")(ui_conflict.check_style_overwrite)
register("ui/dead-control", "控件填了数据却没接任何信号", "ui")(ui_conflict.check_dead_control)
register("ui/missing-super-init", "parent 没有传给 super().__init__", "ui")(ui_conflict.check_missing_super_init)


# --- UI 主题类映射 ---------------------------------------------------------
register("theme/mapping-missing", "主题缺少必需类映射", "theme", docs="stlibs/__init__.py::_ThemeTypingProtocol")(
    theme_mapping.check_mapping_missing
)
register("theme/submodule-missing", "主题缺少必需子模块", "theme")(theme_mapping.check_submodule_missing)
register("theme/member-missing", "映射类缺少契约成员", "theme", docs="stlibs/themes/base.py")(theme_mapping.check_member_missing)
register("theme/member-kind", "映射成员形态与抽象声明不一致", "theme")(theme_mapping.check_member_kind)
register("theme/usage-unsupported", "代码用到的映射主题必须提供", "theme")(theme_mapping.check_usage_unsupported)
register("theme/module-member", "主题子模块缺少被用到的页面", "theme")(theme_mapping.check_module_member)
register("theme/protocol-drift", "用到的映射必须写进契约 Protocol", "theme")(theme_mapping.check_protocol_drift)
register("theme/kind-mismatch", "同名映射在各主题里形态不一致", "theme")(theme_mapping.check_kind_mismatch)
register("theme/alias-duplicate", "多个映射绑到同一个对象", "theme")(theme_mapping.check_alias_duplicate)
register("theme/protocol-declared", "主题契约必须存在", "theme")(theme_mapping.check_protocol_declared)
register("theme/abc-mapping", "契约引用的抽象基类必须存在", "theme")(theme_mapping.check_abc_mapping)


# --- 配置 / 资源 -----------------------------------------------------------
register("config/schema", "configure.json 与 dataclass 字段一致", "config")(config_schema.check_schema)
register("config/missing-key", "代码取用的配置键必须存在", "config")(config_schema.check_missing_key)
register("config/animation", "动画映射与动画 JSON 一致", "config")(config_schema.check_animation)
register("config/prompts", "prompts.json 键完整", "config")(config_schema.check_prompts)

register("resource/missing", "代码引用的资源必须存在", "resource")(resources.check_missing)
register("resource/web-asset", "网页静态资源必须存在", "resource")(resources.check_web_asset)
register("resource/character", "角色模型目录结构完整", "resource")(resources.check_character)
register("resource/static-model", "static.json 与静态素材一致", "resource")(resources.check_static_models)
register("resource/json-valid", "resources 下的 JSON 必须能解析", "resource")(resources.check_json_resources)
register("resource/icon", "未使用的图标素材", "resource")(resources.check_icon_usage)


# --- 网页前后端契约 --------------------------------------------------------
register("web/api-route", "前端调用的接口必须存在", "web")(web_contract.check_api_route)
register("web/api-port", "前后端端口一致", "web")(web_contract.check_api_port)
register("web/config-key", "QW.config 键必须定义", "web")(web_contract.check_config_key)
register("web/dom-id", "JS 取的 DOM id 必须存在", "web")(web_contract.check_dom_id)
register("web/namespace", "QW 命名空间成员必须导出", "web")(web_contract.check_namespace)
register("web/script-loaded", "js 文件必须被 index.html 引入", "web")(web_contract.check_script_loaded)


# --- 基础卫生 --------------------------------------------------------------
register("hygiene/parse-error", "文件必须能被解析", "hygiene")(hygiene.check_parse_error)
register("hygiene/bare-except", "禁止裸 except", "hygiene")(hygiene.check_bare_except)
register("hygiene/attr-typo", "可疑的属性/方法名（疑似拼写错）", "hygiene")(hygiene.check_attribute_typo)
register("hygiene/todo", "TODO/FIXME 统计", "hygiene")(hygiene.check_todo)


# --- 导入图 / 依赖 ---------------------------------------------------------
register("import/cycle", "禁止模块级循环导入", "import")(imports.check_import_cycle)
register("import/requirements", "第三方依赖必须写进 requirements.txt", "import")(imports.check_requirements)
register("import/unused-req", "未被使用的依赖声明", "import")(imports.check_unused_requirements)
