"""
视频精选 Web 应用 — 配置文件
"""
import json
import os
from pathlib import Path

PROJECT_DIR = os.path.dirname(__file__)

# DeepSeek API (用于 AI 摘要和分析)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
except ImportError:
    pass
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-4bf5537df2a34695bf33162169b8cd82")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# YouTube Data API v3 (可选，不填则使用 RSS 模式)
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# DeepL Free API Key (可选, 免费50万字符/月, 不填则走DeepSeek翻译)
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")

# 缓存目录
CACHE_DIR = os.environ.get("VC_CACHE_DIR", os.path.join(PROJECT_DIR, "cache"))


# ──────────────────────────────────────────────
#  从 channels.json 加载频道和分类配置
# ──────────────────────────────────────────────

def _load_channels_config():
    channels_file = os.path.join(PROJECT_DIR, "channels.json")
    try:
        with open(channels_file, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

_channels = _load_channels_config()

# 展开分类→频道列表（供 fetch_youtube_videos 使用）
def _flatten_channels():
    cats = _channels.get("categories", {})
    all_channels = []
    for cat_key, cat_data in cats.items():
        for ch in cat_data.get("channels", []):
            all_channels.append({**ch, "category": cat_key})
    return all_channels

YOUTUBE_EDUCATION_CHANNELS = _flatten_channels() or [
    {"id": "UCAuUUnT6oDeKwE6v1NGQxug", "name": "TED", "category": "演讲思想"},
    {"id": "UCsXVk37bltHxD1rDPwtNM8Q", "name": "Kurzgesagt", "category": "科学科普"},
    {"id": "UCHnyfMqiRRG1u-2MsSQLbXA", "name": "Veritasium", "category": "科学科普"},
    {"id": "UCYO_jab_esuFRV4b17AJtAw", "name": "3Blue1Brown", "category": "数学计算机"},
]

# 分类标签 (用于UI)
CATEGORY_LABELS = _channels.get("youtube_labels") or [
    "科学科普", "演讲思想", "数学计算机", "历史人文", "经济商业", "创意设计", "美食旅游"
]

# 每页视频数量
VIDEOS_PER_PAGE = 48

# 摘要缓存过期时间 (秒) = 7 天
SUMMARY_CACHE_TTL = 86400 * 7

# 视频列表缓存 (秒) = 30 分钟
VIDEO_LIST_CACHE_TTL = 1800

# 最低视频时长 (秒) — 低于此值自动排除
MIN_DURATION_SECONDS = 300  # 5 分钟

# YouTube 请求超时 (秒)
YOUTUBE_TIMEOUT = 8

# 最大并发 YouTube 请求数 (RSS 模式)
YOUTUBE_MAX_WORKERS = 5

# 最大并发 YouTube API 请求数
YOUTUBE_MAX_WORKERS_API = 3
