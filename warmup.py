"""每日预热脚本 — GitHub Actions 定时运行"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VC_CACHE_DIR", "/tmp/vc-warmup-cache")

try:
    from app import app, generate_summary, generate_summaries_parallel, cache_key
    from app import fetch_bilibili_videos, fetch_youtube_videos, _video_score
except Exception as e:
    print(f"导入失败: {e}")
    traceback.print_exc()
    sys.exit(1)


def warmup():
    with app.app_context():
        print("🔥 预热开始...")
        videos = []

        try:
            print("  → 拉取 B站视频...")
            videos.extend(fetch_bilibili_videos(None))
            print(f"     B站: {len(videos)} 个")
        except Exception as e:
            print(f"  !! B站失败: {e}")
            traceback.print_exc()

        try:
            print("  → 拉取 YouTube 视频...")
            yt = fetch_youtube_videos()
            videos.extend(yt)
            print(f"     YouTube: {len(yt)} 个")
        except Exception as e:
            print(f"  !! YouTube失败: {e}")
            traceback.print_exc()

        print(f"  总计: {len(videos)} 个视频")

        if not videos:
            print("  ⚠️ 没有获取到任何视频，退出")
            return

        for v in videos:
            v["score"] = _video_score(v)
        videos.sort(key=lambda v: v["score"], reverse=True)
        top = videos[:20]

        print(f"  → 对 Top {len(top)} 视频生成 AI 摘要...")
        try:
            generate_summaries_parallel(top)
            print(f"  ✅ 摘要生成完成")
        except Exception as e:
            print(f"  !! 摘要失败: {e}")
            traceback.print_exc()

        print(f"✅ 预热完成: {len(top)} 个视频")


if __name__ == "__main__":
    warmup()
