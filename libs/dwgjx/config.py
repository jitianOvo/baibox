"""配置持久化：保存路径、上次预设。

缓存位置：C:\\Users\\用户名\\Pyffmpeg\\config.json
首次打开时默认输出到桌面。
"""

import json
import os
from pathlib import Path
from typing import Optional

from .constants import CONFIG_DIR, CONFIG_FILE


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_default_output_dir() -> Path:
    """首次打开默认输出到桌面；桌面不存在兜底到用户主目录。"""
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop
    # 某些 Windows 系统桌面名是中文
    desktop_cn = Path.home() / "桌面"
    if desktop_cn.exists():
        return desktop_cn
    return Path.home()


def load_config() -> dict:
    """读取上次保存的配置。文件不存在或损坏时返回空 dict。"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(cfg: dict) -> None:
    """写入配置到缓存目录，失败时静默忽略。"""
    try:
        _ensure_config_dir()
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def resolve_output_dir(cfg: dict) -> Path:
    """从配置中取输出目录，不存在或无效则回退默认（桌面）。"""
    raw = cfg.get("output_dir")
    if raw:
        p = Path(raw)
        # 允许保存的路径已不存在，但只要父目录在就用它；否则回退
        if p.parent.exists():
            return p
    return get_default_output_dir()


def resolve_preset_index(cfg: dict, total: int) -> int:
    """从配置中取上次预设索引，越界则回退 0。"""
    idx = cfg.get("preset_index", 0)
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return 0
    if 0 <= idx < total:
        return idx
    return 0
