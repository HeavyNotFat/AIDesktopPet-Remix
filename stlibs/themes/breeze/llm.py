
from __future__ import annotations

import contextlib
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import Config, ConfigLoader, SharingData, get_model_lists, notify, refresh_coop, refresh_models
from ...ai.rag.engine import SUPPORTED_ENGINES
from .primitives import (
    BreezeButton,
    BreezeCard,
    BreezeComboBox,
    BreezeLabel,
    BreezeLineEdit,
    BreezeScrollArea,
    BreezeSlider,
    BreezeSwitch,
    BreezeTable,
    BreezeTabWidget,
    BreezeTextEdit,
)
from .theme import ACCENT_DEEP, ACCENT_SOFT, PRIMARY_DEEP, RADIUS_LARGE, SURFACE, font_css
from .window import PageHint, PageTitle


def _section(text: str, parent=None) -> BreezeLabel:
    """小节标题：主色偏深的粗体小字。"""
    label = BreezeLabel(text, parent)
    label.setStyleSheet(
        f"QLabel {{ background: transparent; border: none; color: {PRIMARY_DEEP}; {font_css(13, weight=600)} }}"
    )
    return label


def _count_chip(parent=None) -> BreezeLabel:
    """数量小胶囊：浅雾蓝底 + 雾蓝字。"""
    chip = BreezeLabel("", parent)
    chip.setStyleSheet(f"""
        QLabel {{
            background: {ACCENT_SOFT};
            color: {ACCENT_DEEP};
            border: none;
            border-radius: {RADIUS_LARGE}px;
            padding: 2px 10px;
            {font_css(12)}
        }}
    """)
    return chip


class BasicWidgetScroll(QWidget):
    """「新增 LLM」页的表单：别名 / 模型名 / Key / URL。"""

    def __init__(self, parent):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # AI 名字
        self.ai_name = BreezeLineEdit("给AI取的别名", parent=self)
        self.ai_name.setMinimumWidth(260)
        layout.addWidget(BreezeCard(
            "AI的名字",
            self.ai_name,
            "给AI取的别名",
            parent=self,
        ))

        # AI Model
        self.ai_model = BreezeLineEdit("服务商要求的模型名，例如 deepseek-chat", parent=self)
        self.ai_model.setMinimumWidth(280)
        layout.addWidget(BreezeCard(
            "AI模型",
            self.ai_model,
            "需要使用的AI模型",
            parent=self,
        ))

        # API Key
        self.api_key = BreezeLineEdit("sk-…（本地服务可以不填）", parent=self)
        self.api_key.setMinimumWidth(320)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(BreezeCard(
            "AI Key密钥",
            self.api_key,
            "访问AI必要的密钥 Key",
            parent=self,
        ))

        # Base URL
        self.api_url = BreezeLineEdit("https://api.deepseek.com", parent=self)
        self.api_url.setMinimumWidth(320)
        layout.addWidget(BreezeCard(
            "Base URL",
            self.api_url,
            "AI响应的API Url",
            parent=self,
        ))

        # 添加
        self.add_button = BreezeButton("添加", parent=self)
        self.add_button.set_border()
        self.add_button.clicked.connect(self.add_llm)
        layout.addWidget(BreezeCard(
            "保存配置",
            self.add_button,
            "添加AI配置",
            parent=self,
        ))

        # 删除已有配置
        self.existing = BreezeComboBox(parent=self)
        self.existing.setMinimumWidth(320)
        self.existing.currentIndexChanged.connect(self.sync_remove_button)
        self.remove_button = BreezeButton("删除", parent=self)
        self.remove_button.setMinimumWidth(110)
        self.remove_button.clicked.connect(self.remove_llm)
        layout.addWidget(BreezeCard(
            "删除配置",
            self._build_remove_row(),
            "选中后删除，密钥一并移除",
            parent=self,
            stacked=True,
        ))

        layout.addWidget(PageHint("配置写在 resources/configure.json：别名进聊天列表，密钥只留在本机。"))
        layout.addStretch()

        self.reload_existing()

    def _build_remove_row(self):
        # 下拉框撑开、按钮固定宽
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.existing, 1)
        layout.addWidget(self.remove_button, 0)
        return row

    def reload_existing(self):
        self.existing.clear()
        for alias, parameters in Config.models.items():
            name = (parameters or {}).get("name") or ""
            self.existing.addItem(f"{alias}   ·   {name}" if name else alias, alias)
        self.sync_remove_button()

    def select_existing(self, alias: str) -> bool:
        index = self.existing.findData(alias)
        if index < 0:
            return False
        self.existing.setCurrentIndex(index)
        return True

    def sync_remove_button(self):
        self.remove_button.setEnabled(bool(self.selected_alias()))

    def selected_alias(self) -> str:
        data = self.existing.currentData()
        return str(data).strip() if data else ""

    def add_llm(self):
        name = self.ai_name.text().strip()
        model = self.ai_model.text().strip()
        base_url = self.api_url.text().strip()
        api_key = self.api_key.text().strip()

        if not name:
            notify("请先填写 AI 的名字（配置里的别名）", "error")
            return
        if name in Config.models:
            notify(f"别名「{name}」已经存在，换个名字或先删除旧配置", "error")
            return
        if not model:
            notify("请填写 AI 模型名（服务商要求的 model 名）", "error")
            return
        if not base_url:
            notify("请填写 Base URL（例如 https://api.deepseek.com）", "error")
            return

        Config.models[name] = {
            "name": model,
            "apikey": api_key or "not-needed",
            "baseurl": base_url,
        }
        ConfigLoader.save_config()

        for field in (self.ai_name, self.ai_model, self.api_key, self.api_url):
            if isinstance(field, BreezeLineEdit):
                field.setText("")

        self.reload_existing()
        refresh_models(name)
        notes = "，未填 Key 已按 not-needed 处理" if not api_key else ""
        notify(f"已添加 API 模型「{name}」，聊天列表已刷新{notes}", "success", 3500)

    def remove_llm(self):
        name = self.selected_alias()
        if not name or name not in Config.models:
            notify("先在下拉里选择要删除的配置", "warning")
            return

        Config.models.pop(name, None)
        ConfigLoader.save_config()
        self.reload_existing()
        refresh_models()
        notify(f"已删除 API 模型「{name}」，密钥已从配置里移除", "success", 3500)


