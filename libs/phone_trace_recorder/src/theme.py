"""设计令牌:全局统一的色板 / 圆角 / 间距 / 字体。

改主题只需要改这里;所有 UI 组件取值都必须来自本模块,不允许散落硬编码。
"""
from __future__ import annotations

APP_TITLE = "手机轨迹录制器 · Phone Trace Recorder"

# ---- 基础色板(深色) ----
BG = "#16161b"         # 窗口底色
SIDE = "#1c1c23"       # 侧栏底色
CARD = "#23232b"       # 卡片 / 输入框底
CARD_HOVER = "#2c2c36"
CARD_SEL = "#26304a"   # 选中卡片(带蓝调)
LINE = "#2e2e38"       # 分隔线 / 描边
LINE_ACC = "#3d4a63"  # 分隔条底色:比描边稍亮,深色 UI 上可见
LOG_BG = "#101014"     # 回放日志底

TXT = "#e9e9f0"        # 主文字
SUB = "#9a9aa8"        # 次级文字
ACC = "#4f8cff"        # 主强调(蓝)
ACC_HOVER = "#3d78e0"
GREEN = "#23a55a"
GREEN_HOVER = "#1d8a4b"
RED = "#e5484d"
RED_HOVER = "#c53b40"
ORANGE = "#e08e3c"     # 长按徽章

OK = "#4ade80"
WARN = "#fbbf24"
ERR = "#f87171"
PULSE = "#ff9a9d"      # 录制按钮呼吸浅色

# ---- 动作类型徽章 ----
TYPE_COLORS = {"tap": GREEN, "long_press": ORANGE, "swipe": ACC}
TYPE_NAMES = {"tap": "点击", "long_press": "长按", "swipe": "滑动"}

FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"

# ---- 圆角 ----
R_SM, R_MD, R_LG, R_PILL = 6, 10, 12, 999
# ---- 间距 ----
PAD_X = 20
SIDE_W = 430           # 侧栏默认宽度(可拖动分隔条调整,记忆持久化)


def font(ctk, size=13, weight="normal"):
    """创建界面字体(需传入 customtkinter 模块)。"""
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def mono(ctk, size=12):
    return ctk.CTkFont(family=MONO_FAMILY, size=size)
