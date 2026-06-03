"""
视频精选 Web 应用 — Flask 后端 v3
新增: 搜索API · 并发YouTube · 视频缓存 · 并行摘要 · 健康检查 · 封面代理 · 深度分析 · 质量评分
"""
import json
import hashlib
import os
import random
import re
import time
from datetime import datetime
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, request

from config import (
    BILIBILI_CATEGORIES,
    BILIBILI_CATEGORY_LABELS,
    BILIBILI_MAX_WORKERS,
    CACHE_DIR,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    MIN_DURATION_SECONDS,
    NOTES_EXPORT_DIR,
    SUMMARY_CACHE_TTL,
    VIDEO_LIST_CACHE_TTL,
    VIDEOS_PER_PAGE,
    YOUTUBE_API_KEY,
    YOUTUBE_EDUCATION_CHANNELS,
    YOUTUBE_MAX_WORKERS,
    YOUTUBE_MAX_WORKERS_API,
    YOUTUBE_TIMEOUT,
)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

# YouTube 时长缓存 (永久，时长不变)
DURATION_CACHE_FILE = Path(CACHE_DIR) / "yt_duration_cache.json"


def _load_duration_cache() -> dict:
    if DURATION_CACHE_FILE.exists():
        try:
            return json.loads(DURATION_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_duration_cache(data: dict) -> None:
    DURATION_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _get_cached_duration(video_id: str) -> int:
    return _load_duration_cache().get(video_id, 0)


def _set_cached_duration(video_id: str, seconds: int) -> None:
    cache = _load_duration_cache()
    cache[video_id] = seconds
    if len(cache) > 5000:
        cache = dict(list(cache.items())[-3000:])
    _save_duration_cache(cache)


# ──────────────────────────────────────────────
#  缓存工具
# ──────────────────────────────────────────────

def cache_get(key: str) -> dict | None:
    cache_file = Path(CACHE_DIR) / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return None


def cache_set(key: str, data: dict) -> None:
    data["_ts"] = time.time()
    cache_file = Path(CACHE_DIR) / f"{key}.json"
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cache_key(*parts: str) -> str:
    return hashlib.md5(":".join(parts).encode()).hexdigest()[:16]


def cache_get_with_ttl(key: str, ttl: int) -> dict | None:
    data = cache_get(key)
    if data and time.time() - data.get("_ts", 0) < ttl:
        return data
    return None


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def parse_duration(raw: str) -> int:
    """解析时长字符串为秒数。支持 mm:ss 和 hh:mm:ss"""
    if not raw:
        return 0
    raw = str(raw).strip()
    # 已经是纯数字（秒）
    if raw.isdigit():
        return int(raw)
    parts = raw.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0


def format_duration(seconds: int) -> str:
    """秒数 → 可读时长: 12:34 或 1:23:45"""
    if seconds <= 0:
        return ""
    h, m = divmod(seconds, 3600)
    m, s = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def duration_badge(seconds: int) -> str:
    """时长标签: 短/中/长"""
    if seconds < 600:
        return "5-10分钟"
    elif seconds < 1800:
        return "10-30分钟"
    elif seconds < 3600:
        return "30-60分钟"
    else:
        return "60分钟以上"


def parse_iso8601_duration(iso_duration: str) -> int:
    """解析 YouTube API 返回的 ISO 8601 时长 (PT12M34S) 为秒数"""
    if not iso_duration:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(iso_duration).strip())
    if not m:
        return 0
    h, mi, s = (int(m.group(g) or 0) for g in (1, 2, 3))
    return h * 3600 + mi * 60 + s


def _proxy_thumbnail(url: str) -> str:
    """将外部图片URL转为本地代理URL，解决B站防盗链"""
    if not url:
        return ""
    return f"/api/thumbnail?url={urllib.parse.quote(url, safe='')}"


def _parse_view_count(raw: str) -> float:
    """解析'12.3万'格式为数字"""
    if not raw:
        return 0
    raw = str(raw).strip()
    if "万" in raw:
        return float(raw.replace("万", "")) * 10000
    try:
        return float(raw)
    except ValueError:
        return 0


def _video_score(v: dict) -> float:
    """视频质量综合评分（含时效性加权）"""
    views = v.get("views_raw", 0) or _parse_view_count(v.get("views", ""))
    danmaku = _parse_view_count(v.get("danmaku", ""))
    dur = v.get("duration_seconds", 0)
    published = v.get("published", 0)

    # 基础: 播放量 (log防止头部垄断)
    score = max(1, views) ** 0.4

    # 互动加成: 弹幕/播放比
    if views > 0 and danmaku > 0:
        engagement = min(danmaku / views * 1000, 10)
        score *= (1 + engagement * 0.5)

    # 时长加成: 中长视频加权（10-60分钟最佳）
    if 600 <= dur <= 3600:
        score *= 1.3
    elif dur > 3600:
        score *= 1.0

    # 时效性加权: 越新越高（24h内+200%, 3天内+150%, 7天内+100%, 14天内+50%）
    if isinstance(published, (int, float)) and published > 0:
        age_hours = (time.time() - published) / 3600
        if age_hours <= 24:
            score *= 3.0
        elif age_hours <= 72:
            score *= 2.5
        elif age_hours <= 168:
            score *= 2.0
        elif age_hours <= 336:
            score *= 1.5

    # 作者权重: 知名作者加成
    top_authors = {"TED", "TED-Ed", "TEDx Talks", "Kurzgesagt", "Veritasium", "CrashCourse", "PBS Space Time", "Mark Rober", "The Royal Institution", "Stanford Online"}
    if v.get("author", "") in top_authors:
        score *= 1.5

    return round(score, 1)


# ──────────────────────────────────────────────
#  B站 视频源
# ──────────────────────────────────────────────

# UA 轮换池 — 防 B站 API 限流
_BILIBILI_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


def _bilibili_headers() -> dict:
    return {
        "User-Agent": random.choice(_BILIBILI_USER_AGENTS),
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Origin": "https://www.bilibili.com",
    }


