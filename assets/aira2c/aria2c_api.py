import os
import re
import subprocess

# aria2 进度行形如：
#   [#4b4905 0B/0B CN:1 DL:0B]
#   [#4b4905 12.3MiB/45.6MiB(27%) CN:4 DL:2.1MiB ETA:14s]
_PROGRESS_RE = re.compile(
    r"\[#[0-9a-f]+\s+([\d.]+[KMGTP]?i?B)/([\d.]+[KMGTP]?i?B)"
    r"(?:\((\d+)%\))?\s+CN:\d+\s+DL:([\d.]+[KMGTP]?i?B)"
    r"(?:\s+ETA:(\S+))?\]"
)


def _parse_progress(line):
    """解析 aria2 一行进度输出；不是进度行时返回 None"""
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    done_str, total_str = m.group(1), m.group(2)
    percent = m.group(3)
    speed_str = m.group(4) or "0B"
    eta_str = m.group(5) or ""

    # 用括号内的百分比优先，否则按已下载/总量估算
    pct = None
    if percent:
        try:
            pct = int(percent)
        except ValueError:
            pct = None
    if pct is None:
        try:
            done = float(done_str.rstrip("iB"))
            total = float(total_str.rstrip("iB"))
            if total > 0:
                pct = min(100, int(done / total * 100))
        except ValueError:
            pct = 0
    return {
        "percent": max(0, min(100, pct or 0)),
        "downloaded": done_str,
        "total": total_str,
        "speed": speed_str,
        "eta": eta_str,
    }


def _build_command(url, threads, headers, cookie, filename, path, min_split_size):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    exe_path = os.path.join(base_dir, "aria2c.exe")

    cmd = [
        exe_path,
        url,
        "-x", str(threads),
        "-s", str(threads),
        "-k", min_split_size,
        "-d", path,
        "--continue=true",
        "--summary-interval=1",
        "--max-connection-per-server=" + str(threads),
        "--split=" + str(threads),
        "--min-split-size=" + min_split_size,
        "--retry-wait=2",
        "--max-tries=15",
        "--timeout=60",
        "--check-certificate=false",
    ]
    if filename:
        cmd += ["-o", filename]

    headers = dict(headers) if headers else {}
    if cookie:
        if isinstance(cookie, dict):
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookie.items())
        else:
            cookie_str = cookie
        headers["Cookie"] = cookie_str
    for k, v in headers.items():
        cmd += ["--header", f"{k}: {v}"]
    return cmd


def aria2_download(url, threads=16, headers=None, cookie=None, filename=None, path=".", min_split_size="1M", on_progress=None):
    """
    极速多线程下载（内置显示版）。
    参数与原版一致，新增:
    on_progress  回调 dict，形如 {"percent":..,"downloaded":..,"total":..,"speed":..,"eta":..}
    不再弹出黑色 CMD 窗口。
    """
    cmd = _build_command(url, threads, headers, cookie, filename, path, min_split_size)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    tail_lines = []
    for line in proc.stdout:
        tail_lines.append(line.strip())
        if len(tail_lines) > 30:
            tail_lines.pop(0)
        info = _parse_progress(line)
        if info and on_progress:
            on_progress(info)
    return_code = proc.wait()
    if return_code != 0:
        raise RuntimeError(
            "aria2 下载失败（退出码 %s）：%s" % (return_code, " | ".join(tail_lines[-6:]))
        )
    return return_code
