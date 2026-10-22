"""深色风格窗口系统:统一浮动窗口基类 + 各类对话框。

【白闪根因与架构】CTkToplevel 在 Windows 上会先以白色底映射窗口、再应用
深色主题,"白→黑"闪烁的时序在框架内部,不可控。因此:

- 统一基类 DarkToplevel 用纯 tk.Toplevel:创建即 withdraw,深色背景与全部
  内容就绪后才显示(显示即最终态);配合深色窗口类背景刷(见
  _ensure_dark_toplevel_class)三重防护,白闪在机制上不可能;
- 系统标题栏可拖动、带程序图标;geometry 为原始像素,无 CTk 二次缩放;
- 确认框 / 输入框 / 多字段 / 选择 / 参数编辑共用同一基类与设计语言。
"""
from __future__ import annotations

import base64
import tkinter as tk

import customtkinter as ctk

from . import storage
from . import theme

_dark_class_done = False


def _ensure_dark_toplevel_class(win):
    """把 TkTopLevel 窗口类的背景刷改为主题深色(只做一次)。

    Windows 在 Tk 首次绘制窗口前会用「窗口类背景刷」填充整个窗口(默认
    白色),这是所有 Toplevel 弹窗"白闪→变黑"的根因。类刷改深后,本进程
    所有同类顶层窗口从出生就是深色。
    """
    global _dark_class_done
    if _dark_class_done:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hwnd = win.winfo_id()
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if buf.value != "TkTopLevel":
            return
        brush = gdi32.CreateSolidBrush(ctypes.c_int(0x001B1616))
        user32.SetClassLongPtrW(hwnd, -10, brush)
        _dark_class_done = True
    except Exception:
        pass


def apply_icon(win):
    """给顶层窗口绑定程序图标(标题栏 + 任务栏),失败静默。

    纯 tk.Toplevel 无 CTk 二次缩放,设置一次即可,不做延迟重设
    (重设图标会让刚弹出的窗口标题栏再闪一下)。
    """
    ico = storage.BASE_DIR / "assets" / "icon.ico"
    if not ico.exists():
        return
    try:
        win.iconbitmap(str(ico))
    except Exception:
        pass