def _parse_bilibili_video(item: dict) -> dict:
    tid = item.get("tid", 0)
    dur_raw = item.get("duration", "")
    dur_sec = parse_duration(dur_raw)
    stat = item.get("stat", {})
    return {
        "id": f"bilibili_{item.get('aid', item.get('id', ''))}",
        "source": "bilibili",
        "title": item.get("title", ""),
        "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
        "thumbnail": _proxy_thumbnail(item.get("pic", "")),
        "author": item.get("owner", {}).get("name", ""),
        "duration": format_duration(dur_sec),
        "duration_seconds": dur_sec,
        "duration_badge": duration_badge(dur_sec),
        "views": format_count(stat.get("view", 0)),
        "views_raw": int(stat.get("view", 0) or 0),
        "danmaku": format_count(stat.get("danmaku", 0)),
        "likes": format_count(stat.get("like", 0)),
        "likes_raw": int(stat.get("like", 0) or 0),
        "category": BILIBILI_CATEGORIES.get(tid, _guess_category(tid)),
        "description": (item.get("desc", "") or "")[:300],
        "published": item.get("pubdate", 0),
        "published_str": datetime.fromtimestamp(item.get("pubdate", 0)).strftime("%Y-%m-%d") if item.get("pubdate", 0) else "",
        "embed_id": item.get("bvid", ""),
        "embed_src": "bilibili",
        "summary": None,
        "favorited": False,
    }


def _guess_category(tid: int) -> str:
    """对未映射的 tid 猜一个合理的分类名"""
    guesses = {
        1: "动画", 13: "番剧", 167: "国创", 3: "音乐", 129: "舞蹈",
        4: "游戏", 5: "娱乐", 119: "鬼畜", 155: "时尚", 160: "生活",
        165: "广告", 166: "搞笑", 181: "影视",
    }
    return guesses.get(tid, f"分区{tid}")


def _fetch_bilibili_ranking(rid: int, rank_type: str) -> list[dict]:
    """获取单个 B站分区的排行榜，SSL 错误自动重试一次"""
    for attempt in range(2):
        try:
            resp = requests.get(
                "https://api.bilibili.com/x/web-interface/ranking/v2",
                params={"rid": rid, "type": rank_type},
                headers=_bilibili_headers(),
                timeout=15,
            )
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("list", [])
            return []
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            if attempt == 0:
                time.sleep(1 + random.random() * 2)  # 1-3s jitter
                continue
            app.logger.warning(f"B站分区 {rid} {rank_type}榜 SSL 重试后仍失败: {e}")
        except Exception as e:
            app.logger.error(f"B站分区 {rid} {rank_type}榜失败: {e}")
            break
    return []


def fetch_bilibili_videos(category_id: int | None = None) -> list[dict]:
    """获取 B站教育类视频（热门 + 并发分区排行榜）"""
    videos = []
    seen_ids = set()

    def add_video(item):
        vid = item.get("aid", item.get("id", ""))
        if vid not in seen_ids:
            seen_ids.add(vid)
            v = _parse_bilibili_video(item)
            if v["category"] in ("动画", "番剧", "游戏", "娱乐", "鬼畜", "搞笑"):
                return
            if v["duration_seconds"] < MIN_DURATION_SECONDS:
                return
            videos.append(v)

    # 1) 热门榜（单次请求）
    try:
        url = "https://api.bilibili.com/x/web-interface/popular"
        resp = requests.get(url, params={"ps": 50, "pn": 1}, headers=_bilibili_headers(), timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            for item in data.get("data", {}).get("list", []):
                tid = item.get("tid", 0)
                if category_id and tid != category_id:
                    continue
                if tid in BILIBILI_CATEGORIES:
                    add_video(item)
    except Exception as e:
        app.logger.error(f"B站热门 API 失败: {e}")

    # 2) 并发拉取各分区周榜 + 日榜
    cats_to_fetch = [category_id] if category_id else [k for k in BILIBILI_CATEGORIES if k < 200]
    tasks = []
    for cid in cats_to_fetch[:12]:
        tasks.append((cid, "weekly"))
    for cid in cats_to_fetch[:6]:
        tasks.append((cid, "daily"))

    if tasks:
        with ThreadPoolExecutor(max_workers=BILIBILI_MAX_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_bilibili_ranking, cid, rank_type): (cid, rank_type)
                for cid, rank_type in tasks
            }
            for future in as_completed(futures):
                cid, rank_type = futures[future]
                try:
                    items = future.result()
                    limit = 6 if rank_type == "weekly" else 3
                    for item in items[:limit]:
                        add_video(item)
                except Exception as e:
                    app.logger.error(f"B站分区 {cid} {rank_type}榜失败: {e}")

    videos.sort(key=lambda v: v.get("published", 0), reverse=True)
    return videos


