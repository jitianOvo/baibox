"""轻量设置持久化:config/settings.json(损坏时自动回退默认值)。"""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "settings.json"

DEFAULTS = {
    "geometry": "1120x700",   # 窗口尺寸位置
    "device": "",             # 上次选择的设备显示名
    "speed": "1x",            # 回放倍速
    "loop": "1",              # 回放循环次数
    "sort": "time_desc",      # 记录排序
    "export_mode": "standard",  # 上次导出模式
    "side_sash": None,         # 左侧栏上下分栏位置(分隔条 y 像素,None=自动)
    "main_sash": None          # 左栏/主区左右分栏位置(分隔条 x 像素,None=自动)
}


def load():
    """读取设置;坏文件/缺项自动回退默认值。"""
    data = dict(DEFAULTS)
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.update({k: raw[k] for k in DEFAULTS if k in raw})
    except (OSError, ValueError):
        pass
    return data


def save(data):
    """原子写入设置;失败静默(设置丢失不影响功能)。"""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({k: data.get(k, DEFAULTS[k]) for k in DEFAULTS},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(CONFIG_FILE)
    except OSError:
        pass
