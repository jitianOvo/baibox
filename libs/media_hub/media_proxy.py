import base64
import re
import secrets
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class MediaProxy:
    """播放任务独立请求头；复用连接，有限预读 HLS 分片。"""
    def __init__(self):
        self.token = secrets.token_hex(16)
        self.headers, self.playlists = {}, set()
        self.contexts, self.current = {}, "legacy"
        self.local = threading.local()
        self.lock = threading.RLock()
        self.cache, self.cache_bytes = OrderedDict(), 0
        self.inflight, self.following = {}, {}
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="media-prefetch")
        self.closed = False
        retry = Retry(total=1, backoff_factor=0.2, status_forcelist=(502, 503, 504))
        self.adapter = HTTPAdapter(pool_connections=12, pool_maxsize=8, max_retries=retry)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self.relay(True)

            def do_GET(self):
                self.relay(False)

            def relay(self, head):
                sent = False
                try:
                    prefix = "/" + owner.token + "/"
                    if not self.path.startswith(prefix):
                        self.send_error(403)
                        return
                    context, encoded, *_ = self.path[len(prefix):].split("/")
                    url = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
                    if urlsplit(url).scheme not in ("http", "https"):
                        raise ValueError("Invalid media URL")
                    settings = owner.contexts.get(context)
                    if settings is None:
                        settings = dict(headers=dict(owner.headers), playlists=set(owner.playlists)) if context == "legacy" else None
                    if settings is None:
                        raise ValueError("Playback expired")
                    key = (context, url)
                    if key in owner.following:
                        body, kind = owner.segment(context, url)
                        owner.prefetch(context, owner.following.get(key, []))
                        start, end, status = 0, len(body) - 1, 200
                        match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                        if match:
                            start = int(match[1]); end = min(end, int(match[2]) if match[2] else end)
                            if start > end:
                                self.send_error(416)
                                return
                            status = 206
                        self.send_response(status)
                        self.send_header("Content-Type", kind)
                        self.send_header("Content-Length", str(end - start + 1))
                        self.send_header("Accept-Ranges", "bytes")
                        if status == 206:
                            self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
                        self.end_headers(); sent = True
                        if not head:
                            self.wfile.write(body[start:end + 1])
                        return
                    headers = dict(settings["headers"])
                    if self.headers.get("Range"):
                        headers["Range"] = self.headers["Range"]
                    with owner.session().get(url, headers=headers, timeout=(4, 12), stream=True) as response:
                        response.raise_for_status()
                        kind = response.headers.get("Content-Type", "application/octet-stream")
                        playlist = url in settings["playlists"] or ".m3u8" in urlsplit(response.url).path.lower() or "mpegurl" in kind.lower()
                        if playlist:
                            chunks, length = [], 0
                            for chunk in response.iter_content(65536):
                                length += len(chunk)
                                if length > 4_000_000:
                                    raise ValueError("Playlist too large")
                                chunks.append(chunk)
                            text = b"".join(chunks).decode("utf-8-sig")
                            segments, lines = [], []
                            for line in text.splitlines():
                                if line and not line.startswith("#"):
                                    remote = urljoin(response.url, line.strip())
                                    segments.append(remote)
                                    line = owner.url(remote, context)
                                else:
                                    line = re.sub(r'URI="([^"]+)"', lambda m: 'URI="' + owner.url(urljoin(response.url, m[1]), context) + '"', line)
                                lines.append(line)
                            if "#EXTINF:" in text and "#EXT-X-ENDLIST" in text:
                                with owner.lock:
                                    for i, remote in enumerate(segments):
                                        owner.following[(context, remote)] = segments[i + 1:i + 3]
                                owner.prefetch(context, segments[:3])
                            body = "\n".join(lines).encode()
                            self.send_response(200)
                            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                            self.send_header("Content-Length", str(len(body)))
                            self.end_headers(); sent = True
                            if not head:
                                self.wfile.write(body)
                        else:
                            self.send_response(response.status_code)
                            self.send_header("Content-Type", kind)
                            for name in ("Content-Length", "Content-Range", "Accept-Ranges"):
                                if name in response.headers:
                                    self.send_header(name, response.headers[name])
                            self.end_headers(); sent = True
                            if not head:
                                for chunk in response.iter_content(65536):
                                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception:
                    if not sent:
                        try:
                            self.send_error(502, "Media source unavailable")
                        except OSError:
                            pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def session(self):
        if not hasattr(self.local, "session"):
            session = requests.Session()
            for scheme in ("https://", "http://"):
                session.mount(scheme, self.adapter)
            self.local.session = session
        return self.local.session

    def start(self, media):
        self.current = secrets.token_hex(8)
        with self.lock:
            self.contexts = {self.current: dict(headers=dict(media.get("headers", {})),
                                              playlists={media["url"]} if media.get("format") == "hls" else set())}
            self.cache.clear(); self.cache_bytes = 0; self.following.clear()
        return self.url(media["url"], self.current)

    def url(self, remote, context=None):
        encoded = base64.urlsafe_b64encode(remote.encode()).decode().rstrip("=")
        suffix = urlsplit(remote).path.rsplit("/", 1)[-1] or "media"
        return f"http://127.0.0.1:{self.server.server_port}/{self.token}/{context or self.current}/{encoded}/{suffix}"

    def segment(self, context, remote):
        key = (context, remote)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            event = self.inflight.get(key)
            fetch = event is None
            if fetch:
                event = self.inflight[key] = threading.Event()
        if not fetch:
            if not event.wait(18):
                raise ValueError("Segment timeout")
            with self.lock:
                if key in self.cache:
                    return self.cache[key]
            raise ValueError("Segment unavailable")
        try:
            settings = self.contexts.get(context, dict(headers=self.headers))
            with self.session().get(remote, headers=settings["headers"], timeout=(4, 10), stream=True) as response:
                response.raise_for_status()
                chunks, length = [], 0
                for chunk in response.iter_content(65536):
                    length += len(chunk)
                    if length > 16_000_000 or self.closed:
                        raise ValueError("Segment exceeds prefetch limit")
                    chunks.append(chunk)
                value = (b"".join(chunks), response.headers.get("Content-Type", "video/mp2t"))
            with self.lock:
                if context == self.current:
                    self.cache[key] = value; self.cache_bytes += length
                    while self.cache_bytes > 48_000_000 and len(self.cache) > 1:
                        _, old = self.cache.popitem(last=False)
                        self.cache_bytes -= len(old[0])
            return value
        finally:
            with self.lock:
                self.inflight.pop(key, None)
                event.set()

    def prefetch(self, context, urls):
        if self.closed or context != self.current:
            return
        for remote in urls:
            with self.lock:
                if (context, remote) in self.cache or (context, remote) in self.inflight:
                    continue
            self.pool.submit(self._prefetch, context, remote)

    def _prefetch(self, context, remote):
        if context != self.current or self.closed:
            return
        try:
            self.segment(context, remote)
        except Exception:
            pass

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.server.shutdown()
        self.server.server_close()
        self.adapter.close()
