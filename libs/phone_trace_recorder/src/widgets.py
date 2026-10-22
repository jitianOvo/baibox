"""轻量自研控件:OptionPicker 下拉选择。

替代 CTkComboBox:
- 第一次点击展开、第二次点击收起;
- 深色菜单与 UI 同色系;自绘 ▾ 箭头,无 CTk 画布箭头的黑色像素点瑕疵。

Windows 坑位说明:菜单弹出时持有 grab,再点按钮时菜单先被 grab 收起、
点击随后才送到按钮 —— 若用 winfo_ismapped 判断会"关了又开"。
因此用 _menu_open 状态 + 打开时间戳判定,并用轮询同步"点击别处关闭"。
"""
from __future__ import annotations

import time
import tkinter as tk

import customtkinter as ctk

from . import theme


class OptionPicker(ctk.CTkButton):
    def __init__(self, master, values, command=None, width=120, font=None, **kw):
        self._values = list(values)
        self._pick_cmd = command
        self._value = self._values[0] if self._values else ""
        self._font = font or theme.font(ctk, 12)
        self._menu = None
        self._menu_open = False
        self._opened_at = 0.0
        super().__init__(master, text=self._label(), anchor="w", width=width,
                         height=32, font=self._font, fg_color=theme.CARD,
                         hover_color=theme.CARD_HOVER, text_color=theme.TXT,
                         corner_radius=theme.R_SM, command=self.toggle, **kw)
        self._build_menu()

    # ---- 对外接口(与 CTkComboBox 用法对齐) ----
    def get(self):
        return self._value

    def set(self, v):
        self._value = v
        self.configure(text=self._label())

    def set_values(self, values, reset=False):
        self._values = list(values)
        self._build_menu()
        if reset or self._value not in self._values:
            self.set(self._values[0] if self._values else "")

    # ---- 内部 ----
    def _label(self):
        return "%s   ▾" % self._value

    def _build_menu(self):
        if self._menu is not None:
            try:
                self._menu.destroy()
            except Exception:
                pass
            self._menu = None
        self._menu_open = False
        self._menu = tk.Menu(self, tearoff=0, bg=theme.CARD, fg=theme.TXT,
                             activebackground=theme.CARD_HOVER,
                             activeforeground="white", bd=0, relief="flat",
                             font=(theme.FONT_FAMILY, 10))
        for v in self._values:
            self._menu.add_command(label=v, command=lambda vv=v: self._choose(vv))

    def toggle(self):
        if not self._menu_open:
            self._open_menu()
            return
        self._close_menu()

    def _open_menu(self):
        """用 post() 非阻塞弹出(tk_popup 在 Windows 上是模态的,会卡住回调,
        这正是"第二次点击还是显示"的根源);再绑定全局点击实现点外关闭。"""
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        self._menu_open = True
        try:
            self._menu.post(x, y)
        except Exception:
            import traceback
            traceback.print_exc()
            self._menu_open = False
            return
        # 点到任何其他控件/空白处时自动收起(菜单自身区域不经过 bind_all)
        # CTk 禁用了 bind_all(怕误用),这里显式走 tkinter 原始方法
        tk.Misc.bind_all(self, "<Button-1>", self._on_global_click, add="+")

    def _on_global_click(self, event):
        if not self._menu_open:
            return
        # 点击在本按钮或其子控件(canvas 等)上:交给按钮自身的 toggle 处理;
        # 点在其余任何地方:收起菜单
        w = event.widget
        while w is not None:
            if w is self:
                return
            w = getattr(w, "master", None)
        self._close_menu()

    def _close_menu(self):
        self._menu_open = False
        try:
            self._menu.unpost()
        except Exception:
            pass
        try:
            tk.Misc.unbind_all(self, "<Button-1>")
        except Exception:
            pass

    def _choose(self, v):
        self._close_menu()
        self._value = v
        self.configure(text=self._label())
        if self._pick_cmd:
            try:
                self._pick_cmd(v)
            except Exception:
                pass