def format_count(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


# ──────────────────────────────────────────────
#  YouTube 视频源 (并发请求)
# ──────────────────────────────────────────────

def _fetch_youtube_channel_rss(channel: dict) -> list[dict]:
    """获取单个 YouTube 频道的 RSS 视频"""
    videos = []
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['id']}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(rss_url, headers=headers, timeout=YOUTUBE_TIMEOUT)
        if resp.status_code != 200:
            app.logger.warning(f"YouTube RSS HTTP {resp.status_code} ({channel['name']})")
            return videos
        text = resp.text
        # 清理非法 XML 字符
        text = re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\u10000-\u10FFFF]", "", text)
        # XML 只支持5种实体，替换掉其他 HTML 实体
        text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)\w+;", " ", text)
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            app.logger.debug(f"YouTube RSS XML parse failed for {channel['name']}, trying permissive mode")
            # 最后手段：正则直接提取数据
            videos = _parse_youtube_rss_regex(resp.text, channel)
            return videos
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "media": "http://search.yahoo.com/mrss/",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        for entry in root.findall("atom:entry", ns)[:4]:
            vid_el = entry.find("atom:id", ns)
            video_id = vid_el.text.split(":")[-1] if vid_el is not None else ""
            title_el = entry.find("atom:title", ns)
            pub_el = entry.find("atom:published", ns)
            pub_ts = 0
            if pub_el is not None and pub_el.text:
                try:
                    pub_ts = int(datetime.fromisoformat(pub_el.text.replace("Z", "+00:00")).timestamp())
                except Exception:
                    pass
            media_group = entry.find("media:group", ns)
            thumbnail = ""
            description = ""
            dur_sec = 0
            if media_group is not None:
                thumb = media_group.find("media:thumbnail", ns)
                if thumb is not None:
                    thumbnail = thumb.get("url", "")
                desc = media_group.find("media:description", ns)
                if desc is not None and desc.text:
                    description = strip_html(desc.text)[:300]
                # YouTube 时长：优先 yt:duration，回退 media:content/@duration
                yt_dur = media_group.find("yt:duration", ns)
                if yt_dur is not None and yt_dur.text:
                    dur_sec = int(yt_dur.text)
                else:
                    dur_el = media_group.find("media:content", ns)
                    if dur_el is not None:
                        dur_sec = int(dur_el.get("duration", 0) or 0)
                # 记录调试信息（仅首次）
                if dur_sec == 0:
                    pass  # YouTube RSS 不提供时长是正常的

            # RSS 无时长时，查缓存
            if dur_sec == 0 and video_id:
                dur_sec = _get_cached_duration(video_id)
            # 过滤短视频（仅当有时长数据时）
            if dur_sec > 0 and dur_sec < MIN_DURATION_SECONDS:
                continue
            # 无时长无缓存 — 放行但标记"时长未知"

            videos.append({
                "id": f"youtube_{video_id}",
                "source": "youtube",
                "title": title_el.text if title_el is not None else "",
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": thumbnail,
                "author": channel["name"],
                "duration": format_duration(dur_sec),
                "duration_seconds": dur_sec,
                "duration_badge": duration_badge(dur_sec) if dur_sec else "",
                "views": "",
                "views_raw": 0,
                "danmaku": "",
                "likes": "",
                "likes_raw": 0,
                "category": "教育",
                "description": description,
                "published": pub_ts,
                "published_str": datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d") if pub_ts else "",
                "embed_id": video_id,
                "embed_src": "youtube",
                "summary": None,
                "favorited": False,
            })
    except Exception as e:
        app.logger.error(f"YouTube RSS 失败 ({channel['name']}): {e}")
    else:
        if videos:
            app.logger.debug(f"YouTube RSS [{channel['name']}]: {len(videos)} 个视频")
    return videos


def fetch_youtube_videos_rss() -> list[dict]:
    """并发获取所有 YouTube 频道 RSS"""
    videos = []
    with ThreadPoolExecutor(max_workers=YOUTUBE_MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_youtube_channel_rss, ch): ch for ch in YOUTUBE_EDUCATION_CHANNELS}
        for future in as_completed(futures):
            try:
                videos.extend(future.result())
            except Exception:
                pass
    return videos


def _parse_youtube_rss_regex(text: str, channel: dict) -> list[dict]:
    """正则方式解析 YouTube RSS（XML 解析失败时的 fallback）"""
    import re as re_mod
    videos = []
    text = re_mod.sub(r"<!\s*\[CDATA\[(.*?)\]\s*\]>", r"\1", text)
    entries = re_mod.findall(r"<(?:atom:)?entry[^>]*>(.*?)</(?:atom:)?entry>", text, re_mod.DOTALL)
    # 如果带命名空间的 entry 没匹配到，尝试不带命名空间
    if not entries:
        entries = re_mod.findall(r"<entry[^>]*>(.*?)</entry>", text, re_mod.DOTALL)
    for entry in entries[:4]:
        vid_match = re_mod.search(r"(?:yt:)?videoId[^>]*>\s*([^<\s]+)", entry)
        if not vid_match:
            vid_match = re_mod.search(r"<id[^>]*>[^:]*:(\w+)\s*<", entry)
        title_match = re_mod.search(r"<(?:media:)?title[^>]*>(.+?)</(?:media:)?title>", entry)
        thumb_match = re_mod.search(r'url\s*=\s*"((?:https?:)?//[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', entry)
        desc_match = re_mod.search(r"<media:description[^>]*>(.*?)</media:description>", entry)
        pub_match = re_mod.search(r"<published>([^<]+)</published>", entry)

        video_id = vid_match.group(1) if vid_match else ""
        title_str = title_match.group(1).strip() if title_match else ""
        if not video_id or not title_str:
            continue
        # 查缓存的时长
        dur_cached = _get_cached_duration(video_id)
        pub_ts = 0
        if pub_match:
            try:
                pub_ts = int(datetime.fromisoformat(pub_match.group(1).replace("Z", "+00:00")).timestamp())
            except Exception:
                pass

        videos.append({
            "id": f"youtube_{video_id}",
            "source": "youtube",
            "title": title_str,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "thumbnail": (thumb_match.group(1) if thumb_match else ""),
            "author": channel["name"],
            "duration": format_duration(dur_cached),
            "duration_seconds": dur_cached,
            "duration_badge": duration_badge(dur_cached) if dur_cached else "",
            "views": "", "views_raw": 0,
            "danmaku": "", "likes": "", "likes_raw": 0,
            "category": "教育",
            "description": (desc_match.group(1).strip() if desc_match else "")[:300],
            "published": pub_ts,
            "published_str": datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d") if pub_ts else "",
            "embed_id": video_id,
            "embed_src": "youtube",
            "summary": None,
            "favorited": False,
        })
    app.logger.debug(f"YouTube regex fallback for {channel['name']}: extracted {len(videos)} videos")
    return videos


def _get_uploads_playlist_id(channel_id: str) -> str:
    """频道ID → 上传列表ID (UCxxx → UUxxx, 无需API)"""
    if channel_id.startswith("UC"):
        return "UU" + channel_id[2:]
    return channel_id


