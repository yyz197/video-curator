# 视频精选 — Video Curator

聚焦学习与深度内容的视频策展工具。聚合 B站 和 YouTube 优质长视频，AI 深度分析、嵌入播放、笔记沉淀、一键导出。

---

## 功能

| 模块 | 说明 |
|------|------|
| 双源聚合 | B站热门+周榜+日榜 / YouTube 53个精选教育频道 |
| AI 深度分析 | 内容概要 + 时间线节点 + 核心要点 + 关联标签 |
| 字幕提取 | YouTube (`youtube-transcript-api`) + B站 (subtitle API) |
| 嵌入播放 | 点击卡片 → 左侧大屏播放器，右侧笔记+AI对话 |
| 视频笔记 | Markdown 编辑，自动保存，支持 AI 对话 |
| 导出到桌面 | 一键生成 Markdown → `~/Desktop/视频笔记/` |
| 频道关注 | 关注作者后推荐加权 2.5x |
| 观看追踪 | 打开记录历史 / 保存笔记标记已看 / 手动标记 |
| 时长过滤 | 自动过滤 <5 分钟短视频，时长缓存永久生效 |
| 每日预热 | GitHub Actions 每天 08:00 预生成 AI 缓存 |

---

## 快速开始

### 环境

- Python 3.11+
- macOS / Linux

### 安装

```bash
git clone <仓库地址>
cd video-curator
pip install -r requirements.txt
```

### 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`：
```env
DEEPSEEK_API_KEY=你的Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
YOUTUBE_API_KEY=你的Key    # 可选
```

| Key | 获取地址 | 说明 |
|------|------|------|
| DeepSeek | platform.deepseek.com | 必需 |
| YouTube | console.cloud.google.com | 可选 |

### 启动

```bash
./start.sh
# 打开 http://localhost:8080
```

---

## 使用流程

浏览发现 → 点击卡片 → 大屏分栏：

- 左侧：视频播放器 + 深度分析（时间线 + 核心要点）
- 右侧：📝 笔记编辑 / 🤖 AI 对话
- 底部：💾保存 📂导出 ✅标记已看

### 筛选方式

全部/B站/YouTube 切换 · 分类标签 · 排序（综合/最新/播放/点赞） · 精华模式 · 偏好设置 · 搜索

### 导出格式

```
~/Desktop/视频笔记/
├── B站/2026-06-02_视频标题.md
└── YouTube/2026-06-02_Title.md
```

每个 md 包含：视频信息、AI 摘要、你的笔记、对话记录。

---

## 项目结构

```
video-curator/
├── app.py              # Flask 后端
├── config.py           # 配置加载
├── channels.json       # 频道分类配置（改此文件增减频道）
├── warmup.py           # GitHub Actions 预热脚本
├── start.sh            # 一键启动
├── requirements.txt
├── .env.example
├── static/
│   ├── css/style.css
│   ├── js/app.js
│   └── js/notes.js
├── templates/index.html
├── cache/              # AI 缓存目录
└── .github/workflows/
    └── warmup.yml      # 每日 08:00 自动触发
```

---

## 自定义频道

编辑 `channels.json` 增删频道，重启即生效，无需改代码。

---

## GitHub Actions 预热

在仓库 Settings → Secrets and variables → Actions 设置：

| Secret | 值 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek Key |
| `YOUTUBE_API_KEY` | YouTube Key |

每天北京时间 08:00 自动拉取视频、生成 AI 缓存、commit 回仓库。本地 `./start.sh` 启动时自动 `git pull`。

---

## API

| 路由 | 方法 | 说明 |
|------|------|------|
| `/api/videos` | GET | 视频列表 |
| `/api/analyze` | GET | 深度分析 |
| `/api/summarize` | GET | 快速摘要 |
| `/api/transcript` | GET | 获取字幕 |
| `/api/chat` | POST | AI 对话 |
| `/api/notes/<id>` | GET | 加载笔记 |
| `/api/notes/save` | POST | 保存笔记 |
| `/api/notes/export` | POST | 导出到桌面 |
| `/api/notes/list` | GET | 笔记列表 |
| `/api/health` | GET | 健康检查 |
| `/api/thumbnail` | GET | 缩略图代理 |
| `/api/categories` | GET | 分类列表 |

---

## 技术栈

Flask · DeepSeek API · YouTube Data API v3 · youtube-transcript-api · B站 API · GitHub Actions

---

## License

MIT
