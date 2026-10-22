# -*- coding: utf-8 -*-
import os
import re
import subprocess
import sys
import threading

import requests

from PySide6.QtCore import Qt, QThread, Signal
from libs.AiMd import render_md
from PySide6.QtWidgets import (
    QDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# SiliconFlow 免费模型
# 对话记忆缓存（通用缓存 core 目录）
_MEM_DIR = os.path.join(os.path.expanduser("~"), "PyCache", "core")
_MEM_FILE = os.path.join(_MEM_DIR, "ai_history.json")


def _load_memory():
    try:
        if os.path.exists(_MEM_FILE):
            with open(_MEM_FILE, "r", encoding="utf-8") as f:
                import json as _json
                data = _json.load(f)
            if isinstance(data, dict):
                return data.get("history", []), data.get("model"), data.get("persona")
    except Exception:
        pass
    return [], None, None


def _save_memory(history, model, persona):
    try:
        os.makedirs(_MEM_DIR, exist_ok=True)
        import json as _json
        with open(_MEM_FILE, "w", encoding="utf-8") as f:
            _json.dump({"history": list(history), "model": model, "persona": persona},
                       f, ensure_ascii=False, indent=2)
    except Exception:
        pass


API_URL = "https://api.siliconflow.cn/v1/chat/completions"
def _api_key():
    key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if key:
        return key
    try:
        import json
        from core_lib import get_path
        path = get_path("data/local/ai_assistant.json")
        with open(path, encoding="utf-8") as file:
            return str(json.load(file).get("api_key", "")).strip()
    except (OSError, ValueError, TypeError):
        return ""


MODELS = [
    ("THUDM/GLM-Z1-9B-0414", "GLM-Z1-9B"),
    ("Qwen/Qwen3-8B", "Qwen3-8B"),
]

# 人设预设
PERSONAS = {
    "智能管家": "你是超级白工具箱的智能管家，回答简洁实用，乐于帮用户完成电脑/手机相关操作。"
                "排版要求：不要在回复首尾包裹 ```markdown 代码块，直接输出普通 markdown 正文，"
                "适当使用加粗、列表让内容易读。",
    "技术导师": "你是资深技术导师，擅长 Android/Windows 折腾，讲解步骤清晰、循序渐进。"
                "排版要求：不要用代码块包裹整段回复，直接输出 markdown 正文，必要时用行内代码标注命令。",
    "精简模式": "你是高效的 AI 助手，只回答关键结论，不废话。不要用代码块包裹整个回复。",
    "猫娘女仆": "你是超级白工具箱的猫娘女仆，温柔粘人、说话带喵尾音（如“喵~”“呢”），"
                "同时业务能力强，能准确引导用户使用工具箱功能。排版要求：直接输出 markdown 正文，"
                "不要用代码块包裹整段回复，语气亲昵但不拖泥带水。",
    "图吧暴躁老哥": "你是贴吧风格的暴躁老哥，说话直白带梗、偶尔吐槽，但对技术问题一针见血。"
                    "排版要求：直接输出 markdown 正文，别整那些花里胡哨的，讲清楚怎么用就行。",
    "撒娇女友": "你是用户的撒娇女友人设，说话可爱黏人、爱撒娇，但遇到技术问题会认真帮忙。"
                "排版要求：直接输出 markdown 正文，语气亲密自然，不要用代码块包裹整段回复。",
}

# 工具箱功能知识库：让模型了解工具箱全貌，减少场外回答
TOOL_KNOWLEDGE = (
    "你运行在「超级白工具箱 V7」内部，工具箱按分区组织功能，用户问功能时优先按这里指路：\n"
    "ADB功能：Scrcpy投屏、设备选择、连接无线设备、打开ADB面板、手机轨迹录制、手机视频无损压缩、"
    "一键备份/还原基带、ADB重启、ADB驱动安装、一加一键解锁BL。\n"
    "FB功能：一键刷入boot.img、fastboot重启。\n"
    "面具/环境：自动安装环境检测软件、Alpha/Sukisu 完美环境、过环境文件发送、常用APP。\n"
    "电脑脚本：腾讯ACE一键根除、激活Win10/11、F1禁止跳Edge、Steam/Epic下载加速、"
    "还原Win10/11右键菜单、资源管理器精简六项隐藏/恢复、删除广告、ToDo网络同步修复。\n"
    "二进制：各类工具（卸载、磁盘分析、Everything、WizTree、RAMMap 等）与安装包（JDK、WPS、"
    "Pycharm、Foxit、运行库、UU、ToDesk、JiJiDown 等）。\n"
    "其他：智能助手（就是本对话）、软件中心、清理本软件缓存/核心组件、分券工具、指定文件夹搜索、"
    "Hash+MD5重复清理、电脑手机清理残留（空文件/空文件夹/智能清理、屏蔽词）、大丸视频压缩、"
    "电脑手机数据备份（打包 .tar.gz）、安装李跳跳。\n"
    "用户让你“执行”某项操作时，先说明它在工具箱哪个分区、叫什么按钮，再给出操作步骤。"
)

# 工具箱指令关键词 → 建议入口
TOOL_HINTS = [
    (["软件", "商店", "下载软件"], "可以试试「其他 → 软件中心」搜索并下载软件。"),
    (["压缩", "视频", "大丸"], "视频压缩请使用「其他 → 大丸视频压缩」。"),
    (["清理", "残留", "缓存"], "清理请使用「其他 → 电脑手机清理残留」或「清理本软件缓存」。"),
    (["备份", "数据"], "备份请使用「其他 → 电脑手机数据备份」。"),
    (["投屏", "scrcpy"], "手机投屏请使用「ADB功能 → Scrcpy投屏」。"),
    (["录制", "轨迹"], "屏幕录制请使用「ADB功能 → 手机轨迹录制」。"),
    (["F1", "edge", "浏览器"], "F1 跳 Edge 问题可在「电脑脚本 → F1禁止跳Edge浏览器」处理。"),
    (["加速", "steam", "epic"], "游戏加速脚本在「电脑脚本 → Steam下载加速 / Epic下载加速」。"),
]


class AiReplyThread(QThread):
    """后台请求大模型，避免阻塞 UI"""

    replied = Signal(str)
    failed = Signal(str)

    def __init__(self, model, messages, persona):
        super().__init__()
        self.model = model
        self.messages = messages
        self.persona = persona

    def run(self):
        try:
            api_key = _api_key()
            if not api_key:
                self.failed.emit("未配置 API 密钥，请设置 SILICONFLOW_API_KEY 或 data/local/ai_assistant.json")
                return
            system = self.persona + "\n\n" + TOOL_KNOWLEDGE
            payload = {
                "model": self.model,
                "messages": [{"role": "system", "content": system}] + self.messages,
                "max_tokens": 800,
                "temperature": 0.7,
            }
            resp = requests.post(API_URL, headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            }, json=payload, timeout=90)
            data = resp.json()
            if resp.status_code == 200 and "choices" in data:
                self.replied.emit(data["choices"][0]["message"]["content"].strip())
            else:
                self.failed.emit(data.get("message") or f"HTTP {resp.status_code}")
        except Exception as exc:
            self.failed.emit(str(exc))


