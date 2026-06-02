"""每日预热脚本 — 拉取视频 + 预生成 AI 分析缓存 (GitHub Actions 定时)"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["VC_CACHE_DIR"] = "/tmp/vc-warmup-cache"

from app import app, generate_summary, generate_summaries_parallel, cache_set, cache_key
from app import fetch_bilibili_videos, fetch_youtube_videos, _video_score


def warmup():
    with app.app_context():
        print("🔥 预热开始...")
        videos = []
        print("  → 拉取 B站视频...")
        videos.extend(fetch_bilibili_videos(None))
        print(f"     B站: {len(videos)} 个")

        print("  → 拉取 YouTube 视频...")
        yt = fetch_youtube_videos()
        videos.extend(yt)
        print(f"     YouTube: {len(yt)} 个, 总计: {len(videos)} 个")

        for v in videos:
            v["score"] = _video_score(v)
        videos.sort(key=lambda v: v["score"], reverse=True)
        top = videos[:20]

        print(f"  → 对 Top {len(top)} 视频生成 AI 摘要...")
        generate_summaries_parallel(top)

        print("  → 预生成深度分析...")
        for i, v in enumerate(top):
            try:
                from app import cache_get_with_ttl, SUMMARY_CACHE_TTL
                # 触发 analyze 逻辑 — 直接调用 generate_summary 的增强版
                # 深度分析缓存通过 cache_key("analyze", title[:80]) 存储
                key = cache_key("analyze", v["title"][:80])
                # 这里只做摘要预缓存，深度分析在用户点击时实时生成
                _ = generate_summary(v)
            except Exception as e:
                print(f"      分析失败 ({v['title'][:30]}): {e}")
            if (i + 1) % 5 == 0:
                print(f"      {i + 1}/{len(top)}")

        print(f"✅ 预热完成: {len(top)} 个视频摘要已缓存")


if __name__ == "__main__":
    warmup()
