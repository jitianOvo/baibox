import ast
import base64
import html
import json
import re
import subprocess
import shutil
import os
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit
from xml.etree import ElementTree

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"


def http_url(url):
    if urlsplit(str(url)).scheme not in ("http", "https"):
        raise ValueError("地址必须以 http:// 或 https:// 开头")
    return str(url)


def fetch(url, *, method="GET", headers=None, data=None, params=None, limit=8_000_000, media_probe=False):
    for attempt in range(2):
        try:
            return _fetch_once(url, method=method, headers=headers, data=data, params=params,
                               limit=limit, media_probe=media_probe)
        except requests.RequestException as exc:
            transient = isinstance(exc, requests.ConnectionError) or (
                exc.response is not None and exc.response.status_code in (502, 503, 504))
            if attempt or method.upper() != "GET" or not transient:
                raise


def _fetch_once(url, *, method="GET", headers=None, data=None, params=None, limit=8_000_000, media_probe=False):
    with requests.request(method, http_url(url), headers={"User-Agent": UA, **(headers or {})},
                          data=data, params=params, timeout=(5, 10), stream=True) as response:
        response.raise_for_status()
        if media_probe and any(part in response.headers.get("Content-Type", "").lower()
                               for part in ("audio/", "video/", "mpegurl")):
            return response
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > limit:
                raise ValueError("响应过大，超过当前读取上限")
            chunks.append(chunk)
        response._content = b"".join(chunks)
        response._content_consumed = True
        content_type = response.headers.get("Content-Type", "")
        charset = re.search(r"charset=[\"']?([\w-]+)", content_type + " " + response.content[:1000].decode("ascii", "ignore"))
        response.encoding = charset.group(1) if charset else "utf-8"
        return response


def json_value(data, path):
    if not path or path == "$":
        return data
    path = path.removeprefix("@json:").strip()
    recursive = path.startswith("$..")
    if recursive:
        field = path[3:].split("[")[0]
        found = []
        def walk(value):
            if isinstance(value, dict):
                if field in value:
                    found.append(value[field])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(data)
        return found
    tokens = re.findall(r"([\w-]+)|\[([*\d-]+)\]|\[['\"]([^'\"]+)['\"]\]", path.lstrip("$ ."))
    values = [data]
    expanded = False
    for field, index, quoted in tokens:
        next_values = []
        for value in values:
            if field or quoted:
                if isinstance(value, dict) and (field or quoted) in value:
                    next_values.append(value[field or quoted])
            elif index == "*" and isinstance(value, list):
                next_values.extend(value)
                expanded = True
            elif index and isinstance(value, list):
                number = int(index)
                if -len(value) <= number < len(value):
                    next_values.append(value[number])
        values = next_values
    return values if expanded else values[0] if values else ""


def parse_document(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "lxml")


def element_rule(document, rule):
    from bs4 import BeautifulSoup, Tag
    nodes = [document]
    for segment in rule.removeprefix("@css:").split("@"):
        if not segment:
            continue
        excluded = re.search(r"!([\d,]+)$", segment)
        if excluded:
            segment = segment[:excluded.start()]
        selector, selection = segment, None
        index = re.search(r"\.(-?\d+(?::-?\d+)?)$|\[(-?\d+:-?\d+)\]$", segment)
        if index:
            selector, selection = segment[:index.start()], next(v for v in index.groups() if v is not None)
        if selector.startswith("class."):
            selector = "".join("." + word for word in selector[6:].split())
        elif selector.startswith("id."):
            selector = "#" + selector[3:]
        elif selector.startswith("tag."):
            selector = selector[4:]
        next_nodes = []
        for node in nodes:
            if not isinstance(node, (Tag, BeautifulSoup)):
                continue
            if selector.startswith("text."):
                found = node.find_all(string=lambda s: s and selector[5:] in s)
                found = [s.parent for s in found]
            else:
                found = node.select(selector)
            if excluded:
                remove = {int(v) for v in excluded.group(1).split(",")}
                found = [v for i, v in enumerate(found) if i not in remove]
            if selection and ":" in selection:
                start, end = map(int, selection.split(":"))
                found = found[start:end:1 if start <= end else -1]
            elif selection:
                pos = int(selection)
                found = [found[pos]] if -len(found) <= pos < len(found) else []
            next_nodes.extend(found)
        nodes = next_nodes
    return nodes


