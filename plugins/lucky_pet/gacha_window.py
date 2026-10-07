from __future__ import annotations

from gacha_model import EXCHANGE_SHARDS, PITY_SSR, RARITIES, RARITY_COLOR, GachaState

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QProgressBar, QHBoxLayout, QVBoxLayout, QFrame, QLabel

PANEL_STYLE = """
QFrame#gacha-panel {
    background: rgba(0, 0, 0, 120);
    border: 1px solid rgba(0, 255, 0, 90);
    border-radius: 10px;
}
QFrame#gacha-panel QLabel { background: transparent; color: #00FF88; }
"""

PITY_STYLE = """
QProgressBar {
    background: rgba(0, 0, 0, 170);
    border: 1px solid rgba(0, 255, 0, 90);
    border-radius: 7px;
    height: 18px;
    text-align: center;
    color: #d8ffd8;
    font-size: 11px;
}
QProgressBar::chunk { background: #ffd166; border-radius: 6px; }
"""

WINDOW_STYLE = """
QWidget { background: #16181c; color: #d8ffd8; }
QLabel { background: transparent; color: #00FF88; }
"""


def _pet_name() -> str:
    try:
        from stlibs import Config

        return str(Config.name or "桌宠")
    except Exception:  # noqa: BLE001 - 拿不到配置就用通称
        return "桌宠"


class GachaWindow(QWidget):
    """扭蛋机面板：上面战绩、中间出货区、下面按钮，底部图鉴。"""

    def __init__(self, api, state: GachaState, on_action=None):
        from stlibs.themes import hacker

        super().__init__(None)
        self.api = api
        self.state = state
        self.on_action = on_action or (lambda action, payload=None: None)
        self.last_results: list = []

        self.setWindowTitle(f"扭蛋机 · {_pet_name()}")
        self.resize(660, 620)
        self.setStyleSheet(WINDOW_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)
        root.addWidget(self._build_header(hacker))
        root.addWidget(self._build_stage(hacker), 1)
        root.addWidget(self._build_codex(hacker), 2)
        root.addLayout(self._build_actions(hacker))

        self.refresh()

    def _build_header(self, hacker) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("gacha-panel")
        panel.setStyleSheet(PANEL_STYLE)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        head = QHBoxLayout()
        self.title = hacker.Label("🎰 桌宠扭蛋机", panel)
        head.addWidget(self.title)
        head.addStretch(1)
        self.coin_label = hacker.Label("", panel)
        head.addWidget(self.coin_label)
        layout.addLayout(head)

        self.stats_label = hacker.Label("", panel)
        layout.addWidget(self.stats_label)

        self.pity_bar = QProgressBar(panel)
        self.pity_bar.setStyleSheet(PITY_STYLE)
        self.pity_bar.setFixedHeight(18)
        layout.addWidget(self.pity_bar)
        return panel

    def _build_stage(self, hacker) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("gacha-panel")
        panel.setStyleSheet(PANEL_STYLE)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self.emoji_row = QLabel("🎁", panel)
        self.emoji_row.setAlignment(Qt.AlignCenter)
        self.emoji_row.setStyleSheet("font-size: 34px; color: #00FF88; background: transparent;")
        layout.addWidget(self.emoji_row)

        self.result_label = QLabel("还没抽过，点下面的按钮试试手气", panel)
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 15px; color: #00FF88; background: transparent;")
        layout.addWidget(self.result_label)
        return panel

    def _build_codex(self, hacker) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("gacha-panel")
        panel.setStyleSheet(PANEL_STYLE)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(hacker.Label("图鉴", panel))

        self.codex_label = QLabel("", panel)
        self.codex_label.setWordWrap(True)
        self.codex_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.codex_label.setStyleSheet("color: #d8ffd8; background: transparent; font-size: 12px;")
        layout.addWidget(self.codex_label)
        layout.addStretch(1)
        return panel

    def _build_actions(self, hacker) -> QHBoxLayout:
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for label, action in (
            ("单抽 10", "pull"),
            ("十连 90", "ten"),
            ("签到", "daily"),
            (f"星辉换 UR {EXCHANGE_SHARDS}", "exchange"),
            ("让桌宠点评", "comment"),
            ("关闭", "close"),
        ):
            button = hacker.Button(label, parent=self)
            button.set_border()
            button.setMinimumHeight(34)
            button.clicked.connect(lambda _checked=False, name=action: self.on_action(name))
            actions.addWidget(button)
        return actions

    def refresh(self):
        state = self.state
        self.coin_label.setText(f"金币 {state.coins}　星辉 {state.shards}")
        self.stats_label.setText(state.stats_text())

        done = PITY_SSR - state.pity_left
        self.pity_bar.setMaximum(PITY_SSR)
        self.pity_bar.setValue(done)
        self.pity_bar.setFormat(f"SSR 保底 {done}/{PITY_SSR}")

        self.codex_label.setText("\n".join(state.codex()) or "（扭蛋机里还没有东西）")

    def show_results(self, results: list, message: str = ""):
        self.last_results = list(results)
        self.emoji_row.setText("".join(item["emoji"] for item in results) or "🎁")

        if results:
            best = max(results, key=lambda item: RARITIES.index(item["rarity"]))
            color = RARITY_COLOR[best["rarity"]]
            names = "、".join(
                f"{item['rarity']} {item['emoji']} {item['name']}" + ("（新）" if item["new"] else f"（+{item['shards']}星辉）")
                for item in results[:5]
            )
            more = f" … 还有 {len(results) - 5} 个" if len(results) > 5 else ""
            self.result_label.setText(f"{best['rarity']}　{names}{more}")
            self.result_label.setStyleSheet(f"font-size: 15px; color: {color}; background: transparent;")
        else:
            self.result_label.setText(message or "这次什么都没抽到")
            self.result_label.setStyleSheet("font-size: 14px; color: #ffd166; background: transparent;")

        self.refresh()

    def set_message(self, message: str, color: str = "#ffd166"):
        self.result_label.setText(message)
        self.result_label.setStyleSheet(f"font-size: 14px; color: {color}; background: transparent;")

    def show_panel(self):
        self.refresh()
        self.show()
        self.raise_()


__all__ = ["GachaWindow", "PANEL_STYLE", "PITY_STYLE", "WINDOW_STYLE"]
