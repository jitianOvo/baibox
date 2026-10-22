"""主界面:深色卡片风(CustomTkinter),设计令牌统一取自 theme.py。

布局:
- 左侧栏:设备选择、录制按钮(录制中呼吸灯)、搜索+排序、记录卡片列表、文件夹入口;
  上方(设备/录制/搜索)与下方(记录列表)之间为可拖动分隔条,位置记忆持久化;
- 右侧:详情区为【持久控件】—— 切换记录只更新内容、不销毁重建,避免闪烁;
  含名称+徽章统计、动作表(网格化表格 + 常驻操作条)、回放输出、工具行、toast。

键盘:Delete 删除选中记录(带确认)、F2 重命名、↑/↓ 切换记录;焦点在输入框内时不拦截。
"""
from __future__ import annotations

import base64
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
import tkinter.filedialog as filedialog

import customtkinter as ctk

from . import adb_utils, exporter, player, storage
from . import settings as app_settings
from . import theme
from .dialogs import (ActionEditDialog, ActionNewDialog, ConfirmDialog,
                      DarkToplevel, InputDialog, NoteDialog, PreviewWindow)
from .recorder import Recorder
from .widgets import OptionPicker

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

SORTS = (("time_desc", "最新优先"), ("time_asc", "最早优先"), ("count_desc", "动作数优先"))
SPEEDS = ("0.5x", "1x", "1.5x", "2x", "3x")
LOOPS = ("1", "2", "3", "5", "10", "自定义…", "∞")

LOOP_INFINITY = "∞"   # 无限循环的统一标记(内部用 0 表示无限)

# 动作表列规格:(标题, 固定像素宽或 None=弹性, 弹性权重)
# 固定列保持像素宽,弹性列按权重分摊剩余宽度 —— 共用同一 grid,列自然靠左对齐。
_TBL_COLS = (("#", 40, 0), ("类型", 64, 0), ("参数(自然方向)", None, 3),
             ("按下时长", 92, 0), ("前等待", 82, 0), ("方向", 68, 0),
             ("备注(双击编辑)", None, 2))

# 分栏:分隔条厚度 / 各面板最小尺寸 / 上方面板默认高度(均为「逻辑像素」)
# 分隔条加粗到 10px:深色 UI 上 8px 几乎看不见,用户反馈「肉眼看不到」
_SASH_LOGICAL = 10
# 默认左栏加宽(原 300/356 太窄,右侧按钮容易被挤压)
_SIDE_MIN, _SIDE_MAX_DEFAULT = 360, 430
_MAIN_MIN = 460
_TOP_MIN, _TOP_MAX_DEFAULT = 180, 320
_BOTTOM_MIN = 150                      # 记录列表最小高度


def _sx(master):
    """控件缩放系数:CTk 控件自动按此放大,原生 tk 控件(分隔条/表格)必须手动换算。"""
    try:
        return float(ctk.ScalingTracker.get_widget_scaling(master))
    except Exception:
        return 1.0


def _sp(master, v):
    """逻辑像素 → 物理像素(原生 tk 控件用)。"""
    return int(round(v * _sx(master)))


class _Sash(tk.Frame):
    """可见的分隔条:浅色底 + 中央握把,悬停变强调蓝。

    拖动时**直接实时落位**(实时回调 on_move 改面板尺寸),不再画任何引导线。
    引导线用 place 跟手移动时,Windows 重绘跟不上,快速来回拖会残留多根蓝线;
    实时落位没有移动中的图形,从根上消除拖影,拖动过程也完全不卡。
    """

    def __init__(self, master, orient="h", on_drop=None, on_move=None):
        self._vertical = (orient == "h")     # "h": 竖向条,左右拖动
        self._base = theme.LINE
        th = _sp(master, _SASH_LOGICAL)
        self._th = max(4, _sp(master, 2))
        self._dragging = False
        super().__init__(master, bg=self._base, cursor=None)
        self.configure(width=(th if self._vertical else 0),
                       height=(0 if self._vertical else th),
                       cursor=("sb_h_double_arrow" if self._vertical
                               else "sb_v_double_arrow"))
        self.on_drop = on_drop
        self.on_move = on_move
        self._grip = tk.Frame(self, bg=theme.SUB, bd=0, highlightthickness=0)
        gw, gl = max(3, _sp(self, 4)), max(24, _sp(self, 56))
        if self._vertical:
            self._grip.place(relx=0.5, rely=0.5, anchor="center", width=gw, height=gl)
        else:
            self._grip.place(relx=0.5, rely=0.5, anchor="center", width=gl, height=gw)
        for w in (self, self._grip):
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<B1-Motion>", self._motion)
            w.bind("<ButtonRelease-1>", self._release)

    def _hover(self, on):
        self.configure(bg=theme.ACC if on else self._base)
        self._grip.configure(bg="#ffffff" if on else theme.SUB)

    def _press(self, event):
        self._dragging = True
        self._hover(True)

    def _motion(self, event):
        if not self._dragging:
            return
        if self.on_move:
            self.on_move(event)

    def _release(self, event):
        if not self._dragging:
            return
        self._dragging = False
        self._hover(False)
        if self.on_drop:
            self.on_drop(event)

    def _rel(self, event):
        """指针相对承载面板的坐标。"""
        m = self.master
        try:
            return (event.x_root - m.winfo_rootx(), event.y_root - m.winfo_rooty())
        except Exception:
            return (0, 0)


