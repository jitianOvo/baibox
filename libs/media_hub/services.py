import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from . import adapters
from .catalog import ADAPTERS
from .selection import episode_match, group_results, rank_music
from .selection import normalized


class Services:
    def __init__(self, catalog):
        self.catalog = catalog

    def search(self, kind, keyword, source_id, platform, page, cancel, notify):
        sources = [s for s in self.catalog.rows(kind, active=True) if s["adapter"] in ADAPTERS]
        if source_id:
            sources = [s for s in sources if s["id"] == source_id]
        else:
            sources.sort(key=lambda s: s["priority"] > 10)
        if not sources:
            raise ValueError("没有启用的兼容源，请到源管理导入或启用")
        # 音源只负责播放链接，音乐搜索元数据每个平台只请求一次。
        if kind == "music" and not source_id:
            sources = [s for s in sources if s["adapter"] == "lx"] or sources
        sources = sources[:1] if kind == "music" else sources[:8]
        found, errors = [], []
        labels = self.catalog.source_labels()
        def one(source, search_platform=platform):
            if cancel.is_set():
                return [], ""
            try:
                rows = adapters.search(source, keyword, page, search_platform)
                for rank, row in enumerate(rows):
                    row["search_rank"] = rank
                if kind != "music":
                    self.catalog.record_health(source["id"], empty=not rows)
                return rows, ""
            except Exception as exc:
                reason = friendly_error(exc)
                if kind != "music":
                    self.catalog.record_health(source["id"], reason)
                return [], f"{source['name']}：{reason}"
        with ThreadPoolExecutor(max_workers=4) as executor:
            platforms = ["kw", "wy", "tx", "mg"] if kind == "music" and platform == "auto" else [platform]
            pending = {executor.submit(one, source, target): source for source in sources for target in platforms}
            for future in as_completed(pending):
                if cancel.is_set():
                    for task in pending:
                        task.cancel()
                    break
                rows, error = future.result()
                if rows:
                    found.extend(rows)
                    notify(dict(type="results", rows=rows))
                if error:
                    errors.append(error)
                notify(dict(type="status", text=f"已找到 {len(found)} 条；完成 {labels.get(pending[future]['id'], '检索')}"))
        rows = rank_music(found, keyword) if kind == "music" else group_results(found, kind)
        if kind != "music":
            rows.sort(key=lambda r: (normalized(r["title"]) != normalized(keyword), not bool(r.get("vod")), r.get("search_rank", 999)))
        return dict(count=len(rows), errors=errors, searched=len(pending), rows=rows, kind=kind)

    def resolve_music(self, source, result, quality, cancel, notify, excluded=()):
        others = [s for s in self.catalog.rows("music", active=True)
                  if s["id"] != source["id"] and s["adapter"] == "lx"]
        # 部分聚合接口的咪咕地址会返回短提示音，优先已实播的候选。
        if result.get("platform") == "mg":
            from .music_search import MIGU_PREFERRED
            preferred = self.catalog.setting("music_migu_preferred", MIGU_PREFERRED)
            others.sort(key=lambda s: preferred.index(s["name"]) if s["name"] in preferred else len(preferred))
        candidates = [source] + others
        errors = []
        labels = self.catalog.source_labels()
        alternatives = result.get("alternatives") or [result]
        attempts = set(excluded)
        for candidate in candidates[:4]:
            for track in alternatives[:4]:
                if len(attempts) >= 12:
                    raise ValueError("本次已尝试多个音频地址仍不可用，请稍后重试或点击换源")
                key = candidate["id"] + ":" + track.get("platform", "") + ":" + str(track.get("url") or track.get("music_info", {}).get("songmid", ""))
                if key in attempts:
                    continue
                attempts.add(key)
                if cancel.is_set():
                    raise ValueError("已取消")
                notify(dict(type="status", text="正在获取播放链接：" + labels.get(candidate["id"], "自动音源")))
                obtained_link = False
                try:
                    media = adapters.music_url(candidate, track, quality)
                    obtained_link = True
                    from .music_search import REFERERS
                    media = adapters.validate_media(media, REFERERS.get(track.get("platform"), ""))
                    self.catalog.record_health(candidate["id"])
                    media["source_name"] = candidate["name"]
                    media["source_id"] = candidate["id"]
                    media["attempts"] = list(attempts)
                    media["expected_duration"] = int(track.get("music_info", {}).get("interval") or 0)
                    return media
                except Exception as exc:
                    error = friendly_error(exc)
                    if obtained_link:
                        self.catalog.set_flags([candidate["id"]], health="init", failures=0,
                                               error="本次媒体地址不可用：" + error)
                    elif "不支持当前平台" not in error:
                        self.catalog.record_health(candidate["id"], error)
                    errors.append(candidate["name"] + "：" + error)
        raise ValueError("当前音源未取得播放地址。可更换音源或平台。\n" + "\n".join(errors))

    def resolve_video(self, result, episode, episodes, cancel, notify, excluded=()):
        attempts, errors = set(excluded), []
        labels = self.catalog.source_labels()
        def try_episode(candidate, row):
            if cancel.is_set():
                raise ValueError("已取消")
            url = candidate["url"]
            if url in attempts:
                return None
            attempts.add(url)
            notify(dict(type="status", text=f"检查 {labels.get(row['source_id'], '源')} · {candidate['title']}"))
            try:
                media = adapters.resolve_media(url, candidate.get("headers"))
                if not media.get("url"):
                    raise ValueError("未识别到可播放媒体，继续换源")
                media = adapters.validate_video(media)
                return dict(media=media, result=row, episode=candidate, attempts=list(attempts))
            except Exception as exc:
                errors.append(row["source_name"] + "：" + friendly_error(exc))
                return None
        candidates = [episode]
        for road in dict.fromkeys(e.get("road", "") for e in episodes):
            matched = episode_match([e for e in episodes if e.get("road", "") == road], episode)
            if matched:
                candidates.append(matched)
        for candidate in candidates:
            resolved = try_episode(candidate, result)
            if resolved:
                return resolved
        alternatives = result.get("alternatives") or []
        for alternative in alternatives[:4]:
            if cancel.is_set():
                raise ValueError("已取消")
            if alternative["source_id"] == result["source_id"]:
                continue
            source = next((s for s in self.catalog.rows("video", active=True) if s["id"] == alternative["source_id"]), None)
            if not source:
                continue
            try:
                other_episodes = adapters.chapters(source, alternative)
                for road in dict.fromkeys(e.get("road", "") for e in other_episodes):
                    matched = episode_match([e for e in other_episodes if e.get("road", "") == road], episode)
                    if matched:
                        resolved = try_episode(matched, {**alternative, "alternatives": alternatives})
                        if resolved:
                            resolved["episodes"] = other_episodes
                            return resolved
            except Exception as exc:
                errors.append(friendly_error(exc))
        raise ValueError("本集已尝试的线路均不可用，可手动换源或打开原网页。\n" + "\n".join(errors[-6:]))

    def check_sources(self, sources, cancel, notify):
        checked = failed = skipped = 0
        def check(source):
            if cancel.is_set() or source["adapter"] not in ADAPTERS:
                return "skip", source["name"]
            try:
                if source["adapter"] == "lx":
                    response = adapters.run_lx(source)
                    self.catalog.set_flags([source["id"]], health="init", failures=0, error="")
                    if response.get("updates"):
                        self.catalog.save_setting("updates:" + source["id"], response["updates"])
                elif source["adapter"] == "direct":
                    with requests.get(adapters.http_url(source["raw"]["url"]), headers=source["raw"].get("headers", {}),
                                      stream=True, timeout=(4, 8)) as response:
                        response.raise_for_status()
                    self.catalog.record_health(source["id"])
                else:
                    query = "三体" if source["kind"] == "book" else "海贼王"
                    result = adapters.search(source, query)
                    self.catalog.record_health(source["id"], empty=not result)
                return "ok", source["name"]
            except Exception as exc:
                self.catalog.record_health(source["id"], friendly_error(exc))
                return "error", source["name"]
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(check, s) for s in sources]
            for future in as_completed(futures):
                state, name = future.result()
                checked += state != "skip"
                failed += state == "error"
                skipped += state == "skip"
                notify(dict(type="status", text=f"检测 {checked}/{len(sources)} · {name}"))
                notify(dict(type="sources"))
                if cancel.is_set():
                    for pending in futures:
                        pending.cancel()
                    break
        return dict(checked=checked, failed=failed, skipped=skipped)

    def import_url(self, url):
        url = adapters.http_url(url.strip())
        if "github.com/" in url and "/blob/" in url:
            url = url.replace("github.com/", "raw.githubusercontent.com/").replace("/blob/", "/")
        response = adapters.fetch(url)
        if "text/html" in response.headers.get("Content-Type", "") and "<html" in response.text.lower():
            raise ValueError("这是网页而非源配置。请复制网页提供的 JSON／JS 原始下载地址后导入")
        result = self.catalog.import_text(response.text, url)
        self.catalog.subscribe(url)
        return result

    def refresh_subscriptions(self, cancel, notify):
        totals = dict(added=0, updated=0, unchanged=0, errors=[])
        for subscription in self.catalog.subscriptions():
            if cancel.is_set():
                break
            url = subscription["url"]
            notify(dict(type="status", text="正在刷新订阅"))
            try:
                result = self.import_url(url)
                for key in ("added", "updated", "unchanged"):
                    totals[key] += result[key]
            except Exception as exc:
                error = friendly_error(exc)
                self.catalog.subscribe(url, error)
                totals["errors"].append(url + "：" + error)
        return totals