def xpath_values(document, rule):
    from lxml import html as lhtml
    tree = lhtml.fromstring(str(document))
    expression = "." + rule if rule.startswith("//") else rule.removeprefix("@xpath:")
    return tree.xpath(expression)


def value(document, rule, base="", many=False):
    if not rule:
        return [] if many else ""
    if any(token in rule for token in ("@js:", "<js>", "java.")):
        raise ValueError("此字段依赖阅读 JavaScript 引擎；可打开原网页或更换基础规则书源")
    if "||" in rule:
        for alternative in rule.split("||"):
            result = value(document, alternative, base, many)
            if result:
                return result
        return [] if many else ""
    if "&&" in rule:
        results = [value(document, part, base, many) for part in rule.split("&&")]
        return [x for result in results for x in result] if many else " · ".join(filter(None, results))
    if "{{" in rule:
        rendered = re.sub(r"\{\{([^}]+)\}\}", lambda m: str(value(document, m[1].strip(), base)), rule)
        return rendered
    parts = rule.split("##")
    clean_rule = parts[0]
    if clean_rule.startswith(("$", "@json:")):
        result = json_value(document, clean_rule)
        if many:
            return result if isinstance(result, list) else [result] if result else []
        result = str(result) if result is not None else ""
    elif clean_rule.startswith(("//", "@xpath:", ".//")):
        nodes = xpath_values(document, clean_rule)
        if many:
            from bs4 import BeautifulSoup
            from lxml import etree
            return [BeautifulSoup(etree.tostring(n, encoding="unicode"), "lxml") if hasattr(n, "tag") else n for n in nodes]
        result = "\n".join(n.text_content() if hasattr(n, "text_content") else str(n) for n in nodes)
    elif clean_rule.startswith(("http://", "https://", "/")):
        result = clean_rule
    else:
        terminals = {"text", "textNodes", "html", "all", "href", "src", "title", "content", "data-src"}
        chain = clean_rule.split("@")
        attribute = chain[-1] if chain[-1] in terminals or chain[-1].startswith("data-") else ""
        selector = "@".join(chain[:-1]) if attribute else clean_rule
        nodes = element_rule(document, selector) if selector else [document]
        if many:
            return nodes
        texts = []
        for node in nodes:
            if attribute in ("text", "textNodes", "html", "all", ""):
                texts.append(node.get_text("\n", strip=True))
            else:
                texts.append(str(node.get(attribute, "")))
        result = "\n".join(filter(None, texts))
    if len(parts) > 1:
        replacement = parts[2] if len(parts) > 2 else ""
        replacement = re.sub(r"\$(\d+)", r"\\g<\1>", replacement)
        result = re.sub(parts[1], replacement, result)
    return html.unescape(result).strip()


def render_template(text, key="", page=1, charset="utf-8", encode_key=True):
    def replace(match):
        expression = match[1].strip()
        if expression in ("key", "encodeURIComponent(key)"):
            return quote(key, safe="", encoding=charset, errors="replace") if encode_key or expression != "key" else key
        options = {"page": str(page), "page-1": str(page - 1), "(page-1)*50": str((page - 1) * 50)}
        if expression in options:
            return options[expression]
        raise ValueError(f"暂未支持的模板表达式：{expression}")
    return re.sub(r"\{\{(.*?)\}\}", replace, text, flags=re.S)


def request_rule(raw, request, key="", page=1):
    base = str(raw["bookSourceUrl"]).split("#")[0]
    split = re.split(r",\s*(?=\{)", request, maxsplit=1)
    options = {}
    if len(split) == 2:
        try:
            options = json.loads(split[1])
        except ValueError:
            options = ast.literal_eval(split[1])
    charset = options.get("charset", "utf-8")
    url = urljoin(base, render_template(split[0], key, page, charset))
    header = raw.get("header") or {}
    if isinstance(header, str):
        try:
            header = json.loads(header)
        except ValueError:
            header = {}
    headers = {"Referer": base, **header, **options.get("headers", {})}
    content_type = next((str(v).lower() for k, v in headers.items() if k.lower() == "content-type"), "")
    body = options.get("body")
    if isinstance(body, str) and body.lstrip().startswith(("{", "[")):
        try:
            body = json.loads(body)
            content_type = "application/json"
        except ValueError:
            pass
    if isinstance(body, (dict, list)):
        def render_data(data):
            if isinstance(data, str):
                return render_template(data, key, page, charset, encode_key=False)
            if isinstance(data, dict):
                return {k: render_data(v) for k, v in data.items()}
            if isinstance(data, list):
                return [render_data(v) for v in data]
            return data
        body = render_data(body)
        if "json" in content_type or isinstance(body, list):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            body = urlencode(body, doseq=True, encoding=charset, errors="replace")
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        body = render_template(str(body), key, page, charset)
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    response = fetch(url, method=options.get("method", "GET"),
                     headers=headers, data=body)
    if options.get("charset"):
        response.encoding = charset
    return parse_document(response.text), response.url