class Basic(QWidget):
    """「新增 LLM」页：表单放进滚动区。"""

    def __init__(self, parent):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.card = BasicWidgetScroll(self)
        self.scroll = BreezeScrollArea(self)
        self.scroll.setWidget(self.card)
        layout.addWidget(self.scroll)


class Memory(QWidget):
    """记忆：两个总开关 + 按模型看它的记忆 JSON。"""

    def __init__(self, parent):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        self.memory_switch = BreezeSwitch(parent=self)
        self.memory_switch.setChecked(Config.memory['shortterm'])
        self.memory_switch.stateChanged.connect(self.check_short)
        layout.addWidget(BreezeCard(
            "短期即时记忆",
            self.memory_switch,
            "只记当前这段对话，关掉就不带上下文",
            parent=self,
        ))

        self.longterm_memory_switch = BreezeSwitch(parent=self)
        self.longterm_memory_switch.setChecked(Config.memory['longterm'])
        self.longterm_memory_switch.stateChanged.connect(self.check_long)
        layout.addWidget(BreezeCard(
            "长期存储记忆",
            self.longterm_memory_switch,
            "落盘保存，下次打开还记得",
            parent=self,
        ))

        # 选模型这一行直接挂在页面上，别套一层容器
        picker = QHBoxLayout()
        picker.setContentsMargins(0, 0, 0, 0)
        picker.setSpacing(8)
        picker.addWidget(BreezeLabel("看哪个模型的记忆", self), 0)
        self.model_selector = BreezeComboBox(self)
        self.model_selector.setMinimumWidth(260)
        self.model_selector.currentTextChanged.connect(self.show_model)
        picker.addWidget(self.model_selector, 1)
        layout.addLayout(picker)

        self.memory_json = BreezeTextEdit("", parent=self)
        layout.addWidget(self.memory_json, 1)

        self.models: list = []
        self.reload_models()

    def showEvent(self, event, /):
        """每次切到这一页都重新扫一遍模型。"""
        super().showEvent(event)
        self.reload_models()

    @staticmethod
    def model_names() -> list:
        names = [*get_model_lists(), *(values['name'] for values in Config.models.values())]
        seen = []
        for name in names:
            if name and name not in seen:
                seen.append(name)
        return seen

    def reload_models(self):
        """重新扫描模型（选中项尽量保留）。"""
        selected = self.model_selector.currentText()
        self.models = self.model_names()

        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        self.model_selector.addItems(self.models)
        if selected in self.models:
            self.model_selector.setCurrentText(selected)
        self.model_selector.blockSignals(False)

        if not self.models:
            self.memory_json.setPlainText("还没有可用模型（先去「新增 LLM」加一个，或 ollama pull 一个）")
            return
        self.show_model(self.model_selector.currentText())

    def refresh(self):
        """按契约暴露的短名字，和 reload_models 一回事。"""
        self.reload_models()

    def show_model(self, model: str):
        """切到某个模型时刷新展示区。"""
        if not model:
            return

        self.current_model = model
        self.memory_json.setPlainText(json.dumps(self._history(model), ensure_ascii=False, indent=3))
        SharingData.add_memory_to_ui[model] = self._receive

    @staticmethod
    def _history(model: str) -> list:
        for llm in list(SharingData.llm_instances.values()):
            if getattr(llm, 'model', None) == model:
                return getattr(getattr(llm, 'memory', None), 'messages', [])
        return []

    def _receive(self, data: list):
        """聊天那边推过来的记忆更新，只认当前选中的模型。"""
        if not isinstance(data, (list, tuple)) or len(data) < 2:
            return
        model, messages = data[0], data[1]
        if model == getattr(self, 'current_model', None):
            self.memory_json.setText(json.dumps(messages, ensure_ascii=False, indent=3))

    @staticmethod
    def check_short(boo: bool):
        Config.memory['shortterm'] = boo
        ConfigLoader.save_config()

    @staticmethod
    def check_long(boo: bool):
        Config.memory['longterm'] = boo
        ConfigLoader.save_config()


