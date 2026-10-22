"""ffmpeg 压缩封装。

修复点：
1. 进度解析同时支持 out_time_ms / out_time_us / out_time=，解决新版 ffmpeg 不再
   输出 out_time_ms 导致 x265 压制时进度条不动 / 偶发抽风。
2. duration=0 时跳过百分比计算，避免 ZeroDivisionError 被裸 except 吞掉。
3. 把裸 except 改成只捕获 ValueError，让 CompressError（取消）正确抛出。
4. Windows 下子进程加 CREATE_NO_WINDOW，避免打包后弹出 cmd 黑框。
5. 输出文件名追加编码后缀（_av/_x265/_hv），防止覆盖原视频。
6. 通过 on_process 回调把 Popen 句柄回传给 worker，使取消能真正终止 ffmpeg。
7. mp4 输出加 +faststart，字幕用 mov_text 兜底（mkv 直拷会失败）。
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

from .constants import DWGJX_MARK, DWGJX_MARK_KEY, ENCODER_SUFFIX, OUTPUT_SUFFIX
from .paths import ffmpeg_path


class CompressError(Exception):
    pass


# Windows 下隐藏子进程控制台窗口
_WIN_CREATE_FLAGS = (
    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
)


# =====================================================================
# 工具函数
# =====================================================================

def _safe_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _parse_hhmmss_us(text: str) -> Optional[int]:
    """把 HH:MM:SS.ffffff 解析为微秒。"""
    m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", text.strip())
    if not m:
        return None
    h, mi, se, frac = m.groups()
    frac = (frac + "000000")[:6]  # 补齐到 6 位
    return (
        int(h) * 3600_000_000
        + int(mi) * 60_000_000
        + int(se) * 1_000_000
        + int(frac)
    )


def _parse_progress_line(line: str) -> Optional[int]:
    """从一行 ffmpeg -progress 输出中提取已处理微秒数。

    兼容字段：
    - out_time_ms（旧版本，名字误导，实为微秒）
    - out_time_us（新版本）
    - out_time=HH:MM:SS.ffffff（兜底）
    """
    line = line.strip()
    if line.startswith("out_time_ms="):
        return _safe_int(line.split("=", 1)[1])
    if line.startswith("out_time_us="):
        return _safe_int(line.split("=", 1)[1])
    if line.startswith("out_time="):
        return _parse_hhmmss_us(line.split("=", 1)[1])
    return None


def get_video_duration(file: Path) -> float:
    """使用 ffmpeg -i 获取视频时长（秒）。"""
    cmd = [ffmpeg_path(), "-i", str(file)]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_WIN_CREATE_FLAGS,
        )
    except OSError:
        return 0.0

    duration_line = next(
        (line for line in (result.stderr + result.stdout).splitlines()
         if "Duration" in line),
        None,
    )
    if not duration_line:
        return 0.0
    m = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", duration_line)
    if not m:
        return 0.0
    h, mi, se, frac = map(int, m.groups())
    # frac 在 ffmpeg 里是百分之一秒（2 位），换算成秒
    return h * 3600 + mi * 60 + se + frac / 100.0


def has_dwgjx_mark(file: Path) -> bool:
    """检测视频元数据是否已带大丸工具箱压缩标识"""
    cmd = [ffmpeg_path(), "-i", str(file)]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=_WIN_CREATE_FLAGS,
        )
    except OSError:
        return False
    text_out = (result.stderr + result.stdout)
    return DWGJX_MARK in text_out


def copy_source_timestamps(source: Path, target: Path) -> None:

    """复制文件系统时间；Windows 下同时复制创建、访问、修改时间。"""
    try:
        stat = source.stat()
        os.utime(target, (stat.st_atime, stat.st_mtime))
    except OSError:
        return

    if os.name != "nt":
        return

    try:
        import ctypes
        from ctypes import wintypes

        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x00000080
        INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
        EPOCH_AS_FILETIME = 116444736000000000
        HUNDREDS_OF_NANOSECONDS = 10000000

        def to_filetime(timestamp: float):
            value = int(timestamp * HUNDREDS_OF_NANOSECONDS + EPOCH_AS_FILETIME)
            return wintypes.FILETIME(value & 0xFFFFFFFF, value >> 32)

        handle = ctypes.windll.kernel32.CreateFileW(
            str(target),
            GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == INVALID_HANDLE_VALUE:
            return

        creation = to_filetime(stat.st_ctime)
        access = to_filetime(stat.st_atime)
        write = to_filetime(stat.st_mtime)
        ctypes.windll.kernel32.SetFileTime(
            handle,
            ctypes.byref(creation),
            ctypes.byref(access),
            ctypes.byref(write),
        )
        ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return


# =====================================================================
# 压缩入口
# =====================================================================

def compress_av1_nvenc(
    files: Iterable[Path],
    output_dir: Path,
    on_progress: Optional[Callable[[int, int, int], None]] = None,
    cq: int = 41,
    preset: str = "p3",
    stop_check: Optional[Callable[[], bool]] = None,
    suffix: str = OUTPUT_SUFFIX,
    on_process: Optional[Callable[[subprocess.Popen], None]] = None,
    on_skipped: Optional[Callable[[str], None]] = None,
) -> None:
    compress_generic_ffmpeg(
        files,
        output_dir,
        codec="av1_nvenc",
        encoder_key="av1",
        on_progress=on_progress,
        stop_check=stop_check,
        cq=cq,
        preset=preset,
        suffix=suffix,
        on_process=on_process,
        on_skipped=on_skipped,
    )


def compress_x265_cpu(
    files: Iterable[Path],
    output_dir: Path,
    on_progress: Optional[Callable[[int, int, int], None]] = None,
    crf: int = 28,
    preset: str = "slow",
    stop_check: Optional[Callable[[], bool]] = None,
    suffix: str = OUTPUT_SUFFIX,
    on_process: Optional[Callable[[subprocess.Popen], None]] = None,
    on_skipped: Optional[Callable[[str], None]] = None,
) -> None:
    compress_generic_ffmpeg(
        files,
        output_dir,
        codec="libx265",
        encoder_key="x265",
        on_progress=on_progress,
        stop_check=stop_check,
        crf=crf,
        preset=preset,
        suffix=suffix,
        on_process=on_process,
        on_skipped=on_skipped,
    )


def compress_hevc_nvenc(
    files: Iterable[Path],
    output_dir: Path,
    on_progress: Optional[Callable[[int, int, int], None]] = None,
    cq: int = 28,
    preset: str = "p5",
    stop_check: Optional[Callable[[], bool]] = None,
    suffix: str = OUTPUT_SUFFIX,
    on_process: Optional[Callable[[subprocess.Popen], None]] = None,
    on_skipped: Optional[Callable[[str], None]] = None,
) -> None:
    compress_generic_ffmpeg(
        files,
        output_dir,
        codec="hevc_nvenc",
        encoder_key="nvenc_h265",
        on_progress=on_progress,
        stop_check=stop_check,
        cq=cq,
        preset=preset,
        suffix=suffix,
        on_process=on_process,
        on_skipped=on_skipped,
    )


def compress_generic_ffmpeg(
    files: Iterable[Path],
    output_dir: Path,
    codec: str,
    encoder_key: str = "",
    on_progress: Optional[Callable[[int, int, int], None]] = None,
    stop_check: Optional[Callable[[], bool]] = None,
    cq: Optional[int] = None,
    crf: Optional[int] = None,
    preset: str = "p5",
    suffix: str = OUTPUT_SUFFIX,
    on_process: Optional[Callable[[subprocess.Popen], None]] = None,
    on_skipped: Optional[Callable[[str], None]] = None,
) -> None:
    files = list(files)
    if not files:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    total_files = len(files)

    # 编码方案对应输出文件名后缀，防止覆盖原视频
    name_suffix = ENCODER_SUFFIX.get(encoder_key, "")

    for idx, file in enumerate(files):
        if stop_check and stop_check():
            raise CompressError("用户取消压缩")
        if not file.exists():
            continue

        # 已带大丸工具箱标识的视频跳过压缩，避免重复处理
        if has_dwgjx_mark(file):
            if on_skipped:
                on_skipped(str(file))
            continue

        duration = get_video_duration(file)
        out_file = output_dir / f"{file.stem}{name_suffix}.{suffix}"

        cmd = [
            ffmpeg_path(),
            "-y",
            "-i", str(file),
            "-map", "0",
            "-map_metadata", "0",
            "-movflags", "+faststart+use_metadata_tags",
            "-progress", "pipe:1",
            "-nostats",
        ]

        # 视频编码参数
        if "nvenc" in codec:
            cmd += ["-c:v", codec, "-pix_fmt", "yuv420p", "-preset", preset]
            if cq is not None:
                cmd += ["-cq", str(cq)]
        else:  # CPU libx265
            cmd += [
                "-c:v", codec,
                "-pix_fmt", "yuv420p",
                "-preset", preset,
                "-tag:v", "hvc1",  # mp4 容器内 h265 标记，提升播放器兼容性
            ]
            if crf is not None:
                cmd += ["-crf", str(crf)]

        # 写入大丸工具箱隐性标识（元数据 comment）
        cmd += ["-metadata", f"{DWGJX_MARK_KEY}=" + DWGJX_MARK]

        # 音频直拷，字幕按输出容器适配
        cmd += ["-c:a", "copy"]
        if suffix.lower() == "mp4":
            # mp4 不支持 ass/ssa 直拷，转 mov_text；不支持的流 ffmpeg 会自动忽略
            cmd += ["-c:s", "mov_text"]
        else:
            cmd += ["-c:s", "copy"]

        cmd.append(str(out_file))

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
            creationflags=_WIN_CREATE_FLAGS,
        )

        # 把进程回传给 worker，使其 cancel() 能真正终止 ffmpeg
        if on_process:
            on_process(process)

        try:
            for line in process.stdout:
                # 每行都检查取消，保证响应及时
                if stop_check and stop_check():
                    process.terminate()
                    raise CompressError("用户取消压缩")

                us = _parse_progress_line(line)
                if us is None:
                    continue
                # duration > 0 才计算百分比，否则跳过（避免 ZeroDivision）
                if duration > 0:
                    percent = min(int(us / 1_000_000 / duration * 100), 100)
                    percent = max(percent, 0)
                    if on_progress:
                        on_progress(percent, idx + 1, total_files)
        finally:
            # 确保子进程退出，避免僵尸 / 文件句柄占用
            try:
                process.stdout.close()
            except Exception:
                pass
            process.wait()

        if process.returncode not in (0, None):
            # 退出码非 0 视为失败（None 表示被信号终止）
            raise CompressError(
                f"压缩失败：{file.name}（ffmpeg 退出码 {process.returncode}）"
            )

        copy_source_timestamps(file, out_file)