def _fetch_youtube_channel_search(channel: dict) -> list[dict]:
    """获取单个 YouTube 频道的最新视频 (playlistItems优先, 失败降级search)"""
    ck = cache_key("yt_search", channel["id"])
    if cached := cache_get_with_ttl(ck, 3600):
        return cached.get("videos", [])

    videos = []
    playlist_id = _get_uploads_playlist_id(channel["id"])
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 5,
                "key": YOUTUBE_API_KEY,
            },
            timeout=YOUTUBE_TIMEOUT,
        )
        data = resp.json()
        if "error" in data or data.get("items") is None:
            # playlistItems 失败, 降级到 search (仅1单位→100单位, 但能兜底)
            app.logger.debug(f"YouTube [{channel['name']}]: playlistItems 失败, 降级 search")
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "channelId": channel["id"],
                    "maxResults": 3,
                    "order": "date",
                    "type": "video",
                    "key": YOUTUBE_API_KEY,
                },
                timeout=YOUTUBE_TIMEOUT,
            )
            data = resp.json()
        if "error" in data:
            err = data["error"]
            msg = err.get("message", str(err))
            app.logger.error(f"YouTube API 错误 ({channel['name']}): HTTP {resp.status_code} — {msg}")
            return videos
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            vid = snippet.get("resourceId", {}).get("videoId", "") or item.get("id", {}).get("videoId", "")
            if not vid:
                continue
            pub_ts = 0
            pub_str = snippet.get("publishedAt", "")
            if pub_str:
                try:
                    pub_ts = int(datetime.fromisoformat(pub_str.replace("Z", "+00:00")).timestamp())
                except Exception:
                    pass
            videos.append({
                "id": f"youtube_{vid}",
                "youtube_id": vid,
                "source": "youtube",
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "author": snippet.get("channelTitle", ""),
                "duration": "",
                "duration_seconds": 0,
                "duration_badge": "",
                "views": "",
                "views_raw": 0,
                "danmaku": "",
                "likes": "",
                "likes_raw": 0,
                "category": "教育",
                "description": strip_html(snippet.get("description", "") or "")[:300],
                "published": pub_ts,
                "published_str": datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d") if pub_ts else "",
                "embed_id": vid,
                "embed_src": "youtube",
                "summary": None,
                "favorited": False,
            })
    except Exception as e:
        app.logger.error(f"YouTube 搜索失败 ({channel['name']}): {e}")
    else:
        cache_set(ck, {"videos": videos})
    return videos


def _enrich_youtube_videos(videos: list[dict]) -> list[dict]:
    """批量获取 YouTube 视频详情，补充时长和播放量"""
    if not videos:
        return videos
    video_ids = [v["youtube_id"] for v in videos if v.get("youtube_id")]
    if not video_ids:
        return videos

    details_map = {}
    for i in range(0, len(video_ids), 50):
        batch_ids = video_ids[i:i + 50]
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "contentDetails,statistics",
                    "id": ",".join(batch_ids),
                    "key": YOUTUBE_API_KEY,
                },
                timeout=YOUTUBE_TIMEOUT,
            )
            data = resp.json()
            if "error" in data:
                err = data["error"]
                msg = err.get("message", str(err))
                app.logger.error(f"YouTube Videos API 错误: HTTP {resp.status_code} — {msg}")
                continue
            for item in data.get("items", []):
                vid = item.get("id", "")
                duration_iso = item.get("contentDetails", {}).get("duration", "")
                dur_sec = parse_iso8601_duration(duration_iso)
                view_count = int(item.get("statistics", {}).get("viewCount", 0) or 0)
                details_map[vid] = {
                    "duration": format_duration(dur_sec),
                    "duration_seconds": dur_sec,
                    "duration_badge": duration_badge(dur_sec),
                    "views": format_count(view_count) if view_count else "",
                    "views_raw": view_count,
                }
        except Exception as e:
            app.logger.error(f"YouTube 视频详情获取失败: {e}")

    for v in videos:
        vid = v.get("youtube_id", "")
        if vid in details_map:
            v.update(details_map[vid])
            _set_cached_duration(vid, details_map[vid]["duration_seconds"])
        else:
            cached_dur = _get_cached_duration(vid)
            if cached_dur > 0:
                v["duration"] = format_duration(cached_dur)
                v["duration_seconds"] = cached_dur
                v["duration_badge"] = duration_badge(cached_dur)

    return videos


def fetch_youtube_videos_api() -> list[dict]:
    """YouTube Data API v3 (需要 API Key) — 并发搜索 + 批量详情"""
    if not YOUTUBE_API_KEY:
        return []
    all_videos = []

    # 并发搜索所有频道
    with ThreadPoolExecutor(max_workers=YOUTUBE_MAX_WORKERS_API) as executor:
        futures = {executor.submit(_fetch_youtube_channel_search, ch): ch for ch in YOUTUBE_EDUCATION_CHANNELS}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    ch = futures[future]
                    app.logger.debug(f"YouTube API [{ch['name']}]: {len(result)} 个视频")
                all_videos.extend(result)
            except Exception:
                pass

    app.logger.info(f"YouTube API 搜索完成: 共 {len(all_videos)} 个视频")

    if all_videos:
        all_videos = _enrich_youtube_videos(all_videos)

        # 过滤短视频
        all_videos = [
            v for v in all_videos
            if v.get("duration_seconds", 0) == 0 or v["duration_seconds"] >= MIN_DURATION_SECONDS
        ]
        app.logger.info(f"YouTube API 过滤后: {len(all_videos)} 个视频")

    return all_videos


def fetch_youtube_videos() -> list[dict]:
    """YouTube 视频获取入口"""
    if YOUTUBE_API_KEY:
        videos = fetch_youtube_videos_api()
        if videos:
            app.logger.info(f"YouTube: 使用 API 模式 — {len(videos)} 个视频")
            return videos
        app.logger.warning("YouTube API 无结果，回退到 RSS 模式")
    return fetch_youtube_videos_rss()