class AiAssistantDialog(QDialog):
    """大模型智能助手：聊天 + 模型切换 + 人设 + 工具箱引导"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("智能助手 · 大模型")
        self.setMinimumSize(620, 560)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.history = []
        self.worker = None
        self._build_ui()
        self._restore_state()
        if not self.history:
            self._greet()
        else:
            self._render_history()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QDialog {
                background-color: #eef2f8;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QLabel#title {
                font-size: 16px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#hint {
                font-size: 11px;
                color: #64748b;
            }
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 7px;
                padding: 4px 8px;
                min-height: 30px;
                color: #1f2937;
            }
            QComboBox:focus { border-color: #2563eb; }
            QComboBox::drop-down {
                border: none; width: 22px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #64748b;
                margin-right: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                outline: none;
                padding: 4px;
                selection-background-color: #e7f0ff;
                selection-color: #0f172a;
            }
            QComboBox QAbstractItemView::item {
                min-height: 28px;
                padding: 2px 8px;
                border-radius: 6px;
                color: #1f2937;
            }
            QTextEdit QScrollBar:vertical {
                background: transparent; width: 10px; margin: 2px 2px 2px 0;
            }
            QTextEdit QScrollBar::handle:vertical {
                background: #c5d1e4; min-height: 28px; border-radius: 5px;
            }
            QTextEdit QScrollBar::handle:vertical:hover { background: #afc0d8; }
            QTextEdit QScrollBar::add-line:vertical, QTextEdit QScrollBar::sub-line:vertical { height: 0; }
            QTextEdit QScrollBar::add-page:vertical, QTextEdit QScrollBar::sub-page:vertical { background: transparent; }
            QPushButton {
                background-color: #eef2f9;
                border: 1px solid #d8e0ec;
                border-radius: 8px;
                color: #1f2937;
                padding: 6px 14px;
                min-height: 32px;
            }
            QPushButton:hover {
                background-color: #e6edf9;
            }
            QPushButton#primary {
                background-color: #2563eb;
                border-color: #2563eb;
                color: white;
                font-weight: 600;
            }
            QPushButton#primary:hover {
                background-color: #1d4ed8;
            }
            QTextEdit#chat {
                background-color: #fbfdff;
                border: 1px solid #dfe7f3;
                border-radius: 10px;
                color: #1f2937;
                font-size: 13px;
                padding: 8px;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                padding: 8px 10px;
                color: #1f2937;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QFrame()
        header.setObjectName("card")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("智能助手")
        title.setObjectName("title")
        hint = QLabel("纯自研工具箱 AI 管家 · SiliconFlow 免费模型 · 可聊天 / 引导操作")
        hint.setObjectName("hint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        hl.addLayout(title_box)
        hl.addStretch()
        hl.addWidget(QLabel("模型"))
        self.model_box = QComboBox()
        for m, label in MODELS:
            self.model_box.addItem(label, m)
        hl.addWidget(self.model_box)
        hl.addWidget(QLabel("人设"))
        self.persona_box = QComboBox()
        for name in PERSONAS:
            self.persona_box.addItem(name)
        hl.addWidget(self.persona_box)
        layout.addWidget(header)

        self.chat_view = QTextEdit()
        self.chat_view.setObjectName("chat")
        self.chat_view.setReadOnly(True)
        layout.addWidget(self.chat_view, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("问点什么，或让我帮你找工具箱里的功能…")
        self.input_edit.returnPressed.connect(self._send)
        btn_send = QPushButton("发送")
        btn_send.setObjectName("primary")
        btn_send.clicked.connect(self._send)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear)
        btn_export = QPushButton("导出对话")
        btn_export.clicked.connect(self._export)
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(btn_send)
        input_row.addWidget(btn_export)
        input_row.addWidget(btn_clear)
        layout.addLayout(input_row)

    def _append(self, who, text):
        if who == "你":
            body = "<br>".join(self._escape_line(l) for l in text.split("\n"))
            self.chat_view.append(f'<b>{who}</b><br><p>{body}</p><br>')
        else:
            self.chat_view.append(f'<b>{who}</b><br>{render_md(text)}<br>')
        # 新消息后始终滚到最底部
        bar = self.chat_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _greet(self):
        self._append("助手", "你好，我是超级白工具箱的智能管家。问我任何问题，或告诉我你想做什么（比如压缩视频、清理残留），我会帮你指路或执行。")

    # ---------- 对话记忆 ----------
    def _restore_state(self):
        hist, model, persona = _load_memory()
        self.history = list(hist)
        # 恢复人设/模型（仍在可选列表内才应用）
        if persona and persona in PERSONAS:
            self.persona_box.setCurrentText(persona)
        if model:
            idx = self.model_box.findData(model)
            if idx >= 0:
                self.model_box.setCurrentIndex(idx)

    def _render_history(self):
        """把已保存的历史重放进聊天区"""
        self.chat_view.clear()
        for msg in self.history:
            if msg.get("role") == "user":
                self._append("你", msg.get("content", ""))
            elif msg.get("role") == "assistant":
                self._append("助手", msg.get("content", ""))

    def _save_history(self):
        _save_memory(self.history, self._current_model(), self.persona_box.currentText())

    def _export(self):
        if not self.history:
            from PySide6.QtWidgets import QMessageBox
            box = QMessageBox(self)
            box.setWindowTitle("导出对话")
            box.setText("当前没有可导出的对话。")
            box.exec()
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出对话", "ai_dialog.txt", "文本文件 (*.txt);;Markdown (*.md)")
        if not path:
            return
        lines = []
        for m in self.history:
            role = "你" if m.get("role") == "user" else "助手"
            lines.append(f"[{role}]\n{m.get('content', '')}\n")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            box = QMessageBox(self)
            box.setWindowTitle("导出完成")
            box.setText(f"对话已导出到：\n{path}")
            box.exec()
        except Exception as exc:
            box = QMessageBox(self)
            box.setWindowTitle("导出失败")
            box.setIcon(QMessageBox.Warning)
            box.setText(f"导出失败：{exc}")
            box.exec()

    def _current_model(self):
        return self.model_box.currentData()

    def _current_persona(self):
        return PERSONAS[self.persona_box.currentText()]

    def _send(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        if self.worker and self.worker.isRunning():
            self._append("系统", "上一条回复还没完成，请稍候…")
            return
        self.input_edit.clear()
        self._append("你", text)
        self.history.append({"role": "user", "content": text})

        # 工具箱引导：命中关键词先给出入口提示，仍让模型补充
        hint = self._tool_hint(text)
        if hint:
            self._append("助手", hint)

        self._append("助手", "正在思考…")
        self.worker = AiReplyThread(self._current_model(), list(self.history), self._current_persona())
        self.worker.replied.connect(self._on_reply)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _tool_hint(self, text):
        low = text.lower()
        for kws, msg in TOOL_HINTS:
            if any(k in low for k in kws):
                return "提示：" + msg
        return None

    def _on_reply(self, reply):
        # 去掉上一次占位
        self._strip_thinking()
        self.history.append({"role": "assistant", "content": reply})
        self._append("助手", reply)
        self._save_history()

    def _on_fail(self, err):
        self._strip_thinking()
        self.history.pop()  # 移除最后一条 user，避免重发时重复
        self._append("系统", f"请求失败：{err}\n请检查网络或稍后重试。")

    def _strip_thinking(self):
        """移除「正在思考…」占位（QTextEdit HTML 结构）"""
        html = self.chat_view.toHtml()
        # 可能以 <p>…</p> 或纯文本存在
        html = re.sub(r"<p[^>]*>正在思考…</p>", "", html)
        html = re.sub(r"正在思考…", "", html)
        html = re.sub(r"<br>\s*<br>", "<br>", html)
        self.chat_view.setHtml(html)

    @staticmethod
    def _escape_line(line):
        import html as _h
        return _h.escape(line, quote=False)

    def _clear(self):
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("清空对话")
        box.setText("确定要清空当前对话吗？清空后不可恢复。")
        box.setIcon(QMessageBox.Warning)
        btn_ok = box.addButton("清空", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() != btn_ok:
            return
        self.history = []
        self.chat_view.clear()
        _save_memory([], self._current_model(), self.persona_box.currentText())
        self._greet()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(event)


def open_ai_assistant(self):
    dlg = getattr(self, "_ai_assistant_dlg", None)
    if dlg is None:
        dlg = AiAssistantDialog(self)
        setattr(self, "_ai_assistant_dlg", dlg)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
