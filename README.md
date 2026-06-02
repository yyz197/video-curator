# 视频精选 — Video Curator

**聚焦学习与深度内容的视频策展工具**。从 B站 和 YouTube 精选高质量长视频，AI 深度分析 + 时间线节点 + 嵌入播放 + 笔记沉淀 + 一键导出。

---

## 功能总览

| 模块 | 能力 |
|------|------|
| 📡 **双源聚合** | B站 热门+周榜+日榜 / YouTube 53个精选频道 |
| 🤖 **AI 深度分析** | 内容概要 + 时间线节点 + 核心要点 + 关联标签 |
| 📜 **字幕提取** | YouTube (`youtube-transcript-api`) + B站 (subtitle API)，AI 分析基于真实内容 |
| 🎬 **嵌入播放** | 点击卡片 → 左侧大屏播放器，右侧笔记 + AI 对话 |
| 📝 **视频笔记** | Markdown 笔记编辑器，自动保存，支持 AI 对话 |
| 📂 **导出到桌面** | 一键生成 Markdown → `~/Desktop/视频笔记/[B站|YouTube]/` |
| 🔔 **频道关注** | 关注作者，后续推荐加权 2.5x |
| ✅ **观看追踪** | 三级状态：打开→记录历史 / 保存笔记→标记已看 / 手动标记 |
| ⏰ **时长过滤** | 自动过滤 < 5 分钟短视频，时长缓存永久生效 |
| 🔥 **GitHub Actions 预热** | 每日 08:00 自动拉取 + 预生成 AI 缓存，打开即用 |

---

## 快速开始

### 1. 环境要求

- Python 3.11+
- macOS / Linux

### 2. 安装

```bash
git clone https://github.com/your-username/video-curator.git
cd video-curator
pip install -r requirements.txt
```

### 3. 配置 API Key

复制模板并填入你的 Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
DEEPSEEK_API_KEY=你的DeepSeek_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
YOUTUBE_API_KEY=你的YouTube_API_Key    # 可选，不填则用 RSS 模式
```

| Key | 获取地址 | 说明 |
|------|------|------|
| DeepSeek | https://platform.deepseek.com | AI 分析/摘要，必填 |
| YouTube | https://console.cloud.google.com | 获取时长+播放量，推荐填写 |

### 4. 启动

```bash
./start.sh
# 浏览器打开 http://localhost:8080
```

---

## 使用流程

```
浏览发现 → 点击卡片 → 大屏分栏
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
        视频播放器      深度分析       📝 笔记
       (嵌入 iframe)   (时间线+要点)   Markdown 编辑
                                        │
                                    🤖 AI 对话
                                    (自由提问)
                                        │
                          [💾保存] [📂导出] [✅已看]
```

### 浏览筛选

| 操作 | 说明 |
|------|------|
| **全部 / B站 / YouTube** | 切换来源（B站默认按最新排序） |
| **分类标签** | 知识、科技、纪录片… |
| **排序** | 综合评分 / 最新发布 / 播放最多 / 点赞最多 |
| **✨ 精华模式** | 只显示 Top 50% 高分视频 |
| **⚙️ 偏好设置** | 勾选兴趣分类，加权推荐 |
| **🔍 搜索** | 标题 / 作者 / 描述 |

### 笔记导出格式

```markdown
# 视频标题

- 来源: B站
- 作者: 毕导
- 链接: https://www.bilibili.com/video/BVxxx

## AI 摘要
[深度分析内容]

## 我的笔记
[你的笔记]

## AI 对话记录
💬 问：这个实验的原理是什么？
🤖 答：...
```

---

## 项目结构

```
video-curator/
├── app.py                 # Flask 后端（API路由 + 视频源 + AI引擎）
├── config.py              # 配置加载（从 .env + channels.json）
├── channels.json          # 频道和分类配置（修改此处增减频道）
├── warmup.py              # GitHub Actions 每日预热脚本
├── start.sh               # 一键启动脚本
├── requirements.txt       # Python 依赖
├── .env.example           # API Key 模板
│
├── static/
│   ├── css/style.css      # 全局样式（含大屏分栏抽屉）
│   ├── js/app.js          # 主前端逻辑
│   └── js/notes.js        # 笔记抽屉逻辑
│
├── templates/
│   └── index.html         # 页面模板
│
├── cache/                 # 缓存目录（AI摘要 + 时长）
├── .github/workflows/
│   └── warmup.yml         # 每日 08:00 自动预热
│
└── ~/Desktop/视频笔记/    # 导出目录
    ├── B站/
    └── YouTube/
```

---

## 自定义频道

编辑 `channels.json` 增删频道：

```json
{
  "youtube": [
    {"id": "UC_CHANNEL_ID", "name": "频道名"},
    ...
  ],
  "bilibili_categories": {
    "36": "知识",
    ...
  },
  "bilibili_labels": ["知识", "科技", ...],
  "title_exclude": ["搞笑", "鬼畜", ...]
}
```

改完重启服务即可生效，无需改 Python 代码。

---

## GitHub Actions 预热

### 设置 Secrets

GitHub 仓库 → Settings → Secrets and variables → Actions：

| Name | Value |
|------|-------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `YOUTUBE_API_KEY` | YouTube Data API Key |

### 效果

- 每天北京时间 **08:00** 自动触发
- 拉取 B站 + YouTube 最新视频
- Top 20 视频预生成 AI 摘要，缓存写入 `cache/`
- 自动 commit + push 回仓库
- `./start.sh` 启动时自动 `git pull`，即开即用

---

## API 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页面 |
| `/api/health` | GET | 健康检查 |
| `/api/videos` | GET | 视频列表（支持 source/category/sort/search/prefs/following/essence） |
| `/api/analyze` | GET | 深度分析（支持 subtitle_text） |
| `/api/summarize` | GET | 快速摘要 |
| `/api/transcript` | GET | 获取视频字幕 |
| `/api/thumbnail` | GET | 缩略图代理 |
| `/api/chat` | POST | AI 对话 |
| `/api/notes/<video_id>` | GET | 加载笔记 |
| `/api/notes/save` | POST | 保存笔记 |
| `/api/notes/export` | POST | 导出到桌面 |
| `/api/notes/list` | GET | 笔记列表 |
| `/api/categories` | GET | 分类列表 |

---

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Flask 3.x + Python |
| 前端 | 原生 JS（无框架） + CSS3 |
| AI | DeepSeek Chat API |
| 视频源 | B站 API + YouTube Data API v3 + RSS |
| 字幕 | `youtube-transcript-api` + B站 subtitle API |
| 调度 | GitHub Actions (cron) |
| 缓存 | JSON 文件（本地 + GitHub 同步） |

---

## License

MIT
