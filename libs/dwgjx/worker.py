"""压缩任务线程：UI 与 ffmpeg 之间的桥接。

修复点：
- 通过 on_process 回调拿到真实 Popen 句柄，cancel() 现在能真正终止 ffmpeg
  进程；旧版 self._current_process 始终为 None，导致取消按钮失效。
- 进度信号扩展为 (percent, current_idx, total_files)，UI 据此推算 ETA。
"""

import subprocess
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal

from .compressor import (
    CompressError,
    compress_av1_nvenc,
    compress_hevc_nvenc,
    compress_x265_cpu,
)


class CompressWorker(QThread):
    done = Signal()
    error = Signal(str)
    skipped = Signal(list)
    # (当前文件百分比, 当前第几个, 总数)
    progress = Signal(int, int, int)

    def __init__(
        self,
        files: list,
        output_dir: Path,
        compress_func: str = "av1",
        ffmpeg_params: Optional[dict] = None,
    ):
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self._is_cancelled = False
        self._current_process: Optional[subprocess.Popen] = None
        self.compress_func = compress_func
        self.ffmpeg_params = ffmpeg_params or {}
        self.skipped_files = []

    # ---------------------------------------------------------------
    def run(self) -> None:
        try:
            def progress_callback(percent: int, idx: int, total: int) -> None:
                if self._is_cancelled:
                    raise CompressError("用户取消压缩")
                self.progress.emit(percent, idx, total)

            def process_callback(proc: subprocess.Popen) -> None:
                self._current_process = proc

            def skipped_callback(path: str) -> None:
                self.skipped_files.append(path)

            common = dict(
                on_progress=progress_callback,
                stop_check=lambda: self._is_cancelled,
                suffix=self.ffmpeg_params.get("suffix", "mp4"),
                on_process=process_callback,
                on_skipped=skipped_callback,
            )

            if self.compress_func == "av1":
                compress_av1_nvenc(
                    self.files,
                    self.output_dir,
                    cq=self.ffmpeg_params.get("cq", 41),
                    preset=self.ffmpeg_params.get("preset", "p3"),
                    **common,
                )
            elif self.compress_func == "x265":
                compress_x265_cpu(
                    self.files,
                    self.output_dir,
                    crf=self.ffmpeg_params.get("crf", 28),
                    preset=self.ffmpeg_params.get("preset", "slow"),
                    **common,
                )
            elif self.compress_func == "nvenc_h265":
                compress_hevc_nvenc(
                    self.files,
                    self.output_dir,
                    cq=self.ffmpeg_params.get("cq", 28),
                    preset=self.ffmpeg_params.get("preset", "p5"),
                    **common,
                )
            else:
                raise CompressError(f"未知压缩方案：{self.compress_func}")
        except CompressError as e:
            self.error.emit(str(e))
            return
        finally:
            # 兜底：线程退出时确保 ffmpeg 子进程已终止
            if self._current_process and self._current_process.poll() is None:
                try:
                    self._current_process.terminate()
                    self._current_process.wait(timeout=3)
                except Exception:
                    try:
                        self._current_process.kill()
                    except Exception:
                        pass

        if self.skipped_files:
            self.skipped.emit(list(self.skipped_files))
        self.done.emit()

    # ---------------------------------------------------------------
    def cancel(self) -> None:
        """请求取消并立即终止 ffmpeg 子进程。"""
        self._is_cancelled = True
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass
