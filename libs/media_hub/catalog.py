import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

KINDS = {"book": "小说", "music": "音乐", "video": "视频"}
ADAPTERS = {"legado", "lx", "maccms", "kazumi", "direct"}


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source(kind, adapter, name, raw, origin="", endpoint="", note="", priority=50):
    identity = endpoint or name
    key = hashlib.sha256(f"{kind}:{adapter}:{identity}".encode()).hexdigest()[:24]
    return dict(id=key, kind=kind, adapter=adapter, name=name, raw=raw,
                origin=origin, endpoint=endpoint, note=note, priority=priority)


def parse_sources(text, origin=""):
    text = text.lstrip("\ufeff").strip()
    origin_path = urlparse(origin).path if "://" in origin else origin
    if (Path(origin_path).suffix.lower() == ".js" or re.search(r"(?:globalThis|window)\.lx|EVENT_NAMES", text)) and not text.startswith("{"):
        match = re.search(r"@name\s+([^\r\n*]+)", text)
        name = match.group(1).strip() if match else Path(origin).name or "LX 音源"
        return [source("music", "lx", name, {"script": text}, origin,
                       note="LX 插件；基础事件、请求及常用加密兼容，检测后选用")]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if text.startswith(("{", "[")):
            raise ValueError("JSON 格式有误，请检查逗号、引号及编码")
        urls = list(dict.fromkeys(re.findall(r"https?://[^\s\"<>]+", text)))
        if not urls:
            raise ValueError("未发现可导入的 JSON、LX 脚本或 HTTP 地址")
        result = []
        for url in urls[:300]:
            url = url.rstrip("),，。]")
            path = urlparse(url).path.lower()
            if re.search(r"\.(?:mp3|m4a|flac|wav|ogg|aac|mp4|mkv|webm|m3u8)$", path):
                kind = "music" if re.search(r"\.(?:mp3|m4a|flac|wav|ogg|aac)$", path) else "video"
                result.append(source(kind, "direct", Path(path).name, {"url": url}, origin, url))
            elif "/provide/vod" in path or "api.php" in path and "vod" in url:
                result.append(source("video", "maccms", urlparse(url).hostname, {"api": url}, origin, url))
            else:
                result.append(source("video", "reference", urlparse(url).hostname, {"url": url}, origin,
                                     url, "参考／订阅地址，请通过“导入网址”读取配置"))
        return result
    if isinstance(data, dict) and data.get("format") == "media-hub-v1":
        entries = data.get("sources", [])
        for item in entries:
            if not isinstance(item, dict) or item.get("kind") not in KINDS or "raw" not in item:
                raise ValueError("听读看备份缺少源字段")
        return entries
    if isinstance(data, dict) and "sites" in data:
        result = []
        for item in data["sites"]:
            adapter = "maccms" if item.get("type") in (0, 1) and str(item.get("api", "")).startswith("http") else "tvbox"
            raw = dict(item, _spider=data.get("spider", ""))
            result.append(source("video", adapter, item.get("name", "视频源"), raw, origin,
                                 str(item.get("api", "")) if adapter == "maccms" else str(item.get("api", "")) + "|" + str(item.get("key", "")),
                                 "需 TVBox Android 插件引擎，原配置已保留" if adapter == "tvbox" else "JSON／XML 采集接口"))
        name = Path(origin_path).stem if origin_path else "TVBox"
        result.append(source("video", "tvbox_config", name + " · 完整配置", data, origin,
                             origin or "TVBox:" + str(data.get("spider", "")),
                             "完整组合配置原样保留，可导出回 TVBox；插件条目需 Android 引擎", 80))
        return result
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("源配置应为对象或数组")
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if "bookSourceUrl" in item:
            rules = item.get("ruleSearch", {})
            search = str(item.get("searchUrl", "")) + json.dumps(
                {key: rules.get(key, "") for key in ("bookList", "name", "bookUrl")}, ensure_ascii=False)
            advanced = any(token in search for token in ("<js>", "@js:", "java.", "source."))
            adapter = "legado_advanced" if advanced else "legado"
            note = "需阅读 JS 引擎，原配置已保留" if advanced else "CSS／XPath／JSON 规则；复杂 JS 章节可打开原网页"
            result.append(source("book", adapter, item.get("bookSourceName", "书源"), item, origin,
                                 item["bookSourceUrl"], note))
        elif "baseURL" in item and "searchURL" in item:
            result.append(source("video", "kazumi", item.get("name", "Kazumi"), item, origin,
                                 item["baseURL"], "Kazumi XPath 规则", 35))
        elif item.get("kind") in KINDS and item.get("adapter"):
            result.append(source(item["kind"], item["adapter"], item.get("name", "自定义源"),
                                 item.get("raw", item), origin, item.get("endpoint", ""), item.get("note", "")))
        elif item.get("api") and str(item["api"]).startswith("http"):
            result.append(source("video", "maccms", item.get("name", "视频接口"), item, origin, item["api"]))
    if not result:
        raise ValueError("配置格式暂未识别，请使用阅读、LX、Kazumi、TVBox 或听读看配置")
    return result