def _open_dir(path):
    try:
        os.startfile(str(path))            # Windows
    except AttributeError:
        subprocess.Popen(["xdg-open", str(path)])


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._setup_icon()
        self._apply_dark_window_class()
        self.cfg = app_settings.load()
        self.title(theme.APP_TITLE)
        self.geometry(self._safe_geometry(self.cfg.get("geometry")))
        self.minsize(980, 620)
        self.configure(fg_color=theme.BG)

        self.recordings = []          # 全量记录
        self.filtered = []            # 搜索+排序后
        self.current = None
        self.recorder = None
        self._rec_active = False
        self._saved_ids = set()
        self._replay = None
        self._preview = None
        self._dev_serials = {}        # 显示名 -> serial
        self._rec_started_at = None
        self._toast_job = None
        self._pulse_job = None
        self._pulse_on = False
        self._sel_action = None
        self._clipboard = None        # Ctrl+C 复制的动作 dict(跨脚本粘贴)
        self._mt_q = queue.Queue()    # 后台线程 → 主线程的回调队列
        self._search_job = None
        self._rendered_sig = None
        # 性能计数器(验收用):MTR_PERF=1 时统计 resize/重排次数与耗时
        self._perf = ({"configure": 0, "refill": 0, "refill_ms": 0.0}
                      if os.environ.get("MTR_PERF") else None)
        self._rendered_sig = None
        # 窗口缩放进行中标记:拖动尺寸期间暂停动作表的逐帧重排,落定后再一次性同步
        self._resizing = False
        self._resize_job = None

        self._build_fonts()
        self._build_main_paned()
        self._build_sidebar()
        self._build_main()
        self._bind_keys()

        # 恢复上次设置:排序立即生效;倍速/次数在持久工具行上直接应用
        saved_sort = {v: k for k, v in SORTS}.get(self.cfg.get("sort"))
        if saved_sort:
            self.sort_box.set({k: v for k, v in SORTS}[saved_sort])
        self.speed_box.set(self.cfg.get("speed") if self.cfg.get("speed") in SPEEDS else "1x")
        loop_val = str(self.cfg.get("loop") or "1")
        if loop_val != LOOP_INFINITY and not (loop_val.isdigit() and int(loop_val) >= 1):
            loop_val = "1"
        self._last_loop = loop_val
        self.loop_box.set(loop_val)

        self.reload_recordings()
        self.refresh_devices(restore=self.cfg.get("device"))
        self.after(200, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 图标 ----------------
    def _setup_icon(self):
        """窗口左上角 + 任务栏使用自绘图标;任务栏独立标识,摆脱 python 默认。"""
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Zai.PhoneTraceRecorder")
        except Exception:
            pass
        ico = storage.BASE_DIR / "assets" / "icon.ico"
        png = storage.BASE_DIR / "assets" / "icon_256.png"
        try:
            if ico.exists():
                self.iconbitmap(str(ico))
                # CTk 缩放可能覆盖图标,延迟再补一次
                self.after(250, lambda: self._try_iconbitmap(ico))
            elif png.exists():
                self._icon_img = tk.PhotoImage(
                    data=base64.b64encode(png.read_bytes()).decode("ascii"))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _apply_dark_window_class(self):
        """【统一根因修复】Windows 在 Tk 首次绘制窗口前,会用「窗口类背景刷」
        把整个窗口填成默认的白色 —— 这就是所有弹窗(确认框/编辑窗/预览窗)
        "白闪一下再变黑"的公共根因。

        把该窗口类的背景刷改为主题深色后,本进程所有顶层窗口(包括以后
        新建的弹窗)从创建那一刻起就是深色,白闪从机制上消失。
        只需在主窗口上设置一次:所有 Tk 顶层窗口共用同一个窗口类。
        """
        try:
            import ctypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hwnd = self.winfo_id()
            GCLP_HBRBACKGROUND = -10
            # COLORREF 为 0x00BBGGRR:RGB(22,22,27) → 0x001B1616(theme.BG)
            self._dark_brush = gdi32.CreateSolidBrush(ctypes.c_int(0x001B1616))
            user32.SetClassLongPtrW(hwnd, GCLP_HBRBACKGROUND, self._dark_brush)
        except Exception:
            pass

    def _try_iconbitmap(self, ico):
        try:
            self.iconbitmap(str(ico))
        except Exception:
            pass

    @staticmethod
    def _safe_geometry(g):
        import re
        return g if isinstance(g, str) and re.fullmatch(r"\d+x\d+([+-]\d+){2}", g) else "1120x700"

    # ---------------- 字体 ----------------
    def _build_fonts(self):
        self.f_title = theme.font(ctk, 17, "bold")
        self.f_name = theme.font(ctk, 16, "bold")
        self.f_big = theme.font(ctk, 16, "bold")
        self.f_normal = theme.font(ctk, 13)
        self.f_small = theme.font(ctk, 11)

    # ---------------- 分栏骨架(网格,分隔条可拖动) ----------------
    def _build_main_paned(self):
        """主窗口 = 网格分栏:左栏 | 竖向分隔条 | 主区。

        用 grid 而非 tk.PanedWindow:后者拖动靠代理窗口画橡皮筋,Windows 上
        快速来回拖动会残留多根蓝线(拖影),且代理期间面板尺寸不同步会互相遮挡;
        网格布局由 Tk 直接分配行列,天然不重叠,配合自定义 _Sash 零拖影。
        """
        self.body = tk.Frame(self, bg=theme.BG)
        self.body.pack(fill="both", expand=True)
        self.body.grid_rowconfigure(0, weight=1)
        self._side_w = self._clamp_side(self.cfg.get("main_sash"))
        self.body.grid_columnconfigure(0, minsize=_sp(self, self._side_w), weight=0)
        self.body.grid_columnconfigure(1, minsize=_sp(self, _SASH_LOGICAL), weight=0)
        self.body.grid_columnconfigure(2, minsize=_sp(self, _MAIN_MIN), weight=1)
        self.sash_x = _Sash(self.body, "h", on_drop=self._drop_side,
                           on_move=self._move_side)
        self.sash_x.grid(row=0, column=1, sticky="ns")

    # ---------------- 左侧栏 ----------------
    def _build_sidebar(self):
        self.side = side = ctk.CTkFrame(self.body, corner_radius=0, fg_color=theme.SIDE)
        side.grid(row=0, column=0, sticky="nsew")
        # 不关闭尺寸传播:左栏宽度由「网格列宽 = max(列下限, 内容自然宽)」决定,
        # 于是左栏永远装得下自己的控件(拖不窄到裁切按钮),结构上不可能遮挡。

        ctk.CTkLabel(side, text="📱 手机轨迹录制器", font=self.f_title,
                     text_color=theme.TXT).pack(anchor="w", padx=theme.PAD_X, pady=(18, 2))
        ctk.CTkLabel(side, text="录制手机点击/滑动 → 一键导出 Python",
                     font=self.f_small, text_color=theme.SUB).pack(anchor="w", padx=theme.PAD_X, pady=(0, 10))

        # 上(设备/录制/搜索)与下(记录列表)两块:中间分隔条可拖动(网格行分配,不重叠)
        self.side_body = tk.Frame(side, bg=theme.SIDE)
        self.side_body.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.side_body.grid_columnconfigure(0, weight=1)
        self._top_h = self._clamp_top(self.cfg.get("side_sash"))
        self.side_body.grid_rowconfigure(0, minsize=_sp(self, self._top_h), weight=0)
        self.side_body.grid_rowconfigure(1, minsize=_sp(self, _SASH_LOGICAL), weight=0)
        self.side_body.grid_rowconfigure(2, minsize=_sp(self, _BOTTOM_MIN), weight=1)

        top_pane = ctk.CTkFrame(self.side_body, fg_color="transparent")
        top_pane.grid(row=0, column=0, sticky="nsew")
        self.top_pane = top_pane
        ctk.CTkLabel(top_pane, text="目标设备", font=self.f_small,
                     text_color=theme.SUB).pack(anchor="w", padx=theme.PAD_X - 4)
        devrow = ctk.CTkFrame(top_pane, fg_color="transparent")
        devrow.pack(fill="x", padx=theme.PAD_X - 4, pady=(4, 2))
        self.dev_box = OptionPicker(devrow, values=["自动选择"], width=170,
                                    font=self.f_normal)
        self.dev_box.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(devrow, text="⟳", width=36, height=32, font=self.f_normal,
                      fg_color=theme.CARD, hover_color=theme.CARD_HOVER,
                      text_color=theme.TXT, command=self.refresh_devices).pack(side="left", padx=(8, 0))
        self.lbl_dev_state = ctk.CTkLabel(top_pane, text="正在检测 adb…", font=self.f_small,
                                          text_color=theme.SUB, anchor="w")
        self.lbl_dev_state.pack(fill="x", padx=theme.PAD_X - 4, pady=(0, 10))

        self.btn_record = ctk.CTkButton(top_pane, text="●  开始录制", font=self.f_big,
                                        height=52, corner_radius=theme.R_LG,
                                        fg_color=theme.GREEN, hover_color=theme.GREEN_HOVER,
                                        text_color="white", command=self._toggle_record)
        self.btn_record.pack(fill="x", padx=theme.PAD_X - 4)
        self.lbl_rec_info = ctk.CTkLabel(top_pane, text="就绪 · 未在录制", font=self.f_small,
                                         text_color=theme.SUB, anchor="w")
        self.lbl_rec_info.pack(fill="x", padx=theme.PAD_X - 4, pady=(8, 10))

        # 搜索 + 排序(搜索框用自带 placeholder;textvariable 会使占位符失效)
        srow = ctk.CTkFrame(top_pane, fg_color="transparent")
        srow.pack(fill="x", padx=theme.PAD_X - 4)
        self.search_box = ctk.CTkEntry(srow, placeholder_text="🔍  搜索记录…",
                                       font=self.f_normal, height=32, fg_color=theme.CARD,
                                       border_width=0, text_color=theme.TXT,
                                       placeholder_text_color=theme.SUB)
        self.search_box.pack(side="left", fill="x", expand=True)
        self.search_box.bind("<KeyRelease>", self._on_search_key)
        self.sort_box = OptionPicker(srow, values=[n for _, n in SORTS], width=96,
                                     font=self.f_small,
                                     command=lambda _v: self.reload_recordings())
        self.sort_box.set("最新优先")
        self.sort_box.pack(side="left", padx=(8, 0))

        list_pane = ctk.CTkFrame(self.side_body, fg_color="transparent")
        list_pane.grid(row=2, column=0, sticky="nsew")
        lstrow = ctk.CTkFrame(list_pane, fg_color="transparent")
        lstrow.pack(fill="x", padx=theme.PAD_X - 4, pady=(8, 0))
        ctk.CTkLabel(lstrow, text="录制记录", font=self.f_normal,
                     text_color=theme.TXT).pack(side="left")
        self.lbl_count = ctk.CTkLabel(lstrow, text="0 条", font=self.f_small, text_color=theme.SUB)
        self.lbl_count.pack(side="right", padx=(0, 10))

        self.list_frame = ctk.CTkScrollableFrame(list_pane, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        self.sash_y = _Sash(self.side_body, "v", on_drop=self._drop_top, on_move=self._move_top)
        self.sash_y.grid(row=1, column=0, sticky="ew")

        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(fill="x", padx=theme.PAD_X, pady=(0, 14))
        ctk.CTkButton(bottom, text="记录文件夹", font=self.f_small, height=28,
                      fg_color=theme.CARD, hover_color=theme.CARD_HOVER,
                      text_color=theme.SUB,
                      command=lambda: _open_dir(storage.RECORDINGS_DIR)
                      ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(bottom, text="导出文件夹", font=self.f_small, height=28,
                      fg_color=theme.CARD, hover_color=theme.CARD_HOVER,
                      text_color=theme.SUB,
                      command=lambda: _open_dir(storage.EXPORTS_DIR)
                      ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        # 等窗口映射后再按实际尺寸钳制一次(避免初始尺寸未生效时分栏越界)
        self.after(150, self._reclamp_panes)

    # ---------------- 右侧主区(占位页 + 持久详情页) ----------------
    def _build_main(self):
        self.main = ctk.CTkFrame(self.body, fg_color="transparent")
        self.main.grid(row=0, column=2, sticky="nsew")
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        # 占位页
        self.placeholder = ctk.CTkFrame(self.main, fg_color="transparent")
        self.placeholder.grid(row=0, column=0, sticky="nsew")
        inner = ctk.CTkFrame(self.placeholder, fg_color="transparent")
        inner.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(inner, text="📱", font=theme.font(ctk, 44),
                     text_color=theme.SUB).pack()
        ctk.CTkLabel(inner, text="从左侧选择一条记录",
                     font=theme.font(ctk, 18, "bold"),
                     text_color=theme.SUB).pack(pady=(6, 8))
        ctk.CTkLabel(inner, text="点击「开始录制」在手机上操作一遍:点击、长按、滑动与每步间隔\n"
                                 "都会被原样记录,可回放,也可导出双击即跑的 .py。\n\n"
                                 "选中记录后:Delete 删除 · F2 重命名 · ↑/↓ 切换",
                     font=self.f_normal, text_color=theme.SUB, justify="center").pack()

        # 详情页:持久控件,切换记录只更新内容(不销毁重建 → 无闪烁)
        self.detail = ctk.CTkFrame(self.main, fg_color="transparent")
        self.detail.grid(row=0, column=0, sticky="nsew")
        self.detail.grid_columnconfigure(0, weight=1)
        self.detail.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self.detail, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 6))
        namerow = ctk.CTkFrame(head, fg_color="transparent")
        namerow.pack(fill="x")
        self.name_var = ctk.StringVar()
        self.ent_name = ctk.CTkEntry(namerow, textvariable=self.name_var, font=self.f_name,
                                     height=38, fg_color=theme.CARD, border_width=0,
                                     text_color=theme.TXT)
        self.ent_name.pack(side="left", fill="x", expand=True)
        self.ent_name.bind("<Return>", lambda e: self._apply_rename())
        self.ent_name.bind("<FocusOut>", lambda e: self._apply_rename())
        ctk.CTkLabel(namerow, text=" 回车保存 · F2 改名", font=self.f_small,
                     text_color=theme.SUB).pack(side="left", padx=(8, 0))
        self.chips_row = ctk.CTkFrame(head, fg_color="transparent")
        self.chips_row.pack(fill="x", pady=(8, 0))

        self.act_wrap = ctk.CTkFrame(self.detail, fg_color="transparent")
        self.act_wrap.grid(row=1, column=0, sticky="nsew", padx=24)

        # 动作表 = 原生 tk 网格 + 垂直滚动(行由 _render_table 重建,表头常驻)
        self._build_table_shell()

        # 操作条:常驻显示(高度固定),只改按钮可用态与提示文字,不做显示/隐藏(避免布局跳动)
        self.act_bar = ctk.CTkFrame(self.act_wrap, fg_color=theme.CARD,
                                    corner_radius=theme.R_MD, height=40)
        self.act_bar.pack(fill="x", pady=(6, 0))
        self.act_bar.pack_propagate(False)
        self.act_lbl = ctk.CTkLabel(self.act_bar, text="", font=self.f_small,
                                    text_color=theme.SUB, anchor="w")
        self.act_lbl.pack(side="left", padx=(12, 8))
        self.btn_act_new = ctk.CTkButton(self.act_bar, text="✚  新建", width=84, height=28,
                                         font=self.f_small, fg_color=theme.CARD_HOVER,
                                         hover_color=theme.LINE, text_color=theme.OK,
                                         command=self._open_new_action)
        self.btn_act_new.pack(side="left", padx=3, pady=6)
        self.btn_act_edit = ctk.CTkButton(self.act_bar, text="✎  编辑参数", width=104, height=28,
                                          font=self.f_small, fg_color=theme.ACC,
                                          hover_color=theme.ACC_HOVER, text_color="white",
                                          command=lambda: self._edit_action(self._sel_action))
        self.btn_act_edit.pack(side="left", padx=3, pady=6)
        self.btn_act_del = ctk.CTkButton(self.act_bar, text="✕  删除", width=84, height=28,
                                         font=self.f_small, fg_color=theme.CARD_HOVER,
                                         hover_color=theme.LINE, text_color=theme.ERR,
                                         command=lambda: self._remove_gesture(self._sel_action))
        self.btn_act_del.pack(side="left", padx=3, pady=6)
        self._update_act_bar()

        self.txt_log = ctk.CTkTextbox(self.detail, height=132, font=theme.mono(ctk, 12),
                                      fg_color=theme.LOG_BG, text_color="#9ad29a",
                                      wrap="word", corner_radius=theme.R_LG)

        bar = ctk.CTkFrame(self.detail, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=24, pady=12)
        self.btn_replay = ctk.CTkButton(bar, text="▶  回放测试", width=116, height=36,
                                        font=self.f_normal, fg_color=theme.ACC,
                                        hover_color=theme.ACC_HOVER, text_color="white",
                                        command=self._toggle_replay)
        self.btn_replay.pack(side="left")
        self.speed_box = OptionPicker(bar, values=list(SPEEDS), width=72, font=self.f_small)
        self.speed_box.pack(side="left", padx=(10, 4))
        ctk.CTkLabel(bar, text="倍速", font=self.f_small,
                     text_color=theme.SUB).pack(side="left")
        self.loop_box = OptionPicker(bar, values=list(LOOPS), width=72, font=self.f_small,
                                     command=self._on_loop_pick)
        self.loop_box.pack(side="left", padx=(16, 4))
        ctk.CTkLabel(bar, text="遍", font=self.f_small,
                     text_color=theme.SUB).pack(side="left")
        self.btn_preview = ctk.CTkButton(bar, text="🖥  画面预览", width=112, height=36,
                                         font=self.f_normal, fg_color=theme.CARD,
                                         hover_color=theme.CARD_HOVER, text_color=theme.TXT,
                                         command=self._preview_device)
        self.btn_preview.pack(side="left", padx=(16, 0))
        self.btn_export = ctk.CTkButton(bar, text="⬇  导出为 .py", width=128, height=36,
                                        font=self.f_normal, fg_color=theme.CARD,
                                        hover_color=theme.CARD_HOVER, text_color=theme.TXT,
                                        command=self._open_export_dialog)
        self.btn_export.pack(side="left", padx=(8, 0))
        self.btn_delete = ctk.CTkButton(bar, text="删除", width=64, height=36,
                                        font=self.f_normal, fg_color="transparent",
                                        hover_color=theme.CARD_HOVER, border_width=1,
                                        border_color=theme.LINE, text_color=theme.ERR,
                                        command=self._delete_current)
        self.btn_delete.pack(side="right")

        # toast:常驻网格槽位,空态透明 —— 显示/隐藏只改文字与颜色,不做 grid()/grid_remove()
        # (反复出现/消失会挤压动作表高度,造成可见的布局跳动/闪烁)
        self.lbl_toast = ctk.CTkLabel(self.detail, text="", font=self.f_small,
                                      text_color=theme.SUB, anchor="w", fg_color="transparent",
                                      corner_radius=theme.R_PILL, height=30)
        self.lbl_toast.grid(row=4, column=0, sticky="w", padx=24, pady=(2, 12))

        # 初始:无选中 → 显示占位页
        self.detail.grid_remove()

    def _show_detail(self, on):
        if on:
            self.placeholder.grid_remove()
            self.detail.grid()
        else:
            self.detail.grid_remove()
            self.placeholder.grid()

    def _load_detail(self):
        """把 self.current 的内容填充进持久控件(不销毁任何控件)。"""
        rec = self.current
        if not rec:
            return
        self.name_var.set(rec["name"])
        gs = rec.get("gestures", [])
        self._sel_action = 1 if gs else None
        self._render_meta()
        self._render_table()
        try:
            self.txt_log.grid_remove()
        except Exception:
            pass

    def _chip(self, parent, text, color):
        return ctk.CTkLabel(parent, text=" %s " % text, font=theme.font(ctk, 10),
                            text_color=color, fg_color=theme.CARD,
                            corner_radius=theme.R_PILL, height=18)

    def _render_meta(self):
        """徽章统计行:内容不变时不重建,避免切换/刷新时的 chip 闪烁。"""
        rec = self.current
        if not rec:
            return
        s = storage.summarize(rec)
        dev = rec.get("device", {})
        res = dev.get("resolution") or [0, 0]
        chips = [(rec.get("created_at", ""), theme.SUB),
                 ("%s · %dx%d" % (dev.get("model", "未知机型"), res[0], res[1]), theme.SUB)]
        if s["tap"]:
            chips.append(("点击 %d" % s["tap"], theme.GREEN))
        if s["long_press"]:
            chips.append(("长按 %d" % s["long_press"], theme.ORANGE))
        if s["swipe"]:
            chips.append(("滑动 %d" % s["swipe"], theme.ACC))
        chips.append(("≈ %.1f 秒" % (s["total_ms"] / 1000.0), theme.WARN))
        sig = tuple(chips)
        if getattr(self, "_chips_sig", None) == sig and self.chips_row.winfo_children():
            return
        self._chips_sig = sig
        for w in self.chips_row.winfo_children():
            w.destroy()
        for txt, c in chips:
            self._chip(self.chips_row, txt, c).pack(side="left", padx=(0, 6))

    # ---------------- 动作表(网格化表格:所有列常显,弹性列自动伸缩) ----------------
    @staticmethod
    def _trunc(s, n):
        s = str(s)
        return s if len(s) <= n else s[:max(0, n - 1)] + "…"

    def _build_table_shell(self):
        """用原生 tk.Canvas + 单内框 grid 搭动作表:列共用同一 grid → 天然左对齐;
        tk.Label 轻量,避免 CTk 逐行重建在窗口拖动/缩放时卡顿。"""
        # 原生 tk 控件不参与 CTk 自动缩放:字体用负值像素字号、尺寸用 _sp() 换算
        # (负值字号 = 像素高度,与 CTkFont 的渲染口径一致)
        self._tf_head = (theme.FONT_FAMILY, -_sp(self, 10), "bold")
        self._tf_cell = (theme.FONT_FAMILY, -_sp(self, 11))

        wrap = tk.Frame(self.act_wrap, bg=theme.CARD)
        wrap.pack(fill="both", expand=True)

        self.tbl_canvas = tk.Canvas(wrap, bg=theme.CARD, highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(wrap, orient="vertical", command=self.tbl_canvas.yview,
                           bg=theme.CARD_HOVER, troughcolor=theme.CARD,
                           activebackground=theme.ACC, bd=0, highlightthickness=0,
                           relief="flat", width=_sp(self, 10))
        self.tbl_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tbl_canvas.pack(side="left", fill="both", expand=True)

        self.tbl_inner = tk.Frame(self.tbl_canvas, bg=theme.CARD)
        self._tbl_win = self.tbl_canvas.create_window((0, 0), window=self.tbl_inner, anchor="nw")
        self.tbl_inner.bind("<Configure>", self._on_tbl_inner_configure)
        self.tbl_canvas.bind("<Configure>", self._on_tbl_canvas_configure)
        self.bind("<MouseWheel>", self._on_tbl_wheel, add="+")

        # 列配置(表头与数据行共用 self.tbl_inner 的同一组列)
        pad = _sp(self, 8)
        for idx, (title, w, weight) in enumerate(_TBL_COLS):
            if w is None:
                self.tbl_inner.grid_columnconfigure(idx, weight=weight,
                                                    minsize=_sp(self, 80))
            else:
                self.tbl_inner.grid_columnconfigure(idx, weight=0, minsize=_sp(self, w))

        # 表头(常驻,作为 inner 第 0 行,不随数据行重建);高度由内容决定,避免裁切
        self.tbl_head = tk.Frame(self.tbl_inner, bg=theme.CARD_HOVER)
        self.tbl_head.grid(row=0, column=0, columnspan=len(_TBL_COLS), sticky="ew")
        for idx, (title, w, weight) in enumerate(_TBL_COLS):
            self.tbl_head.grid_columnconfigure(idx, weight=weight if w is None else 0,
                                               minsize=(_sp(self, 80) if w is None
                                                        else _sp(self, w)))
            lbl = tk.Label(self.tbl_head, text=title, bg=theme.CARD_HOVER, fg=theme.SUB,
                           font=self._tf_head, anchor="w", padx=pad, pady=_sp(self, 5))
            lbl.grid(row=0, column=idx, sticky="ew")

        self._tbl_rows = []
        self._tbl_sync_rows = None   # 已同步行数签名;行数变化才重算 scrollregion

    def _on_tbl_inner_configure(self, event):
        # 缩放过程中暂停重排;行数未变也不重算(单元格单行等高,高度与列宽无关)。
        if self._resizing:
            return
        rows = len(getattr(self, "_tbl_rows", ()))
        if rows == getattr(self, "_tbl_sync_rows", -1):
            return
        self._tbl_sync_rows = rows
        if getattr(self, "_tbl_scr_job", None):
            self.after_cancel(self._tbl_scr_job)
        self._tbl_scr_job = self.after(1, self._sync_tbl_scrollregion)

    def _sync_tbl_scrollregion(self):
        self._tbl_scr_job = None
        try:
            self.tbl_canvas.configure(scrollregion=self.tbl_canvas.bbox("all"))
        except Exception:
            pass

    def _on_tbl_canvas_configure(self, event):
        # 缩放中暂停;宽度未变也跳过,避免 itemconfigure 连锁触发 inner Configure。
        if self._resizing:
            return
        w = event.width
        if w == getattr(self, "_tbl_win_w", -1):
            return
        if getattr(self, "_tbl_win_job", None):
            self.after_cancel(self._tbl_win_job)
        self._tbl_win_job = self.after(
            1, lambda w=w: self._apply_tbl_win_width(w))

    def _apply_tbl_win_width(self, w):
        self._tbl_win_job = None
        try:
            self._tbl_win_w = w
            self.tbl_canvas.itemconfigure(self._tbl_win, width=w)
        except Exception:
            pass

    def _on_tbl_wheel(self, event):
        """鼠标滚轮在动作表区域内时滚动表格(指针在别处不干预其他滚动区)。"""
        try:
            if not hasattr(self, "tbl_canvas") or not self.tbl_canvas.winfo_exists():
                return
            x = self.tbl_canvas.winfo_rootx()
            y = self.tbl_canvas.winfo_rooty()
            w = self.tbl_canvas.winfo_width()
            h = self.tbl_canvas.winfo_height()
            if x <= event.x_root <= x + w and y <= event.y_root <= y + h:
                self.tbl_canvas.yview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass

    def _render_table(self):
        """重建表格体(表头常驻不重建)。共用 grid,天然列对齐;tk.Label 轻量。"""
        rec = self.current
        for w in list(self.tbl_inner.winfo_children()):
            if w is not self.tbl_head:
                w.destroy()
        self._tbl_rows = []
        self._tbl_sync_rows = None   # 重建后强制重算一次 scrollregion
        gs = rec.get("gestures", []) if rec else []
        if not gs:
            self._sel_action = None
            empty = tk.Label(self.tbl_inner,
                             text="  (该记录没有动作 · 点「✚ 新建」添加第一步)",
                             bg=theme.CARD, fg=theme.SUB, anchor="w", font=self._tf_cell)
            empty.grid(row=1, column=0, columnspan=len(_TBL_COLS),
                       sticky="ew", padx=_sp(self, 10), pady=_sp(self, 12))
            self._tbl_rows.append((None, [empty]))
            self._update_act_bar()
            return
        if self._sel_action is None or not (1 <= self._sel_action <= len(gs)):
            self._sel_action = 1
        for i, g in enumerate(gs, 1):
            self._build_table_row(i, g)
        self._update_act_bar()

    def _build_table_row(self, i, g):
        """构建单行:7 例原生网格单元格,单击选中、备注列双击编辑、长按拖拽排序。"""
        gtype = g["type"]
        tcolor = theme.TYPE_COLORS.get(gtype, theme.SUB)
        tname = theme.TYPE_NAMES.get(gtype, gtype)
        if gtype == "swipe":
            par = "(%d,%d) → (%d,%d)" % (g["x1"], g["y1"], g["x2"], g["y2"])
        else:
            par = "(%d, %d)" % (g["x"], g["y"])
        ori = g.get("rot")
        if ori in (90, 270):
            ori_txt = "横 %d°" % ori
        elif ori is None:
            ori_txt = "—"
        else:
            ori_txt = "竖 %d°" % ori
        note = (g.get("note") or "").strip()
        note_txt = note if note else "—"

        values = [str(i), tname, self._trunc(par, 48), "%dms" % g["duration_ms"],
                  "%dms" % g["delay_ms"], ori_txt, self._trunc(note_txt, 40)]
        colors = [theme.SUB, tcolor, tcolor, theme.TXT, theme.TXT,
                  theme.SUB if ori is None else theme.TXT,
                  theme.WARN if note else theme.SUB]

        cells = []
        for col, (txt, fg) in enumerate(zip(values, colors)):
            lbl = tk.Label(self.tbl_inner, text=txt, bg=theme.CARD, fg=fg,
                           font=self._tf_cell, anchor="w", padx=_sp(self, 8))
            lbl.grid(row=i, column=col, sticky="ew", ipady=_sp(self, 4))
            lbl.bind("<ButtonPress-1>", lambda e, nn=i: self._on_row_press(nn, e))
            lbl.bind("<B1-Motion>", lambda e, nn=i: self._drag_motion(nn, e))
            lbl.bind("<ButtonRelease-1>", lambda e, nn=i: self._drag_end(nn, e))
            if col == len(_TBL_COLS) - 1:   # 备注列双击编辑
                lbl.bind("<Double-Button-1>", lambda e, nn=i: self._open_note(nn))
            cells.append(lbl)
        self._tbl_rows.append((i, cells))
        self._apply_row_bg(i)

    def _apply_row_bg(self, n):
        for i, cells in getattr(self, "_tbl_rows", []):
            bg = theme.CARD_SEL if i == n else theme.CARD
            for w in cells:
                w.configure(bg=bg)

    def _select_action(self, n):
        """选中/取消选中动作行:只改行底色与操作条状态,不重建任何控件。"""
        self._sel_action = n
        self._apply_row_bg(n)
        self._update_act_bar()

    # ---------------- 拖拽排序(长按左键拖动) ----------------
    def _on_row_press(self, i, event):
        self._select_action(i)
        self._drag_idx = i
        self._drag_target = i

    def _target_from_y(self, y_root):
        best = None
        for i, cells in getattr(self, "_tbl_rows", []):
            if not cells or i is None:
                continue
            try:
                y0 = cells[0].winfo_rooty()
                center = y0 + cells[0].winfo_height() / 2.0
            except Exception:
                continue
            if best is None or abs(center - y_root) < abs(best[1] - y_root):
                best = (i, center)
        return best[0] if best else None

    def _drag_motion(self, i, event):
        if getattr(self, "_drag_idx", None) is None:
            return
        tgt = self._target_from_y(event.y_root)
        if tgt is None or tgt == self._drag_target:
            return
        self._drag_target = tgt
        # 拖拽反馈:目标行用浅色高亮,其余恢复选中/常态(不重建,不闪)
        for ii, cells in self._tbl_rows:
            bg = theme.CARD
            if ii == tgt:
                bg = theme.CARD_HOVER
            elif ii == self._sel_action:
                bg = theme.CARD_SEL
            for w in cells:
                w.configure(bg=bg)

    def _drag_end(self, i, event):
        if getattr(self, "_drag_idx", None) is None:
            return
        src = self._drag_idx
        tgt = self._drag_target
        self._drag_idx = None
        self._drag_target = None
        if src == tgt:
            self._select_action(self._sel_action)   # 恢复选中高亮
            return
        if self._move_gesture(src, tgt):
            self._sel_action = tgt
            self._render_table()
            self._select_action(tgt)

    def _move_gesture(self, src, tgt):
        """把第 src 个动作移动到第 tgt 位(1-based),其余顺移;返回是否发生移动。"""
        rec = self.current
        gs = rec.get("gestures", []) if rec else []
        if not (1 <= src <= len(gs)) or not (1 <= tgt <= len(gs)) or src == tgt:
            return False
        g = gs.pop(src - 1)
        gs.insert(tgt - 1, g)
        storage.save(rec)
        self._render_meta()
        return True

    def _update_act_bar(self):
        """常驻操作条:按当前选中态切换按钮可用性与提示文字(不显示/隐藏,不重建)。"""
        rec = self.current
        n = self._sel_action
        valid = bool(rec and n and 1 <= n <= len(rec["gestures"]))
        if valid:
            g = rec["gestures"][n - 1]
            typ = theme.TYPE_NAMES.get(g["type"], g["type"])
            self.act_lbl.configure(text=" 动作 #%d · %s" % (n, typ))
        else:
            self.act_lbl.configure(text=" 点击动作行选中 · 双击备注列编辑备注")
        self.btn_act_new.configure(state="normal" if rec else "disabled")
        self.btn_act_edit.configure(state="normal" if valid else "disabled")
        self.btn_act_del.configure(state="normal" if valid else "disabled")

    def _open_new_action(self):
        """新建动作:插入位置可手动选(默认末尾,即当前动作数+1),添加后选中新行。"""
        rec = self.current
        if not rec:
            return
        total = len(rec.get("gestures", []))
        dlg = ActionNewDialog(self, total=total)
        self.wait_window(dlg)
        g = dlg.result
        if not g:
            return
        pos = dlg.insert_at
        pos = max(1, min(int(pos), total + 1))   # 1~total+1,越界钳制
        gs = rec["gestures"]
        gs.insert(pos - 1, g)                     # 插入后,原 pos 起自动 +1
        self._sel_action = pos
        storage.save(rec)
        self._render_meta()
        self._render_table()
        self._select_action(pos)
        self.toast("✓ 已添加动作 #%d(%s)" % (pos, theme.TYPE_NAMES.get(g["type"], g["type"])))

    def _edit_action(self, idx):
        """集成参数编辑:坐标 + 按下时长 + 等待 + 方向 + 序号移动,同一窗口一次完成。"""
        rec = self.current
        if not rec or idx is None or not (1 <= idx <= len(rec["gestures"])):
            return
        # 直接用索引取对象,避免 .index() 在内容相同的重复动作上定位错位
        g = rec["gestures"][idx - 1]
        self._sel_action = idx
        self._select_action(idx)
        dlg = ActionEditDialog(self, g, total=len(rec["gestures"]), current=idx)
        self.wait_window(dlg)
        r = dlg.result
        if not r:
            return
        for k, v in r.items():
            g[k] = v
        new_idx = idx
        if dlg.new_pos and dlg.new_pos != idx:
            # 序号移动:先取出原对象,再插到新位置(原位置之后的编号顺移)
            rec["gestures"].pop(idx - 1)
            rec["gestures"].insert(dlg.new_pos - 1, g)
            new_idx = dlg.new_pos
        self._sel_action = new_idx
        self._save_and_refresh()
        self.toast("✓ 动作 #%d 参数已更新" % new_idx)

    def _save_and_refresh(self):
        """动作参数编辑后的统一收尾:保存 + 刷新统计与表格,并保持该行选中。"""
        rec = self.current
        if not rec:
            return
        storage.save(rec)
        self._render_meta()
        self._render_table()
        if self._sel_action is not None:
            self._select_action(self._sel_action)

    def _remove_gesture(self, idx):
        """删除单个动作,带确认弹窗;删除后选中原位置的下一动作(无则上一动作)。"""
        rec = self.current
        if not rec or idx is None or not (1 <= idx <= len(rec["gestures"])):
            return
        g = rec["gestures"][idx - 1]
        dlg = ConfirmDialog(self, "删除动作",
                            "确定删除动作 #%d(%s)?此操作不可撤销。"
                            % (idx, theme.TYPE_NAMES.get(g["type"], g["type"])), "删除")
        self.wait_window(dlg)
        if not dlg.confirmed:
            return
        rec["gestures"].pop(idx - 1)
        storage.save(rec)
        # 删除后落位:原位置还有动作则选中它,否则选中新末位;都没有则取消选中
        nxt = None
        if rec["gestures"]:
            nxt = idx if idx <= len(rec["gestures"]) else len(rec["gestures"])
        self._sel_action = nxt
        self._render_meta()
        self._render_table()
        if nxt:
            self._select_action(nxt)
        self.toast("已删除动作 #%d" % idx)

    def _open_note(self, idx):
        """打开动作备注编辑窗口(双击备注列触发)。"""
        rec = self.current
        if not rec or idx is None or not (1 <= idx <= len(rec["gestures"])):
            return
        g = rec["gestures"][idx - 1]
        self._sel_action = idx
        self._select_action(idx)
        dlg = NoteDialog(self, "动作 #%d 备注" % idx, initial=g.get("note", ""))
        self.wait_window(dlg)
        if dlg.value is None:
            return
        g["note"] = dlg.value
        storage.save(rec)
        self._render_meta()
        self._render_table()
        self._select_action(idx)
        self.toast("✓ 备注已保存")

    # ---------------- 记录列表(卡片) ----------------
    def _on_search_key(self, event=None):
        """搜索防抖:停止输入 250ms 后才刷新,避免逐字重建列表造成闪烁。"""
        if self._search_job:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(250, self._debounced_reload)

    def _debounced_reload(self):
        self._search_job = None
        self.reload_recordings()

    def reload_recordings(self):
        self.recordings = storage.load_all()
        self._apply_filter()
        if hasattr(self, "lbl_count"):
            self.lbl_count.configure(text="%d 条" % len(self.recordings))

    def _sort_key(self):
        name = self.sort_box.get() if hasattr(self, "sort_box") else "最新优先"
        return {v: k for k, v in SORTS}.get(name, "time_desc")

    def _apply_filter(self):
        kw = ""
        if hasattr(self, "search_box"):
            kw = self.search_box.get().strip().lower()
        recs = [r for r in self.recordings if not kw or kw in r["name"].lower()]
        mode = self._sort_key()
        if mode == "time_asc":
            recs.sort(key=lambda r: r.get("created_at", ""))
        elif mode == "count_desc":
            recs.sort(key=lambda r: len(r.get("gestures", [])), reverse=True)
        else:
            recs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        self.filtered = recs
        self._render_list()

    def _render_list(self):
        if not hasattr(self, "list_frame"):
            return
        # 过滤结果与当前渲染一致时跳过重建(输入防抖之外的第二道防闪烁)
        sig = tuple(r.get("_file") for r in self.filtered)
        if getattr(self, "_rendered_sig", None) == sig and self.list_frame.winfo_children():
            return
        self._rendered_sig = sig
        canvas = getattr(self.list_frame, "_parent_canvas", None)
        pos = None
        try:
            if canvas is not None and canvas.winfo_exists():
                pos = canvas.yview()[0]
        except Exception:
            pos = None
        for w in self.list_frame.winfo_children():
            w.destroy()
        self._cards = {}
        if not self.filtered:
            ctk.CTkLabel(self.list_frame, text="无匹配记录", font=self.f_small,
                         text_color=theme.SUB).pack(pady=18)
        for rec in self.filtered:
            self._build_card(rec)
        if pos and canvas is not None:
            try:
                canvas.yview_moveto(pos)
            except Exception:
                pass

    def _build_card(self, rec):
        sel = bool(self.current and rec.get("_file") == self.current.get("_file"))
        # 边框恒为 1px(选中换强调色),避免选中态 0↔1 切换造成的 2px 高度跳动
        card = ctk.CTkFrame(self.list_frame, corner_radius=theme.R_MD,
                            fg_color=theme.CARD_SEL if sel else "transparent",
                            border_width=1,
                            border_color=theme.ACC if sel else theme.LINE)
        card.pack(fill="x", padx=3, pady=2)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=9, pady=5)
        if sel:
            # 注意:CTkFrame 默认请求高度 200px,必须显式给矮高度,否则把整卡撑胖
            ctk.CTkFrame(inner, width=3, height=2, corner_radius=2, fg_color=theme.ACC
                         ).pack(side="left", fill="y", padx=(0, 8))
        body = ctk.CTkFrame(inner, fg_color="transparent")
        body.pack(side="left", fill="x", expand=True)

        name = rec["name"] if len(rec["name"]) <= 18 else rec["name"][:17] + "…"
        ctk.CTkLabel(body, text=name, font=theme.font(ctk, 12), text_color=theme.TXT,
                     anchor="w", height=20).pack(fill="x")
        s = storage.summarize(rec)
        meta = "%s · %d 个动作 · %.1fs" % (rec.get("created_at", "")[5:16],
                                          len(rec.get("gestures", [])),
                                          s["total_ms"] / 1000.0)
        ctk.CTkLabel(body, text=meta, font=theme.font(ctk, 10), text_color=theme.SUB,
                     anchor="w", height=16).pack(fill="x")
        chips = ctk.CTkFrame(body, fg_color="transparent", height=20)
        chips.pack(fill="x")
        if s["tap"]:
            self._chip(chips, "点击 %d" % s["tap"], theme.GREEN).pack(side="left", padx=(0, 4))
        if s["long_press"]:
            self._chip(chips, "长按 %d" % s["long_press"], theme.ORANGE).pack(side="left", padx=(0, 4))
        if s["swipe"]:
            self._chip(chips, "滑动 %d" % s["swipe"], theme.ACC).pack(side="left", padx=(0, 4))
        if any(g.get("rot") in (90, 270) for g in rec.get("gestures", [])):
            self._chip(chips, "含横屏", theme.WARN).pack(side="left", padx=(0, 4))

        self._bind_card(card, lambda r=rec: self.select_recording(r))
        card._rec_id = rec.get("id")
        card._rec_file = rec.get("_file")
        self._cards[rec.get("id")] = card
        if not sel:
            card.bind("<Enter>", lambda e, c=card: c.configure(fg_color=theme.CARD))
            card.bind("<Leave>", lambda e, c=card: c.configure(fg_color="transparent"))

    def _bind_card(self, w, cb):
        w.bind("<Button-1>", lambda e: cb())
        for c in w.winfo_children():
            self._bind_card(c, cb)

    def _style_selection(self):
        """只更新各卡片的选中样式,不重建列表(避免切换闪烁)。

        边框宽度恒为 1px(与 _build_card 一致),只换颜色 —— 避免选中态
        0↔1 切换造成整列高度跳动。
        """
        cur_file = self.current.get("_file") if self.current else None
        for card in getattr(self, "_cards", {}).values():
            sel = bool(cur_file and getattr(card, "_rec_file", None) == cur_file)
            card.configure(fg_color=theme.CARD_SEL if sel else "transparent",
                           border_color=theme.ACC if sel else theme.LINE)

    def select_recording(self, rec):
        self.current = rec
        self._style_selection()
        self._show_detail(True)
        self._load_detail()
        try:
            # 关键:把焦点从搜索框等输入控件移到主窗口。
            # 点卡片不会自动移焦点(Tk 的 Frame/Label 不接受焦点),焦点留在
            # 输入框时 Delete/↑↓ 会被输入框吃掉。注意必须聚焦主窗本身,
            # 聚焦内部控件在窗口未映射时焦点会是 None,按键会被 Tk 丢弃。
            self.focus_set()
        except Exception:
            pass

    def _clear_current(self):
        self.current = None
        self._style_selection()
        self._show_detail(False)

    def _select_by_id(self, rid):
        for r in self.recordings:
            if r.get("id") == rid:
                self.select_recording(r)
                return

    def _move_selection(self, delta):
        if not self.filtered:
            return
        ids = [r.get("_file") for r in self.filtered]
        try:
            idx = ids.index(self.current.get("_file")) if self.current else -1
        except ValueError:
            idx = -1
        idx = max(0, min(len(ids) - 1, idx + delta))
        self.select_recording(self.filtered[idx])

    def _apply_rename(self):
        if not self.current:
            return
        new = self.name_var.get().strip()
        if not new or new == self.current["name"]:
            return
        self.current["name"] = new
        storage.save(self.current)
        self.reload_recordings()
        self.toast("✓ 已重命名为「%s」" % new)

    def _delete_current(self):
        rec = self.current
        if not rec:
            return
        dlg = ConfirmDialog(self, "删除记录",
                            "确定删除「%s」?\n共 %d 个动作,删除后不可恢复。"
                            % (rec["name"], len(rec.get("gestures", []))), "删除")
        self.wait_window(dlg)
        if not dlg.confirmed:
            return
        if storage.delete(rec):
            self.toast("已删除「%s」" % rec["name"])
            self._clear_current()
            self.reload_recordings()
        else:
            self.toast("删除失败:文件不存在或被其他程序占用", ok=False)

    # ---------------- 键盘 ----------------
    def _bind_keys(self):
        self.bind("<Delete>", self._on_delete_key)
        self.bind("<F2>", self._on_f2)
        self.bind("<Up>", lambda e: self._arrow(-1))
        self.bind("<Down>", lambda e: self._arrow(1))
        self.bind("<Control-c>", self._copy_action)
        self.bind("<Control-v>", self._paste_action)
        # 顶层窗口尺寸变化时进入“缩放中”状态,落定后再做一次性重排
        self.bind("<Configure>", self._on_root_configure, add="+")

    def _on_root_configure(self, event):
        # 只关心顶层自身的尺寸变化(窗口缩放);子控件的 Configure 也会冒泡到这里,
        # 通过比较事件 widget 是否为本窗口来过滤,避免误判。
        if event.widget is not self:
            return
        size = (event.width, event.height)
        if size == getattr(self, "_root_size", None):
            return                      # 纯移动(位置变化,尺寸不变)不算缩放
        self._root_size = size
        self._resizing = True
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._on_resize_settle)

    def _on_resize_settle(self):
        self._resize_job = None
        self._resizing = False
        # 缩放结束:清掉“上次宽度/行数”缓存,强制动作表补齐一次滚动区与宽度
        self._tbl_win_w = -1
        self._tbl_sync_rows = None
        # 分栏尺寸随窗口重新钳制(保证左栏不越界、两面板不互相遮挡)
        self._reclamp_panes()
        if getattr(self, "tbl_canvas", None) and self.tbl_canvas.winfo_exists():
            w = self.tbl_canvas.winfo_width()
            if w > 1:
                self._apply_tbl_win_width(w)
            self._sync_tbl_scrollregion()

    def _editable_focus(self):
        try:
            w = self.focus_get()
        except Exception:
            return False
        return bool(w) and w.winfo_class() in ("Entry", "Text", "TEntry",
                                               "TCombobox", "Spinbox", "TSpinbox")

    def _on_delete_key(self, event=None):
        if self._editable_focus():
            return
        self._delete_current()

    def _on_f2(self, event=None):
        if self._editable_focus() or not self.current:
            return
        self.ent_name.focus_set()
        self.ent_name.select_range(0, "end")

    def _arrow(self, delta):
        if self._editable_focus():
            return
        self._move_selection(delta)

    def _copy_action(self, event=None):
        """Ctrl+C:复制当前选中动作(可在任一脚本粘贴)。"""
        if self._editable_focus():
            return None                       # 输入框内让系统复制优先
        rec = self.current
        n = self._sel_action
        if not rec or not n or not (1 <= n <= len(rec.get("gestures", []))):
            self.toast("请先选中一行动作再复制", ok=False)
            return "break"
        self._clipboard = dict(rec["gestures"][n - 1])   # 深拷贝,避免改原对象
        self.toast("✓ 已复制动作 #%d(可在任意脚本 Ctrl+V 粘贴)" % n)
        return "break"

    def _paste_action(self, event=None):
        """Ctrl+V:粘贴到当前脚本末尾(跨脚本亦可),粘贴后选中新动作。"""
        if self._editable_focus():
            return None
        g = getattr(self, "_clipboard", None)
        rec = self.current
        if not g or not rec:
            self.toast("剪贴板为空,先 Ctrl+C 复制一行动作", ok=False)
            return "break"
        rec["gestures"].append(dict(g))
        storage.save(rec)
        self._sel_action = len(rec["gestures"])
        self._render_meta()
        self._render_table()
        self._select_action(self._sel_action)
        self.toast("✓ 已粘贴到末尾 #%d" % self._sel_action)
        return "break"

    # ---------------- 设备 ----------------
    def refresh_devices(self, restore=None):
        if not adb_utils.adb_ready():
            self.lbl_dev_state.configure(text="✗ 未找到 adb,请加入系统环境变量 PATH",
                                         text_color=theme.ERR)
            self.dev_box.configure(state="disabled")
            return
        self.dev_box.configure(state="normal")
        self.lbl_dev_state.configure(text="正在检测设备…", text_color=theme.SUB)
        threading.Thread(target=self._dev_worker, args=(restore,), daemon=True).start()

    def _dev_worker(self, restore=None):
        try:
            lst = adb_utils.devices_detailed()
        except Exception as e:
            msg = str(e)
            self._call_soon(lambda: self.lbl_dev_state.configure(text="✗ %s" % msg,
                                                                 text_color=theme.ERR))
            return

        def apply():
            self._dev_serials = {}
            vals = ["自动选择"]
            for s, st, m in lst:
                disp = ("%s · %s" % (s, m)) if m else s
                if st != "device":
                    disp += "(%s)" % st
                self._dev_serials[disp] = s
                vals.append(disp)
            self.dev_box.set_values(vals)      # OptionPicker 专用,勿用 configure(values=…)
            if restore and restore in vals:
                self.dev_box.set(restore)
            elif self.dev_box.get() not in vals:
                self.dev_box.set("自动选择")
            ok = [d for d in lst if d[1] == "device"]
            if ok:
                self.lbl_dev_state.configure(text="✓ 已连接 %d 台设备" % len(ok),
                                             text_color=theme.OK)
            else:
                self.lbl_dev_state.configure(text="未检测到已连接设备(检查 USB 线与调试授权)",
                                             text_color=theme.WARN)
        self._call_soon(apply)

    def _selected_serial(self):
        return self._dev_serials.get(self.dev_box.get())

    # ---------------- 录制 ----------------
    def _toggle_record(self):
        if self._rec_active:
            # 立即恢复按钮,杀进程/收尾/保存转后台
            self._rec_active = False
            self._set_pulse(False)
            self.btn_record.configure(text="●  开始录制", fg_color=theme.GREEN,
                                      hover_color=theme.GREEN_HOVER, state="disabled")
            self.lbl_rec_info.configure(text="正在保存记录…", text_color=theme.SUB)
            threading.Thread(target=self._stop_worker, daemon=True).start()
            return
        if self._replay:
            self.toast("回放进行中,请先停止回放", ok=False)
            return
        self.recorder = Recorder(self._selected_serial(),
                                 on_status=self._cb_rec_status,
                                 on_finished=self._cb_rec_finished)
        try:
            self.recorder.start()
        except Exception as e:
            self.toast("无法开始录制:%s" % e, ok=False)
            return
        self._rec_active = True
        self._rec_started_at = time.time()
        self.btn_record.configure(text="■  结束录制", fg_color=theme.RED,
                                  hover_color=theme.RED_HOVER)
        self._set_pulse(True)
        self.lbl_rec_info.configure(text="准备中…", text_color=theme.ERR)

    def _stop_worker(self):
        try:
            self.recorder.stop()
        except Exception:
            pass

    def _cb_rec_status(self, s):
        self._call_soon(lambda: self._rec_active and self.lbl_rec_info.configure(
            text=s, text_color=theme.ERR if "捕捉" in s else theme.WARN))

    def _cb_rec_finished(self, rec, err):
        self._call_soon(lambda: self._finish_recording(rec, err))

    def _finish_recording(self, rec, err):
        self._rec_active = False
        self._set_pulse(False)
        self.btn_record.configure(text="●  开始录制", fg_color=theme.GREEN,
                                  hover_color=theme.GREEN_HOVER, state="normal")
        self.lbl_rec_info.configure(text="就绪 · 未在录制", text_color=theme.SUB)
        if rec is None:
            if err:
                self.toast("录制失败:%s" % err, ok=False)
            return
        if rec["id"] in self._saved_ids:
            return
        self._saved_ids.add(rec["id"])
        if not rec["gestures"]:
            self.toast("未捕捉到任何手机操作,已放弃保存" + (("(%s)" % err) if err else ""),
                       ok=False)
            return
        storage.save(rec)
        self.reload_recordings()
        self._select_by_id(rec["id"])
        self.toast("✓ 已自动保存「%s」( %d 个动作 )" % (rec["name"], len(rec["gestures"])))

    def _set_pulse(self, on):
        if on:
            self._pulse_on = False
            self._pulse_step()
        else:
            if self._pulse_job:
                try:
                    self.after_cancel(self._pulse_job)
                except Exception:
                    pass
                self._pulse_job = None
            try:
                self.btn_record.configure(text_color="white")
            except Exception:
                pass

    def _pulse_step(self):
        if not self._rec_active:
            return
        self._pulse_on = not self._pulse_on
        try:
            self.btn_record.configure(text_color=theme.PULSE if self._pulse_on else "white")
        except Exception:
            return
        self._pulse_job = self.after(600, self._pulse_step)

    # ---------------- 回放 ----------------
    def _toggle_replay(self):
        if self._replay:
            self.btn_replay.configure(text="正在停止…", state="disabled")
            self._replay.stop()
            return
        if self._rec_active:
            self.toast("录制进行中,请先结束录制", ok=False)
            return
        if not self.current:
            return
        try:
            speed = float(self.speed_box.get().rstrip("x") or 1)
        except ValueError:
            speed = 1.0
        try:
            raw_loop = self.loop_box.get()
            loop = 0 if raw_loop == LOOP_INFINITY else int(raw_loop)
        except ValueError:
            loop = 1
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.insert("1.0", "—— 回放输出 ——\n")
        self.txt_log.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 0))
        self._replay = player.start(self.current, self._selected_serial(), speed,
                                    loop=loop, on_line=self._cb_log,
                                    on_done=self._cb_replay_done)
        self.btn_replay.configure(text="■  停止回放", fg_color=theme.RED,
                                  hover_color=theme.RED_HOVER)

    def _cb_log(self, line):
        self._call_soon(lambda: self._append_log(line))

    def _append_log(self, line):
        if not (self.txt_log and self.txt_log.winfo_exists()):
            return
        self.txt_log.insert("end", line + "\n")
        try:
            ln = int(float(self.txt_log.index("end-1c").split(".")[0]))
            if ln > 400:
                self.txt_log.delete("1.0", "%d.0" % (ln - 300))
        except Exception:
            pass
        self.txt_log.see("end")

    def _cb_replay_done(self, code):
        self._call_soon(lambda: self._replay_done(code))

    def _replay_done(self, code):
        self._replay = None
        self.btn_replay.configure(text="▶  回放测试", fg_color=theme.ACC,
                                  hover_color=theme.ACC_HOVER, state="normal")
        if code == 0:
            self.toast("✓ 回放完成(退出码 0)")
        else:
            self.toast("回放结束,退出码 %s(详见下方输出)" % code, ok=False)

    def _on_loop_pick(self, v):
        """下拉选择遍数:常规预设/∞ 直接生效;选中“自定义…”弹输入框。"""
        if v != "自定义…":
            self._last_loop = v
            return
        prev = getattr(self, "_last_loop", "1")
        dlg = InputDialog(self, "自定义遍数", "回放循环次数", initial="1",
                          hint="输入正整数(≥1)表示执行遍数,输入 0 或“∞”表示无限循环。\n")
        self.wait_window(dlg)
        val = dlg.value
        n = None
        if val is not None:
            val = val.strip()
            if val in ("0", LOOP_INFINITY):
                n = LOOP_INFINITY
            elif val.isdigit() and int(val) > 0:
                n = val
        if n:
            self._last_loop = n
            self.loop_box.set(n)
        else:
            self.loop_box.set(prev)
            if val is not None:
                self.toast("遍数需为正整数(或 0/∞ 表示无限)", ok=False)

    # ---------------- 画面预览 ----------------
    def _preview_device(self):
        if self._rec_active:
            self.toast("录制进行中,暂不能预览", ok=False)
            return
        self.btn_preview.configure(state="disabled", text="⏳  截取中…")
        threading.Thread(target=self._preview_worker,
                         args=(self._selected_serial(),), daemon=True).start()

    def _preview_worker(self, serial):
        try:
            data = adb_utils.screencap(serial)
        except Exception as e:
            msg = str(e)
            self._call_soon(lambda: self._preview_failed(msg))
            return
        self._call_soon(lambda: self._show_preview(data))

    def _preview_failed(self, msg):
        self.btn_preview.configure(state="normal", text="🖥  画面预览")
        self.toast("画面预览失败:%s" % msg, ok=False)

    def _show_preview(self, data):
        self.btn_preview.configure(state="normal", text="🖥  画面预览")
        try:
            if self._preview is not None and self._preview.winfo_exists():
                self._preview.update_image(data)
                self._preview.lift()
                return
        except Exception:
            pass
        self._preview = PreviewWindow(self, data, on_refresh=self._preview_device)

    # ---------------- 导出 ----------------
    def _open_export_dialog(self):
        rec = self.current
        if not rec:
            return
        # 浮动编辑窗口(统一 DarkToplevel:可拖动/带图标/无白闪)
        dlg = DarkToplevel(self, "导出为 Python 回放脚本", width=430)
        card = ctk.CTkFrame(dlg, fg_color=theme.BG)
        card.pack(fill="both", expand=True, padx=22, pady=18)
        ctk.CTkLabel(card, text="导出「%s」" % rec["name"], font=self.f_name,
                     text_color=theme.TXT, anchor="w").pack(fill="x", padx=22, pady=(18, 8))
        ctk.CTkLabel(card, text="脚本文件名", font=self.f_small,
                     text_color=theme.SUB, anchor="w").pack(anchor="w", padx=22)
        ent = ctk.CTkEntry(card, font=self.f_normal, height=36, fg_color=theme.CARD,
                           border_width=0, text_color=theme.TXT)
        ent.insert(0, rec["name"])
        ent.pack(fill="x", padx=22, pady=(4, 14))

        mode = ctk.StringVar(value=self.cfg.get("export_mode") or "standard")
        ctk.CTkRadioButton(card, text="标准模式 · adb input 注入(无需 root,推荐)",
                           variable=mode, value="standard", font=self.f_small,
                           fg_color=theme.ACC, text_color=theme.TXT).pack(anchor="w", padx=22, pady=4)
        ctk.CTkRadioButton(card, text="root 增强 · sendevent 原始事件流(实验性,需已 root)",
                           variable=mode, value="root", font=self.f_small,
                           fg_color=theme.ACC, text_color=theme.TXT).pack(anchor="w", padx=22, pady=4)
        ctk.CTkLabel(card, text="导出的 .py 双击即可按原节奏回放一遍;\n"
                               "脚本默认使用系统环境变量中的 adb。",
                     font=self.f_small, text_color=theme.SUB, justify="left"
                     ).pack(anchor="w", padx=22, pady=(8, 14))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(0, 18))

        def do_export():
            name = ent.get().strip() or rec["name"]
            path = filedialog.asksaveasfilename(
                parent=dlg, title="选择导出位置", defaultextension=".py",
                initialdir=str(storage.EXPORTS_DIR), initialfile=name + ".py",
                filetypes=[("Python 脚本", "*.py")])
            if not path:
                return
            try:
                exporter.export(rec, path, mode.get())
            except Exception as e:
                import tkinter.messagebox as messagebox
                messagebox.showerror("导出失败", str(e), parent=self)
                return
            self.cfg["export_mode"] = mode.get()
            app_settings.save(self.cfg)
            dlg.destroy()
            self.toast("✓ 已导出:%s" % path)

        ctk.CTkButton(row, text="导出", width=96, height=34, font=self.f_normal,
                      fg_color=theme.ACC, hover_color=theme.ACC_HOVER,
                      text_color="white", command=do_export).pack(side="right")
        ctk.CTkButton(row, text="取消", width=72, height=34, font=self.f_normal,
                      fg_color=theme.CARD, hover_color=theme.CARD_HOVER,
                      text_color=theme.SUB, command=dlg.destroy).pack(side="right", padx=(0, 8))

        # DarkToplevel 创建即 withdraw,内容就绪后再居中显示(否则窗口不可见 → 点击无效果)
        dlg.show_centered()

    # ---------------- 杂项 ----------------
    def _call_soon(self, fn):
        """后台线程 → 主线程投递;由 _poll 在主线程统一执行。

        不用 after(0):跨线程调用 after 在非主循环场景会抛 RuntimeError,
        导致回调静默丢失(设备检测卡在“正在检测设备…”的根因)。
        """
        self._mt_q.put(fn)

    def toast(self, msg, ok=True):
        if not hasattr(self, "lbl_toast"):
            return
        if self._toast_job:
            try:
                self.after_cancel(self._toast_job)
            except Exception:
                pass
            self._toast_job = None
        try:
            # 槽位常驻,只改文字与颜色 —— 不做 grid()/grid_remove(),避免布局跳动闪烁
            self.lbl_toast.configure(text=" %s " % msg, text_color=theme.OK if ok else theme.ERR,
                                     fg_color=theme.CARD)
        except Exception:
            return
        self._toast_job = self.after(5000, self._hide_toast)

    def _hide_toast(self):
        self._toast_job = None
        try:
            # 空态:文字清空、背景转透明,槽位高度不变
            self.lbl_toast.configure(text="", fg_color="transparent")
        except Exception:
            pass

    def _poll(self):
        try:
            # 执行后台线程投递的回调(设备检测/录制状态/回放输出/预览)
            while True:
                try:
                    fn = self._mt_q.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception:
                    import traceback
                    traceback.print_exc()
            if self._rec_active and self.recorder and self.recorder.parser is not None:
                n = len(self.recorder.parser.gestures)
                el = int(time.time() - self._rec_started_at)
                self.lbl_rec_info.configure(
                    text="● 录制中 %02d:%02d · 已捕捉 %d 个动作" % (el // 60, el % 60, n),
                    text_color=theme.ERR)
        finally:
            self.after(200, self._poll)

    def _save_settings(self):
        try:
            cfg = {"geometry": self.geometry(),
                   "device": self.dev_box.get() if hasattr(self, "dev_box") else "",
                   "speed": self.speed_box.get() if hasattr(self, "speed_box") else "1x",
                   "loop": self.loop_box.get() if hasattr(self, "loop_box") else "1",
                   "sort": self._sort_key()}
            # 记忆分栏位置:left 宽度(左右分隔条)+ 上方面板高(上下分隔条)
            cfg["main_sash"] = int(getattr(self, "_side_w", theme.SIDE_W))
            cfg["side_sash"] = int(getattr(self, "_top_h", _TOP_MAX_DEFAULT))
            self.cfg.update(cfg)
            app_settings.save(self.cfg)
        except Exception:
            pass

    # ---------------- 分栏尺寸钳制与落位(对外统一用逻辑像素) ----------------
    def _unscaled(self, px):
        """物理像素 → 逻辑像素(与设置文件、界面代码保持同一单位)。"""
        return int(round(px / _sx(self)))

    def _side_floor(self):
        """左栏宽度下限:不小于内容自然宽度(保证控件永不被裁切)。"""
        try:
            return max(_SIDE_MIN, self._unscaled(self.side.winfo_reqwidth()))
        except Exception:
            return _SIDE_MIN

    def _top_floor(self):
        """上方面板高度下限:不小于内容自然高度(保证按钮/搜索框永不被裁切)。"""
        try:
            return max(_TOP_MIN, self._unscaled(self.top_pane.winfo_reqheight()))
        except Exception:
            return _TOP_MIN

    def _clamp_side(self, v):
        """左栏宽度:下限=内容自然宽,上限保证主区不被挤没(尺寸未就绪时不做上限钳制)。"""
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = _SIDE_MAX_DEFAULT
        lo = self._side_floor()
        try:
            avail = self._unscaled(self.body.winfo_width())
        except Exception:
            avail = 0
        if avail <= 100:
            return max(lo, v)
        hi = max(lo + 60, avail - _MAIN_MIN - _SASH_LOGICAL)
        return int(max(lo, min(v, hi)))

    def _clamp_top(self, v):
        """上方面板高度:下限=内容自然高,上限保证记录列表不被挤没。"""
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = _TOP_MAX_DEFAULT
        lo = self._top_floor()
        try:
            avail = self._unscaled(self.side_body.winfo_height())
        except Exception:
            avail = 0
        if avail <= 100:
            return max(lo, v)
        hi = max(lo + 60, avail - _BOTTOM_MIN - _SASH_LOGICAL)
        return int(max(lo, min(v, hi)))

    def _apply_side_w(self, w):
        """只改网格列下限:列宽 = max(下限, 内容自然宽),控件不会被裁切。"""
        self._side_w = w
        self.body.grid_columnconfigure(0, minsize=_sp(self, w))

    def _apply_top_h(self, h):
        self._top_h = h
        self.side_body.grid_rowconfigure(0, minsize=_sp(self, h))

    def _move_side(self, event):
        """左右分隔条拖动中:实时落位(左栏宽度),无引导线、无残影。"""
        x = self._unscaled(event.x_root - self.body.winfo_rootx())
        self._apply_side_w(self._clamp_side(x))

    def _drop_side(self, event):
        """左右分隔条松手:最终钳制一次(宽度已在拖动中实时应用)。"""
        x = self._unscaled(event.x_root - self.body.winfo_rootx())
        self._apply_side_w(self._clamp_side(x))

    def _move_top(self, event):
        """上下分隔条拖动中:实时落位(上方面板高度),无引导线、无残影。"""
        y = self._unscaled(event.y_root - self.side_body.winfo_rooty())
        self._apply_top_h(self._clamp_top(y))

    def _drop_top(self, event):
        """上下分隔条松手:最终钳制一次(高度已在拖动中实时应用)。"""
        y = self._unscaled(event.y_root - self.side_body.winfo_rooty())
        self._apply_top_h(self._clamp_top(y))

    def _reclamp_panes(self):
        """窗口尺寸变化后重新钳制,保证两个面板都留在可视范围内且互不遮挡。"""
        if not self.cfg.get("side_sash") and not getattr(self, "_top_autofit", False):
            # 首次运行:上方面板高度贴合内容,不留大片空白
            self._top_autofit = True
            self._apply_top_h(self._top_floor())
        w = self._clamp_side(self._side_w)
        if w != self._side_w:
            self._apply_side_w(w)
        h = self._clamp_top(self._top_h)
        if h != self._top_h:
            self._apply_top_h(h)

    def _on_close(self):
        try:
            self._save_settings()
            if self._rec_active and self.recorder:
                rec = self.recorder.stop()
                if rec and rec.get("gestures") and rec["id"] not in self._saved_ids:
                    storage.save(rec)
            if self._replay:
                self._replay.stop()
        finally:
            self.destroy()
