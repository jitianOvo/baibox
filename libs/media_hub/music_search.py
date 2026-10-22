"""平台元数据与 LX 播放脚本解耦，接口变化时只维护这一层。"""
import hashlib
import json
import time


PLATFORMS = {"kw": "酷我", "wy": "网易", "tx": "QQ", "mg": "咪咕"}
MIGU_PREFERRED = ["屿溪-终章", "墨澜聚合音源", "星澜聚合音源 (StellarWave)"]
REFERERS = {"kw": "https://www.kuwo.cn/", "wy": "https://music.163.com/",
            "tx": "https://y.qq.com/", "mg": "https://music.migu.cn/"}


def search_extra(fetch, platform, keyword, page):
    if platform == "tx":
        data = fetch("https://c.y.qq.com/soso/fcgi-bin/client_search_cp",
                     params=dict(w=keyword, p=page, n=40, format="json"),
                     headers={"Referer": REFERERS[platform]}).json()
        if data.get("code") != 0:
            raise ValueError("QQ 搜索暂不可用")
        return [dict(source="tx", name=s["songname"], singer=" / ".join(a["name"] for a in s.get("singer", [])),
                     songmid=s["songmid"], songId=s["songid"], id=s["songid"],
                     albumName=s.get("albumname", ""), albumMid=s.get("albummid", ""),
                     strMediaMid=s.get("media_mid") or s["songmid"], interval=s.get("interval", 0))
                for s in data.get("data", {}).get("song", {}).get("list", [])]
    if platform != "mg":
        raise ValueError("未知音乐平台")
    timestamp = str(int(time.time() * 1000))
    device = "963B7AA0D21511ED807EE5846EC87D20"
    signature = hashlib.md5((keyword + "6cdc72a439cef99a3418d2a78aa28c73" +
                             "yyapp2d16148780a1dcc7408e06336b98cfd50" + device + timestamp).encode()).hexdigest()
    switches = {"song": 1, "album": 0, "singer": 0, "tagSong": 1, "mvSong": 0,
                "bestShow": 1, "songlist": 0, "lyricSong": 0}
    data = fetch("https://jadeite.migu.cn/music_search/v3/search/searchAll",
                 params=dict(text=keyword, pageNo=page, pageSize=40, sort=0, sid="USS",
                             isCorrect=0, isCopyright=1, searchSwitch=json.dumps(switches, separators=(",", ":"))),
                 headers={"uiVersion": "A_music_3.6.1", "deviceId": device, "timestamp": timestamp,
                          "sign": signature, "channel": "0146921", "User-Agent":
                          "Mozilla/5.0 (Linux; Android 11; MI 11) AppleWebKit/534.30 Mobile Safari/534.30"}).json()
    if data.get("code") != "000000":
        raise ValueError("咪咕搜索暂不可用")
    rows, seen = [], set()
    for group in data.get("songResultData", {}).get("resultList", []):
        for song in group if isinstance(group, list) else [group]:
            key = song.get("copyrightId")
            if not key or not song.get("songId") or key in seen:
                continue
            seen.add(key)
            rows.append(dict(source="mg", name=song["name"], songmid=song["songId"],
                             id=song["songId"], copyrightId=key, albumName=song.get("album", ""),
                             albumId=song.get("albumId", ""), interval=song.get("duration") or 0,
                             singer=" / ".join(a["name"] for a in song.get("singerList", []))))
    return rows