# ──────────────────────────────────────────────
#  AI 摘要引擎
# ──────────────────────────────────────────────

def generate_summary(video: dict) -> str | None:
    if not DEEPSEEK_API_KEY:
        return None
    ck = cache_key("summary", video["source"], video["id"])
    if cached := cache_get_with_ttl(ck, SUMMARY_CACHE_TTL):
        return cached.get("summary")

    title = video.get("title", "")
    description = video.get("description", "")
    author = video.get("author", "")
    if not title:
        return None

    prompt = f"""请为以下视频生成一个简洁的中文摘要（100-200字），帮助用户判断是否值得观看。

视频标题：{title}
视频作者：{author}
视频简介：{description[:500] if description else '无'}

要求：
1. 用2-3句话概括视频可能涉及的核心内容
2. 标注视频的深度级别（入门/进阶/专业）
3. 推荐观看人群（如：适合XX领域学习者）
4. 语言简洁有力，避免套话

请直接输出摘要，不要加"摘要："等前缀。"""

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 250, "temperature": 0.5},
            timeout=30,
        )
        data = resp.json()
        summary = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if summary:
            cache_set(ck, {"summary": summary})
            return summary
    except Exception as e:
        app.logger.error(f"DeepSeek 摘要失败: {e}")
    return None


def generate_summaries_parallel(videos: list[dict]) -> None:
    """并行生成多个视频的 AI 摘要"""
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(generate_summary, v): i for i, v in enumerate(videos)}
        for future in as_completed(futures):
            i = futures[future]
            try:
                videos[i]["summary"] = future.result()
            except Exception:
                pass


def _time_distribution(videos: list[dict]) -> dict:
    """统计视频时间分布"""
    now = time.time()
    today = 0
    week = 0
    month = 0
    older = 0
    for v in videos:
        pub = v.get("published", 0)
        if not pub:
            continue
        age_hours = (now - pub) / 3600
        if age_hours <= 24:
            today += 1
        elif age_hours <= 168:
            week += 1
        elif age_hours <= 720:
            month += 1
        else:
            older += 1
    return {"today": today, "week": week, "month": month, "older": older}


# ──────────────────────────────────────────────
#  字幕提取
# ──────────────────────────────────────────────

TRANSCRIPT_DIR = Path(CACHE_DIR) / "transcripts"
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def _get_transcript_cache_path(source: str, embed_id: str) -> Path:
    key = f"{source}_{embed_id}"
    return TRANSCRIPT_DIR / f"{cache_key(key)}.txt"


def fetch_youtube_transcript(video_id: str) -> str:
    """YouTube 字幕: 逐语言尝试，缓存结果（纯文本）"""
    result = _fetch_youtube_transcript_raw(video_id)
    return result["text"] if result else ""


def _fetch_youtube_transcript_raw(video_id: str) -> dict | None:
    """YouTube 字幕: 逐语言尝试，返回原始分段（text + segments）"""
    if not video_id:
        return None
    cache_path = _get_transcript_cache_path("youtube", video_id)
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"text": str(data), "segments": []}
        except (json.JSONDecodeError, OSError):
            pass

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=["zh-Hans", "zh", "en"])
        segments = [{"start": round(t.start, 1), "duration": round(t.duration, 1), "original": t.text} for t in transcript if t.text]
        text = " ".join(t["original"] for t in segments)
        text = " ".join(text.split())
        data = {"text": text[:4000], "segments": segments[:200]}
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except Exception:
        app.logger.debug(f"YouTube 字幕获取失败: {video_id}")
        return None


def fetch_bilibili_transcript(bvid: str) -> str:
    """B站字幕: 纯文本"""
    data = _fetch_bilibili_transcript_raw(bvid)
    return data["text"] if data else ""


def _fetch_bilibili_transcript_raw(bvid: str) -> dict | None:
    """B站字幕: 返回带时间戳的分段数据"""
    if not bvid:
        return None
    cache_path = _get_transcript_cache_path("bilibili", bvid)
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {"text": str(data), "segments": []}
        except (json.JSONDecodeError, OSError):
            pass

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid}, headers=headers, timeout=10,
        )
        data = resp.json()
        subtitles = data.get("data", {}).get("subtitle", {}).get("list", [])
        if not subtitles:
            return None
        sub_url = subtitles[0].get("subtitle_url", "")
        if not sub_url:
            return None
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        sub_resp = requests.get(sub_url, headers=headers, timeout=10)
        sub_data = sub_resp.json()
        segments = []
        lines = []
        for item in sub_data.get("body", []):
            content = item.get("content", "")
            if content:
                segments.append({
                    "start": round(float(item.get("from", 0)), 1),
                    "duration": round(float(item.get("to", 0)) - float(item.get("from", 0)), 1),
                    "original": content,
                })
                lines.append(content)
        text = " ".join(lines)
        text = " ".join(text.split())
        result = {"text": text[:4000], "segments": segments[:200]}
        cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result
    except Exception:
        app.logger.debug(f"B站字幕获取失败: {bvid}")
        return None


def get_transcript_for_video(video: dict) -> str:
    """统一入口 — 纯文本"""
    embed_id = video.get("embed_id", "") or video.get("youtube_id", "")
    source = video.get("source", "")
    if source == "youtube":
        return fetch_youtube_transcript(embed_id)
    if source == "bilibili":
        return fetch_bilibili_transcript(embed_id)
    return ""


def get_transcript_timed(video: dict) -> dict | None:
    """统一入口 — 带时间戳分段"""
    embed_id = video.get("embed_id", "") or video.get("youtube_id", "")
    source = video.get("source", "")
    if source == "youtube":
        return _fetch_youtube_transcript_raw(embed_id)
    if source == "bilibili":
        return _fetch_bilibili_transcript_raw(embed_id)
    return None


