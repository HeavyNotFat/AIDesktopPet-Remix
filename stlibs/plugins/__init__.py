from .api import (  # noqa: F401
    ALL_HOOKS,
    CHAT_REPLY,
    CHAT_SEND,
    COMMAND,
    EVENT,
    HOOK_HELP,
    MENU,
    ON_LOAD,
    ON_UNLOAD,
    SYSTEM_PROMPT,
    PluginAPI,
    PluginError,
)
from .icons import (  # noqa: F401
    badge_icon,
    badge_pixmap,
    clear_cache as clear_icon_cache,
    plugin_icon,
    plugin_pixmap,
)
from .manager import (  # noqa: F401
    DEFAULT_DIR,
    MenuGroup,
    MenuItem,
    PluginInfo,
    PluginManager,
    PluginsPanel,
)
from .manifest import ICON_SUFFIXES, ManifestError, PluginManifest  # noqa: F401

# 注意：这里**不要**再导出名叫 manager 的单例 —— 那会把同名的子包
# ``stlibs.plugins.manager`` 覆盖掉。单例请用 stlibs.plugin_manager()，
# 或者 stlibs.plugins.manager.manager。

__all__ = [
    "ALL_HOOKS",
    "CHAT_REPLY",
    "CHAT_SEND",
    "COMMAND",
    "DEFAULT_DIR",
    "EVENT",
    "HOOK_HELP",
    "ICON_SUFFIXES",
    "MENU",
    "ManifestError",
    "MenuGroup",
    "MenuItem",
    "ON_LOAD",
    "ON_UNLOAD",
    "PluginAPI",
    "PluginError",
    "PluginInfo",
    "PluginManager",
    "PluginManifest",
    "PluginsPanel",
    "SYSTEM_PROMPT",
    "badge_icon",
    "badge_pixmap",
    "clear_icon_cache",
    "plugin_icon",
    "plugin_pixmap",
]