class RAGWidgetScroll(QWidget):
    """RAG 配置：开关、知识库、引擎、分块参数、识别模型。"""

    def __init__(self, parent):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 下次启动清除缓存
        clear_cache_next_time = BreezeButton("清除缓存", parent=self)
        clear_cache_next_time.clicked.connect(self.clear_cache)
        layout.addWidget(BreezeCard(
            "清除缓存",
            clear_cache_next_time,
            "下次启动时清除RAG缓存（加入新RAG时请清除）",
            parent=self,
        ))

        # 启用 RAG
        enable_rag_switch = BreezeSwitch(parent=self)
        enable_rag_switch.setChecked(Config.rag['enable'])
        enable_rag_switch.stateChanged.connect(self.check_enable)
        layout.addWidget(BreezeCard(
            "启用RAG",
            enable_rag_switch,
            "启用知识库检索",
            parent=self,
        ))

        # BM25 检索
        enable_bm25_switch = BreezeSwitch(parent=self)
        enable_bm25_switch.setChecked(Config.rag['bm25_enable'])
        enable_bm25_switch.stateChanged.connect(self.check_bm25_enable)
        layout.addWidget(BreezeCard(
            "启用BM25",
            enable_bm25_switch,
            "强化关键字检索，答案更符合问题",
            parent=self,
        ))

        # 压缩 RAG
        compressed_rag_switch = BreezeSwitch(parent=self)
        compressed_rag_switch.setChecked(Config.rag['compressed_enable'])
        compressed_rag_switch.stateChanged.connect(self.check_compressed_enable)
        layout.addWidget(BreezeCard(
            "启用压缩RAG",
            compressed_rag_switch,
            "RAG 字段过长压缩RAG",
            parent=self,
        ))

        # 配置知识库类型
        self.knowledge_base_type = BreezeComboBox(parent=self)
        self.knowledge_base_type.setMinimumWidth(220)
        for dir_ in self._collections():
            self.knowledge_base_type.addItem(dir_)
        self.knowledge_base_type.setCurrentText(Config.rag['collection'])
        self.knowledge_base_type.currentTextChanged.connect(self.check_type)
        layout.addWidget(BreezeCard(
            "知识库类型",
            self.knowledge_base_type,
            "选择知识库类型",
            parent=self,
        ))

        # RAG 引擎
        rag_engine = BreezeComboBox(parent=self)
        rag_engine.setMinimumWidth(220)
        rag_engine.addItems(SUPPORTED_ENGINES)
        rag_engine.setCurrentText(Config.rag['engine'])
        rag_engine.currentTextChanged.connect(self.check_engine)
        layout.addWidget(BreezeCard(
            "RAG引擎",
            rag_engine,
            "Chroma 轻量，Lance多元",
            parent=self,
        ))

        # 区块大小
        block_size = BreezeSlider(Qt.Orientation.Horizontal, self)
        block_size.setMinimum(128)
        block_size.setMaximum(2048)
        block_size.setValue(Config.rag['chunks'])
        block_size_card = BreezeCard(
            f"区块大小（{Config.rag['chunks']} / tks）",
            block_size,
            "单次筛选的最大 Tokens",
            parent=self,
            stacked=True,
        )
        block_size.valueChanged.connect(self.check_chunks)
        block_size.valueChanged.connect(
            lambda: block_size_card.set_title(f"区块大小（{block_size.value()} / tks）")
        )
        layout.addWidget(block_size_card)

        # 重排序
        top_k_slider = BreezeSlider(Qt.Orientation.Horizontal, self)
        top_k_slider.setMaximum(50)
        top_k_slider.setValue(Config.rag['top_k'])
        top_k_card = BreezeCard(
            f"重排序（{Config.rag['top_k']}）",
            top_k_slider,
            "（Cross-Encoder）增强用户体验(设置top_k)",
            parent=self,
            stacked=True,
        )
        top_k_slider.valueChanged.connect(self.check_top_k)
        top_k_slider.valueChanged.connect(lambda: top_k_card.set_title(f"重排序（{top_k_slider.value()}）"))
        layout.addWidget(top_k_card)

        # Overlap
        overlap = BreezeSlider(Qt.Orientation.Horizontal, self)
        overlap.setMaximum(100)
        overlap.setValue(Config.rag['overlap'])
        overlap_card = BreezeCard(
            f"重叠率（{Config.rag['overlap']} %）",
            overlap,
            "话语气和指代关系的连续性。",
            parent=self,
            stacked=True,
        )
        overlap.valueChanged.connect(self.check_overlap)
        overlap.valueChanged.connect(lambda: overlap_card.set_title(f"重叠率（{overlap.value()} %）"))
        layout.addWidget(overlap_card)

        # Embedding Model
        self.embedding_model = BreezeLineEdit("", parent=self)
        self.embedding_model.setText(Config.rag['embedding'])
        self.embedding_model.setMinimumWidth(240)
        self.embedding_model.textChanged.connect(self.check_embedding)
        layout.addWidget(BreezeCard(
            "嵌入（向量）模型",
            self.embedding_model,
            "捕获文本的语义信息",
            parent=self,
        ))

        # Model
        self.model = BreezeComboBox(parent=self)
        self.model.addItems(get_model_lists())
        self.model.setCurrentText(Config.rag['model'])
        self.model.setMinimumWidth(280)
        self.model.currentTextChanged.connect(self.check_model)
        layout.addWidget(BreezeCard(
            "识别模型",
            self.model,
            "识别是否需要RAG检索",
            parent=self,
        ))

        layout.addWidget(PageHint("换知识库或换嵌入模型之后记得清一次缓存，否则还是老向量。"))
        layout.addStretch()

        for methods in dir(self):
            if methods.startswith('check_'):
                with contextlib.suppress(Exception):  # 逐个字段容错，缺字段不影响其它配置
                    getattr(self, methods)()

    @staticmethod
    def _collections() -> list[str]:
        """./resources/rag 下的知识库，chroma_db 由引擎自建。"""
        try:
            entries = os.listdir("./resources/rag")
        except OSError:
            # 目录不在（打包、换过工作目录）时返回空表
            return []
        return [name for name in entries if name != "chroma_db"]

    def check_model(self, text: str | None = None):
        if text is None:
            text = self.model.currentText()
        Config.rag['model'] = text
        ConfigLoader.save_config()

    def check_type(self, text: str | None = None):
        if text is None:
            text = self.knowledge_base_type.currentText()
        Config.rag['collection'] = text
        ConfigLoader.save_config()

    def check_embedding(self, text: str | None = None):
        if text is None:
            text = self.embedding_model.text()
        Config.rag['embedding'] = text
        ConfigLoader.save_config()

    @staticmethod
    def clear_cache():
        Config.rag['clear_cache'] = True
        ConfigLoader.save_config()

    @staticmethod
    def check_enable(boo: bool):
        Config.rag['enable'] = boo
        ConfigLoader.save_config()

    @staticmethod
    def check_compressed_enable(boo: bool):
        Config.rag['compressed_enable'] = boo
        ConfigLoader.save_config()

    @staticmethod
    def check_bm25_enable(boo: bool):
        Config.rag['bm25_enable'] = boo
        ConfigLoader.save_config()

    @staticmethod
    def check_engine(value: str):
        Config.rag['engine'] = value
        ConfigLoader.save_config()

    @staticmethod
    def check_top_k(value: int):
        Config.rag['top_k'] = value
        ConfigLoader.save_config()

    @staticmethod
    def check_chunks(value: int):
        Config.rag['chunks'] = value
        ConfigLoader.save_config()

    @staticmethod
    def check_overlap(value: int):
        Config.rag['overlap'] = value
        ConfigLoader.save_config()