# ──────────────────────────────────────────────
#  API 路由
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "deepseek": bool(DEEPSEEK_API_KEY), "youtube_key": bool(YOUTUBE_API_KEY)})


@app.route("/api/thumbnail")
def api_thumbnail():
    """代理外部图片，解决B站防盗链"""
    url = request.args.get("url", "")
    if not url:
        return "", 400
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        return Response(resp.content, mimetype=resp.headers.get("Content-Type", "image/jpeg"))
    except Exception:
        return "", 500


@app.route("/api/analyze")
def api_analyze():
    """深度分析视频内容 — 结构化输出 + 时间线"""
    title = request.args.get("title", "")
    description = request.args.get("description", "")
    author = request.args.get("author", "")
    category = request.args.get("category", "")
    duration = request.args.get("duration", "")
    duration_sec = int(request.args.get("duration_sec", 0) or 0)
    dur_min = duration_sec // 60 if duration_sec else 0
    subtitle_text = request.args.get("subtitle_text", "")[:3000]

    if not title or not DEEPSEEK_API_KEY:
        return jsonify({"error": "缺少标题或API未配置"}), 400

    ck = cache_key("analyze", title[:80])
    if cached := cache_get_with_ttl(ck, SUMMARY_CACHE_TTL * 2):
        return jsonify(cached)

    timeline_hint = ""
    if dur_min > 0:
        seg_count = min(5, max(2, dur_min // 5))
        seg_interval = dur_min // seg_count
        timeline_hint = f"请根据字幕定位真实时间节点（共{seg_count}个），例如 00:00-{seg_interval:02d}:00 ..."

    subtitle_context = ""
    if subtitle_text:
        subtitle_context = f"【视频字幕节选】\n{subtitle_text}\n\n"

    prompt = f"""你是专业内容策展人。{subtitle_context}请基于以上信息做深度观前分析，帮助观众在观看前了解内容。

【视频信息】
标题：{title}
作者：{author}
分类：{category}
时长：{duration}
简介：{description[:600] if description else '无'}

请严格用以下结构输出（Markdown格式）：

## 内容概要
（3-4句话精炼概括本期内容，让观众10秒内了解主题）

## 核心知识点
- 知识1：详细说明 + 相关背景（有字幕则基于字幕深入展开）
- 知识2：详细说明 + 相关背景
- 知识3：详细说明 + 相关背景
（列举3-5个核心知识点，每个都要结合字幕具体内容展开）

## 关键术语
- **术语1** (英文原文): 一句话解释
- **术语2** (英文原文): 一句话解释
（提取视频中出现的专业术语、人名、地名等，附英文原文和简洁解释）

## 背景补充
（补充与主题相关的历史背景、前沿进展或关联知识，帮助理解视频语境）

## 观看建议
- 知识密度：⭐1-5星
- 适看人群：（具体描述）
- 一句话建议：（是否值得看，为什么）"""

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1500, "temperature": 0.3},
            timeout=45,
        )
        data = resp.json()
        analysis = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if analysis:
            result = {"analysis": analysis, "cached": False}
            cache_set(ck, result)
            return jsonify(result)
    except Exception as e:
        app.logger.error(f"深度分析失败: {e}")

    return jsonify({"error": "分析生成失败"}), 500


