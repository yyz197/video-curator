"""每日预热脚本 — GitHub Actions 定时运行
新增强: 字幕预加载 + 翻译 + 深度分析 — 本地打开即用
"""
import json
import sys
import os
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("VC_CACHE_DIR", "/tmp/vc-warmup-cache")

try:
    from app import app, generate_summary, generate_summaries_parallel, cache_key, cache_set, cache_get
    from app import fetch_youtube_videos, _video_score, _video_score_featured, get_transcript_timed
    from config import VIDEOS_PER_PAGE, CATEGORY_LABELS, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
except Exception as e:
    print(f"导入失败: {e}")
    traceback.print_exc()
    sys.exit(1)


def _save_video_list_cache(source: str, videos: list, label: str, sort: str = "score", latest_days: int = 0) -> None:
    total = len(videos)
    extra = f"latest_days={latest_days}" if latest_days else ""
    ck = cache_key("videos", source, "", "1", "", sort, str(latest_days))
    data = {
        "_ts": time.time(),
        "videos": videos,
        "total": total, "page": 1, "per_page": VIDEOS_PER_PAGE,
        "has_more": total > VIDEOS_PER_PAGE,
        "categories": CATEGORY_LABELS, "search": None,
    }
    cache_set(ck, data)
    print(f"     {label}: 缓存 {total} 个视频 (key={ck})")


def _prefetch_analysis(video: dict) -> None:
    """预生成深度分析"""
    import requests as req

    ck = cache_key("analyze", video.get("title", "")[:80])
    if cache_get(ck):
        return
    if not DEEPSEEK_API_KEY:
        return

    # 尝试获取字幕作为上下文
    subtitle_context = ""
    try:
        embed_id = video.get("embed_id", "") or video.get("youtube_id", "")
        timed = get_transcript_timed({"source": video.get("source", ""), "embed_id": embed_id})
        if timed and timed.get("text"):
            subtitle_context = f"【视频字幕节选】\n{timed['text'][:3000]}\n\n"
    except Exception:
        pass

    prompt = f"""你是专业内容策展人。{subtitle_context}请基于以上信息做深度观前分析,帮助观众在观看前了解内容。

【视频信息】
标题：{video.get('title','')}
作者：{video.get('author','')}
分类：{video.get('category','教育')}
时长：{video.get('duration','')}
简介：{(video.get('description','') or '')[:600]}

请严格用以下结构输出(Markdown格式):

## 内容概要
(3-4句话精炼概括)

## 核心知识点
- 知识1: 详细说明
- 知识2: 详细说明
- 知识3: 详细说明
(3-5个)

## 关键术语
- **术语1** (原文): 解释
(提取专业术语, 附英文原文)

## 背景补充
(相关历史/前沿背景)

## 观看建议
- 知识密度: ⭐1-5星
- 适看人群: (描述)
- 一句话建议: (是否值得)"""

    try:
        resp = req.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 1500, "temperature": 0.3},
            timeout=60,
        )
        data = resp.json()
        analysis = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if analysis:
            cache_set(ck, {"analysis": analysis, "cached": False})
    except Exception as e:
        print(f"      分析失败: {e}")


def warmup():
    with app.app_context():
        print("🔥 预热开始...")

        # ── YouTube 精选模式 (深挖3页=每频道150条) ──
        yt_deep = []
        try:
            print("  → 拉取 YouTube 精选模式 (深挖历史)...")
            yt_deep = fetch_youtube_videos(max_pages=3)
            print(f"     YouTube 精选: {len(yt_deep)} 个视频")
        except Exception as e:
            print(f"  !! YouTube 精选失败: {e}")
            traceback.print_exc()

        # ── YouTube 普通模式 ──
        yt_videos = []
        try:
            print("  → 拉取 YouTube 普通模式...")
            yt_videos = fetch_youtube_videos(max_pages=1)
            print(f"     YouTube 普通: {len(yt_videos)} 个视频")
        except Exception as e:
            print(f"  !! YouTube失败: {e}")
            traceback.print_exc()

        all_videos = yt_deep
        print(f"  总计: {len(all_videos)} 个视频 (精选)")
        if not all_videos:
            print("  ⚠️ 没有获取到任何视频，退出")
            return

        # ── 精选模式评分 (去时效性加权) ──
        for v in all_videos:
            v["score"] = _video_score_featured(v)
        all_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)

        # ── 普通模式评分 ──
        for v in yt_videos:
            v["score"] = _video_score(v)
        yt_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)

        # ── 缓存精选列表 ──
        print("  → 缓存精选列表...")
        _save_video_list_cache("youtube", all_videos, "精选(score)", "score")

        # ── 缓存最新列表 (近7天 + 质量过滤) ──
        from app import _latest_quality_filter
        cutoff = time.time() - 7 * 86400
        latest_videos = [v for v in yt_videos if v.get("published", 0) >= cutoff and _latest_quality_filter(v)]
        latest_videos.sort(key=lambda v: (v["score"], v.get("published", 0)), reverse=True)
        _save_video_list_cache("youtube", latest_videos, "最新(latest)", "latest", 7)
        print(f"     最新模式: {len(latest_videos)} 个视频 (7天窗口)")

        # ── AI 摘要 (Top 30 精选) ──
        top_n = min(30, len(all_videos))
        top = all_videos[:top_n]
        print(f"  → 对 Top {len(top)} 视频生成 AI 摘要...")
        try:
            generate_summaries_parallel(top)
            print(f"  ✅ 摘要完成")
        except Exception as e:
            print(f"  !! 摘要失败: {e}")

        # ── 深度分析 (Top 20 精选) ──
        top20 = all_videos[:20]
        print(f"  → 对 Top {len(top20)} 视频生成深度分析...")
        for i, v in enumerate(top20):
            try:
                _prefetch_analysis(v)
                print(f"     [{i+1}/{len(top20)}] {v.get('title','')[:40]}")
            except Exception as e:
                print(f"     [{i+1}] 失败: {e}")

        print(f"✅ 预热完成: 精选 {len(all_videos)}个 + 最新 {len(latest_videos)}个 | {len(top20)}分析 + {len(top)}摘要\n💡 字幕翻译请在本地开VPN后点按钮获取")


if __name__ == "__main__":
    warmup()