class RAG(QWidget):
    """RAG 页：配置项放进滚动区。"""

    def __init__(self, parent):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.card = RAGWidgetScroll(self)
        self.scroll = BreezeScrollArea(self)
        self.scroll.setWidget(self.card)
        layout.addWidget(self.scroll)


class MCP(QWidget):
    """MCP：总开关 + 服务器表，表格里改完立刻落盘。"""

    def __init__(self, parent):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # 开启MCP
        self.mcp_switch = BreezeSwitch(parent=self)
        self.mcp_switch.setChecked(Config.mcp['enable'])
        self.mcp_switch.stateChanged.connect(self.check_mcp)
        layout.addWidget(BreezeCard(
            "开启MCP",
            self.mcp_switch,
            "允许模型调用本机的 MCP 服务器",
            parent=self,
        ))

        # MCP表格
        self.mcp_table = BreezeTable(parent=self)
        self.mcp_table.setHorizontalHeaderLabels(['服务器ID', '参数', '启动命令'])
        for server in Config.mcp['mcp']:
            self.add_data(server['server'], ' '.join(server['args']), server['command'])
        # 参数最长，让它吃掉多余宽度；首尾两列按内容给固定宽
        self.mcp_table.setColumnWidth(0, 130)
        self.mcp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mcp_table.horizontalHeader().setStretchLastSection(False)
        self.mcp_table.setColumnWidth(2, 140)
        self.mcp_table.itemChanged.connect(self.change_data)
        layout.addWidget(self.mcp_table, 1)

        # 增加MCP面板
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        add_mcp_button = BreezeButton("添加MCP", parent=self)
        add_mcp_button.set_border()
        add_mcp_button.clicked.connect(self.add_mcp)
        buttons.addWidget(add_mcp_button)
        remove_mcp_button = BreezeButton("删除MCP", parent=self)
        remove_mcp_button.clicked.connect(self.remove_mcp)
        buttons.addWidget(remove_mcp_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        layout.addWidget(PageHint("双击单元格直接改：参数用空格分开，改完自动保存。"))

    @staticmethod
    def change_data(item: QTableWidgetItem):
        servers = Config.mcp.setdefault('mcp', [])
        while len(servers) <= item.row():
            servers.append({'server': "", 'args': [], 'command': ""})

        if item.column() == 0:
            servers[item.row()]['server'] = item.text()
        elif item.column() == 1:
            servers[item.row()]['args'] = item.text().split(' ')
        else:
            servers[item.row()]['command'] = item.text()
        ConfigLoader.save_config()

    @staticmethod
    def check_mcp(boo: bool):
        Config.mcp['enable'] = boo
        ConfigLoader.save_config()

    def _cell(self, row, column):
        item = self.mcp_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def save(self):
        """把整张 MCP 表写回配置。"""
        servers = [
            {
                "server": self._cell(row, 0),
                "args": self._cell(row, 1).split(' '),
                "command": self._cell(row, 2),
            }
            for row in range(self.mcp_table.rowCount())
        ]
        Config.mcp['mcp'] = servers
        ConfigLoader.save_config()
        notify(f"已保存 {len(servers)} 个 MCP 服务器", "success", 3000)

    def add_data(self, server, args, command):
        row = self.mcp_table.rowCount()
        self.mcp_table.insertRow(row)
        self.mcp_table.setItem(row, 0, QTableWidgetItem(server))
        self.mcp_table.setItem(row, 1, QTableWidgetItem(args))
        self.mcp_table.setItem(row, 2, QTableWidgetItem(command))

    def add_mcp(self):
        # 空行也得建出单元格，否则那一行点不进去编辑
        row = self.mcp_table.rowCount()
        self.mcp_table.blockSignals(True)
        self.mcp_table.insertRow(row)
        for column in range(3):
            self.mcp_table.setItem(row, column, QTableWidgetItem(""))
        self.mcp_table.blockSignals(False)

        Config.mcp['mcp'].append({'server': "", 'args': [], 'command': ""})
        notify(f"已添加一行（第 {row + 1} 行），填写后自动保存", "info", 3000)

    def remove_mcp(self):
        # 删除表格
        row = self.mcp_table.currentRow()
        if row < 0:
            return  # 没选中行时 pop(-1) 会误删最后一条
        self.mcp_table.removeRow(row)
        Config.mcp['mcp'].pop(row)
        ConfigLoader.save_config()


class Cooperation(QWidget):
    """多模型协作：主模型出稿/定稿，配在表里的模型按角色给意见。"""

    MODES = (("review", "评审改稿"), ("parallel", "并行汇总"))

    def __init__(self, parent):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        columns = QHBoxLayout()
        columns.setSpacing(10)

        # 左栏：开关三件套 + 可用模型（搜索 + 列表 + 加入按钮）
        left = QVBoxLayout()
        left.setSpacing(8)

        self.enable_switch = BreezeSwitch(parent=self)
        self.enable_switch.setChecked(bool(Config.coop["enable"]))
        self.enable_switch.stateChanged.connect(self.check_enable)
        left.addWidget(BreezeCard(
            "开启多模型协作",
            self.enable_switch,
            "主模型之外再叫几个模型帮忙",
            parent=self,
        ))

        self.mode_combo = BreezeComboBox(parent=self)
        self.mode_combo.addItems([label for _, label in self.MODES])
        self.mode_combo.setCurrentIndex(max(0, [key for key, _ in self.MODES].index(self._mode())))
        self.mode_combo.currentIndexChanged.connect(self.check_mode)
        left.addWidget(BreezeCard(
            "协作模式",
            self.mode_combo,
            "评审改稿：逐个提意见；并行汇总：一起回答",
            parent=self,
        ))

        self.rounds_slider = BreezeSlider(Qt.Orientation.Horizontal, self)
        self.rounds_slider.setMinimum(1)
        self.rounds_slider.setMaximum(3)
        self.rounds_slider.setValue(int(Config.coop.get("rounds") or 1))
        self.rounds_slider.valueChanged.connect(self.check_rounds)
        rounds_card = BreezeCard(
            f"评审轮数（{self.rounds_slider.value()} 轮）",
            self.rounds_slider,
            "轮数越多改得越细，也越慢",
            parent=self,
            stacked=True,
        )
        self.rounds_slider.valueChanged.connect(
            lambda: rounds_card.set_title(f"评审轮数（{self.rounds_slider.value()} 轮）")
        )
        left.addWidget(rounds_card)

        # 数量放在标题右边，一眼能看出筛掉了多少
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(_section("可用模型（双击加入协作）", self), 1)
        self.available_label = _count_chip(self)
        head.addWidget(self.available_label, 0)
        left.addLayout(head)

        self.model_search = BreezeLineEdit("搜索模型…", parent=self)
        self.model_search.textChanged.connect(self.filter_models)
        left.addWidget(self.model_search)

        self.model_table = BreezeTable(parent=self)
        self.model_table.setHorizontalHeaderLabels(["模型", "来源"])
        self.model_table.horizontalHeader().setStretchLastSection(False)
        self.model_table.setColumnWidth(0, 190)
        self.model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.model_table.setColumnWidth(1, 80)
        self.model_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model_table.cellDoubleClicked.connect(lambda *_args: self.add_selected())
        left.addWidget(self.model_table, 1)

        join_button = BreezeButton("加入协作 →", parent=self)
        join_button.set_border()
        join_button.clicked.connect(self.add_selected)
        left.addWidget(join_button)

        columns.addLayout(left, 1)

        # 右栏：协作成员表 + 一排操作
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(_section("协作成员（主模型之外，按角色给意见）", self))

        self.agent_table = BreezeTable(parent=self)
        self.agent_table.setHorizontalHeaderLabels(["模型", "角色名", "提示词"])
        self.agent_table.setColumnWidth(0, 95)
        self.agent_table.setColumnWidth(1, 85)
        self.agent_table.setColumnWidth(2, 115)
        self.agent_table.itemChanged.connect(self.change_data)
        right.addWidget(self.agent_table, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for label, slot in (
            ("添加空行", self.add_agent),
            ("删除选中", self.remove_agent),
            ("保存协作", self.save_agents),
        ):
            button = BreezeButton(label, parent=self)
            if label == "保存协作":
                button.set_border()
            button.clicked.connect(slot)
            buttons.addWidget(button)
        right.addLayout(buttons)

        columns.addLayout(right, 1)
        root.addLayout(columns, 1)

        self.refresh()

    def _mode(self):
        mode = str(Config.coop.get("mode") or "review")
        return mode if mode in dict(self.MODES) else "review"

    def showEvent(self, event, /):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        """切到这个页签时重新读配置。"""
        self.agent_table.blockSignals(True)
        self.agent_table.setRowCount(0)
        for agent in Config.coop.get("agents") or []:
            self.add_row(agent.get("model", ""), agent.get("name", ""), agent.get("prompt", ""))
        self.agent_table.blockSignals(False)

        self.models = self._available_models()
        self.filter_models(self.model_search.text())

    @staticmethod
    def _available_models() -> list:
        """可用模型（云端别名 + 本地模型），带来源标识、去过重。"""
        rows = [(alias, str(values.get("name") or alias), "API") for alias, values in Config.models.items()]
        rows += [(model, model, "本地") for model in get_model_lists()]

        seen, unique = set(), []
        for key, model, source in rows:
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append((key, model, source))
        return unique

    @staticmethod
    def _count_text(matched: int, total: int, keyword: str = "") -> str:
        """数量文案：总数或匹配数，没有模型时给指路。"""
        if not total:
            return "（还没有可用模型，先去「新增 LLM」加一个）"
        if keyword:
            return f"匹配 {matched} / 共 {total}"
        return f"{total} 个模型"

    def filter_models(self, keyword: str):
        """按关键字筛可用模型。"""
        keyword = (keyword or "").strip().lower()
        rows = [row for row in self.models
                if not keyword or keyword in row[0].lower() or keyword in row[1].lower()]

        table = self.model_table
        table.blockSignals(True)
        table.setRowCount(0)
        for key, model, source in rows:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(key))
            table.setItem(row, 1, QTableWidgetItem(source))
            table.item(row, 0).setToolTip(model)
        table.blockSignals(False)
        table.rows = rows

        # 数量文案跟着列表走，别和表里实际行数对不上
        self.available_label.setText(self._count_text(len(rows), len(self.models), keyword))

    def add_selected(self):
        """把列表里选中的模型加成协作成员。"""
        rows = getattr(self.model_table, "rows", [])
        index = self.model_table.currentRow()
        if index < 0 or index >= len(rows):
            notify("先在上面的列表里选一个模型", "warning")
            return

        model = rows[index][0]
        if any(self._cell(row, 0) == model for row in range(self.agent_table.rowCount())):
            notify(f"「{model}」已经在协作成员里了", "warning")
            return

        self.add_row(model, "", "")
        notify(f"已加入协作：{model}（记得点保存协作）", "success")

    def add_row(self, model, name, prompt):
        row = self.agent_table.rowCount()
        self.agent_table.insertRow(row)
        self.agent_table.setItem(row, 0, QTableWidgetItem(model))
        self.agent_table.setItem(row, 1, QTableWidgetItem(name))
        self.agent_table.setItem(row, 2, QTableWidgetItem(prompt))

    def _collect(self):
        agents = []
        for row in range(self.agent_table.rowCount()):
            model = self._cell(row, 0)
            name = self._cell(row, 1)
            prompt = self._cell(row, 2)
            if not model and not name and not prompt:
                continue
            if not model:
                notify(f"第 {row + 1} 行没有填模型名，已跳过", "warning")
                continue
            agents.append({"model": model, "name": name or model, "prompt": prompt})
        return agents

    def _cell(self, row, column):
        item = self.agent_table.item(row, column)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def check_enable(boo: bool):
        Config.coop["enable"] = boo
        ConfigLoader.save_config()
        refresh_coop()
        notify(f"多模型协作已{'开启' if boo else '关闭'}", "success" if boo else "info")

    @staticmethod
    def check_mode(index: int):
        mode = Cooperation.MODES[max(0, min(index, len(Cooperation.MODES) - 1))][0]
        Config.coop["mode"] = mode
        ConfigLoader.save_config()
        refresh_coop()
        notify(f"协作模式：{dict(Cooperation.MODES)[mode]}", "info")

    @staticmethod
    def check_rounds(value: int):
        Config.coop["rounds"] = int(value)
        ConfigLoader.save_config()
        refresh_coop()

    @staticmethod
    def change_data(item: QTableWidgetItem):
        agents = Config.coop.setdefault("agents", [])
        while len(agents) <= item.row():
            agents.append({"model": "", "name": "", "prompt": ""})

        key = {0: "model", 1: "name", 2: "prompt"}.get(item.column())
        if key is None:
            return
        agents[item.row()][key] = item.text().strip()
        ConfigLoader.save_config()
        refresh_coop()

    def add_agent(self):
        row = self.agent_table.rowCount()
        # 建行时 setItem 会触发 itemChanged，先静音免得重复追加
        self.agent_table.blockSignals(True)
        self.add_row("", "", "")
        self.agent_table.blockSignals(False)

        Config.coop.setdefault("agents", []).append({"model": "", "name": "", "prompt": ""})
        ConfigLoader.save_config()
        notify(f"已添加一行（第 {row + 1} 行），填好模型后点「保存协作」", "info", 3000)

    def remove_agent(self):
        row = self.agent_table.currentRow()
        if row < 0:
            notify("先在表里选中一行", "warning")
            return

        self.agent_table.blockSignals(True)
        self.agent_table.removeRow(row)
        self.agent_table.blockSignals(False)

        agents = Config.coop.setdefault("agents", [])
        if row < len(agents):
            agents.pop(row)
        ConfigLoader.save_config()
        refresh_coop()
        notify("已删除该协作模型", "success", 2000)

    def save_agents(self):
        agents = self._collect()
        known = set(Config.models) | set(get_model_lists())
        unknown = [agent["model"] for agent in agents if agent["model"] not in known]

        Config.coop["agents"] = agents
        ConfigLoader.save_config()
        refresh_coop()

        if not agents:
            notify("协作配置已保存，但还没有配置任何模型", "warning")
        elif unknown:
            notify(f"已保存，但这些模型现在不存在：{'、'.join(unknown)}", "warning", 4000)
        else:
            notify(f"协作配置已保存：主模型 + {len(agents)} 个协作模型", "success", 3000)

    def save(self):
        """按契约暴露的短名字，落盘协作成员。"""
        self.save_agents()


class Skills(QWidget):
    """技能：可以套在提问外面的提示词，聊天时按 /名字 使用。"""

    def __init__(self, parent):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        root.addWidget(_section("技能列表（聊天时打 /名字，或点聊天窗的「技能」按钮）", self))

        self.skill_table = BreezeTable(parent=self)
        self.skill_table.setHorizontalHeaderLabels(["技能名", "说明", "提示词"])
        self.skill_table.setColumnWidth(0, 110)
        self.skill_table.setColumnWidth(1, 140)
        self.skill_table.setColumnWidth(2, 330)
        self.skill_table.itemChanged.connect(self.change_data)
        root.addWidget(self.skill_table, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for label, slot in (
            ("添加技能", self.add_skill),
            ("删除选中", self.remove_skill),
            ("保存技能", self.save_skills),
        ):
            button = BreezeButton(label, parent=self)
            if label == "保存技能":
                button.set_border()
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch()
        root.addLayout(buttons)

        self.refresh()

    def showEvent(self, event, /):
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        self.skill_table.blockSignals(True)
        self.skill_table.setRowCount(0)
        for skill in Config.skills or []:
            if not isinstance(skill, dict):
                continue
            self.add_row(skill.get("name", ""), skill.get("description", ""), skill.get("prompt", ""))
        self.skill_table.blockSignals(False)

    def add_row(self, name, description, prompt):
        row = self.skill_table.rowCount()
        self.skill_table.insertRow(row)
        self.skill_table.setItem(row, 0, QTableWidgetItem(name))
        self.skill_table.setItem(row, 1, QTableWidgetItem(description))
        self.skill_table.setItem(row, 2, QTableWidgetItem(prompt))

    def _cell(self, row, column):
        item = self.skill_table.item(row, column)
        return item.text().strip() if item is not None else ""

    def _collect(self):
        skills = []
        names = set()
        for row in range(self.skill_table.rowCount()):
            name = self._cell(row, 0)
            description = self._cell(row, 1)
            prompt = self._cell(row, 2)
            if not name and not prompt:
                continue
            if not name:
                notify(f"第 {row + 1} 行没有技能名，已跳过", "warning")
                continue
            if name in names:
                notify(f"技能名「{name}」重复了，后面的那条已跳过", "warning")
                continue
            names.add(name)
            skills.append({"name": name, "description": description, "prompt": prompt})
        return skills

    @staticmethod
    def change_data(item: QTableWidgetItem):
        skills = Config.skills if isinstance(Config.skills, list) else []
        Config.skills = skills
        while len(skills) <= item.row():
            skills.append({"name": "", "description": "", "prompt": ""})

        key = {0: "name", 1: "description", 2: "prompt"}.get(item.column())
        if key is None:
            return
        skills[item.row()][key] = item.text().strip()
        ConfigLoader.save_config()

    def add_skill(self):
        row = self.skill_table.rowCount()
        self.skill_table.blockSignals(True)
        self.add_row("", "", "")
        self.skill_table.blockSignals(False)

        if not isinstance(Config.skills, list):
            Config.skills = []
        Config.skills.append({"name": "", "description": "", "prompt": ""})
        ConfigLoader.save_config()
        notify(f"已添加一行（第 {row + 1} 行），填好后点「保存技能」", "info", 3000)

    def remove_skill(self):
        row = self.skill_table.currentRow()
        if row < 0:
            notify("先在表里选中一行", "warning")
            return

        self.skill_table.blockSignals(True)
        self.skill_table.removeRow(row)
        self.skill_table.blockSignals(False)

        skills = Config.skills if isinstance(Config.skills, list) else []
        Config.skills = skills
        if row < len(skills):
            skills.pop(row)
        ConfigLoader.save_config()
        notify("已删除该技能", "success", 2000)

    def save_skills(self):
        skills = self._collect()
        Config.skills = skills
        ConfigLoader.save_config()

        if not skills:
            notify("技能列表已清空", "warning")
        else:
            notify(f"已保存 {len(skills)} 个技能：{'、'.join(item['name'] for item in skills)}", "success", 3000)

    def save(self):
        """按契约暴露的短名字，落盘技能列表。"""
        self.save_skills()


class LLMPage(QWidget):
    """LLM 设置总页：六个页签。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("LLM")
        self.setWindowTitle("LLM 设置")
        self.setStyleSheet(f"QWidget#LLM {{ background: {SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.window_title = PageTitle(self.windowTitle())
        root.addWidget(self.window_title)
        root.addWidget(PageHint("模型会进聊天列表；记忆、知识库、MCP、协作与技能在下面几页里调。"))

        self.tab_widget = BreezeTabWidget(self)
        self.tab_widget.addTab(Basic(self), "新增 LLM")
        self.tab_widget.addTab(Memory(self), "记忆 配置")
        self.tab_widget.addTab(RAG(self), "RAG 配置")
        self.tab_widget.addTab(MCP(self), "MCP 设置")
        self.tab_widget.addTab(Cooperation(self), "协作 设置")
        self.tab_widget.addTab(Skills(self), "技能 Skills")
        root.addWidget(self.tab_widget, 1)


__all__ = [
    "Basic",
    "BasicWidgetScroll",
    "Cooperation",
    "LLMPage",
    "MCP",
    "Memory",
    "RAG",
    "RAGWidgetScroll",
    "Skills",
]