def friendly_error(exc):
    if isinstance(exc, requests.Timeout):
        return "请求超时，可稍后重试"
    if isinstance(exc, requests.ConnectionError):
        return "连接失败，请检查网络或更新源地址"
    if isinstance(exc, requests.HTTPError):
        return f"HTTP {exc.response.status_code}，源暂时不可用"
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return str(exc)[:600]
    return f"{type(exc).__name__}：{str(exc)[:300]}"


def ffmpeg_binary():
    from libs.dwgjx.paths import ffmpeg_path
    bundled = ffmpeg_path()
    return bundled if Path(bundled).is_file() else shutil.which("ffmpeg")


def download(media, destination, cancel, notify):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = adapters.http_url(media["url"])
    headers = {"User-Agent": adapters.UA, **media.get("headers", {})}
    if media.get("format") == "hls" or re.search(r"\.m3u8(?:[?#]|$)", url, re.I):
        ffmpeg = ffmpeg_binary()
        if not ffmpeg:
            raise ValueError("HLS 视频需要 FFmpeg；请先在“大丸视频压缩”安装核心组件")
        partial = path.with_name(path.stem + ".part" + path.suffix)
        log = path.with_name(path.name + ".download.log")
        header_text = "".join(f"{key}: {value}\r\n" for key, value in headers.items()
                              if "\r" not in str(value) and "\n" not in str(value))
        command = [ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-rw_timeout", "15000000",
                   "-protocol_whitelist", "http,https,httpproxy,tcp,tls,crypto,data", "-headers", header_text,
                   "-i", url, "-c", "copy", str(partial)]
        try:
            with log.open("w", encoding="utf-8") as errors:
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                while process.poll() is None:
                    if cancel.wait(0.5):
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise ValueError("下载已取消；HLS 重试会从头开始")
                    size = partial.stat().st_size if partial.exists() else 0
                    notify(dict(type="download", text=f"正在合并视频 · {size / 1048576:.1f} MB"))
            if process.returncode != 0:
                raise ValueError("视频下载失败：" + log.read_text(encoding="utf-8", errors="replace")[-500:])
            if not partial.exists() or partial.stat().st_size == 0:
                raise ValueError("视频文件为空")
            partial.replace(path)
        finally:
            log.unlink(missing_ok=True)
        return str(path)
    partial = path.with_name(path.name + ".part")
    metadata = path.with_name(path.name + ".part.json")
    offset = 0
    if partial.exists() and metadata.exists():
        try:
            saved = json.loads(metadata.read_text(encoding="utf-8"))
            if saved.get("url") == url:
                offset = partial.stat().st_size
                headers["Range"] = f"bytes={offset}-"
                if saved.get("validator"):
                    headers["If-Range"] = saved["validator"]
        except (ValueError, OSError):
            pass
    with requests.get(url, headers=headers, stream=True, timeout=(5, 15)) as response:
        response.raise_for_status()
        if response.headers.get("Content-Type", "").startswith("text/html"):
            raise ValueError("下载地址返回网页，请重新获取媒体链接")
        if response.status_code != 206:
            offset = 0
        elif not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise ValueError("服务器返回的续传位置有误，请换一个保存文件名重新下载")
        metadata.write_text(json.dumps(dict(url=url, validator=response.headers.get("ETag") or
                                           response.headers.get("Last-Modified", ""))), encoding="utf-8")
        expected = int(response.headers.get("Content-Length", 0))
        total, written, last = expected + offset, offset, 0
        with partial.open("ab" if offset else "wb") as file:
            for chunk in response.iter_content(131072):
                if cancel.is_set():
                    raise ValueError("下载已取消；再次下载到同一位置可续传直链文件")
                file.write(chunk)
                written += len(chunk)
                if time.monotonic() - last > 0.4:
                    notify(dict(type="download", text=f"下载 {written / 1048576:.1f} MB" +
                                (f" / {total / 1048576:.1f} MB" if total else "")))
                    last = time.monotonic()
        if expected and written != total:
            raise ValueError("下载不完整，保留临时文件以便续传")
    partial.replace(path)
    metadata.unlink(missing_ok=True)
    return str(path)
