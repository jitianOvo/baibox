"""记录存储:全部落在软件目录内的 recordings/ 文件夹,数量无上限。

- 每条记录一个 JSON 文件,文件名 = 记录名_短ID.json,可直接查看/备份/手动删除;
- 列表 = 目录扫描,无需中央索引;
- 改名 = 更新 JSON 内容 + 重命名文件。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # 软件所在目录
RECORDINGS_DIR = BASE_DIR / "recordings"            # 录制记录缓存(自动保存到这里)
EXPORTS_DIR = BASE_DIR / "exports"                  # 默认导出目录
TEMP_DIR = BASE_DIR / "temp"                        # 运行期临时文件


def ensure_dirs():
    for d in (RECORDINGS_DIR, EXPORTS_DIR, TEMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def safe_name(name):
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", str(name)).strip()
    return cleaned or "未命名"


def save(rec):
    """保存/更新记录;记录名变化时自动重命名文件。返回文件路径。"""
    ensure_dirs()
    path = RECORDINGS_DIR / ("%s_%s.json" % (safe_name(rec["name"]), rec["id"]))
    old = rec.get("_file")
    data = {k: v for k, v in rec.items() if not k.startswith("_")}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(path)
    if old and Path(old) != path and Path(old).exists():
        try:
            Path(old).unlink()
        except OSError:
            pass
    rec["_file"] = str(path)
    return path


def load_all():
    """扫描 recordings/,按创建时间倒序返回记录列表;损坏文件自动跳过。"""
    ensure_dirs()
    recs = []
    for f in sorted(RECORDINGS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "gestures" in data:
                data["_file"] = str(f)
                recs.append(data)
        except (OSError, ValueError):
            continue
    recs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return recs


def delete(rec):
    """删除记录文件;返回 True=成功,False=不存在或被占用(如被别的程序打开)。"""
    f = rec.get("_file")
    if not f or not Path(f).exists():
        return False
    try:
        Path(f).unlink()
        return True
    except OSError:
        return False


def summarize(rec):
    """统计:动作数、分类计数、预计总时长(ms)。"""
    gs = rec.get("gestures", [])
    c = {"tap": 0, "long_press": 0, "swipe": 0}
    for g in gs:
        c[g["type"]] = c.get(g["type"], 0) + 1
    total = sum(g.get("delay_ms", 0) + g.get("duration_ms", 0) for g in gs)
    return {"count": len(gs), "tap": c["tap"], "long_press": c["long_press"],
            "swipe": c["swipe"], "total_ms": total}
