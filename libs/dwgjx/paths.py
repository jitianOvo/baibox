"""资源路径解析，兼容源码运行 / PyInstaller / Nuitka 三种模式。

策略优先级：
1. PyInstaller：sys._MEIPASS 即资源根
2. Nuitka standalone：exe 同目录即资源根（assets/、core/ 与 exe 平级）
3. Nuitka onefile：__file__ 指向解压后的临时目录，parent.parent 即资源根
4. 源码运行：__file__ 在 src/ 下，parent.parent 即项目根

为了健壮，会按上述顺序依次探测 assets/ 是否存在，命中即返回。
"""

import os
import sys
from pathlib import Path


def _is_nuitka() -> bool:
    main_mod = sys.modules.get("__main__")
    return main_mod is not None and "__compiled__" in dir(main_mod)


def _is_pyinstaller() -> bool:
    return getattr(sys, "frozen", False)


def _candidate_roots() -> list:
    """返回所有可能的资源根目录候选，按优先级排序。"""
    candidates = []

    # 1. PyInstaller 的 _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))

    # 2. Nuitka standalone：exe 同目录
    #    （onefile 模式下 sys.executable 指向原 exe，资源在临时目录，
    #     会由下面 __file__ 兜底；但 exe 同目录也可能放资源，先试）
    try:
        candidates.append(Path(sys.executable).parent)
    except Exception:
        pass

    # 3. Nuitka onefile / 源码：__file__ 在 src/ 下，parent.parent 是资源根
    try:
        here = Path(__file__).resolve().parent  # src/
        candidates.append(here.parent)  # 项目根 / 临时根
    except Exception:
        pass

    # 4. cwd 兜底
    candidates.append(Path.cwd())

    # 去重保序
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def app_root() -> Path:
    """获取资源根目录（assets/、core/ 所在目录）。"""
    for c in _candidate_roots():
        if (c / "assets").exists() or (c / "core").exists():
            return c
    # 没找到带 assets/core 的目录，返回最可能的候选
    # 优先用 __file__ 推断（源码与 Nuitka onefile 都对）
    try:
        return Path(__file__).resolve().parent.parent
    except Exception:
        return Path(sys.executable).parent


def get_resource(relative_path: str) -> str:
    """获取资源文件绝对路径。relative_path 相对 app_root。"""
    return str(app_root() / relative_path)


def ffmpeg_path() -> str:
    """ffmpeg 可执行文件绝对路径（PyCache/core 通用缓存）。"""
    return str(Path.home() / "PyCache" / "core" / "dwgjx-core.exe")


def assets_dir() -> Path:
    return app_root() / "assets"
