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
    from app import fetch_bilibili_videos, fetch_youtube_videos, _video_score
    from app import get_transcript_timed, _translate_text_en_to_zh
    from config import VIDEOS_PER_PAGE, BILIBILI_CATEGORY_LABELS, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, SUMMARY_CACHE_TTL, DEEPL_API_KEY
except Exception as e:
    print(f"导入失败: {e}")
    traceback.print_exc()
    sys.exit(1)


def _save_video_list_cache(source: str, videos: list, label: str, sort: str = "score") -> None:
    total = len(videos)
    ck = cache_key("videos", source, "", "1", "", sort)
    data = {
        "_ts": time.time(),
        "videos": videos,
        "total": total, "page": 1, "per_page": VIDEOS_PER_PAGE,
        "has_more": total > VIDEOS_PER_PAGE,
        "categories": BILIBILI_CATEGORY_LABELS, "search": None,
    }
    cache_set(ck, data)
    print(f"     {label}: 缓存 {total} 个视频 (key={ck})")


def _prefetch_subtitle_and_translate(video: dict) -> None:
    """预加载字幕并翻译, 缓存到本地"""
    embed_id = video.get("embed_id", "") or video.get("youtube_id", "")
    if not embed_id:
        return
    source = video.get("source", "")
    ck = cache_key("translate", source, video.get("id", ""))

    # 已有缓存跳过
    if cache_get(ck):
        return

    # 获取带时间戳的字幕
    timed = get_transcript_timed({"source": source, "embed_id": embed_id})
    if not timed or not timed.get("segments"):
        return

    raw_text = timed.get("text", "")

    # B站字幕已是中文, 直接存
    if source == "bilibili":
        cache_set(ck, {"translation": raw_text[:2000]})
        return

    # YouTube: 使用统一翻译函数 (DeepL优先, DeepSeek兜底, 全量不截断)
    translation = _translate_text_en_to_zh(raw_text)
    if translation:
        cache_set(ck, {"translation": translation})


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
        top_n = min(30, len(all_videos))
        top = all_videos[:top_n]
        print(f"  → 对 Top {len(top)} 视频生成 AI 摘要...")
        try:
            generate_summaries_parallel(top)
            print(f"  ✅ 摘要完成")
        except Exception as e:
            print(f"  !! 摘要失败: {e}")

        # ── 字幕 + 翻译 (Top 15 YouTube) ──
        yt_top = [v for v in all_videos if v.get("source") == "youtube"][:15]
        print(f"  → 对 Top {len(yt_top)} YouTube 视频预加载字幕...")
        for i, v in enumerate(yt_top):
            try:
                _prefetch_subtitle_and_translate(v)
                print(f"     [{i+1}/{len(yt_top)}] {v.get('title','')[:40]}")
            except Exception as e:
                print(f"     [{i+1}] 失败: {e}")

        # ── 深度分析 (Top 20) ──
        top20 = all_videos[:20]
        print(f"  → 对 Top {len(top20)} 视频生成深度分析...")
        for i, v in enumerate(top20):
            try:
                _prefetch_analysis(v)
                print(f"     [{i+1}/{len(top20)}] {v.get('title','')[:40]}")
            except Exception as e:
                print(f"     [{i+1}] 失败: {e}")

        print(f"✅ 预热完成: {len(top20)}分析 + {len(yt_top)}字幕 + {len(top)}摘要 + {len(all_videos)}列表")


if __name__ == "__main__":
    warmup()