def item(source, title, url, subtitle="", **extra):
    return dict(source_id=source["id"], source_name=source["name"], kind=source["kind"],
                title=title, url=url, subtitle=subtitle, **extra)


def search(source, keyword, page=1, platform="wy"):
    raw, adapter = source["raw"], source["adapter"]
    if adapter == "legado":
        doc, base = request_rule(raw, raw.get("searchUrl", ""), keyword, page)
        rules = raw.get("ruleSearch", {})
        results = []
        for node in value(doc, rules.get("bookList", ""), base, True)[:60]:
            name = value(node, rules.get("name", "text"), base)
            url = value(node, rules.get("bookUrl", "href"), base)
            try:
                author = value(node, rules.get("author", ""), base)
            except ValueError:
                author = ""
            if name and url:
                results.append(item(source, name, urljoin(base, url), author))
        return results
    if adapter == "maccms":
        params = {"ac": "detail", "wd": keyword}
        if page > 1:
            params["pg"] = page
        response = fetch(raw["api"], params=params, headers=raw.get("headers"))
        try:
            data = response.json()
        except ValueError:
            xml = ElementTree.fromstring(response.content)
            data = {"list": [dict(vod_id=v.findtext("id"), vod_name=v.findtext("name"),
                                 vod_remarks=v.findtext("note"), vod_play_url="$$$".join(dd.text or "" for dd in v.findall("./dl/dd")),
                                 vod_play_from="$$$".join(dd.get("flag", "线路") for dd in v.findall("./dl/dd"))) for v in xml.findall("./list/video")]}
        if not isinstance(data, dict) or not isinstance(data.get("list"), list):
            raise ValueError("视频接口未返回可识别的作品列表")
        return [item(source, v.get("vod_name", "无标题"), str(v.get("vod_id", "")),
                     " · ".join(str(v.get(field, "")) for field in ("type_name", "vod_year", "vod_remarks") if v.get(field)), vod=v) for v in data["list"][:60]]
    if adapter == "kazumi":
        if raw.get("searchType") == "api":
            raise ValueError("此 Kazumi 源使用新版 API 规则；当前适配 XPath 规则")
        url = raw["searchURL"].replace("@keyword", quote(keyword)).replace("@page", str(page))
        response = fetch(url, method="POST" if raw.get("usePost") else "GET",
                         headers={"Referer": raw["baseURL"], "User-Agent": raw.get("userAgent") or UA})
        from lxml import html as lhtml
        doc = lhtml.fromstring(response.text)
        results = []
        for node in doc.xpath(raw["searchList"])[:60]:
            names = node.xpath("." + raw["searchName"] if raw["searchName"].startswith("//") else raw["searchName"])
            links = node.xpath("." + raw["searchResult"] if raw["searchResult"].startswith("//") else raw["searchResult"])
            if names and links:
                name = names[0].text_content() if hasattr(names[0], "text_content") else str(names[0])
                link = links[0].get("href", "") if hasattr(links[0], "get") else str(links[0])
                if link:
                    results.append(item(source, name.strip(), urljoin(response.url, link)))
        return results
    if adapter in ("lx", "gd"):
        return search_music(source, keyword, platform, page)
    if adapter == "direct":
        return [item(source, source["name"], raw["url"], headers=raw.get("headers", {}))] if keyword.lower() in source["name"].lower() else []
    raise ValueError(source.get("note") or "此源需要对应应用的插件引擎")


