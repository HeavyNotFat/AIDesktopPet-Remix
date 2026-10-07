"""hacker 主题的单模型聊天页：LLM 实例缓存、函数调用线程、插件改写、协作出稿。

``__init__.py`` 把它映射成契约里的 ``ModelChat``，`stlibs/graphics/chat.py` 为每个模型建一页。
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ... import SharingData, derfer
from ...ai import cloud, local
from ..base import CombinedMeta, ModelChatABS

from .feedback import HackerNotify

# 模型名 → LLM 实例：同一个模型被多个聊天页共用一份（含记忆与函数调用）


cache_llm_class = {}


# BASE

class ModelChat(QWidget, ModelChatABS, metaclass=CombinedMeta):
    def __init__(
        self,
        ai_name: str, model: str,
        is_local: bool,
        api_key: str | None = None,
        base_url: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.is_local = is_local
        if is_local:
            if model in cache_llm_class.keys():
                self.ai_llm = cache_llm_class[model]
            else:
                self.ai_llm = local.LLM(model)
                cache_llm_class[model] = self.ai_llm
        else:
            if model in cache_llm_class.keys():
                self.ai_llm = cache_llm_class[model]
            else:
                # noinspection PyTypeChecker
                self.ai_llm = cloud.LLM(model, api_key, base_url)
                cache_llm_class[model] = self.ai_llm

        # 记忆面板可能还没建过（比如设置页没打开就先聊天），取不到回调就跳过
        memory_callback = SharingData.add_memory_to_ui.get(model)
        if memory_callback is not None:
            self.ai_llm.memory_signal.connect(memory_callback)

        # 同一个实例会被多个聊天页共用，协作提示只接一次
        coop_signal = getattr(self.ai_llm, "coop_signal", None)
        if coop_signal is not None and not getattr(self.ai_llm, "_coop_notify_bound", False):
            coop_signal.connect(self.on_coop_event)
            self.ai_llm._coop_notify_bound = True

        self.setWindowTitle(ai_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = SharingData.theme.Label("AI TERMINAL")
        title.setFixedHeight(30)
        layout.addWidget(title)

        self.chat = SharingData.theme.ChatWidget()
        self.chat.userInputSignal.connect(self.add_user_msg)

        layout.addWidget(self.chat)

        self.current_assistant_bubble = None

    @staticmethod
    def return_llm_class(model) -> local.LLM | cloud.LLM:
        return cache_llm_class[model]

    def chat_finished(self, all_message):
        self.chat.enable_send_button()

        # 插件可以改最终回复（流式已经把原文写进气泡了，这里按需重写）
        final = self._plugin_text(all_message or "", "assistant")
        bubble = self.current_assistant_bubble
        if bubble is not None and final and final != (all_message or ""):
            bubble.text_label.setText(final)
            self.chat.update_bubble_widths()
            self.chat.scroll_to_bottom()

        from ... import emit_sdk_event, plugin_manager

        try:
            plugin_manager().emit_event("chat_finished", {"reply": final})
        except Exception:  # noqa: BLE001
            pass
        emit_sdk_event("chat_finished", {"reply": final})

    def add_user_msg(self, msg: str, attachments=None):
        self.current_assistant_bubble = self.chat.add_assistant_msg()
        self.chat.disable_send_button()

        attachments = list(attachments or [])
        self._warn_if_blind(attachments)

        skill = getattr(self.chat, "active_skill", None)
        prompt = self._combined_prompt(skill)
        msg = self._plugin_text(msg, "user")

        t = derfer.LLMAICallback(self.ai_llm, msg, self, skill=prompt, attachments=attachments)
        self.worker = t
        t.finished.connect(self.chat_finished)
        t.text_chunk.connect(self.add_assistant_msg)
        t.tool_event.connect(self.on_tool_event)
        t.start()

    @staticmethod
    def _plugin_text(text: str, role: str) -> str:
        """让插件改用户输入（chat_send）或回复（chat_reply）。"""
        from ... import plugin_manager

        try:
            return plugin_manager().chat_text(text, role)
        except Exception:  # noqa: BLE001 - 插件坏了不能挡住聊天
            return text

    @staticmethod
    def _combined_prompt(skill) -> str | None:
        """技能提示词 + 插件要求的系统提示词，一起当成 system 段注入。

        都没有就返回 None —— 别给 LLM 传一个没意义的空串。
        """
        from ... import plugin_prompts

        parts = []
        prompt = (skill or {}).get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            parts.append(prompt.strip())
        parts.extend(item for item in plugin_prompts() if str(item).strip())
        return "\n\n".join(parts) if parts else None

    def _warn_if_blind(self, attachments):
        """带了图片但模型看不见图时直说 —— 否则用户只会以为"AI 没收到图片"。

        提示只是锦上添花，任何异常都不能挡住发送。
        """
        from ...ai import attachment as attachment_api

        try:
            if not attachment_api.images(attachments) or not getattr(self, "is_local", False):
                return
            model = getattr(self.ai_llm, "model", "")
            if attachment_api.can_see_images(model):
                return
        except Exception:  # noqa: BLE001
            return

        HackerNotify(
            f"{model} 是纯文本模型，看不了图片（换成带 vision 的模型，"
            "或用文字描述图片内容）",
            "warning",
            5000,
        )

    def on_tool_event(self, event: dict):
        """音频挂到当前气泡上等用户点播放；其它事件先忽略（MCP 工具的结果还是走文本）。"""
        if event.get("type") != "audio":
            return
        data = event.get("data")
        if not data or self.current_assistant_bubble is None:
            return

        self.current_assistant_bubble.attach_audio(data)
        transcript = event.get("transcript")
        if transcript and not self.current_assistant_bubble.text().strip():
            self.current_assistant_bubble.append_text(transcript)
        self.chat.scroll_to_bottom()

    @staticmethod
    def on_coop_event(event: dict):
        stage = event.get("stage")
        agent = event.get("agent") or "协作模型"

        if stage == "draft":
            HackerNotify("多模型协作：主模型正在出初稿…", "info", 2000)
        elif stage == "review_start":
            HackerNotify(f"多模型协作：{agent} 正在评审…", "info", 2000)
        elif stage == "review_done":
            HackerNotify(f"{agent} 评审完成", "info", 1500)
        elif stage == "agent_start":
            HackerNotify(f"多模型协作：{agent} 正在回答…", "info", 2000)
        elif stage == "agent_done":
            HackerNotify(f"{agent} 回答完成", "info", 1500)
        elif stage == "final":
            HackerNotify("多模型协作：主模型正在定稿…", "info", 2000)
        elif stage == "agent_error":
            HackerNotify(f"{agent} 协作失败：{event.get('detail', '未知错误')}", "error", 4000)
        elif stage == "empty":
            HackerNotify(
                f"{event.get('detail', '协作没有生效')}（协作设置里检查模型与开关）",
                "warning",
                3500,
            )

    def add_assistant_msg(self, msg: str):
        if not msg:
            return

        if self.current_assistant_bubble is not None:
            self.current_assistant_bubble.append_text(msg)
            self.chat.update_bubble_widths()
            self.chat.scroll_to_bottom()
