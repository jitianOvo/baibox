import hashlib
import json
import os
from pathlib import Path

from . import adapters


def download_book(source, title, episodes, destination, cancel, notify):
    if not episodes:
        raise ValueError("没有可下载的章节")
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial, checkpoint = Path(str(path) + ".part"), Path(str(path) + ".part.json")
    identity = hashlib.sha256(json.dumps([source["id"], title, episodes], ensure_ascii=False,
                                        sort_keys=True).encode()).hexdigest()
    state = dict(identity=identity, completed=0, bytes=0)
    if checkpoint.exists() and partial.exists():
        try:
            previous = json.loads(checkpoint.read_text(encoding="utf-8"))
            if previous["identity"] == identity and 0 <= previous["completed"] <= len(episodes) and partial.stat().st_size >= previous["bytes"]:
                state = previous
        except (ValueError, KeyError, TypeError):
            pass
    with partial.open("r+b" if partial.exists() else "w+b") as output:
        output.truncate(state["bytes"])
        output.seek(state["bytes"])
        if not state["completed"]:
            output.write((title + "\n\n").encode("utf-8"))
        for index in range(state["completed"], len(episodes)):
            if cancel.is_set():
                raise InterruptedError("已取消，已完成章节可在同一路径继续下载")
            chapter = episodes[index]
            notify(dict(type="status", text=f"下载小说 {index + 1}/{len(episodes)} · {chapter['title']}"))
            try:
                content = adapters.chapter_text(source, chapter)
                if content.get("url") or not content.get("text", "").strip():
                    raise ValueError("本章没有可保存的文字正文")
            except Exception as exc:
                raise ValueError(f"{chapter['title']} 下载失败：{exc}。已完成章节保留，重试同一路径可继续") from exc
            if cancel.is_set():
                raise InterruptedError("已取消，已完成章节可在同一路径继续下载")
            output.write((content.get("title", chapter["title"]) + "\n\n" + content["text"] + "\n\n").encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
            state.update(completed=index + 1, bytes=output.tell())
            pending = Path(str(checkpoint) + ".tmp")
            pending.write_text(json.dumps(state), encoding="utf-8")
            os.replace(pending, checkpoint)
    os.replace(partial, path)
    checkpoint.unlink(missing_ok=True)
    return str(path)