class DarkToplevel(tk.Toplevel):
    """统一浮动窗口基组件(替代 CTkToplevel)。

    三重防白闪:
    1. 创建即 withdraw,深色背景与全部内容就绪后才 deiconify(显示即最终态);
    2. 窗口类背景刷已改为深色(TkTopLevel 类);
    3. 纯 tk.Toplevel 的 geometry 为原始像素,不经过 CTk 二次缩放。

    具备:系统标题栏(可拖动)、程序图标、尺寸随内容、居中于父窗口。
    """

    def __init__(self, master, title="", width=380):
        super().__init__(master)
        self.withdraw()
        self._master = master
        self._width = width
        _ensure_dark_toplevel_class(self)
        self.title(title)
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        apply_icon(self)
        self.bind("<Escape>", lambda e: self.destroy())

    def show_centered(self):
        """内容就绪后调用:按内容自适应尺寸,居中于父窗口并显示。

        顺序敏感:transient 必须在 deiconify 之前设置 —— 窗口已映射后再设
        父属关系会让系统重排/重绘一次,造成"弹出后闪跳一下"的观感。
        """
        self.update_idletasks()
        w = max(self._width, self.winfo_reqwidth())
        h = self.winfo_reqheight()
        try:
            mx, my = self._master.winfo_rootx(), self._master.winfo_rooty()
            mw, mh = self._master.winfo_width(), self._master.winfo_height()
            x = mx + max(0, (mw - w) // 2)
            y = my + max(40, (mh - h) // 3)
        except Exception:
            x = y = 120
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        try:
            self.transient(self._master)
        except Exception:
            pass
        self.deiconify()
        self.lift()


class _Modal(DarkToplevel):
    """深色模态浮动窗口基类:统一尺寸/圆角/间距/图标/可拖动。

    确认框、输入框、多字段、选择、参数编辑共用本基类(同一设计语言)。
    用法不变:wait_window(dlg) 等待关闭(OK/取消/Esc 均 destroy 自身)。
    """

    def __init__(self, master, title, width=380):
        DarkToplevel.__init__(self, master, title, width)
        self.body = ctk.CTkFrame(self, fg_color=theme.BG)
        self.body.pack(fill="both", expand=True, padx=22, pady=18)

    def _finish_build(self):
        self.show_centered()
        try:
            self.grab_set()      # 模态:主窗其余控件暂不响应
        except Exception:
            pass

    def _btn(self, parent, text, command, kind="normal"):
        colors = {"danger": (theme.RED, theme.RED_HOVER, "white"),
                  "primary": (theme.ACC, theme.ACC_HOVER, "white"),
                  "ghost": (theme.CARD, theme.CARD_HOVER, theme.SUB)}
        fg, hv, tc = colors[kind]
        return ctk.CTkButton(parent, text=text, command=command, width=92, height=34,
                             font=theme.font(ctk, 13), fg_color=fg,
                             hover_color=hv, text_color=tc, corner_radius=theme.R_SM)


class ConfirmDialog(_Modal):
    """危险操作确认框。结束后读 dlg.confirmed。"""

    def __init__(self, master, title, message, confirm_text="删除", width=380):
        _Modal.__init__(self, master, title, width)
        self.confirmed = False
        ctk.CTkLabel(self.body, text=title, font=theme.font(ctk, 16, "bold"),
                     text_color=theme.TXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(self.body, text=message, font=theme.font(ctk, 12),
                     text_color=theme.SUB, anchor="w", justify="left",
                     wraplength=width - 64).pack(fill="x", pady=(10, 18))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x")
        ok = self._btn(row, confirm_text, self._ok, "danger")
        ok.pack(side="right")
        ok.focus_set()
        self._btn(row, "取消", self.destroy, "ghost").pack(side="right", padx=(0, 10))
        self.bind("<Return>", lambda e: self._ok())
        self._finish_build()

    def _ok(self):
        self.confirmed = True
        self.destroy()


class InputDialog(_Modal):
    """单值输入框。结束后读 dlg.value(None=取消)。"""

    def __init__(self, master, title, label, initial="", hint=None, width=380):
        _Modal.__init__(self, master, title, width)
        self.value = None
        ctk.CTkLabel(self.body, text=title, font=theme.font(ctk, 16, "bold"),
                     text_color=theme.TXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(self.body, text=label, font=theme.font(ctk, 12),
                     text_color=theme.SUB, anchor="w").pack(fill="x", pady=(10, 4))
        self.ent = ctk.CTkEntry(self.body, font=theme.font(ctk, 13), height=36,
                                fg_color=theme.CARD, border_width=0, text_color=theme.TXT,
                                corner_radius=theme.R_SM)
        self.ent.insert(0, initial)
        self.ent.pack(fill="x")
        self.ent.select_range(0, "end")
        if hint:
            ctk.CTkLabel(self.body, text=hint, font=theme.font(ctk, 11),
                         text_color=theme.SUB, anchor="w", justify="left",
                         wraplength=width - 64).pack(fill="x", pady=(8, 0))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        ok = self._btn(row, "确定", self._ok, "primary")
        ok.pack(side="right")
        self._btn(row, "取消", self.destroy, "ghost").pack(side="right", padx=(0, 10))
        self.bind("<Return>", lambda e: self._ok())
        self._finish_build()
        self.ent.focus_set()

    def _ok(self):
        self.value = self.ent.get().strip()
        self.destroy()


class FieldsDialog(_Modal):
    """多字段输入框(如滑动坐标起止点)。结束后读 dlg.values(字符串列表,None=取消)。"""

    def __init__(self, master, title, note, fields, hint=None, width=380):
        """fields: [(字段名, 初始值), ...]"""
        _Modal.__init__(self, master, title, width)
        self.values = None
        ctk.CTkLabel(self.body, text=title, font=theme.font(ctk, 16, "bold"),
                     text_color=theme.TXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(self.body, text=note, font=theme.font(ctk, 12),
                     text_color=theme.SUB, anchor="w", justify="left",
                     wraplength=width - 64).pack(fill="x", pady=(8, 4))
        self.entries = []
        for label, initial in fields:
            ctk.CTkLabel(self.body, text=label, font=theme.font(ctk, 11),
                         text_color=theme.SUB, anchor="w").pack(fill="x", pady=(8, 2))
            e = ctk.CTkEntry(self.body, font=theme.font(ctk, 13), height=34,
                             fg_color=theme.CARD, border_width=0, text_color=theme.TXT,
                             corner_radius=theme.R_SM)
            e.insert(0, str(initial))
            e.pack(fill="x")
            self.entries.append(e)
        if hint:
            ctk.CTkLabel(self.body, text=hint, font=theme.font(ctk, 11),
                         text_color=theme.SUB, anchor="w", justify="left",
                         wraplength=width - 64).pack(fill="x", pady=(10, 0))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        ok = self._btn(row, "确定", self._ok, "primary")
        ok.pack(side="right")
        self._btn(row, "取消", self.destroy, "ghost").pack(side="right", padx=(0, 10))
        self.bind("<Return>", lambda e: self._ok())
        self._finish_build()
        if self.entries:
            self.entries[0].focus_set()
            self.entries[0].select_range(0, "end")

    def _ok(self):
        self.values = [e.get().strip() for e in self.entries]
        self.destroy()


class ChoiceDialog(_Modal):
    """单选对话框。结束后读 dlg.value(None=取消)。options: [(value, label), ...]"""

    def __init__(self, master, title, options, current=None, hint=None, width=360):
        _Modal.__init__(self, master, title, width)
        self.value = None
        values = [v for v, _ in options]
        ctk.CTkLabel(self.body, text=title, font=theme.font(ctk, 16, "bold"),
                     text_color=theme.TXT, anchor="w").pack(fill="x")
        var = ctk.StringVar(value=current if current in values else (values[0] if values else ""))
        for val, lbl in options:
            ctk.CTkRadioButton(self.body, text=lbl, variable=var, value=val,
                               font=theme.font(ctk, 12), fg_color=theme.ACC,
                               text_color=theme.TXT,
                               radiobutton_width=18, radiobutton_height=18
                               ).pack(anchor="w", pady=5)
        if hint:
            ctk.CTkLabel(self.body, text=hint, font=theme.font(ctk, 11),
                         text_color=theme.SUB, anchor="w", justify="left",
                         wraplength=width - 64).pack(fill="x", pady=(10, 0))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        ok = self._btn(row, "确定", self._ok, "primary")
        ok.pack(side="right")
        self._btn(row, "取消", self.destroy, "ghost").pack(side="right", padx=(0, 10))
        self.bind("<Return>", lambda e: self._ok())
        self._ok_var = var
        self._finish_build()

    def _ok(self):
        self.value = self._ok_var.get()
        self.destroy()


class ActionEditDialog(_Modal):
    """动作参数集成编辑:坐标(自动按点击/滑动给字段)+ 按下时长 + 等待 + 方向 + 序号移动。

    确定后 dlg.result 为参数 dict(已做类型/范围校验),取消为 None;
    dlg.new_pos 为移动后的新序号(id=total 时可为 None/原值,表示不移动)。
    字段非法时不关窗,直接在窗内红字提示。
    """

    def __init__(self, master, g, total=1, current=1, note=None, width=400):
        gtype = g["type"]
        title = "编辑动作参数(%s)" % theme.TYPE_NAMES.get(gtype, gtype)
        _Modal.__init__(self, master, title, width)
        self.result = None
        self.new_pos = None
        self._total = max(1, int(total))
        self.entries = []
        swipe = gtype == "swipe"
        self._entries = []
        self._keys = []

        ctk.CTkLabel(self.body, text=title, font=theme.font(ctk, 16, "bold"),
                     text_color=theme.TXT, anchor="w").pack(fill="x")
        if note:
            ctk.CTkLabel(self.body, text=note, font=theme.font(ctk, 11),
                         text_color=theme.SUB, anchor="w", justify="left",
                         wraplength=width - 64).pack(fill="x", pady=(6, 2))

        # 序号移动(可把该动作加塞到别的位置,原位置之后的编号顺移)
        posrow = ctk.CTkFrame(self.body, fg_color="transparent")
        posrow.pack(fill="x", pady=(10, 2))
        ctk.CTkLabel(posrow, text="动作序号 #", font=theme.font(ctk, 11),
                     text_color=theme.SUB).pack(side="left")
        self._pos_entry = ctk.CTkEntry(posrow, font=theme.font(ctk, 13), width=70,
                                       height=30, fg_color=theme.CARD, border_width=0,
                                       text_color=theme.TXT, corner_radius=theme.R_SM)
        self._pos_entry.insert(0, str(current))
        self._pos_entry.pack(side="left", padx=(6, 0))
        ctk.CTkLabel(posrow, text="(1~%d,改此值可调顺序)" % self._total,
                     font=theme.font(ctk, 10), text_color=theme.SUB
                     ).pack(side="left", padx=(8, 0))

        coord_fields = ([("起点 X", g["x1"]), ("起点 Y", g["y1"]),
                         ("终点 X", g["x2"]), ("终点 Y", g["y2"])] if swipe
                        else [("坐标 X", g["x"]), ("坐标 Y", g["y"])])
        rows = coord_fields + [("按下时长 (ms)", g["duration_ms"]),
                               ("执行前等待 (ms)", g["delay_ms"])]
        for label, val in rows:
            ctk.CTkLabel(self.body, text=label, font=theme.font(ctk, 11),
                         text_color=theme.SUB, anchor="w").pack(fill="x", pady=(7, 2))
            e = ctk.CTkEntry(self.body, font=theme.font(ctk, 13), height=34,
                             fg_color=theme.CARD, border_width=0, text_color=theme.TXT,
                             corner_radius=theme.R_SM)
            e.insert(0, str(val))
            e.pack(fill="x")
            self.entries.append(e)
            self._entries.append(e)
            self._keys.append(label)

        ctk.CTkLabel(self.body, text="方向(该步操作时手机旋转)", font=theme.font(ctk, 11),
                     text_color=theme.SUB, anchor="w").pack(fill="x", pady=(10, 3))
        rot = str(int(g.get("rot", 0) or 0))
        self._rot_var = ctk.StringVar(value=rot)
        self._rot_row = ctk.CTkFrame(self.body, fg_color="transparent")
        self._rot_row.pack(fill="x")
        # CTkRadioButton 默认宽度 160px,四个并排必然裁切第四项;
        # 显式给小宽度,保证任意情况下四个选项(圆圈+文字)完整可见
        for val, lbl in (("0", "竖 0°"), ("90", "横 90°"),
                         ("180", "倒 180°"), ("270", "横 270°")):
            ctk.CTkRadioButton(self._rot_row, text=lbl, variable=self._rot_var,
                               value=val, width=80, font=theme.font(ctk, 11),
                               fg_color=theme.ACC, text_color=theme.TXT,
                               radiobutton_width=18, radiobutton_height=18,
                               ).pack(side="left", padx=(0, 6))

        self.lbl_err = ctk.CTkLabel(self.body, text="", font=theme.font(ctk, 11),
                                    text_color=theme.ERR, anchor="w", justify="left",
                                    wraplength=width - 64)
        self.lbl_err.pack(fill="x", pady=(10, 0))

        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        ok = self._btn(row, "保存", self._ok, "primary")
        ok.pack(side="right")
        self._btn(row, "取消", self.destroy, "ghost").pack(side="right", padx=(0, 10))
        self.bind("<Return>", lambda e: self._ok())
        self._finish_build()
        if self._entries:
            self._entries[0].focus_set()
            self._entries[0].select_range(0, "end")

    def _ok(self):
        # 序号移动解析(1~total)
        try:
            new_pos = int(self._pos_entry.get().strip())
        except ValueError:
            self._show_err("序号需为整数")
            return
        if not (1 <= new_pos <= self._total):
            self._show_err("序号需在 1~%d 之间" % self._total)
            return
        self.new_pos = new_pos

        try:
            nums = [int(e.get().strip()) for e in self._entries]
            rot = int(self._rot_var.get())
        except ValueError:
            self._show_err("所有字段都需要非负整数(时长需 ≥ 1)")
            return
        swipe = len(nums) == 6
        if any(v < 0 for v in nums) or nums[-2] < 1:
            self._show_err("坐标 ≥ 0,按下时长 ≥ 1ms,等待 ≥ 0ms")
            return
        result = {"duration_ms": nums[-2], "delay_ms": nums[-1], "rot": rot,
                  "ori": "landscape" if rot in (90, 270) else "portrait"}
        if swipe:
            result.update({"x1": nums[0], "y1": nums[1], "x2": nums[2], "y2": nums[3]})
        else:
            result.update({"x": nums[0], "y": nums[1]})
        self.result = result
        self.destroy()

    def _show_err(self, msg):
        self.lbl_err.configure(text="⚠ " + msg)


class NoteDialog(_Modal):
    """动作备注编辑(多行文本)。

    确定后 dlg.value 为字符串(留空 = 清除备注),取消为 None。
    Enter 在文本框内换行,Ctrl+Enter 或「保存」按钮确定。
    """

    def __init__(self, master, title, initial="", width=420):
        _Modal.__init__(self, master, title, width)
        self.value = None
        ctk.CTkLabel(self.body, text=title, font=theme.font(ctk, 16, "bold"),
                     text_color=theme.TXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(self.body, text="备注内容(留空 = 清除备注,支持多行)",
                     font=theme.font(ctk, 11), text_color=theme.SUB,
                     anchor="w").pack(fill="x", pady=(10, 4))
        self.txt = ctk.CTkTextbox(self.body, height=120, font=theme.font(ctk, 13),
                                  fg_color=theme.CARD, border_width=0,
                                  text_color=theme.TXT, corner_radius=theme.R_SM)
        self.txt.insert("1.0", initial)
        self.txt.pack(fill="x")

        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        ok = self._btn(row, "保存", self._ok, "primary")
        ok.pack(side="right")
        self._btn(row, "取消", self.destroy, "ghost").pack(side="right", padx=(0, 10))
        self.bind("<Control-Return>", lambda e: self._ok())
        self._finish_build()
        self.txt.focus_set()
        # CTkTextbox 无 select_range,经底层 tk Text 全选以便直接覆盖
        try:
            self.txt._textbox.tag_add("sel", "1.0", "end-1c")
        except Exception:
            pass

    def _ok(self):
        self.value = self.txt.get("1.0", "end").strip()
        self.destroy()


class ActionNewDialog(_Modal):
    """新建动作:位置 + 类型 + 坐标 + 按下时长 + 执行前等待 + 方向,一次配置完成。

    确定后 dlg.result 为完整动作 dict(含 type/坐标/时长/等待/方向/note),
    dlg.insert_at 为 1-based 插入序号(1~total+1);取消时 result 为 None。
    total = 当前已有动作数,默认插入位置 = total+1(追加到末尾),可手动改。
    """

    _TYPE_DEFAULTS = {
        "tap":        {"label": "点击", "coords": ("坐标 X", "坐标 Y"),
                       "dur": 100, "count": 2},
        "long_press": {"label": "长按", "coords": ("坐标 X", "坐标 Y"),
                       "dur": 600, "count": 2},
        "swipe":      {"label": "滑动", "coords": ("起点 X", "起点 Y", "终点 X", "终点 Y"),
                       "dur": 300, "count": 4},
    }

    def __init__(self, master, total=0, width=420):
        _Modal.__init__(self, master, "新建动作", width)
        self.result = None
        self.insert_at = total + 1
        self._total = total
        self._entries = []
        self._type_var = ctk.StringVar(value="tap")
        self._rot_var = ctk.StringVar(value="0")

        ctk.CTkLabel(self.body, text="新建动作", font=theme.font(ctk, 16, "bold"),
                     text_color=theme.TXT, anchor="w").pack(fill="x")

        # 插入位置(默认末尾,可手动选择 1~total+1)
        posrow = ctk.CTkFrame(self.body, fg_color="transparent")
        posrow.pack(fill="x", pady=(10, 2))
        ctk.CTkLabel(posrow, text="插入位置 #", font=theme.font(ctk, 11),
                     text_color=theme.SUB).pack(side="left")
        self._pos_entry = ctk.CTkEntry(posrow, font=theme.font(ctk, 13), width=70,
                                       height=30, fg_color=theme.CARD, border_width=0,
                                       text_color=theme.TXT, corner_radius=theme.R_SM)
        self._pos_entry.insert(0, str(self.insert_at))
        self._pos_entry.pack(side="left", padx=(6, 0))
        ctk.CTkLabel(posrow, text="(1~%d,末尾追加)" % (total + 1),
                     font=theme.font(ctk, 10), text_color=theme.SUB
                     ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(self.body, text="动作类型", font=theme.font(ctk, 11),
                     text_color=theme.SUB, anchor="w").pack(fill="x", pady=(10, 3))
        trow = ctk.CTkFrame(self.body, fg_color="transparent")
        trow.pack(fill="x")
        for val in ("tap", "long_press", "swipe"):
            ctk.CTkRadioButton(trow, text=self._TYPE_DEFAULTS[val]["label"],
                               variable=self._type_var, value=val, width=88,
                               font=theme.font(ctk, 12), fg_color=theme.ACC,
                               text_color=theme.TXT, radiobutton_width=18,
                               radiobutton_height=18,
                               command=self._rebuild_fields).pack(side="left", padx=(0, 6))

        self.fields_box = ctk.CTkFrame(self.body, fg_color="transparent")
        self.fields_box.pack(fill="x", pady=(4, 0))
        self.fields_box.grid_columnconfigure(0, weight=1)
        self.fields_box.grid_columnconfigure(1, weight=1)
        self._rebuild_fields()

        ctk.CTkLabel(self.body, text="方向(该步操作时手机旋转)", font=theme.font(ctk, 11),
                     text_color=theme.SUB, anchor="w").pack(fill="x", pady=(10, 3))
        rrow = ctk.CTkFrame(self.body, fg_color="transparent")
        rrow.pack(fill="x")
        for val, lbl in (("0", "竖 0°"), ("90", "横 90°"),
                         ("180", "倒 180°"), ("270", "横 270°")):
            ctk.CTkRadioButton(rrow, text=lbl, variable=self._rot_var, value=val,
                               width=80, font=theme.font(ctk, 11), fg_color=theme.ACC,
                               text_color=theme.TXT, radiobutton_width=18,
                               radiobutton_height=18).pack(side="left", padx=(0, 6))

        self.lbl_err = ctk.CTkLabel(self.body, text="", font=theme.font(ctk, 11),
                                    text_color=theme.ERR, anchor="w", justify="left",
                                    wraplength=width - 64)
        self.lbl_err.pack(fill="x", pady=(10, 0))

        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        ok = self._btn(row, "添加", self._ok, "primary")
        ok.pack(side="right")
        self._btn(row, "取消", self.destroy, "ghost").pack(side="right", padx=(0, 10))
        self.bind("<Return>", lambda e: self._ok())
        self._finish_build()
        if self._entries:
            self._entries[0].focus_set()
            self._entries[0].select_range(0, "end")

    def _entry(self, label, value):
        """fields_box 内新增一行带标签的输入框,返回 entry。"""
        f = ctk.CTkFrame(self.fields_box, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=label, font=theme.font(ctk, 11),
                     text_color=theme.SUB, anchor="w").pack(fill="x")
        e = ctk.CTkEntry(f, font=theme.font(ctk, 13), height=30,
                         fg_color=theme.CARD, border_width=0, text_color=theme.TXT,
                         corner_radius=theme.R_SM)
        e.insert(0, str(value))
        e.pack(fill="x")
        self._entries.append(e)
        return f

    def _rebuild_fields(self):
        """按当前类型重建坐标/时长/等待字段(切换类型时调用)。"""
        for w in self.fields_box.winfo_children():
            w.destroy()
        self._entries = []
        spec = self._TYPE_DEFAULTS[self._type_var.get()]
        # 坐标字段按 2 列排布
        for i, label in enumerate(spec["coords"]):
            f = self._entry(label, 0)
            f.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 8), pady=(5, 0))
        # 时长 + 等待:同一行两列(in_= 把输入框容器挂到 hbox 上)
        hbox = ctk.CTkFrame(self.fields_box, fg_color="transparent")
        hbox.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        hbox.grid_columnconfigure(0, weight=1)
        hbox.grid_columnconfigure(1, weight=1)
        f1 = self._entry("按下时长 (ms)", spec["dur"])
        f1.grid(in_=hbox, row=0, column=0, sticky="ew", padx=(0, 8))
        f2 = self._entry("执行前等待 (ms)", 500)
        f2.grid(in_=hbox, row=0, column=1, sticky="ew")

    def _ok(self):
        # 插入位置解析(1~total+1)
        try:
            pos = int(self._pos_entry.get().strip())
        except ValueError:
            self.lbl_err.configure(text="⚠ 插入位置需为整数")
            return
        if not (1 <= pos <= self._total + 1):
            self.lbl_err.configure(text="⚠ 插入位置需在 1~%d 之间" % (self._total + 1))
            return
        self.insert_at = pos

        try:
            nums = [int(e.get().strip()) for e in self._entries]
            rot = int(self._rot_var.get())
        except ValueError:
            self.lbl_err.configure(text="⚠ 所有字段都需要整数(时长需 ≥ 1)")
            return
        spec = self._TYPE_DEFAULTS[self._type_var.get()]
        n = spec["count"]
        if len(nums) != n + 2:
            self.lbl_err.configure(text="⚠ 字段数量异常,请重试")
            return
        coords, dur, delay = nums[:n], nums[n], nums[n + 1]
        if any(v < 0 for v in coords) or dur < 1 or delay < 0:
            self.lbl_err.configure(text="⚠ 坐标 ≥ 0,按下时长 ≥ 1ms,等待 ≥ 0ms")
            return
        g = {"type": self._type_var.get(), "delay_ms": delay, "duration_ms": dur,
             "rot": rot, "ori": "landscape" if rot in (90, 270) else "portrait",
             "note": ""}
        if self._type_var.get() == "swipe":
            g.update({"x1": coords[0], "y1": coords[1], "x2": coords[2], "y2": coords[3]})
        else:
            g.update({"x": coords[0], "y": coords[1]})
        self.result = g
        self.destroy()


class PreviewWindow(DarkToplevel):
    """设备画面预览窗(update_image 可反复刷新)。"""

    def __init__(self, master, png_bytes, on_refresh=None):
        DarkToplevel.__init__(self, master, "设备画面预览(F5 刷新)", width=340)
        self.attributes("-topmost", True)   # 置顶弹出,确保不被主窗挡住
        self._on_refresh = on_refresh
        self._photo = None

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(bar, text="手机当前画面(缩放显示)", font=theme.font(ctk, 12),
                     text_color=theme.SUB).pack(side="left")
        if on_refresh:
            ctk.CTkButton(bar, text="⟳ 刷新", width=76, height=28,
                          font=theme.font(ctk, 12), fg_color=theme.CARD,
                          hover_color=theme.CARD_HOVER, text_color=theme.TXT,
                          corner_radius=theme.R_SM, command=self.refresh).pack(side="right")
            self.bind("<F5>", lambda e: self.refresh())
        self.img_label = ctk.CTkLabel(self, text="加载中…", font=theme.font(ctk, 13),
                                      text_color=theme.SUB)
        self.img_label.pack(padx=14, pady=(0, 14))
        self.update_image(png_bytes)

    def refresh(self):
        if callable(self._on_refresh):
            self._on_refresh()

    def update_image(self, png_bytes):
        try:
            try:
                import ctypes
                us = ctypes.windll.user32
                sw, sh = us.GetSystemMetrics(0), us.GetSystemMetrics(1)   # 物理像素
            except Exception:
                sw, sh = 1920, 1080
            # 画面尽量占满(66% 高 / 52% 宽);tk.PhotoImage = 原始像素,无缩放漂移
            max_h = sh * 0.66
            max_w = sw * 0.52
            ph = tk.PhotoImage(data=base64.b64encode(png_bytes).decode("ascii"))
            factor = max(1, round(max(ph.width() / max_w, ph.height() / max_h)))
            if factor > 1:
                ph = ph.subsample(factor, factor)
            self._photo = ph
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # 原生像素显示为刻意选择,压掉 HighDPI 提示
                self.img_label.configure(image=self._photo, text="")
        except Exception:
            import traceback
            traceback.print_exc()   # 预览失败必须留痕,不允许静默
            self._photo = None
            self.img_label.configure(image=None, text="截图解码失败(详见控制台日志)")
        self._center_and_show()

    def _center_and_show(self):
        try:
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            try:
                import ctypes
                us = ctypes.windll.user32
                sw, sh = us.GetSystemMetrics(0), us.GetSystemMetrics(1)
            except Exception:
                sw, sh = 1920, 1080
            w, h = min(w, sw), min(h, sh)
            mx, my = self._master.winfo_rootx(), self._master.winfo_rooty()
            mw, mh = self._master.winfo_width(), self._master.winfo_height()
            x = mx + max(0, (mw - w) // 2)
            y = my + max(30, (mh - h) // 4)
            x = min(max(0, x), max(0, sw - w))
            y = min(max(0, y), max(0, sh - h))
            self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        except Exception:
            pass
        self.deiconify()
        self.lift()


def _load_photo(png_bytes, max_w, max_h):
    """PNG 字节 → 在 max_w×max_h 内尽量放大的图片对象。"""
    ph = tk.PhotoImage(data=base64.b64encode(png_bytes).decode("ascii"))
    factor = max(1, round(max(ph.width() / max_w, ph.height() / max_h)))
    if factor > 1:
        ph = ph.subsample(factor, factor)
    return ph
