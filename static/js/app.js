/**
 * 视频精选 v2 — 前端逻辑
 * 新增: 搜索 · 暗色模式 · 收藏 · 骨架屏 · Toast
 */
(function () {
    "use strict";

    // ── State ──
    const state = {
        source: "all",
        category: "",
        page: 1,
        withSummary: false,
        search: "",
        hasMore: false,
        isLoading: false,
        videos: [],
        categories: [],
        sort: "score",
        timeDistribution: null,
    };

    // ── DOM ──
    const $ = (sel) => document.querySelector(sel);

    const videoGrid = $("#videoGrid");
    const statusText = $("#statusText");
    const loadMore = $("#loadMore");
    const loadMoreBtn = $("#loadMoreBtn");
    const emptyState = $("#emptyState");
    const emptyTitle = $("#emptyTitle");
    const emptyDesc = $("#emptyDesc");
    const categoryTags = $("#categoryTags");
    const sourceTabs = $("#sourceTabs");
    const summaryToggle = $("#summaryToggle");
    const refreshBtn = $("#refreshBtn");
    const modalOverlay = $("#modalOverlay");
    const modalBody = $("#modalBody");
    const modalClose = $("#modalClose");
    const searchInput = $("#searchInput");
    const searchClear = $("#searchClear");
    const sortSelect = $("#sortSelect");
    const darkModeBtn = $("#darkModeBtn");
    const favoritesBtn = $("#favoritesBtn");
    const favoritesPanel = $("#favoritesPanel");
    const favoritesList = $("#favoritesList");
    const favoritesEmpty = $("#favoritesEmpty");
    const favoritesClose = $("#favoritesClose");
    const toastContainer = $("#toastContainer");
    const favoritesOverlay = document.getElementById("favoritesOverlay") || createFavoritesOverlay();

    function createFavoritesOverlay() {
        const el = document.createElement("div");
        el.className = "favorites-overlay";
        el.id = "favoritesOverlay";
        document.body.appendChild(el);
        el.addEventListener("click", closeFavorites);
        return el;
    }

    // ── Skeleton ──
    function showSkeleton(count = 8) {
        videoGrid.innerHTML = Array.from({ length: count }, () => `
            <div class="skeleton-card">
                <div class="skeleton-thumb"></div>
                <div class="skeleton-body">
                    <div class="skeleton-line wide"></div>
                    <div class="skeleton-line medium"></div>
                    <div class="skeleton-line short"></div>
                </div>
            </div>
        `).join("");
    }

    // ── Toast ──
    function showToast(msg, type = "") {
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.textContent = msg;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 3200);
    }

    // ── Dark Mode ──
    function initDarkMode() {
        const saved = localStorage.getItem("vc-dark-mode");
        if (saved === "dark" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
            document.documentElement.setAttribute("data-theme", "dark");
            darkModeBtn.textContent = "☀️";
        }
    }

    function toggleDarkMode() {
        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        if (isDark) {
            document.documentElement.removeAttribute("data-theme");
            darkModeBtn.textContent = "🌙";
            localStorage.setItem("vc-dark-mode", "light");
        } else {
            document.documentElement.setAttribute("data-theme", "dark");
            darkModeBtn.textContent = "☀️";
            localStorage.setItem("vc-dark-mode", "dark");
        }
    }

    // ── Favorites (localStorage) ──
    function getFavorites() {
        try {
            return JSON.parse(localStorage.getItem("vc-favorites") || "[]");
        } catch { return []; }
    }

    function saveFavorites(favs) {
        localStorage.setItem("vc-favorites", JSON.stringify(favs));
    }

    function isFavorited(videoId) {
        return getFavorites().some((f) => f.id === videoId);
    }

    function toggleFavorite(video) {
        let favs = getFavorites();
        const idx = favs.findIndex((f) => f.id === video.id);
        if (idx >= 0) {
            favs.splice(idx, 1);
            showToast("已取消收藏");
        } else {
            favs.unshift({ id: video.id, source: video.source, title: video.title, url: video.url, thumbnail: video.thumbnail, author: video.author });
            showToast("已加入收藏", "success");
        }
        saveFavorites(favs);
        updateFavButtons();
        renderFavorites();

        // Update card fav button
        const card = document.querySelector(`.video-card[data-video-id="${video.id}"]`);
        if (card) {
            const btn = card.querySelector(".card-fav-btn");
            if (btn) toggleFavButton(btn, isFavorited(video.id));
        }
    }

    function toggleFavButton(btn, fav) {
        btn.textContent = fav ? "⭐" : "☆";
        btn.classList.toggle("favorited", fav);
    }

    function updateFavButtons() {
        document.querySelectorAll(".video-card").forEach((card) => {
            const vid = card.dataset.videoId;
            const btn = card.querySelector(".card-fav-btn");
            if (btn) toggleFavButton(btn, isFavorited(vid));
        });
    }

    function renderFavorites() {
        const favs = getFavorites();
        if (favs.length === 0) {
            favoritesEmpty.style.display = "block";
            favoritesList.style.display = "none";
            return;
        }
        favoritesEmpty.style.display = "none";
        favoritesList.style.display = "flex";
        favoritesList.innerHTML = favs
            .map(
                (f) => `
            <div class="fav-item" onclick="window.open('${escapeHTML(f.url)}', '_blank')">
                ${f.thumbnail ? `<img class="fav-item-thumb" src="${escapeHTML(f.thumbnail)}" alt="" onerror="this.style.display='none'" loading="lazy">` : ""}
                <div class="fav-item-info">
                    <div class="fav-item-title">${escapeHTML(f.title)}</div>
                    <div class="fav-item-author">${escapeHTML(f.author)}</div>
                </div>
                <button class="fav-item-remove" onclick="event.stopPropagation(); window._VC.removeFavorite('${escapeHTML(f.id)}')">&times;</button>
            </div>`
            )
            .join("");
    }

    function openFavorites() {
        renderFavorites();
        favoritesPanel.classList.add("open");
        favoritesOverlay.classList.add("open");
    }

    function closeFavorites() {
        favoritesPanel.classList.remove("open");
        favoritesOverlay.classList.remove("open");
    }

    window._VC = window._VC || {};
    window._VC.removeFavorite = function (id) {
        let favs = getFavorites();
        favs = favs.filter((f) => f.id !== id);
        saveFavorites(favs);
        updateFavButtons();
        renderFavorites();
        showToast("已取消收藏");
    };

    // ── API ──
    async function fetchAPI(path) {
        try {
            const resp = await fetch(path);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (err) {
            console.error("API error:", err);
            showToast("网络请求失败，请检查连接", "error");
            return null;
        }
    }

    function buildAPIUrl() {
        const params = new URLSearchParams();
        if (state.source !== "all") params.set("source", state.source);
        if (state.category) params.set("category", state.category);
        if (state.search) params.set("search", state.search);
        params.set("page", state.page);
        params.set("with_summary", state.withSummary);
        params.set("sort", state.sort);
        // 偏好 + 精华
        const prefs = getPreferences();
        if (prefs.length > 0) params.set("prefs", prefs.join(","));
        if (getEssenceMode()) params.set("essence", "true");
        // 关注频道
        const following = getFollowedAuthors();
        if (following.length > 0) params.set("following", following.join(","));
        return `/api/videos?${params.toString()}`;
    }

    function getFollowedAuthors() {
        try { return JSON.parse(localStorage.getItem("vc-following") || "[]"); } catch { return []; }
    }

    // ── Loading ──
    function setLoading(msg) {
        statusText.textContent = msg;
    }

    // ── Render ──
    function renderHeroCard(video) {
        const sourceClass = video.source === "bilibili" ? "bilibili" : "youtube";
        const sourceLabel = video.source === "bilibili" ? "B站" : "YouTube";
        const hasSummary = video.summary && video.summary.length > 0;
        return `
        <div class="hero-card" data-video-id="${video.id}" data-source="${video.source}" tabindex="0">
            <div class="hero-thumb">
                ${video.thumbnail ? `<img src="${escapeHTML(video.thumbnail)}" alt="" loading="eager" onerror="this.style.display='none'">` : ""}
                <span class="hero-source-badge ${sourceClass}">${sourceLabel}</span>
                ${video.duration ? `<span class="hero-duration-float">${escapeHTML(video.duration)}</span>` : ""}
            </div>
            <div class="hero-body">
                <h3 class="hero-title">${escapeHTML(video.title)}</h3>
                <div class="hero-meta">
                    <span>👤 ${escapeHTML(video.author)}</span>
                    ${video.published_str ? `<span>📅 ${escapeHTML(video.published_str)}</span>` : ""}
                    ${video.views ? `<span>👁 ${escapeHTML(video.views)}</span>` : ""}
                </div>
                <div class="hero-tags">
                    <span class="card-category">${escapeHTML(video.category || "未分类")}</span>
                    ${video.duration_badge ? `<span class="card-duration-badge">${escapeHTML(video.duration_badge)}</span>` : ""}
                </div>
                ${hasSummary ? `<div class="hero-summary">${escapeHTML(video.summary)}</div>` : ""}
            </div>
        </div>`;
    }

    function renderVideoCard(video) {
        const sourceClass = video.source === "bilibili" ? "source-bilibili" : "source-youtube";
        const sourceLabel = video.source === "bilibili" ? "B站" : "YouTube";
        const hasSummary = video.summary && video.summary.length > 0;
        const fav = isFavorited(video.id);

        return `
        <div class="video-card" data-video-id="${video.id}" data-source="${video.source}" tabindex="0">
            <div class="card-thumb">
                ${video.thumbnail ? `<img src="${escapeHTML(video.thumbnail)}" alt="" loading="lazy" onerror="this.style.display='none'">` : ""}
                <span class="card-source-tag ${sourceClass}">${sourceLabel}</span>
                ${video.duration ? `<span class="card-duration-float">${escapeHTML(video.duration)}</span>` : ""}
                <button class="card-fav-btn ${fav ? 'favorited' : ''}" data-fav-video='${escapeAttr(JSON.stringify({id:video.id,source:video.source,title:video.title,url:video.url,thumbnail:video.thumbnail,author:video.author}))}'>
                    ${fav ? '⭐' : '☆'}
                </button>
            </div>
            <div class="card-body">
                <h3 class="card-title" role="link" tabindex="0">${escapeHTML(video.title)}</h3>
                <div class="card-meta">
                    <span>👤 ${escapeHTML(video.author)}</span>
                    ${video.duration ? `<span>⏱ ${escapeHTML(video.duration)}</span>` : ""}
                    ${video.views ? `<span>👁 ${escapeHTML(video.views)}</span>` : ""}
                    ${video.likes ? `<span>👍 ${escapeHTML(video.likes)}</span>` : ""}
                    ${video.danmaku ? `<span>💬 ${escapeHTML(video.danmaku)}</span>` : ""}
                </div>
                <div class="card-tags">
                    <span class="card-category">${escapeHTML(video.category || "未分类")}</span>
                    ${video.duration_badge ? `<span class="card-duration-badge">${escapeHTML(video.duration_badge)}</span>` : ""}
                    ${video.published_str ? `<span class="card-pub-date">📅 ${escapeHTML(video.published_str)}</span>` : ""}
                </div>
                ${hasSummary
                    ? `<div class="card-summary show"><span class="summary-label">🤖 AI 摘要</span>${escapeHTML(video.summary)}</div>`
                    : `<div class="card-summary"></div>`
                }
                ${!hasSummary
                    ? `<button class="summary-btn" data-summary-video='${escapeAttr(JSON.stringify(video))}'>✨ AI 摘要</button>`
                    : ""
                }
            </div>
        </div>`;
    }

    function renderVideos(videos, append = false) {
        if (!append) videoGrid.innerHTML = "";
        if (videos.length === 0 && !append) {
            emptyState.style.display = "block";
            emptyTitle.textContent = state.search ? "未找到匹配视频" : "暂无视频";
            emptyDesc.textContent = state.search ? "尝试其他关键词" : "换个分类或刷新试试";
            loadMore.style.display = "none";
            return;
        }
        emptyState.style.display = "none";

        let displayVideos = videos;
        // Hero card: 只在首页、无搜索、无分类过滤时显示
        if (!append && state.page === 1 && !state.search && !state.category) {
            const hero = displayVideos[0];
            const rest = displayVideos.slice(1);
            videoGrid.insertAdjacentHTML("beforeend", renderHeroCard(hero));
            // 分区标题
            const sortLabel = state.sort === "time" ? "🆕 最新内容" : "✨ 精选推荐";
            videoGrid.insertAdjacentHTML("beforeend", `<div class="section-header">${sortLabel}</div>`);
            displayVideos = rest;
        }

        displayVideos.forEach((v) => {
            videoGrid.insertAdjacentHTML("beforeend", renderVideoCard(v));
        });
        // 交错入场动画
        const newCards = videoGrid.querySelectorAll(".video-card:not(.card-enter)");
        newCards.forEach((card, i) => {
            card.style.animationDelay = (i * 40) + "ms";
            card.classList.add("card-enter");
        });
        bindCardEvents();
        if (window.updateWatchedBadges) window.updateWatchedBadges();
    }

    // ── Card Events ──
    function bindCardEvents() {
        // Hero card click
        videoGrid.querySelectorAll(".hero-card").forEach((card) => {
            if (!card._bound) {
                card._bound = true;
                card.addEventListener("click", function (e) {
                    const vid = this.dataset.videoId;
                    const video = state.videos.find((v) => v.id === vid);
                    if (video) openNotesDrawer(video);
                });
            }
        });

        videoGrid.querySelectorAll(".video-card").forEach((card) => {
            if (!card._bound) {
                card._bound = true;
                card.addEventListener("click", function (e) {
                    if (e.target.closest(".card-fav-btn") || e.target.closest(".summary-btn")) return;
                    const vid = this.dataset.videoId;
                    const video = state.videos.find((v) => v.id === vid);
                    if (video) openNotesDrawer(video);
                });
            }
        });

        videoGrid.querySelectorAll(".card-thumb, .hero-thumb").forEach((el) => {
            if (!el._bound2) {
                el._bound2 = true;
                el.addEventListener("click", function (e) {
                    e.stopPropagation();
                    const video = state.videos.find((v) => v.id === this.closest(".video-card").dataset.videoId);
                    if (video) window.open(video.url, "_blank");
                });
            }
        });

        // Fav buttons
        videoGrid.querySelectorAll(".card-fav-btn").forEach((btn) => {
            if (!btn._bound) {
                btn._bound = true;
                btn.addEventListener("click", function (e) {
                    e.stopPropagation();
                    const video = JSON.parse(this.dataset.favVideo);
                    toggleFavorite(video);
                });
            }
        });

        // Summary buttons
        videoGrid.querySelectorAll(".summary-btn").forEach((btn) => {
            if (!btn._bound) {
                btn._bound = true;
                btn.addEventListener("click", function () {
                    summarizeCard(this);
                });
            }
        });
    }

    // ── Load Videos ──
    async function loadVideos(reset = true) {
        if (state.isLoading) return;
        state.isLoading = true;

        if (reset) {
            state.page = 1;
            showSkeleton();
        }
        setLoading("正在加载视频...");
        loadMore.style.display = "none";

        const data = await fetchAPI(buildAPIUrl());
        if (!data) {
            setLoading("加载失败，请检查网络连接");
            state.isLoading = false;
            return;
        }

        state.videos = reset ? data.videos : [...state.videos, ...data.videos];
        state.hasMore = data.has_more;
        state.categories = data.categories || [];
        state.timeDistribution = data.time_distribution || null;

        renderVideos(data.videos, !reset);
        if (!reset) renderCategories();
        updateTimeDistribution();

        if (data.has_more) loadMore.style.display = "block";

        const count = reset ? data.videos.length : state.videos.length;
        setLoading(`共 ${data.total} 个视频 · 当前显示 ${count} 个${state.search ? ' · 搜索: "' + state.search + '"' : ""}`);
        state.isLoading = false;
    }

    // ── Categories ──
    function renderCategories() {
        const cats = state.categories;
        if (cats.length === 0) return;

        categoryTags.innerHTML =
            '<button class="filter-tag active" data-category="">全部</button>' +
            cats.map((c) => `<button class="filter-tag" data-category="${escapeHTML(c)}">${escapeHTML(c)}</button>`).join("");

        categoryTags.querySelectorAll(".filter-tag").forEach((btn) => {
            btn.addEventListener("click", () => {
                categoryTags.querySelectorAll(".filter-tag").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                state.category = btn.dataset.category;
                loadVideos(true);
            });
        });
    }

    // ── Summarize ──
    async function summarizeCard(btn) {
        const videoData = JSON.parse(btn.dataset.summaryVideo);
        const summaryEl = btn.parentElement.querySelector(".card-summary");

        btn.disabled = true;
        btn.innerHTML = '<span class="dot-pulse">生成摘要中</span>';

        const params = new URLSearchParams({
            video_id: videoData.id || "",
            source: videoData.source || "",
            title: videoData.title || "",
            description: videoData.description || "",
            author: videoData.author || "",
        });

        const data = await fetchAPI(`/api/summarize?${params.toString()}`);

        if (data && data.summary) {
            summaryEl.innerHTML = `<span class="summary-label">🤖 AI 摘要</span>${escapeHTML(data.summary)}`;
            summaryEl.classList.add("show");
            btn.remove();
        } else {
            btn.disabled = false;
            btn.textContent = "⚠️ 重试";
        }
    }

    // ── Modal ──
    modalClose.addEventListener("click", () => modalOverlay.classList.remove("open"));
    modalOverlay.addEventListener("click", (e) => {
        if (e.target === modalOverlay) modalOverlay.classList.remove("open");
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            modalOverlay.classList.remove("open");
            closeFavorites();
        }
    });

    async function openAnalyzeModal(video) {
        const sourceLabel = video.source === "bilibili" ? "B站" : "YouTube";
        modalBody.innerHTML = `
            <h2>${escapeHTML(video.title)}</h2>
            <div class="modal-meta">
                <span>📺 ${sourceLabel}</span>
                <span>👤 ${escapeHTML(video.author)}</span>
                ${video.duration ? `<span>⏱ ${escapeHTML(video.duration)}</span>` : ""}
                ${video.views ? `<span>👁 ${escapeHTML(video.views)}</span>` : ""}
                <span>🏷 ${escapeHTML(video.category || "未分类")}</span>
                ${video.duration_badge ? `<span class="modal-dur-badge">${escapeHTML(video.duration_badge)}</span>` : ""}
            </div>
            <div class="modal-quick-summary" id="modalQuickSummary">
                <span class="summary-label">🤖 快速摘要</span>
                <span id="quickSummaryText">生成中...</span>
            </div>
            <div class="modal-deep-analysis" id="modalDeepAnalysis">
                <span class="analysis-label">📊 深度分析</span>
                <div class="analysis-loading" id="analysisLoading">
                    <span class="dot-pulse">正在深度分析视频内容</span>
                </div>
                <div class="analysis-content markdown-body" id="analysisContent" style="display:none"></div>
            </div>
            <div class="modal-translation" id="modalTranslation" style="display:none">
                <span class="analysis-label">🌐 中文字幕翻译</span>
                <div class="translation-content" id="translationContent">
                    <span class="dot-pulse">正在翻译</span>
                </div>
            </div>
            <div class="modal-actions">
                <a href="${escapeHTML(video.url)}" target="_blank" class="modal-link">🔗 前往观看</a>
                <button class="modal-fav-btn" id="modalFavBtn" data-fav-video='${escapeAttr(JSON.stringify({id:video.id,source:video.source,title:video.title,url:video.url,thumbnail:video.thumbnail,author:video.author}))}'>
                    ${isFavorited(video.id) ? '⭐ 已收藏' : '☆ 收藏'}
                </button>
                <button class="modal-translate-btn" id="modalTranslateBtn">🌐 翻译字幕</button>
            </div>
        `;
        modalOverlay.classList.add("open");

        // 并行：快速摘要 + 深度分析
        fetchQuickSummary(video);
        fetchDeepAnalysis(video);

        // 收藏按钮
        const favBtn = document.getElementById("modalFavBtn");
        if (favBtn) {
            favBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                const v = JSON.parse(this.dataset.favVideo);
                toggleFavorite(v);
                this.textContent = isFavorited(v.id) ? '⭐ 已收藏' : '☆ 收藏';
            });
        }
        // 翻译按钮
        const translateBtn = document.getElementById("modalTranslateBtn");
        if (translateBtn) {
            translateBtn.addEventListener("click", () => {
                translateBtn.disabled = true;
                translateBtn.textContent = "⏳ 翻译中...";
                fetchTranslation(video);
            });
        }
    }

    async function fetchQuickSummary(video) {
        const el = document.getElementById("quickSummaryText");
        const params = new URLSearchParams({
            video_id: video.id, source: video.source,
            title: video.title, description: video.description || "", author: video.author,
        });
        const data = await fetchAPI(`/api/summarize?${params.toString()}`);
        if (data && data.summary) {
            el.textContent = data.summary;
        } else {
            el.textContent = "摘要暂不可用";
        }
    }

    async function fetchDeepAnalysis(video) {
        const loading = document.getElementById("analysisLoading");
        const content = document.getElementById("analysisContent");
        const params = new URLSearchParams({
            title: video.title, description: video.description || "",
            author: video.author, category: video.category || "",
            duration: video.duration || "",
        });
        const data = await fetchAPI(`/api/analyze?${params.toString()}`);
        if (data && data.analysis) {
            loading.style.display = "none";
            content.style.display = "block";
            content.innerHTML = renderMarkdown(data.analysis);
        } else {
            loading.innerHTML = "深度分析暂不可用，请稍后重试";
        }
    }

    function renderMarkdown(text) {
        let html = escapeHTML(text);
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/\\n/g, '<br>');
        html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
        html = html.replace(/⭐/g, '★');
        return html;
    }

    async function fetchTranslation(video) {
        const container = document.getElementById("modalTranslation");
        const content = document.getElementById("translationContent");
        const btn = document.getElementById("modalTranslateBtn");
        container.style.display = "block";

        const params = new URLSearchParams({
            video_id: video.id,
            source: video.source,
            embed_id: video.embed_id || video.youtube_id || "",
        });
        const data = await fetchAPI(`/api/translate?${params.toString()}`);
        if (data && data.translation) {
            content.textContent = data.translation;
            content.style.whiteSpace = "pre-wrap";
            content.style.fontSize = "13px";
            content.style.lineHeight = "1.8";
            content.style.color = "var(--text)";
            if (data.cached) {
                btn.textContent = "🌐 已翻译(缓存)";
            } else {
                btn.textContent = "🌐 翻译完成";
            }
            btn.disabled = true;
        } else {
            content.textContent = data?.error || "翻译失败，可能无可翻译字幕";
            btn.textContent = "⚠️ 重试";
            btn.disabled = false;
        }
    }

    // ── Search ──
    let searchDebounce;
    searchInput.addEventListener("input", () => {
        const val = searchInput.value.trim();
        searchClear.style.display = val ? "block" : "none";

        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(() => {
            state.search = val;
            state.category = "";
            categoryTags.querySelectorAll(".filter-tag").forEach((b) => b.classList.remove("active"));
            const allBtn = categoryTags.querySelector('[data-category=""]');
            if (allBtn) allBtn.classList.add("active");
            loadVideos(true);
        }, 400);
    });

    searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            searchInput.value = "";
            searchClear.style.display = "none";
            state.search = "";
            loadVideos(true);
        }
    });

    searchClear.addEventListener("click", () => {
        searchInput.value = "";
        searchClear.style.display = "none";
        state.search = "";
        loadVideos(true);
    });

    // ── Source Tabs ──
    const DEFAULT_SORT = { bilibili: "time", youtube: "score", all: "score" };
    sourceTabs.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            sourceTabs.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            state.source = tab.dataset.source;
            state.category = "";
            state.search = "";
            searchInput.value = "";
            searchClear.style.display = "none";
            // 自动切换默认排序: B站→最新, YouTube→综合
            const defaultSort = DEFAULT_SORT[state.source] || "score";
            state.sort = defaultSort;
            sortSelect.value = defaultSort;
            loadVideos(true);
        });
    });

    // ── Summary Toggle ──
    summaryToggle.addEventListener("change", () => {
        state.withSummary = summaryToggle.checked;
        loadVideos(true);
    });

    // ── Refresh ──
    refreshBtn.addEventListener("click", () => loadVideos(true));

    // ── Dark Mode ──
    darkModeBtn.addEventListener("click", toggleDarkMode);

    // ── Favorites ──
    favoritesBtn.addEventListener("click", openFavorites);
    favoritesClose.addEventListener("click", closeFavorites);

    // ── Load More ──
    loadMoreBtn.addEventListener("click", () => {
        if (state.isLoading) return;
        state.page += 1;
        loadVideos(false);
    });

    // ── Infinite Scroll ──
    let scrollTimeout;
    window.addEventListener("scroll", () => {
        if (scrollTimeout) clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
            if (!state.hasMore || state.isLoading) return;
            const rect = loadMore.getBoundingClientRect();
            if (rect.top < window.innerHeight + 300) {
                state.page += 1;
                loadVideos(false);
            }
        }, 300);
    });

    // ── Back to Top ──
    const backToTop = document.getElementById("backToTop");
    window.addEventListener("scroll", () => {
        backToTop.classList.toggle("visible", window.scrollY > 600);
    }, { passive: true });
    backToTop.addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
    });

    // ── Helpers ──
    function escapeHTML(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function escapeAttr(str) {
        return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // ── Preferences ──
    const prefOverlay = document.getElementById("prefOverlay");
    const prefPanel = document.getElementById("prefPanel");
    const prefGrid = document.getElementById("prefGrid");
    const prefBtn = document.getElementById("prefBtn");
    const prefClose = document.getElementById("prefClose");
    const prefSave = document.getElementById("prefSave");
    const essenceToggle = document.getElementById("essenceToggle");

    const DEFAULT_CATEGORIES = [
        "知识", "科学科普", "科技", "财经商业", "人文历史",
        "纪录片", "校园学习", "社科法律", "职业职场", "设计创意", "计算机技术", "数码", "资讯",
    ];

    function getPreferences() {
        try { return JSON.parse(localStorage.getItem("vc-prefs") || "[]"); } catch { return []; }
    }

    function savePreferences(prefs) {
        localStorage.setItem("vc-prefs", JSON.stringify(prefs));
    }

    function getEssenceMode() {
        return localStorage.getItem("vc-essence") === "true";
    }

    function renderPrefPanel() {
        const prefs = getPreferences();
        prefGrid.innerHTML = DEFAULT_CATEGORIES.map(c =>
            `<div class="pref-chip${prefs.includes(c) ? ' selected' : ''}" data-cat="${c}">${c}</div>`
        ).join("");
        prefGrid.querySelectorAll(".pref-chip").forEach(chip => {
            chip.addEventListener("click", () => chip.classList.toggle("selected"));
        });
    }

    function openPrefPanel() {
        renderPrefPanel();
        prefOverlay.classList.add("open");
        prefPanel.classList.add("open");
    }

    function closePrefPanel() {
        prefOverlay.classList.remove("open");
        prefPanel.classList.remove("open");
    }

    prefBtn.addEventListener("click", openPrefPanel);
    prefClose.addEventListener("click", closePrefPanel);
    prefOverlay.addEventListener("click", closePrefPanel);

    prefSave.addEventListener("click", () => {
        const selected = [...prefGrid.querySelectorAll(".pref-chip.selected")].map(c => c.dataset.cat);
        savePreferences(selected);
        closePrefPanel();
        showToast(selected.length > 0 ? `已保存 ${selected.length} 个偏好` : "已清空偏好", "success");
        loadVideos(true);
    });

    essenceToggle.checked = getEssenceMode();
    essenceToggle.addEventListener("change", () => {
        localStorage.setItem("vc-essence", essenceToggle.checked);
        loadVideos(true);
    });

    // 首次使用自动弹出偏好设置
    if (!localStorage.getItem("vc-prefs")) {
        setTimeout(openPrefPanel, 800);
    }

    // ── Time Distribution ──
    function updateTimeDistribution() {
        const td = state.timeDistribution;
        if (!td) return;
        let parts = [];
        if (td.today > 0) parts.push(`今天 ${td.today}`);
        if (td.week > 0) parts.push(`本周 ${td.week}`);
        if (td.month > 0) parts.push(`本月 ${td.month}`);
        if (td.older > 0) parts.push(`更早 ${td.older}`);
        if (parts.length > 0) {
            document.getElementById("timeDist").textContent = "🕐 " + parts.join(" · ");
            document.getElementById("timeDist").style.display = "inline";
        }
    }

    // ── Sort ──
    const savedSort = localStorage.getItem("vc-sort");
    if (savedSort && sortSelect) {
        sortSelect.value = savedSort;
        state.sort = savedSort;
    }
    sortSelect.addEventListener("change", () => {
        state.sort = sortSelect.value;
        localStorage.setItem("vc-sort", state.sort);
        loadVideos(true);
    });

    // ── Init ──
    initDarkMode();
    loadVideos(true);
})();
