"""
视频精选 Web 应用 — 配置文件
"""
import json
import os
from pathlib import Path

PROJECT_DIR = os.path.dirname(__file__)

# DeepSeek API (用于 AI 视频摘要)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))
except ImportError:
    pass
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-4bf5537df2a34695bf33162169b8cd82")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# YouTube Data API v3 (可选，不填则使用 RSS 模式)
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# 缓存目录
CACHE_DIR = os.environ.get("VC_CACHE_DIR", "/tmp/video-curator-cache")


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

YOUTUBE_EDUCATION_CHANNELS = _channels.get("youtube") or [
    {"id": "UCAuUUnT6oDeKwE6v1NGQxug", "name": "TED"},
    {"id": "UCsXVk37bltHxD1rDPwtNM8Q", "name": "Kurzgesagt"},
    {"id": "UCHnyfMqiRRG1u-2MsSQLbXA", "name": "Veritasium"},
    {"id": "UCYO_jab_esuFRV4b17AJtAw", "name": "3Blue1Brown"},
    {"id": "UCX6b17PVsYBQ0ip5gyeme-Q", "name": "CrashCourse"},
    {"id": "UCpVm7bg6pXKo1Pr6k5kxG9A", "name": "National Geographic"},
    {"id": "UCiMn6TkPYOlMYNOhCgBDf4A", "name": "BBC Earth"},
    {"id": "UC4ri3N_FPYRWqHkh-WrZqoQ", "name": "OverSimplified"},
    {"id": "UCsooa4yRKGN_zEE8iknghZA", "name": "TED-Ed"},
    {"id": "UCsT0YIqwnpJCM-mx7-gSA4Q", "name": "TEDx Talks"},
    {"id": "UC6107grRI4m0o2-emgoDnAA", "name": "SmarterEveryDay"},
    {"id": "UC7_gcs09iThXybpVgjHZ_7g", "name": "PBS Space Time"},
    {"id": "UCZYTClx2T1of7BRZ86-8fow", "name": "SciShow"},
    {"id": "UCUK0lqRq8YSh3npnhQbPR5g", "name": "MinutePhysics"},
    {"id": "UCYeF244yNGuFefuFKqxIAXw", "name": "The Royal Institution"},
    {"id": "UC1zZE_kJ8rQHgLTVfobLi_g", "name": "Mark Rober"},
    {"id": "UC2C_jShtL-nGq1uW7H5VH_Q", "name": "CGP Grey"},
    {"id": "UCoxcjq-8xIDTYp3uz647V5A", "name": "Numberphile"},
    {"id": "UC9-y-6csu5WGm29I7JiwpnA", "name": "Computerphile"},
    {"id": "UC4Ey2LOVGrfmqZzh_ySP-XQ", "name": "Kings and Generals"},
    {"id": "UCXMXWGMM7UeDmLW_PdEVQxg", "name": "Vox"},
    {"id": "UCBa659QWEk1AI4Tg--mrJ5A", "name": "Tom Scott"},
    {"id": "UCJkMlOu7faDgqh4PfzbpLdg", "name": "Nerdwriter1"},
    {"id": "UCeiYXex_fwgYDonaTcSIk6w", "name": "MinuteEarth"},
    {"id": "UCXIJgqnII2ZOINSWNOGFThA", "name": "Bloomberg Originals"},
    {"id": "UCoOae5nYA7VqaXzerajD0lg", "name": "Ali Abdaal"},
    {"id": "UC4a-Gbdw7vLB-NbBGxEw4jw", "name": "Steve Mould"},
    {"id": "UC6nSFpj9HTCZ5t-NJa3fO7A", "name": "Physics Girl"},
]

BILIBILI_CATEGORIES = _channels.get("bilibili_categories") or {
    36: "知识",
    201: "科学科普",
    207: "社科法律",
    208: "人文历史",
    209: "财经商业",
    226: "校园学习",
    227: "职业职场",
    228: "设计创意",
    229: "野生技术协会",
    230: "演讲公开课",
    188: "科技",
    95: "数码",
    231: "计算机技术",
    232: "科工机械",
    233: "极客DIY",
    177: "纪录片",
    178: "科学探索",
    202: "资讯",
    203: "热点",
    204: "环球",
}

BILIBILI_CATEGORY_LABELS = _channels.get("bilibili_labels") or [
    "知识", "科学科普", "社科法律", "人文历史", "财经商业",
    "科技", "数码", "计算机技术", "纪录片", "校园学习",
    "职业职场", "设计创意", "资讯",
]

TITLE_EXCLUDE = _channels.get("title_exclude", [])

# 每页视频数量
VIDEOS_PER_PAGE = 24

# 摘要缓存过期时间 (秒) = 7 天
SUMMARY_CACHE_TTL = 86400 * 7

# 视频列表缓存 (秒) = 10 分钟 — 避免频繁调用B站API
VIDEO_LIST_CACHE_TTL = 600

# 最低视频时长 (秒) — 低于此值自动排除
MIN_DURATION_SECONDS = 300  # 5 分钟

# YouTube 请求超时 (秒) — RSS 模式单个频道
YOUTUBE_TIMEOUT = 8

# 最大并发 YouTube 请求数 (RSS 模式)
YOUTUBE_MAX_WORKERS = 5

# 最大并发 YouTube API 请求数 (Data API v3, 受 API 配额限制)
YOUTUBE_MAX_WORKERS_API = 3

# 笔记导出目录
NOTES_EXPORT_DIR = os.path.expanduser("~/Desktop/视频笔记")
