import json
import os

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


class Basic(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerLabel, HackerLineEdit, HackerButton

        # AI 名字
        HackerLabel("AI 名字", self).setGeometry(20, 20, 120, 30)
        self.ai_name = HackerLineEdit(self)
        self.ai_name.setGeometry(150, 20, 450, 30)

        # AI Model
        HackerLabel("AI 模型", self).setGeometry(20, 60, 120, 30)
        self.ai_model = HackerLineEdit(self)
        self.ai_model.setGeometry(150, 60, 450, 30)

        # API Key
        HackerLabel("API Key", self).setGeometry(20, 100, 120, 30)
        self.api_key = HackerLineEdit(self)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setGeometry(150, 100, 450, 30)

        # Base URL
        HackerLabel("Base URL", self).setGeometry(20, 140, 120, 30)
        self.api_url = HackerLineEdit(self)
        self.api_url.setGeometry(150, 140, 450, 30)

        # 添加
        self.add_button = HackerButton("添加", parent=self)
        self.add_button.set_border()
        self.add_button.clicked.connect(self.add_llm)
        self.add_button.setGeometry(520, 180, 80, 30)

    def add_llm(self):
        if self.ai_name.text() in Config.models.keys():
            return
        Config.models.update({self.ai_name.text(): {}})
        Config.models[self.ai_name.text()].update(
            {
                "name": self.ai_model.text(),
                "apikey": self.api_key.text(),
                "apiurl": self.api_url.text(),
            }
        )
        ConfigLoader.save_config(Config)


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

    def check_short(self, boo: bool):
        Config.memory['shortterm'] = boo
        ConfigLoader.save_config(Config)

    def check_long(self, boo: bool):
        Config.memory['longterm'] = boo
        ConfigLoader.save_config(Config)


class RAGWidgetScroll(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        from . import HackerComboBox, HackerSwitch, HackerSlider, HackerCard, HackerLineEdit

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

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
        # 配置知识库类型
        knowledge_base_type = HackerComboBox(parent=self)
        knowledge_base_type.setFixedWidth(200)
        for dir_ in os.listdir("./resources/rag"):
            if os.path.isdir(f"./resources/rag/{dir_}"):
                continue
            dir_ = dir_.replace(".txt", "")
            knowledge_base_type.addItem(dir_)
        knowledge_base_type.setCurrentText(Config.rag['type'])
        knowledge_base_type_card = HackerCard(
            "知识库类型",
            knowledge_base_type,
            "选择知识库类型"
        )
        knowledge_base_type.currentTextChanged.connect(self.check_type)
        layout.addWidget(knowledge_base_type_card)
        layout.addStretch()
        # RAG 引擎
        rag_engine = HackerComboBox(parent=self)
        rag_engine.setFixedWidth(200)
        rag_engine.addItems(['chroma', 'lance', 'milvus'])
        rag_engine.setCurrentText(Config.rag['type'])
        rag_engine_card = HackerCard(
            "RAG引擎",
            rag_engine,
            "Chroma轻量，Lance多元，Milvus海量。"
        )
        rag_engine.currentTextChanged.connect(self.check_engine)
        layout.addWidget(rag_engine_card)
        layout.addStretch()
        # 元数据过滤
        metadata_filter_switch = HackerSwitch(parent=self)
        metadata_filter_switch.setChecked(Config.rag['meta'])
        metadata_filter_switch_card = HackerCard(
            "元数据过滤",
            metadata_filter_switch,
            "对数据库中多元化数据进行筛选"
        )
        metadata_filter_switch.stateChanged.connect(self.check_meta)
        layout.addWidget(metadata_filter_switch_card)
        layout.addStretch()
        # 缓存
        cache_slide = HackerSlider(parent=self)
        cache_slide.setFixedWidth(250)
        cache_slide.setMaximum(512)
        cache_slide.setValue(Config.rag['cache'])
        cache_slide_card = HackerCard(
            "LRU缓存（0-512）",
            cache_slide,
            "用内存加速RAG（可能导致无多元化结果）"
        )
        cache_slide.valueChanged.connect(self.check_cache)
        cache_slide.valueChanged.connect(lambda: cache_slide_card.set_title(f"LRU缓存（{cache_slide.value()}）"))
        layout.addWidget(cache_slide_card)
        layout.addStretch()
        # 混合检索
        bm25_slider = HackerSlider(parent=self)
        bm25_slider.setFixedWidth(200)
        bm25_slider.setValue(Config.rag['bm25'] * 100)
        bm25_slider_card = HackerCard(
            f"BM25混合检索（{Config.rag['bm25']}）",
            bm25_slider,
            "专有名词/昵称敏感"
        )
        bm25_slider.valueChanged.connect(self.check_bm25)
        bm25_slider.valueChanged.connect(lambda: bm25_slider_card.set_title(f"BM25混合检索（{bm25_slider.value() / 100}）"))
        layout.addWidget(bm25_slider_card)
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
        resort_slider = HackerSlider(parent=self)
        resort_slider.setFixedWidth(200)
        resort_slider.setValue(Config.rag['resort'])
        resort_slider.setMaximum(50)
        resort_card = HackerCard(
            f"重排序（{Config.rag['resort']}）",
            resort_slider,
            "（Cross-Encoder）增强用户体验(设置top_k)"
        )
        resort_slider.valueChanged.connect(self.check_resort)
        resort_slider.valueChanged.connect(lambda: resort_card.set_title(f"重排序（{resort_slider.value()}）"))
        layout.addWidget(resort_card)
        layout.addStretch()
        # Overlap
        overlap = HackerSlider(parent=self)
        overlap.setFixedWidth(200)
        overlap.setValue(Config.rag['overlap'])
        overlap_card = HackerCard(
            "重叠率（15 %）",
            overlap,
            "话语气和指代关系的连续性。"
        )
        overlap.valueChanged.connect(self.check_overlap)
        overlap.valueChanged.connect(lambda: overlap_card.set_title(f"重叠率（{overlap.value()} %）"))
        layout.addWidget(overlap_card)
        layout.addStretch()
        # Embedding Model
        embedding_model = HackerLineEdit(parent=self)
        embedding_model.setText(Config.rag['embedding'])
        embedding_model.setFixedWidth(200)
        embedding_model_card = HackerCard(
            "嵌入（向量）模型",
            embedding_model,
            "捕获文本的语义信息"
        )
        embedding_model.textChanged.connect(self.check_embedding)
        layout.addWidget(embedding_model_card)
        layout.addStretch()
        # Model
        model = HackerComboBox(parent=self)
        model.addItems(get_model_lists())
        model.setCurrentText(Config.rag['model'])
        model.setFixedWidth(200)
        model_card = HackerCard(
            "识别模型",
            model,
            "识别是否需要RAG检索"
        )
        model.currentTextChanged.connect(self.check_model)
        layout.addWidget(model_card)
        layout.addStretch()

    def check_model(self, value: str):
        Config.rag['model'] = value
        ConfigLoader.save_config(Config)

    def check_engine(self, value: int):
        Config.rag['engine'] = value
        ConfigLoader.save_config(Config)

    def check_enable(self, boo: bool):
        Config.rag['enable'] = boo
        ConfigLoader.save_config(Config)

    def check_type(self, value: int):
        Config.rag['type'] = value
        ConfigLoader.save_config(Config)

    def check_cache(self, boo: bool):
        Config.rag['cache'] = boo
        ConfigLoader.save_config(Config)

    def check_bm25(self, value: int):
        Config.rag['bm25'] = value / 100
        ConfigLoader.save_config(Config)

    def check_resort(self, value: int):
        Config.rag['resort'] = value
        ConfigLoader.save_config(Config)

    def check_meta(self, boo: bool):
        Config.rag['meta'] = boo
        ConfigLoader.save_config(Config)

    def check_chunks(self, value: int):
        Config.rag['chunks'] = value
        ConfigLoader.save_config(Config)

    def check_overlap(self, value: int):
        Config.rag['overlap'] = value
        ConfigLoader.save_config(Config)

    def check_embedding(self, text: str):
        Config.rag['embedding'] = text
        ConfigLoader.save_config(Config)


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

    def change_data(self, item: QTableWidgetItem):
        if item.column() == 0:
            Config.mcp['mcp'][item.row()]['server'] = item.text()
        elif item.column() == 1:
            Config.mcp['mcp'][item.row()]['args'] = item.text().split(' ')
        else:
            Config.mcp['mcp'][item.row()]['command'] = item.text()
        ConfigLoader.save_config(Config)

    def check_mcp(self, boo: bool):
        Config.mcp['enable'] = boo
        ConfigLoader.save_config(Config)

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
        ConfigLoader.save_config(Config)


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
