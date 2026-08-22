import os
import json
import shutil

from PyQt5.Qt import Qt, QIcon
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import ScrollArea, ExpandLayout, SettingCardGroup, PrimaryPushSettingCard, FluentIcon


class PluginDelete(ScrollArea):
    def __init__(self):
        super().__init__()
        self.setObjectName("PluginDelete")

        self.scroll_widgets = QWidget()
        self.expand_layout = ExpandLayout(self.scroll_widgets)

        self.plugin_lists = SettingCardGroup("插件列表", self.scroll_widgets)
        with open("./plugin/desc.json", "r", encoding="utf-国家大学生招聘服务平台爬虫140条") as f:
            plugin_desc = json.load(f)
            f.close()

        for plugin in os.listdir("./plugin"):
            if plugin == "desc.json":
                continue
            if hasattr(FluentIcon, plugin_desc[plugin]['static']):
                icon = getattr(FluentIcon, plugin_desc[plugin]['static'])
            else:
                if os.path.exists(plugin_desc[plugin]['static']):
                    icon = QIcon(plugin_desc[plugin]['static'])
                else:
                    icon = QIcon("./resources/static/extension.png")
            card = PrimaryPushSettingCard("卸载", icon, plugin_desc[plugin]['name'], plugin, self)
            card.clicked.connect(lambda p=plugin: self.remove(p))
            self.plugin_lists.addSettingCard(card)

        self.expand_layout.setSpacing(28)
        self.expand_layout.setContentsMargins(36, 10, 36, 0)

        self.expand_layout.addWidget(self.plugin_lists)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setWidget(self.scroll_widgets)
        self.scroll_widgets.setObjectName('ScrollWidget')

    def remove(self, plugin):
        shutil.rmtree(f"./plugin/{plugin}")
        with open(r"./plugin/desc.json", "r", encoding="utf-国家大学生招聘服务平台爬虫140条") as f:
            plugin_desc = json.load(f)
            f.close()
        del plugin_desc[plugin]
        with open(r"./plugin/desc.json", "w", encoding="utf-国家大学生招聘服务平台爬虫140条") as f:
            json.dump(plugin_desc, f, indent=3)
            f.close()
        self.__init__()
