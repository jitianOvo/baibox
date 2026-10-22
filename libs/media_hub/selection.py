import re


def normalized(text):
    return re.sub(r"[\s\W_]+", "", text).casefold()


def group_results(rows, kind):
    if kind == "music":
        return rows
    grouped = {}
    for row in sorted(rows, key=lambda r: not bool(r.get("vod"))):
        key = normalized(row["title"])
        if kind == "video" and row.get("vod"):
            vod = row["vod"]
            category = vod.get("type_name", "")
            if any(part in category for part in ("动漫", "动画")):
                category = "动漫"
            elif "剧" in category and "短剧" not in category:
                category = "剧集"
            year = str(vod.get("vod_year", ""))
            if re.fullmatch(r"(?:19|20)\d{2}", year):
                key = key.removesuffix(year)
            key += ":" + category + ":" + year
        if kind == "book":
            key += ":" + normalized(row.get("subtitle", ""))
        if kind == "video" and not row.get("vod"):
            candidates = [k for k in grouped if k.split(":")[0] == key]
            if len(candidates) == 1:
                key = candidates[0]
        if key not in grouped:
            grouped[key] = {**row, "alternatives": []}
        if not any(r["source_id"] == row["source_id"] and r["url"] == row["url"] for r in grouped[key]["alternatives"]):
            grouped[key]["alternatives"].append(row)
    return list(grouped.values())


def rank_music(rows, keyword):
    query = normalized(keyword)
    variants = re.compile(r"DJ|remix|伴奏|翻唱|女声|男声|治愈版|童声|环绕|加速|降调|升调|串烧|改编|chunk", re.I)
    def score(row):
        name, singer = row["title"], row.get("subtitle", "")
        exact = normalized(name) == query
        combined = query in normalized(name + singer)
        return (bool(variants.search(name)), not exact, not combined, row.get("search_rank", 999), row.get("platform") != "kw")
    unique = {}
    for row in sorted(rows, key=score):
        key = (normalized(row["title"]), normalized(row.get("subtitle", "")))
        if key not in unique:
            unique[key] = {**row, "alternatives": []}
        unique[key]["alternatives"].append(row)
    return list(unique.values())


def episode_match(episodes, requested):
    wanted = normalized(requested.get("title", ""))
    exact = next((e for e in episodes if normalized(e["title"]) == wanted), None)
    if exact:
        return exact
    digits = re.findall(r"\d+", requested.get("title", ""))
    if digits:
        return next((e for e in episodes if re.findall(r"\d+", e["title"]) == digits), None)
    return None
