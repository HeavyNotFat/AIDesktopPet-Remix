import json
import os

from ...ai.rag.engine import SUPPORTED_ENGINES
from ... import Config, ConfigLoader, SharingData
from ... import get_model_lists

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTableWidgetItem
from PySide6.QtCore import QRect


class MemoryShowItem(QWidget):
    def __init__(self, model: str, parent):
        super().__init__(parent)
        from . import HackerTextEdit

        self.model = model

        self.memory_json = HackerTextEdit("", parent=self)
        self.memory_json.setGeometry(QRect(0, 0, 600, 260))

    def add(self, data: list):
        if data[0] == self.model:
            self.memory_json.setText(json.dumps(data[1], ensure_ascii=False, indent=3))


class BasicWidgetScroll(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLineEdit, HackerButton, HackerCard

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

        self.setLayout(layout)

    def add_llm(self):
        if self.ai_name.text() in Config.models.keys():
            return
        Config.models.update({self.ai_name.text(): {}})
        Config.models[self.ai_name.text()].update(
            {
                "name": self.ai_model.text(),
                "apikey": self.api_key.text(),
                "baseurl": self.api_url.text(),
            }
        )
        ConfigLoader.save_config()


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
        from . import HackerSwitch, HackerLabel, HackerTabWidget

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

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 40, 20, 20)
        self.tab_widget = HackerTabWidget(self)
        # 添加模型
        for model in get_model_lists():
            m = MemoryShowItem(model, self)
            SharingData.add_memory_to_ui.update({model: m.add})
            self.tab_widget.addTab(m, model)
        for parameters in Config.models.values():
            m = MemoryShowItem(parameters['name'],  self)
            SharingData.add_memory_to_ui.update({parameters['name']: m.add})
            self.tab_widget.addTab(m, parameters['name'])

        layout.addWidget(self.tab_widget)
        layout.setGeometry(QRect(10, 75, 600, 360))

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
        # 启用？
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
        # 启用BM25
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
        # 压缩启用
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
            # "Chroma轻量，Lance多元，Milvus海量。"
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
                try: getattr(self, methods)()
                except: pass

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

        # 开启MCP
        HackerLabel("开启MCP", self).setGeometry(20, 10, 150, 30)
        mcp_switch = HackerSwitch(parent=self)
        mcp_switch.setChecked(Config.mcp['enable'])
        mcp_switch.setGeometry(170, 5, 100, 30)
        mcp_switch.stateChanged.connect(self.check_mcp)

        # MCP表格
        self.mcp_table = HackerTable(parent=self)
        self.mcp_table.setGeometry(20, 50, 600, 300)
        self.mcp_table.setHorizontalHeaderLabels(['服务器ID', '参数', '启动命令'])
        for server in Config.mcp['mcp']:
            self.add_data(server['server'], ' '.join(server['args']), server['command'])
        self.mcp_table.itemChanged.connect(self.change_data)

        # 增加MCP面板
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
        if item.column() == 0:
            Config.mcp['mcp'][item.row()]['server'] = item.text()
        elif item.column() == 1:
            Config.mcp['mcp'][item.row()]['args'] = item.text().split(' ')
        else:
            Config.mcp['mcp'][item.row()]['command'] = item.text()
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
        # 增加表格
        row = self.mcp_table.rowCount()
        self.mcp_table.insertRow(row)
        Config.mcp['mcp'].append({'server': "", 'args': [], 'command': ""})

    def remove_mcp(self):
        # 删除表格
        row = self.mcp_table.currentRow()
        if row >= 0:
            self.mcp_table.removeRow(row)
        Config.mcp['mcp'].pop(row)
        ConfigLoader.save_config()


class Cooperation(QWidget):
    def __init__(self, parent):
        super().__init__(parent)


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
        self.tab_widget.addTab(Basic(self), "基础 设置")
        self.tab_widget.addTab(Memory(self), "记忆 配置")
        self.tab_widget.addTab(RAG(self), "RAG 配置")
        self.tab_widget.addTab(MCP(self), "MCP 设置")
        self.tab_widget.addTab(Cooperation(self), "协作 设置")
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def resizeEvent(self, event, /):
        super().resizeEvent(event)
        self.window_title.setGeometry(0, 0, self.width(), 30)