class Catalog:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "catalog.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, kind TEXT, adapter TEXT, name TEXT, raw TEXT,
                    origin TEXT, endpoint TEXT, note TEXT, priority INTEGER DEFAULT 50,
                    enabled INTEGER DEFAULT 1, archived INTEGER DEFAULT 0,
                    health TEXT DEFAULT 'unknown', failures INTEGER DEFAULT 0,
                    checked TEXT DEFAULT '', error TEXT DEFAULT '', updated TEXT);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS subscriptions (url TEXT PRIMARY KEY, checked TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, kind TEXT, title TEXT,
                    payload TEXT, updated TEXT);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    def setting(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def save_setting(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def source_labels(self):
        with self.connect() as db:
            saved = db.execute("SELECT value FROM settings WHERE key='source_numbers_v2'").fetchone()
            numbers = json.loads(saved[0]) if saved else {}
            for kind in KINDS:
                group = numbers.setdefault(kind, {})
                next_number = max(group.values(), default=-1) + 1
                for row in db.execute("SELECT id FROM sources WHERE kind=? ORDER BY CASE WHEN adapter IN ('legado','lx','maccms','kazumi','direct') THEN 0 ELSE 1 END, priority, rowid", (kind,)):
                    if row[0] not in group:
                        group[row[0]] = next_number
                        next_number += 1
            db.execute("INSERT OR REPLACE INTO settings VALUES ('source_numbers_v2',?)", (json.dumps(numbers),))
        return {key: f"源 {number}" for group in numbers.values() for key, number in group.items()}

    def bootstrap(self, bundle):
        if self.setting("seeded") or not Path(bundle).exists():
            return
        self.import_text(Path(bundle).read_text(encoding="utf-8"), str(bundle), backup=False)
        self.save_setting("seeded", True)

    def curate_defaults(self):
        if self.setting("curated_v2"):
            return
        self.backup()
        with self.connect() as db:
            db.execute("UPDATE sources SET priority=2 WHERE kind='music' AND name LIKE '%裤佬%' AND priority=50")
            db.execute("UPDATE sources SET priority=2 WHERE kind='book' AND name='酷我小说' AND priority=50")
        self.save_setting("curated_v2", True)

    def rows(self, kind=None, active=False):
        sql, values = "SELECT * FROM sources WHERE 1=1", []
        if kind:
            sql += " AND kind=?"
            values.append(kind)
        if active:
            sql += " AND enabled=1 AND archived=0"
        sql += " ORDER BY CASE health WHEN 'ok' THEN 0 WHEN 'init' THEN 1 WHEN 'unknown' THEN 2 WHEN 'empty' THEN 3 ELSE 4 END, priority, name"
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(sql, values)]
        for row in rows:
            row["raw"] = json.loads(row["raw"])
        return rows

    def backup(self):
        folder = self.folder / "backups"
        folder.mkdir(exist_ok=True)
        path = folder / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3")
        with self.connect() as db, sqlite3.connect(path, factory=ClosingConnection) as target:
            db.backup(target)
        for old in sorted(folder.glob("*.sqlite3"))[:-10]:
            old.unlink()
        return path

    def import_text(self, text, origin="", backup=True):
        entries = parse_sources(text, origin)
        if backup:
            self.backup()
        added = updated = unchanged = 0
        with self.connect() as db:
            for entry in entries:
                if entry.get("kind") not in KINDS:
                    continue
                raw = json.dumps(entry["raw"], ensure_ascii=False, sort_keys=True)
                old = db.execute("SELECT raw FROM sources WHERE id=?", (entry["id"],)).fetchone()
                if old and old[0] == raw:
                    for field in ("enabled", "archived", "health", "failures"):
                        if field in entry:
                            db.execute(f"UPDATE sources SET {field}=? WHERE id=?", (entry[field], entry["id"]))
                    unchanged += 1
                    continue
                values = [entry.get(key, "") for key in ("id", "kind", "adapter", "name")]
                values += [raw] + [entry.get(key, "") for key in ("origin", "endpoint", "note")]
                values += [entry.get("priority", 50), stamp()]
                if old:
                    db.execute("""UPDATE sources SET kind=?,adapter=?,name=?,raw=?,origin=?,endpoint=?,note=?,priority=?,
                               updated=?,health='unknown',failures=0,error='' WHERE id=?""", values[1:] + [values[0]])
                    updated += 1
                else:
                    enabled = int(entry["adapter"] in ADAPTERS and entry["raw"].get("enabled", True)
                                  and not entry["raw"].get("deprecated", False))
                    db.execute("""INSERT INTO sources (id,kind,adapter,name,raw,origin,endpoint,note,priority,updated,enabled)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?)""", values + [enabled])
                    added += 1
                for field in ("enabled", "archived", "health", "failures"):
                    if field in entry:
                        db.execute(f"UPDATE sources SET {field}=? WHERE id=?", (entry[field], entry["id"]))
        return dict(added=added, updated=updated, unchanged=unchanged)

    def restore(self, path):
        with sqlite3.connect(path, factory=ClosingConnection) as saved:
            tables = {r[0] for r in saved.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"sources", "settings", "subscriptions", "history"}.issubset(tables):
                raise ValueError("这不是听读看的数据库备份")
            self.backup()
            with self.connect() as db:
                saved.backup(db)

    def set_flags(self, ids, **flags):
        allowed = {"enabled", "archived", "health", "failures", "error"}
        if not flags or not set(flags).issubset(allowed):
            raise ValueError("无效状态字段")
        with self.connect() as db:
            sql = "UPDATE sources SET " + ",".join(key + "=?" for key in flags) + " WHERE id=?"
            db.executemany(sql, [list(flags.values()) + [key] for key in ids])

    def record_health(self, key, error="", empty=False):
        with self.connect() as db:
            row = db.execute("SELECT failures FROM sources WHERE id=?", (key,)).fetchone()
            if not row:
                return
            failures = row[0] + 1 if error else 0
            health = "error" if error else "empty" if empty else "ok"
            db.execute("UPDATE sources SET health=?,failures=?,checked=?,error=? WHERE id=?",
                       (health, failures, stamp(), error[:500], key))
            if failures >= 3:
                db.execute("UPDATE sources SET enabled=0 WHERE id=?", (key,))

    def subscribe(self, url, error=""):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO subscriptions VALUES (?,?,?)", (url, stamp(), error[:500]))

    def subscriptions(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM subscriptions")]

    def remove_subscriptions(self, urls):
        self.backup()
        with self.connect() as db:
            db.executemany("DELETE FROM subscriptions WHERE url=?", [(url,) for url in urls])

    def remember(self, kind, title, payload):
        with self.connect() as db:
            db.execute("DELETE FROM history WHERE kind=? AND title=?", (kind, title))
            db.execute("INSERT INTO history (kind,title,payload,updated) VALUES (?,?,?,?)",
                       (kind, title, json.dumps(payload, ensure_ascii=False), stamp()))
            db.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 100)")

    def recent(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM history ORDER BY id DESC LIMIT 100")]

    def export(self):
        return json.dumps({"format": "media-hub-v1", "sources": self.rows()}, ensure_ascii=False, indent=2)
