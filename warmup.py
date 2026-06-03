"""每日预热脚本 — GitHub Actions 定时运行"""
import json
import sys
import os
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VC_CACHE_DIR", "/tmp/vc-warmup-cache")

try:
    from app import app, generate_summary, generate_summaries_parallel, cache_key, cache_set
    from app import fetch_bilibili_videos, fetch_youtube_videos, _video_score
    from config import VIDEOS_PER_PAGE, BILIBILI_CATEGORY_LABELS
except Exception as e:
    print(f"导入失败: {e}")
    traceback.print_exc()
    sys.exit(1)


def _save_video_list_cache(source: str, videos: list, label: str, sort: str = "score") -> None:
    """保存视频列表缓存，供 app.py 的 api_videos 读取"""
    total = len(videos)
    page1 = videos[:VIDEOS_PER_PAGE]
    ck = cache_key("videos", source, "", "1", "", sort)
    data = {
        "_ts": time.time(),
        "videos": page1,
        "total": total,
        "page": 1,
        "per_page": VIDEOS_PER_PAGE,
        "has_more": total > VIDEOS_PER_PAGE,
        "categories": BILIBILI_CATEGORY_LABELS,
        "search": None,
    }
    cache_set(ck, data)
    print(f"     {label}: 缓存 {len(page1)}/{total} 个视频 (key={ck})")


def warmup():
    with app.app_context():
        print("🔥 预热开始...")

        # ── B站 ──
        bili_videos = []
        try:
            print("  → 拉取 B站视频...")
            bili_videos = fetch_bilibili_videos(None)
            print(f"     B站: {len(bili_videos)} 个")
        except Exception as e:
            print(f"  !! B站失败: {e}")
            traceback.print_exc()

        # ── YouTube ──
        yt_videos = []
        try:
            print("  → 拉取 YouTube 视频...")
            yt_videos = fetch_youtube_videos()
            print(f"     YouTube: {len(yt_videos)} 个")
        except Exception as e:
            print(f"  !! YouTube失败: {e}")
            traceback.print_exc()

        all_videos = bili_videos + yt_videos
        print(f"  总计: {len(all_videos)} 个视频")

        if not all_videos:
            print("  ⚠️ 没有获取到任何视频，退出")
            return

        # ── 评分排序 ──
        for v in all_videos:
            v["score"] = _video_score(v)
        all_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)

        for v in bili_videos:
            v["score"] = _video_score(v)
        bili_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)

        for v in yt_videos:
            v["score"] = _video_score(v)
        yt_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)

        # ── 缓存视频列表 ──
        print("  → 缓存视频列表...")
        _save_video_list_cache("all", all_videos, "全部", "score")
        _save_video_list_cache("bilibili", bili_videos, "B站", "time")
        _save_video_list_cache("youtube", yt_videos, "YouTube", "score")

        # ── AI 摘要 (Top 30) ──
        top_n = 30
        top = all_videos[:top_n]
        print(f"  → 对 Top {len(top)} 视频生成 AI 摘要...")
        try:
            generate_summaries_parallel(top)
            print(f"  ✅ 摘要生成完成")
        except Exception as e:
            print(f"  !! 摘要失败: {e}")
            traceback.print_exc()

        print(f"✅ 预热完成: {len(top)} 个摘要 + {len(all_videos)} 个视频缓存")


if __name__ == "__main__":
    warmup()