@app.route("/api/videos")
def api_videos():
    source = request.args.get("source", "all")
    category = request.args.get("category", "")
    page = max(1, int(request.args.get("page", 1)))
    with_summary = request.args.get("with_summary", "false").lower() == "true"
    search = request.args.get("search", "").strip()
    prefs = request.args.get("prefs", "")  # 逗号分隔的偏好分类
    essence = request.args.get("essence", "false").lower() == "true"
    sort = request.args.get("sort", "")
    following = request.args.get("following", "")  # 逗号分隔的关注作者
    _sort_explicit = request.args.get("sort") is not None

    # B站默认按时间排序（推新），YouTube/全部默认综合评分（发现优质）
    if not sort:
        sort = "time" if source in ("bilibili",) else "score"

    # 视频列表短期缓存键
    list_ck = cache_key("videos", source, category, str(page), search[:20], sort)

    # 偏好分类解析（提前，供缓存过滤使用）
    preferred_cats = [p.strip() for p in prefs.split(",") if p.strip()]

    # 缓存策略: 短期(30min)优先, 预热(24h)兜底, prefs/essence时缩短预热有效期
    if not with_summary and not search:
        # 1) 短期缓存 (无偏好/无精华时)
        if not prefs and not essence and not following:
            if cached := cache_get_with_ttl(list_ck, VIDEO_LIST_CACHE_TTL):
                return jsonify(cached)
        # 2) 预热缓存 (最多4h有效, 避免整天看旧数据)
        warmup_ttl = 14400 if (prefs or essence) else 86400  # 4h有偏好, 24h无偏好
        if warmup_cached := cache_get_with_ttl(list_ck, warmup_ttl):
            videos = warmup_cached.get("videos", [])
            total = warmup_cached.get("total", len(videos))
            if preferred_cats:
                for v in videos:
                    if v["category"] in preferred_cats:
                        v["score"] = v.get("score", 10) * 2.0
                    elif any(pc in v.get("description", "") or pc in v["title"] for pc in preferred_cats):
                        v["score"] = v.get("score", 10) * 1.5
            if essence:
                videos.sort(key=lambda v: (v.get("score", 0), v.get("published", 0)), reverse=True)
                videos = videos[: max(12, len(videos) // 2)]
                total = len(videos)
            videos = videos[:VIDEOS_PER_PAGE]
            result = {
                "videos": videos, "total": total, "page": page,
                "per_page": VIDEOS_PER_PAGE, "has_more": total > VIDEOS_PER_PAGE,
                "categories": BILIBILI_CATEGORY_LABELS, "search": None, "cached": True,
            }
            return jsonify(result)

    all_videos = []

    if source in ("bilibili", "all"):
        cat_id = None
        if category:
            cat_id = next((k for k, v in BILIBILI_CATEGORIES.items() if v == category), None)
        all_videos.extend(fetch_bilibili_videos(cat_id))

    if source in ("youtube", "all"):
        all_videos.extend(fetch_youtube_videos())

    # 搜索过滤
    if search:
        q = search.lower()
        all_videos = [
            v for v in all_videos
            if q in v["title"].lower() or q in v.get("description", "").lower() or q in v["author"].lower()
        ]

    # 视频质量评分
    for v in all_videos:
        v["score"] = _video_score(v)

    # 偏好加权
    if preferred_cats:
        for v in all_videos:
            if v["category"] in preferred_cats:
                v["score"] *= 2.0
            elif any(pc in v.get("description", "") or pc in v["title"] for pc in preferred_cats):
                v["score"] *= 1.5

    # 关注频道加权：提升但不绕过审核
    following_authors = [f.strip() for f in following.split(",") if f.strip()]
    if following_authors:
        for v in all_videos:
            if v.get("author", "") in following_authors:
                v["score"] *= 2.5

    # 精华模式: 只保留前 50%
    if essence:
        all_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)
        all_videos = all_videos[: max(12, len(all_videos) // 2)]

    # 排序
    if sort == "time":
        all_videos.sort(key=lambda v: v.get("published", 0), reverse=True)
    elif sort == "views":
        all_videos.sort(key=lambda v: v.get("views_raw", 0), reverse=True)
    elif sort == "likes":
        all_videos.sort(key=lambda v: v.get("likes_raw", 0), reverse=True)
    else:
        all_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)

    # 分页
    total = len(all_videos)
    start = (page - 1) * VIDEOS_PER_PAGE
    end = start + VIDEOS_PER_PAGE
    paged = all_videos[start:end]

    # 并行 AI 摘要
    if with_summary and DEEPSEEK_API_KEY:
        generate_summaries_parallel(paged)

    result = {
        "videos": paged,
        "total": total,
        "page": page,
        "per_page": VIDEOS_PER_PAGE,
        "has_more": end < total,
        "categories": BILIBILI_CATEGORY_LABELS,
        "search": search if search else None,
        "sort": sort,
        "time_distribution": _time_distribution(all_videos),
    }

    # 缓存非摘要非搜索非偏好非精华非自定义排序的结果
    if not with_summary and not search and not prefs and not essence and sort == "score":
        cache_set(list_ck, result)

    return jsonify(result)


@app.route("/api/summarize")
def api_summarize():
    video_id = request.args.get("video_id", "")
    source = request.args.get("source", "")
    title = request.args.get("title", "")
    description = request.args.get("description", "")
    author = request.args.get("author", "")

    if not title and not video_id:
        return jsonify({"error": "缺少视频信息"}), 400

    ck = cache_key("summary", source, video_id)
    if cached := cache_get_with_ttl(ck, SUMMARY_CACHE_TTL):
        return jsonify({"summary": cached.get("summary"), "cached": True})

    summary = generate_summary({"id": video_id, "source": source, "title": title, "description": description, "author": author})
    if summary:
        return jsonify({"summary": summary, "cached": False})
    return jsonify({"error": "摘要生成失败"}), 500


@app.route("/api/categories")
def api_categories():
    return jsonify({"bilibili": BILIBILI_CATEGORY_LABELS, "youtube": ["教育", "科技"]})


@app.route("/api/transcript")
def api_transcript():
    source = request.args.get("source", "")
    embed_id = request.args.get("embed_id", "")
    timed = request.args.get("timed", "false").lower() == "true"
    if not embed_id:
        return jsonify({"text": "", "segments": []})
    video = {"source": source, "embed_id": embed_id}
    if timed:
        data = get_transcript_timed(video)
        return jsonify({"text": data["text"] if data else "", "segments": data["segments"] if data else []})
    text = get_transcript_for_video(video)
    return jsonify({"text": text, "segments": []})


@app.route("/api/translate")
def api_translate():
    """翻译视频字幕为中文，并返回时间轴分段数据"""
    video_id = request.args.get("video_id", "")
    source = request.args.get("source", "")
    embed_id = request.args.get("embed_id", "")
    if not video_id and not embed_id:
        return jsonify({"error": "缺少视频信息"}), 400
    if not DEEPSEEK_API_KEY:
        return jsonify({"error": "DeepSeek API 未配置"}), 400

    video = {"source": source, "embed_id": embed_id or video_id}

    # 获取带时间戳的分段字幕
    timed_data = get_transcript_timed(video)
    if not timed_data or not timed_data.get("segments"):
        return jsonify({"translation": "", "segments": [], "error": "无法获取字幕"})

    segments = timed_data.get("segments", [])
    raw_text = timed_data.get("text", "")

    # B站字幕通常是中文, 直接返回分段, 无需调用DeepSeek翻译
    if source == "bilibili":
        return jsonify({
            "translation": raw_text[:2000],
            "segments": segments[:300],
            "cached": True,
        })

    ck = cache_key("translate", source, video_id or embed_id)
    if cached := cache_get_with_ttl(ck, SUMMARY_CACHE_TTL):
        return jsonify({
            "translation": cached.get("translation", ""),
            "segments": segments,
            "cached": True,
        })

    # 分段翻译
    chunk_size = 2500
    chunks = [raw_text[i:i + chunk_size] for i in range(0, len(raw_text), chunk_size)]
    translations = []

    for idx, chunk in enumerate(chunks[:6]):
        chunk_prompt = f"将以下英文视频字幕翻译为简体中文。要求：自然流畅，保留原意，适合阅读。直接输出译文，不要说明。\n\n{chunk}" if idx == 0 else f"继续翻译（第{idx+1}段/接上文）：\n\n{chunk}"
        try:
            resp = requests.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": chunk_prompt}], "max_tokens": 1000, "temperature": 0.3},
                timeout=45,
            )
            data = resp.json()
            translation = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if translation:
                translations.append(translation)
        except Exception as e:
            app.logger.error(f"翻译失败 (段 {idx+1}): {e}")

    full_translation = "\n\n".join(translations)
    if full_translation:
        cache_set(ck, {"translation": full_translation})
        return jsonify({
            "translation": full_translation,
            "segments": segments[:300],  # 完整覆盖视频
            "cached": False,
        })
    return jsonify({"translation": "", "segments": [], "error": "翻译生成失败"}), 500


# ──────────────────────────────────────────────
#  视频笔记 API
# ──────────────────────────────────────────────

NOTES_CACHE_DIR = Path(CACHE_DIR) / "notes"
NOTES_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _notes_json_path(video_id: str) -> Path:
    return NOTES_CACHE_DIR / f"{cache_key(video_id)}.json"


def _load_notes(video_id: str) -> dict:
    p = _notes_json_path(video_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_notes(video_id: str, data: dict) -> None:
    data["updated_at"] = datetime.now().isoformat()
    p = _notes_json_path(video_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@app.route("/api/notes/<path:video_id>")
def api_load_notes(video_id):
    notes = _load_notes(video_id)
    if not notes:
        return jsonify({"video_id": video_id, "notes": "", "ai_summary": "", "chat_history": [], "exported": False})
    return jsonify(notes)


@app.route("/api/notes/save", methods=["POST"])
def api_save_notes():
    data = request.get_json(force=True)
    video_id = data.get("video_id", "")
    if not video_id:
        return jsonify({"error": "缺少 video_id"}), 400
    existing = _load_notes(video_id)
    existing.update(data)
    _save_notes(video_id, existing)
    return jsonify({"status": "ok", "video_id": video_id})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True)
    message = data.get("message", "").strip()
    title = data.get("title", "")
    description = data.get("description", "")
    author = data.get("author", "")
    subtitle_text = data.get("subtitle_text", "")[:2500]
    chat_history = data.get("chat_history", [])

    if not message or not title or not DEEPSEEK_API_KEY:
        return jsonify({"error": "缺少必要信息或API未配置"}), 400

    context_lines = [f"视频标题：{title}"]
    if author:
        context_lines.append(f"视频作者：{author}")
    if description:
        context_lines.append(f"视频简介：{description[:400]}")
    if subtitle_text:
        context_lines.append(f"视频字幕节选：\n{subtitle_text}")
    video_context = "\n".join(context_lines)

    messages = [
        {"role": "system", "content": f"你是一个视频学习助手。用户正在观看以下视频，请根据视频主题回答用户问题，回答要简洁、有深度。\n\n{video_context}"},
    ]

    for h in chat_history[-6:]:
        messages.append(h)

    messages.append({"role": "user", "content": message})

    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": messages, "max_tokens": 400, "temperature": 0.5},
            timeout=40,
        )
        resp_data = resp.json()
        reply = resp_data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if reply:
            return jsonify({"reply": reply})
    except Exception as e:
        app.logger.error(f"AI 对话失败: {e}")

    return jsonify({"error": "对话生成失败"}), 500


@app.route("/api/notes/export", methods=["POST"])
def api_export_notes():
    data = request.get_json(force=True)
    video_id = data.get("video_id", "")
    if not video_id:
        return jsonify({"error": "缺少 video_id"}), 400

    existing = _load_notes(video_id)

    title = data.get("title", existing.get("title", ""))
    author = data.get("author", existing.get("author", ""))
    url = data.get("url", existing.get("url", ""))
    source = data.get("source", existing.get("source", ""))
    category = data.get("category", existing.get("category", ""))
    notes = data.get("notes", existing.get("notes", ""))
    ai_summary = existing.get("ai_summary", "")
    chat_history = existing.get("chat_history", [])
    viewed_at = existing.get("viewed_at", [])

    source_label = "B站" if source == "bilibili" else "YouTube" if source == "youtube" else source
    export_dir = Path(os.path.expanduser(NOTES_EXPORT_DIR)) / source_label
    export_dir.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:80]
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}_{safe_title}.md"
    filepath = export_dir / filename

    chat_section = ""
    if chat_history:
        chat_lines = ["## AI 对话记录\n"]
        for h in chat_history:
            role_tag = "### 💬 问" if h["role"] == "user" else "### 🤖 答"
            chat_lines.append(f"{role_tag}\n\n{h['content']}\n")
        chat_section = "\n".join(chat_lines)

    md_content = f"""# {title}

- **来源**: {source_label}
- **作者**: {author}
- **分类**: {category}
- **链接**: {url}
- **观看时间**: {', '.join(viewed_at) if viewed_at else date_str}
- **导出时间**: {datetime.now().strftime("%Y-%m-%d %H:%M")}

---

## AI 摘要

{ai_summary or '暂无 AI 摘要，可先保存笔记后查看。'}

---

## 我的笔记

{notes or '暂无笔记'}

---

{chat_section}
"""

    filepath.write_text(md_content, encoding="utf-8")

    existing["exported"] = True
    existing["export_path"] = str(filepath)
    _save_notes(video_id, existing)

    return jsonify({"status": "ok", "path": str(filepath)})


@app.route("/api/notes/list")
def api_notes_list():
    files = sorted(NOTES_CACHE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files[:50]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "video_id": d.get("video_id", ""),
                "title": d.get("title", ""),
                "author": d.get("author", ""),
                "source": d.get("source", ""),
                "category": d.get("category", ""),
                "url": d.get("url", ""),
                "exported": d.get("exported", False),
                "viewed_at": d.get("viewed_at", []),
            })
        except (json.JSONDecodeError, OSError):
            pass
    return jsonify(result)


if __name__ == "__main__":
    print("🎬 视频精选 Web 应用 v2 启动中...")
    print(f"   DeepSeek API: {'已配置' if DEEPSEEK_API_KEY else '未配置（摘要功能不可用）'}")
    print(f"   YouTube API: {'已配置' if YOUTUBE_API_KEY else '未配置（使用 RSS 并发模式）'}")
    app.run(host="0.0.0.0", port=8080, debug=True)