def search_music(source, keyword, platform, page):
    if platform in ("tx", "mg"):
        from .music_search import search_extra
        return [item(source, s["name"], str(s["songmid"]), s["singer"], music_info=s, platform=platform)
                for s in search_extra(fetch, platform, keyword, page)]
    if platform == "kw":
        response = fetch("https://search.kuwo.cn/r.s", params=dict(all=keyword, ft="music", client="kt",
                         pn=page - 1, rn=60, rformat="json", encoding="utf8", uid="794762570",
                         ver="kwplayer_ar_9.2.2.1", vipver=1, show_copyright_off=1, newver=1,
                         cluster=0, strategy=2012, vermerge=1, mobi=1, issubtitle=1))
        try:
            data = response.json()
        except ValueError:
            data = ast.literal_eval(response.text)
        results = []
        for song in data.get("abslist", []):
            number = str(song.get("MUSICRID", "")).replace("MUSIC_", "")
            info = dict(id=number, songmid=number, musicId=number, name=html.unescape(song.get("SONGNAME") or song.get("NAME", "")),
                        singer=html.unescape(song.get("ARTIST", "")), source="kw", interval=song.get("DURATION", ""),
                        albumName=html.unescape(song.get("ALBUM", "")))
            results.append(item(source, info["name"], number, info["singer"], music_info=info, platform="kw"))
        return results
    response = fetch("https://music.163.com/api/search/get", params=dict(s=keyword, type=1, limit=60, offset=(page - 1) * 60),
                     headers={"Referer": "https://music.163.com/"})
    data = response.json()
    if data.get("code") != 200:
        raise ValueError("网易搜索暂不可用，请切换酷我")
    results = []
    for song in data.get("result", {}).get("songs", []):
        number = str(song["id"])
        singer = " / ".join(a["name"] for a in song.get("artists", []))
        info = dict(id=number, songmid=number, songId=number, name=song["name"], singer=singer, source="wy",
                    interval=song.get("duration", 0) // 1000, albumName=song.get("album", {}).get("name", ""))
        results.append(item(source, song["name"], number, singer, music_info=info, platform="wy"))
    return results


def chapters(source, result):
    raw, adapter = source["raw"], source["adapter"]
    if adapter == "maccms":
        vod = result.get("vod", {})
        if not vod.get("vod_play_url"):
            response = fetch(raw["api"], params={"ac": "detail", "ids": result["url"]})
            vod = response.json()["list"][0]
        roads = str(vod.get("vod_play_from", "")).split("$$$")
        episodes = []
        for road_index, playlist in enumerate(str(vod.get("vod_play_url", "")).split("$$$")):
            road = roads[road_index] if road_index < len(roads) else f"线路{road_index + 1}"
            for number, episode in enumerate(playlist.split("#")):
                name, sep, url = episode.partition("$")
                if sep and url.startswith("http"):
                    episodes.append(dict(title=name, road=road, number=number,
                                         url=url, headers=raw.get("headers", {})))
        if not episodes:
            raise ValueError("作品没有可访问的播放地址")
        episodes.sort(key=lambda episode: 0 if re.search(r"\.(m3u8|mp4)(?:[?#]|$)", episode["url"], re.I) else 1)
        return episodes
    if adapter == "legado":
        doc, base = request_rule(raw, result["url"])
        info_rules = raw.get("ruleBookInfo", {})
        if info_rules.get("init"):
            doc = json_value(doc, info_rules["init"])
        toc_rule = info_rules.get("tocUrl", "")
        if toc_rule:
            toc_url = value(doc, toc_rule, base)
            if toc_url and urljoin(base, toc_url) != base:
                doc, base = request_rule(raw, urljoin(base, toc_url))
        rules, episodes, seen = raw.get("ruleToc", {}), [], set()
        for _ in range(5):
            for node in value(doc, rules.get("chapterList", ""), base, True):
                name = value(node, rules.get("chapterName", "text"), base)
                link = value(node, rules.get("chapterUrl", "href"), base)
                link = urljoin(base, link)
                if name and link not in seen:
                    episodes.append(dict(title=name, url=link))
                    seen.add(link)
            next_rule = rules.get("nextTocUrl", "")
            if not next_rule:
                break
            next_url = urljoin(base, value(doc, next_rule, base))
            if next_url in seen or next_url == base:
                break
            seen.add(next_url)
            doc, base = request_rule(raw, next_url)
        if not episodes:
            raise ValueError("目录未匹配到章节，请在源管理检查目录规则")
        return episodes
    if adapter == "kazumi":
        from lxml import html as lhtml
        response = fetch(result["url"], headers={"Referer": raw.get("referer") or raw["baseURL"]})
        doc, episodes = lhtml.fromstring(response.text), []
        roads = doc.xpath(raw.get("chapterRoads", "//body"))
        for road_index, road in enumerate(roads):
            path = raw["chapterResult"]
            for link in road.xpath("." + path if path.startswith("//") else path):
                episodes.append(dict(title=link.text_content().strip(), road=f"线路{road_index + 1}",
                                     url=urljoin(response.url, link.get("href", "")), headers={"Referer": response.url}))
        if not episodes:
            raise ValueError("选集规则未匹配；可打开原网页检查站点变化")
        return episodes
    return [dict(title=result["title"], url=result["url"], headers=result.get("headers", {}))]


def chapter_text(source, episode):
    raw = source["raw"]
    doc, base = request_rule(raw, episode["url"])
    rules = raw.get("ruleContent", {})
    text = value(doc, rules.get("content", ""), base)
    if not text:
        raise ValueError("正文为空，请检查此源的正文规则")
    replacement = rules.get("replaceRegex", "")
    if replacement:
        parts = replacement.split("##")
        pattern = parts[1] if parts[0] == "" and len(parts) > 1 else parts[0]
        if "{{" not in pattern:
            text = re.sub(pattern, parts[2] if len(parts) > 2 else "", text)
    if text.startswith(("http://", "https://")) and "\n" not in text:
        return dict(url=text, text="", title=episode["title"])
    return dict(text=text, url="", title=episode["title"])


def run_lx(source, action="init", result=None, quality="128k"):
    runner = Path(__file__).with_name("lx_runner.js")
    node = shutil.which("node")
    if not node:
        raise ValueError("LX 音源需要 Node.js 22.13+；本机未找到 node，请配置到 PATH 后重启")
    request = dict(script=source["raw"]["script"], action=action, info=result, quality=quality, name=source["name"])
    try:
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
        process = subprocess.run([node, "--permission", f"--allow-fs-read={runner}", "--max-old-space-size=128", str(runner)],
                                 input=json.dumps(request), env=environment,
                                 text=True, encoding="utf-8", capture_output=True, timeout=32,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise ValueError("LX 音源超时（32 秒），请检测音源或切换另一个源") from None
    try:
        response = json.loads(process.stdout)
    except ValueError:
        if "--permission" in process.stderr and "bad option" in process.stderr:
            raise ValueError("Node.js 版本过旧，请使用支持 --permission 的 Node.js 22.13+（本机已验证 24.11.1）") from None
        raise ValueError("LX 音源运行失败，请切换音源或检查脚本兼容性") from None
    if response.get("error"):
        raise ValueError(response["error"])
    return response


def music_url(source, result, quality="128k"):
    if source["adapter"] == "direct":
        return dict(url=result["url"], headers=result.get("headers", {}))
    response = run_lx(source, "musicUrl", result, quality)
    resolved = response.get("result")
    if isinstance(resolved, dict):
        return dict(url=http_url(resolved.get("url", "")), headers=resolved.get("headers", {}))
    return dict(url=http_url(resolved), headers={})


def validate_media(media, referer=""):
    headers = {"User-Agent": UA, **({"Referer": referer} if referer else {}), **media.get("headers", {})}
    with requests.get(http_url(media["url"]), headers={**headers, "Range": "bytes=0-4095"},
                      stream=True, timeout=(4, 8)) as response:
        response.raise_for_status()
        sample = next(response.iter_content(4096), b"")
        if not sample or response.headers.get("Content-Type", "").startswith("text/html") or sample.lstrip().startswith((b"<html", b"<!DOCTYPE", b'{"')):
            raise ValueError("媒体地址返回空内容或错误页，请更换音源")
    return {**media, "headers": headers}


def hls_variants(body, base):
    variants, attributes = [], None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            attributes = dict(re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', line.partition(":")[2]))
        elif line and not line.startswith("#") and attributes is not None:
            resolution = attributes.get("RESOLUTION", "").strip('"')
            bandwidth = int(attributes.get("BANDWIDTH", "0") or 0)
            height = int(resolution.split("x")[-1]) if re.fullmatch(r"\d+x\d+", resolution) else 0
            label = f"{height}p" if height else (f"{bandwidth // 1000} kbps" if bandwidth else "源清晰度")
            variants.append(dict(url=urljoin(base, line), label=label, resolution=resolution, bandwidth=bandwidth))
            attributes = None
    variants.sort(key=lambda v: (int(v["resolution"].split("x")[-1]) if v["resolution"] else 0, v["bandwidth"]), reverse=True)
    # 同高度可能有不同码率，明确区分。
    labels = [v["label"] for v in variants]
    for variant in variants:
        if labels.count(variant["label"]) > 1:
            variant["label"] += f" · {variant['bandwidth'] // 1000} kbps"
    return variants


def validate_video(media, depth=0):
    """先检查清单与第一片，避免 API 正常但视频已失效的假成功。"""
    if not media.get("url"):
        return media
    if depth >= 4:
        raise ValueError("视频清单跳转过多")
    media = validate_media(media)
    url, headers = media["url"], media["headers"]
    if not (media.get("format") == "hls" or ".m3u8" in urlsplit(url).path.lower()):
        return media
    variants = media.get("variants", [])
    master_url = media.get("master_url", "")
    for _ in range(4):
        response = fetch(url, headers=headers, limit=4_000_000)
        if not response.text.lstrip().startswith("#EXTM3U"):
            raise ValueError("视频清单无效")
        lines = response.text.splitlines()
        links = [urljoin(response.url, line.strip()) for line in lines if line.strip() and not line.startswith("#")]
        if not links:
            raise ValueError("视频清单没有分片")
        if any(line.startswith("#EXT-X-STREAM-INF") for line in lines):
            variants = hls_variants(response.text, response.url)
            master_url = response.url
            errors = []
            for variant in variants:
                try:
                    return validate_video({**media, "url": variant["url"], "variants": variants,
                                           "master_url": master_url, "selected_variant": variant["url"]}, depth + 1)
                except Exception as exc:
                    errors.append(str(exc))
            raise ValueError("源提供的清晰度均不可用：" + "; ".join(errors[-2:]))
        validate_media(dict(url=links[0], headers=headers))
        return {**media, "url": response.url, "format": "hls", "variants": variants,
                "master_url": master_url}
    raise ValueError("视频清单跳转过多")


def resolve_video_link(url, headers=None):
    media = resolve_media(url, headers)
    return validate_video(media) if media.get("url") else media


def resolve_media(url, headers=None, depth=0):
    http_url(url)
    if re.search(r"\.(?:m3u8|mp4|mp3|flac|m4a|aac|ogg|wav|mkv|webm)(?:[?#]|$)", url, re.I):
        return dict(url=url, headers=headers or {})
    response = fetch(url, headers=headers, media_probe=True)
    if any(part in response.headers.get("Content-Type", "").lower() for part in ("video/", "audio/", "mpegurl")):
        return dict(url=response.url, headers=headers or {}, format="hls" if "mpegurl" in response.headers.get("Content-Type", "").lower() else "")
    body = html.unescape(response.text).replace("\\/", "/")
    if body.lstrip().startswith("#EXTM3U"):
        return dict(url=response.url, headers=headers or {}, format="hls")
    player = re.search(r"(?:var\s+)?player_\w+\s*=\s*(\{[^\n]+?\})\s*[;<]", body)
    if player:
        try:
            data = json.loads(player[1])
            target = data.get("url", "")
            if str(data.get("encrypt")) == "1":
                target = unquote(target)
            elif str(data.get("encrypt")) == "2":
                target = unquote(base64.b64decode(target).decode())
            if target.startswith("http") and depth < 2:
                return resolve_media(target, {**(headers or {}), "Referer": response.url}, depth + 1)
        except (ValueError, KeyError):
            pass
    candidates = re.findall(r"https?://[^\s\"'<>]+?\.(?:m3u8|mp4|mp3)(?:\?[^\s\"'<>]*)?", body)
    if candidates:
        return dict(url=candidates[0], headers={**(headers or {}), "Referer": response.url})
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, "lxml")
    element = soup.select_one("video[src],audio[src],source[src]")
    if element:
        return dict(url=urljoin(response.url, element["src"]), headers={**(headers or {}), "Referer": response.url})
    iframe = soup.select_one("iframe[src]")
    if iframe and depth < 2:
        return resolve_media(urljoin(response.url, iframe["src"]), {"Referer": response.url}, depth + 1)
    return dict(url="", page=url, headers=headers or {})
