import json
import os

from ...ai.rag.engine import SUPPORTED_ENGINES
from ... import Config, ConfigLoader, SharingData
from ... import get_model_lists, notify, refresh_coop, refresh_models

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTableWidgetItem, QHeaderView
from PySide6.QtCore import QRect, Qt


class BasicWidgetScroll(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLineEdit, HackerButton, HackerCard, HackerComboBox

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # AI 名字
        self.ai_name = HackerLineEdit("", parent=self)
        ai_name_card = HackerCard(
            "AI的名字",
            self.ai_name,
            "给AI取的别名"
        )
        layout.addWidget(ai_name_card)
        layout.addStretch()

        # AI Model
        self.ai_model = HackerLineEdit("", parent=self)
        self.ai_model.setFixedWidth(250)
        ai_model_card = HackerCard(
            "AI模型",
            self.ai_model,
            "需要使用的AI模型"
        )
        layout.addWidget(ai_model_card)
        layout.addStretch()

        # API Key
        self.api_key = HackerLineEdit("", parent=self)
        self.api_key.setFixedWidth(350)
        self.api_key.setEchoMode(QLineEdit.Password)
        api_key_card = HackerCard(
            "AI Key密钥",
            self.api_key,
            "访问AI必要的密钥 Key"
        )
        layout.addWidget(api_key_card)
        layout.addStretch()

        # Base URL
        self.api_url = HackerLineEdit("", parent=self)
        self.api_url.setFixedWidth(350)
        api_url_card = HackerCard(
            "Base URL",
            self.api_url,
            "AI响应的API Url"
        )
        layout.addWidget(api_url_card)
        layout.addStretch()

        # 添加
        self.add_button = HackerButton("添加", parent=self)
        self.add_button.set_border()
        self.add_button.clicked.connect(self.add_llm)
        button_card = HackerCard(
            "保存配置",
            self.add_button,
            "添加AI配置"
        )
        layout.addWidget(button_card)
        layout.addStretch()

        # 删除已有配置
        self.existing = HackerComboBox(self)
        self.existing.setMinimumWidth(320)
        self.existing.currentIndexChanged.connect(self.sync_remove_button)
        self.remove_button = HackerButton("删除", parent=self)
        self.remove_button.set_border()
        self.remove_button.setMinimumWidth(110)
        self.remove_button.clicked.connect(self.remove_llm)
        remove_card = HackerCard(
            "删除配置",
            self._build_remove_row(),
            "选中后删除，密钥一并移除",
            stacked=True,
        )
        layout.addWidget(remove_card)
        layout.addStretch()

        self.reload_existing()
        self.setLayout(layout)

    def _build_remove_row(self):
        # 上下排的卡片里独占一行
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
        from . import HackerLineEdit

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
            if isinstance(field, HackerLineEdit):
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
    def __init__(self, parent):
        super().__init__(parent)
        from . import ScrollArea

        card = BasicWidgetScroll(self)
        scroll = ScrollArea(self)
        scroll.setWidget(card)
        scroll.setGeometry(QRect(10, 10, 600, 400))


class Memory(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerSwitch, HackerLabel, HackerComboBox, HackerTextEdit

        HackerLabel("短期即时记忆", self).setGeometry(20, 20, 200, 30)
        self.memory_switch = HackerSwitch(parent=self)
        self.memory_switch.setGeometry(240, 15, 80, 30)
        self.memory_switch.setChecked(Config.memory['shortterm'])
        self.memory_switch.stateChanged.connect(self.check_short)

        HackerLabel("长期存储记忆", self).setGeometry(20, 60, 200, 30)
        self.longterm_memory_switch = HackerSwitch(parent=self)
        self.longterm_memory_switch.setGeometry(240, 55, 80, 30)
        self.longterm_memory_switch.setChecked(Config.memory['longterm'])
        self.longterm_memory_switch.stateChanged.connect(self.check_long)

        HackerLabel("看哪个模型的记忆", self).setGeometry(20, 100, 200, 30)
        self.model_selector = HackerComboBox(self)
        self.model_selector.setGeometry(220, 95, 380, 32)
        self.model_selector.currentTextChanged.connect(self.show_model)

        self.memory_json = HackerTextEdit("", parent=self)
        self.memory_json.setGeometry(QRect(20, 140, 580, 280))

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
        """重新扫描模型并填充下拉框，尽量保留原来选中的项。"""
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

    def show_model(self, model: str):
        """切到某个模型：只刷新展示区。"""
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
        """聊天那边推过来的记忆更新：只认当前选中的模型。"""
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
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerComboBox, HackerSwitch, HackerSlider, HackerCard, HackerLineEdit, HackerButton

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 下次启动清除缓存
        clear_cache_next_time = HackerButton("清除缓存", parent=self)
        clear_cache_next_time.clicked.connect(self.clear_cache)
        clear_cache_next_time_card = HackerCard(
            "清除缓存",
            clear_cache_next_time,
            "下次启动时清除RAG缓存（加入新RAG时请清除）"
        )
        layout.addWidget(clear_cache_next_time_card)
        layout.addStretch()
        # 启用 RAG
        enable_rag_switch = HackerSwitch(parent=self)
        enable_rag_switch.setChecked(Config.rag['enable'])
        enable_rag_switch_card = HackerCard(
            "启用RAG",
            enable_rag_switch,
            "启用知识库检索"
        )
        enable_rag_switch.stateChanged.connect(self.check_enable)
        layout.addWidget(enable_rag_switch_card)
        layout.addStretch()
        # 启用 BM25 检索
        enable_bm25_switch = HackerSwitch(parent=self)
        enable_bm25_switch.setChecked(Config.rag['bm25_enable'])
        enable_bm25_switch_card = HackerCard(
            "启用BM25",
            enable_bm25_switch,
            "强化关键字检索，答案更符合问题"
        )
        enable_bm25_switch.stateChanged.connect(self.check_bm25_enable)
        layout.addWidget(enable_bm25_switch_card)
        layout.addStretch()
        # 启用压缩 RAG
        compressed_rag_switch = HackerSwitch(parent=self)
        compressed_rag_switch.setChecked(Config.rag['compressed_enable'])
        compressed_rag_switch_card = HackerCard(
            "启用压缩RAG",
            compressed_rag_switch,
            "RAG 字段过长压缩RAG"
        )
        compressed_rag_switch.stateChanged.connect(self.check_compressed_enable)
        layout.addWidget(compressed_rag_switch_card)
        layout.addStretch()
        # 配置知识库类型
        self.knowledge_base_type = HackerComboBox(parent=self)
        self.knowledge_base_type.setFixedWidth(200)
        for dir_ in os.listdir("./resources/rag"):
            if dir_ == "chroma_db": continue
            self.knowledge_base_type.addItem(dir_)
        self.knowledge_base_type.setCurrentText(Config.rag['collection'])
        knowledge_base_type_card = HackerCard(
            "知识库类型",
            self.knowledge_base_type,
            "选择知识库类型"
        )
        self.knowledge_base_type.currentTextChanged.connect(self.check_type)
        layout.addWidget(knowledge_base_type_card)
        layout.addStretch()
        # RAG 引擎
        rag_engine = HackerComboBox(parent=self)
        rag_engine.setFixedWidth(200)
        rag_engine.addItems(SUPPORTED_ENGINES)
        rag_engine.setCurrentText(Config.rag['engine'])
        rag_engine_card = HackerCard(
            "RAG引擎",
            rag_engine,
            "Chroma 轻量，Lance多元"
        )
        rag_engine.currentTextChanged.connect(self.check_engine)
        layout.addWidget(rag_engine_card)
        layout.addStretch()
        # 区块大小
        block_size = HackerSlider(parent=self)
        block_size.setFixedWidth(300)
        block_size.setMinimum(128)
        block_size.setMaximum(2048)
        block_size.setValue(Config.rag['chunks'])
        block_size_card = HackerCard(
            f"区块大小（{Config.rag['chunks']} / tks）",
            block_size,
            "单次筛选的最大 Tokens"
        )
        block_size.valueChanged.connect(self.check_chunks)
        block_size.valueChanged.connect(lambda: block_size_card.set_title(f"区块大小（{block_size.value()} / tks）"))
        layout.addWidget(block_size_card)
        layout.addStretch()
        # 重排序
        top_k_slider = HackerSlider(parent=self)
        top_k_slider.setFixedWidth(200)
        top_k_slider.setValue(Config.rag['top_k'])
        top_k_slider.setMaximum(50)
        top_k_card = HackerCard(
            f"重排序（{Config.rag['top_k']}）",
            top_k_slider,
            "（Cross-Encoder）增强用户体验(设置top_k)"
        )
        top_k_slider.valueChanged.connect(self.check_top_k)
        top_k_slider.valueChanged.connect(lambda: top_k_card.set_title(f"重排序（{top_k_slider.value()}）"))
        layout.addWidget(top_k_card)
        layout.addStretch()
        # Overlap
        overlap = HackerSlider(parent=self)
        overlap.setFixedWidth(200)
        overlap.setValue(Config.rag['overlap'])
        overlap_card = HackerCard(
            f"重叠率（{Config.rag['overlap']} %）",
            overlap,
            "话语气和指代关系的连续性。"
        )
        overlap.valueChanged.connect(self.check_overlap)
        overlap.valueChanged.connect(lambda: overlap_card.set_title(f"重叠率（{overlap.value()} %）"))
        layout.addWidget(overlap_card)
        layout.addStretch()
        # Embedding Model
        self.embedding_model = HackerLineEdit(parent=self)
        self.embedding_model.setText(Config.rag['embedding'])
        self.embedding_model.setFixedWidth(200)
        embedding_model_card = HackerCard(
            "嵌入（向量）模型",
            self.embedding_model,
            "捕获文本的语义信息"
        )
        self.embedding_model.textChanged.connect(self.check_embedding)
        layout.addWidget(embedding_model_card)
        layout.addStretch()
        # Model
        self.model = HackerComboBox(parent=self)
        self.model.addItems(get_model_lists())
        self.model.setCurrentText(Config.rag['model'])
        self.model.setFixedWidth(350)
        model_card = HackerCard(
            "识别模型",
            self.model,
            "识别是否需要RAG检索"
        )
        self.model.currentTextChanged.connect(self.check_model)
        layout.addWidget(model_card)
        layout.addStretch()

        for methods in dir(self):
            if methods.startswith('check_'):
                try:
                    getattr(self, methods)()
                except Exception:  # noqa: BLE001 - 逐个字段容错，缺字段不影响其它配置
                    pass

    def check_model(self, text: str | None = None):
        if text is None: text = self.model.currentText()
        Config.rag['model'] = text
        ConfigLoader.save_config()

    def check_type(self, text: str | None = None):
        if text is None: text = self.knowledge_base_type.currentText()
        Config.rag['collection'] = text
        ConfigLoader.save_config()

    def check_embedding(self, text: str | None = None):
        if text is None: text = self.embedding_model.text()
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
    def check_engine(value: int):
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
    def __init__(self, parent):
        super().__init__(parent)
        from . import ScrollArea

        card = RAGWidgetScroll(self)
        scroll = ScrollArea(self)
        scroll.setWidget(card)
        scroll.setGeometry(QRect(10, 10, 600, 400))


class MCP(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerSwitch, HackerTable, HackerLabel, HackerButton

        # 开启 MCP
        HackerLabel("开启MCP", self).setGeometry(20, 10, 150, 30)
        mcp_switch = HackerSwitch(parent=self)
        mcp_switch.setChecked(Config.mcp['enable'])
        mcp_switch.setGeometry(170, 5, 100, 30)
        mcp_switch.stateChanged.connect(self.check_mcp)

        # MCP 服务器表格
        self.mcp_table = HackerTable(parent=self)
        self.mcp_table.setGeometry(20, 50, 600, 300)
        self.mcp_table.setHorizontalHeaderLabels(['服务器ID', '参数', '启动命令'])
        for server in Config.mcp['mcp']:
            self.add_data(server['server'], ' '.join(server['args']), server['command'])
        # 调整列宽
        self.mcp_table.setColumnWidth(0, 110)
        self.mcp_table.setColumnWidth(1, 400)
        self.mcp_table.setColumnWidth(2, 90)
        self.mcp_table.itemChanged.connect(self.change_data)

        # 增删 MCP 的按钮
        add_mcp_button = HackerButton("添加MCP", parent=self)
        add_mcp_button.set_border()
        add_mcp_button.setGeometry(20, 360, 100, 30)
        add_mcp_button.clicked.connect(self.add_mcp)
        remove_mcp_button = HackerButton("删除MCP", parent=self)
        remove_mcp_button.set_border()
        remove_mcp_button.setGeometry(130, 360, 100, 30)
        remove_mcp_button.clicked.connect(self.remove_mcp)

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

    def add_data(self, server, args, command):
        row = self.mcp_table.rowCount()
        self.mcp_table.insertRow(row)
        self.mcp_table.setItem(row, 0, QTableWidgetItem(server))
        self.mcp_table.setItem(row, 1, QTableWidgetItem(args))
        self.mcp_table.setItem(row, 2, QTableWidgetItem(command))

    def add_mcp(self):
        # 空行也得建出单元格，否则点不进去编辑
        row = self.mcp_table.rowCount()
        self.mcp_table.blockSignals(True)
        self.mcp_table.insertRow(row)
        for column in range(3):
            self.mcp_table.setItem(row, column, QTableWidgetItem(""))
        self.mcp_table.blockSignals(False)

        Config.mcp['mcp'].append({'server': "", 'args': [], 'command': ""})
        notify(f"已添加一行（第 {row + 1} 行），填写后自动保存", "info", 3000)

    def remove_mcp(self):
        row = self.mcp_table.currentRow()
        if row < 0:
            return  # 没有选中行时 pop(-1) 会误删最后一条
        self.mcp_table.removeRow(row)
        Config.mcp['mcp'].pop(row)
        ConfigLoader.save_config()


class Cooperation(QWidget):
    """多模型协作：主模型出稿/定稿，配在表里的模型按角色给意见。"""
    MODES = (("review", "评审改稿"), ("parallel", "并行汇总"))

    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerSwitch, HackerTable, HackerLabel, HackerButton, HackerComboBox, HackerSlider, HackerLineEdit

        HackerLabel("开启多模型协作", self).setGeometry(20, 10, 200, 30)
        self.enable_switch = HackerSwitch(parent=self)
        self.enable_switch.setChecked(bool(Config.coop["enable"]))
        self.enable_switch.setGeometry(220, 5, 80, 30)
        self.enable_switch.stateChanged.connect(self.check_enable)

        HackerLabel("协作模式", self).setGeometry(20, 50, 160, 30)
        self.mode_combo = HackerComboBox(self)
        self.mode_combo.addItems([label for _, label in self.MODES])
        self.mode_combo.setCurrentIndex(max(0, [key for key, _ in self.MODES].index(self._mode())))
        self.mode_combo.setGeometry(180, 45, 200, 30)
        self.mode_combo.currentIndexChanged.connect(self.check_mode)

        HackerLabel("评审轮数", self).setGeometry(20, 90, 160, 30)
        self.rounds_slider = HackerSlider(Qt.Orientation.Horizontal, self)
        self.rounds_slider.setMinimum(1)
        self.rounds_slider.setMaximum(3)
        self.rounds_slider.setValue(int(Config.coop.get("rounds") or 1))
        self.rounds_slider.setGeometry(180, 95, 200, 30)
        self.rounds_slider.valueChanged.connect(self.check_rounds)

        self.model_search = HackerLineEdit("搜索模型…", parent=self)
        self.model_search.setGeometry(20, 140, 280, 30)
        self.model_search.textChanged.connect(self.filter_models)

        # 搜索时显示"匹配 N / 共 M"，一眼看得出筛选掉多少
        self.available_label = HackerLabel("", self)
        self.available_label.setGeometry(20, 172, 280, 20)

        self.model_table = HackerTable(parent=self)
        self.model_table.setGeometry(20, 196, 280, 182)
        self.model_table.setHorizontalHeaderLabels(["模型", "来源"])
        self.model_table.setColumnWidth(0, 190)
        self.model_table.setColumnWidth(1, 80)
        self.model_table.setEditTriggers(HackerTable.EditTrigger.NoEditTriggers)
        self.model_table.cellDoubleClicked.connect(lambda *_args: self.add_selected())

        join_button = HackerButton("加入协作 →", parent=self)
        join_button.set_border()
        join_button.setGeometry(20, 392, 130, 28)
        join_button.clicked.connect(self.add_selected)

        HackerLabel("协作成员（主模型之外，按角色给意见）", self).setGeometry(315, 130, 305, 24)

        self.agent_table = HackerTable(parent=self)
        self.agent_table.setGeometry(315, 156, 305, 222)
        self.agent_table.setHorizontalHeaderLabels(["模型", "角色名", "提示词"])
        self.agent_table.setColumnWidth(0, 95)
        self.agent_table.setColumnWidth(1, 85)
        self.agent_table.setColumnWidth(2, 115)
        self.agent_table.itemChanged.connect(self.change_data)

        for index, (label, slot) in enumerate((
            ("添加空行", self.add_agent),
            ("删除选中", self.remove_agent),
            ("保存协作", self.save_agents),
        )):
            button = HackerButton(label, parent=self)
            button.set_border()
            button.setGeometry(315 + index * 100, 384, 95, 28)
            button.clicked.connect(slot)

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
        keys = self._available_models()
        self.filter_models(self.model_search.text())
        if not keys:
            self.available_label.setText("（还没有可用模型，先去「新增 LLM」加一个）")

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

    def filter_models(self, keyword: str):
        """按关键字筛可用模型，模型多的时候靠它找。"""
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

        total = len(self.models)
        if not total:
            self.available_label.setText("（还没有可用模型，先去「新增 LLM」加一个）")
        elif keyword:
            self.available_label.setText(f"匹配 {len(rows)} / 共 {total}")
        else:
            self.available_label.setText(f"{total} 个模型")

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


class Skills(QWidget):
    """技能：可以随时套在提问外面的提示词。"""
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerTable, HackerLabel, HackerButton

        HackerLabel("技能列表（聊天时打 /名字，或点聊天窗的「技能」按钮）", self).setGeometry(20, 10, 560, 30)

        self.skill_table = HackerTable(parent=self)
        self.skill_table.setGeometry(20, 46, 600, 300)
        self.skill_table.setHorizontalHeaderLabels(["技能名", "说明", "提示词"])
        self.skill_table.setColumnWidth(0, 110)
        self.skill_table.setColumnWidth(1, 140)
        self.skill_table.setColumnWidth(2, 330)
        self.skill_table.itemChanged.connect(self.change_data)

        add_button = HackerButton("添加技能", parent=self)
        add_button.set_border()
        add_button.setGeometry(20, 358, 100, 30)
        add_button.clicked.connect(self.add_skill)

        remove_button = HackerButton("删除选中", parent=self)
        remove_button.set_border()
        remove_button.setGeometry(130, 358, 100, 30)
        remove_button.clicked.connect(self.remove_skill)

        save_button = HackerButton("保存技能", parent=self)
        save_button.set_border()
        save_button.setGeometry(240, 358, 100, 30)
        save_button.clicked.connect(self.save_skills)

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


class LLMPage(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerTabWidget

        self.setObjectName("LLM")
        self.setWindowTitle("大语言模型设置")
        self.window_title = HackerLabel(self.windowTitle(), self)
        self.window_title.set_center()
        self.window_title.setGeometry(0, 0, self.width(), 30)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 40, 20, 20)
        self.tab_widget = HackerTabWidget(self)
        self.tab_widget.addTab(Basic(self), "新增 LLM")
        self.tab_widget.addTab(Memory(self), "记忆 配置")
        self.tab_widget.addTab(RAG(self), "RAG 配置")
        self.tab_widget.addTab(MCP(self), "MCP 设置")
        self.tab_widget.addTab(Cooperation(self), "协作 设置")
        self.tab_widget.addTab(Skills(self), "技能 Skills")
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)
