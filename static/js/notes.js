/**
 * 视频笔记抽屉 v2 — 深度分析 · 嵌入播放 · 分级已看
 */
(function () {
    "use strict";

    let currentVideo = null;
    let chatHistory = [];
    let isSaving = false;
    let isWatched = false;
    let currentSubtitle = "";
    let subtitleSegments = [];
    let subtitleTimer = null;
    let isSubtitleLoaded = false;

    const $ = (sel) => document.querySelector(sel);

    const notesDrawer = $("#notesDrawer");
    const notesOverlay = $("#notesOverlay");
    const notesClose = $("#notesClose");
    const notesTitle = $("#notesTitle");
    const notesAuthor = $("#notesAuthor");
    const notesSource = $("#notesSource");
    const notesSummaryText = $("#notesSummaryText");
    const notesEditor = $("#notesEditor");
    const notesSaveBtn = $("#notesSaveBtn");
    const notesExportBtn = $("#notesExportBtn");
    const notesLinkBtn = $("#notesLinkBtn");
    const notesDoneBtn = $("#notesDoneBtn");
    const notesDuration = $("#notesDuration");
    const notesViews = $("#notesViews");
    const chatMessages = $("#chatMessages");
    const chatInput = $("#chatInput");
    const chatSendBtn = $("#chatSendBtn");
    const videoPlayerContainer = $("#videoPlayerContainer");
    const followBtn = $("#followBtn");
    const notesTranslateBtn = $("#notesTranslateBtn");
    const subtitleList = $("#subtitleList");

    const tabBtns = document.querySelectorAll(".notes-tab");
    const tabContents = document.querySelectorAll(".notes-tab-content");

    // ── Markdown Rendering ──
    function renderMarkdown(text) {
        let html = (text || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        // Timeline nodes: "- 00:00-XX:XX description"
        html = html.replace(/^- (\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s+(.+)$/gm, '<div class="timeline-node"><span class="timeline-time">$1-$2</span><span class="timeline-text">$3</span></div>');
        html = html.replace(/^- (\d{1,2}:\d{2})\s*[-~到]+\s*(\S+?)\s+(.+)$/gm, '<div class="timeline-node"><span class="timeline-time">$1-$2</span><span class="timeline-text">$3</span></div>');
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        // Remaining list items (non-timeline)
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/\n/g, '<br>');
        html = html.replace(/(<li>.*?<\/li>)/gs, '<ul>$1</ul>');
        html = html.replace(/⭐/g, '★');
        return html;
    }

    // ── Open / Close ──
    function openNotesDrawer(video) {
        try {
        currentVideo = video;
        chatHistory = [];
        chatMessages.innerHTML = '<div class="chat-empty">输入问题，AI 将根据视频内容为你解答</div>';
        notesEditor.value = "";
        showEmptyGuide(true);
        notesSummaryText.innerHTML = "";
        subtitleList.innerHTML = '<span class="dot-pulse">正在加载字幕</span>';
        subtitleSegments = [];
        isSubtitleLoaded = false;
        if (subtitleTimer) { clearInterval(subtitleTimer); subtitleTimer = null; }
        notesTranslateBtn.disabled = false;
        // 按钮文案随来源变化
        if (video.source === "bilibili") {
            notesTranslateBtn.textContent = "📄 查看字幕";
            notesTranslateBtn.style.display = "";
        } else {
            notesTranslateBtn.textContent = "🌐 翻译字幕";
            notesTranslateBtn.style.display = (video.source === "youtube") ? "" : "none";
        }
        isWatched = isVideoWatched(video.id);

        // Header
        notesTitle.textContent = video.title || "";
        notesAuthor.textContent = "👤 " + (video.author || "");
        notesSource.textContent = video.source === "bilibili" ? "B站" : video.source === "youtube" ? "YouTube" : video.source || "";
        notesSource.className = "notes-source-tag " + (video.source === "bilibili" ? "bilibili" : "youtube");
        notesDuration.textContent = video.duration ? "⏱ " + video.duration : "";
        notesViews.textContent = video.views ? "👁 " + video.views : "";
        notesLinkBtn.href = video.url || "#";

        // Update done button state
        updateDoneButton();

        // Setup follow button
        setupFollowButton(video.author);

        // Setup video player
        setupVideoPlayer(video);

        // Load saved notes
        loadNotes(video.id);

        // Fetch subtitle (async, don't block UI)
        fetchSubtitle(video).then(() => {
            fetchDeepAnalysis(video);
        });

        // Record to view history (no badge)
        recordViewHistory(video.id);

        // Tab: default to note
        switchTab("note");

        // Open
        notesDrawer.classList.add("open");
        notesOverlay.classList.add("open");
        document.body.style.overflow = "hidden";

        // Focus editor after transition (skip if hidden)
        setTimeout(() => {
            if (notesEditor.style.display !== "none") notesEditor.focus();
        }, 300);
        } catch (e) {
            console.error("openNotesDrawer 出错:", e);
        }
    }

    function closeNotesDrawer() {
        notesDrawer.classList.remove("open");
        notesOverlay.classList.remove("open");
        document.body.style.overflow = "";
        videoPlayerContainer.innerHTML = "";
        if (subtitleTimer) { clearInterval(subtitleTimer); subtitleTimer = null; }
        currentVideo = null;
    }

    window.openNotesDrawer = openNotesDrawer;
    notesClose.addEventListener("click", closeNotesDrawer);
    notesOverlay.addEventListener("click", closeNotesDrawer);
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && notesDrawer.classList.contains("open")) {
            closeNotesDrawer();
        }
    });

    // ── Video Player ──
    function setupVideoPlayer(video) {
        videoPlayerContainer.innerHTML = "";
        const embedId = video.embed_id || video.youtube_id || "";
        if (!embedId) {
            videoPlayerContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:14px">暂无嵌入播放地址<br><a href="' + (video.url || '#') + '" target="_blank" style="color:var(--accent);margin-top:8px">🔗 点此观看</a></div>';
            return;
        }
        let embedHtml = "";
        if (video.embed_src === "bilibili" || video.source === "bilibili") {
            embedHtml = '<iframe src="https://player.bilibili.com/player.html?bvid=' + embedId + '&autoplay=0&poster=1" allowfullscreen scrolling="no" frameborder="0"></iframe>';
        } else {
            embedHtml = '<iframe src="https://www.youtube.com/embed/' + embedId + '?autoplay=0&rel=0&enablejsapi=1" allowfullscreen allow="autoplay; encrypted-media" frameborder="0" id="youtubePlayer"></iframe>';
        }
        videoPlayerContainer.innerHTML = embedHtml;
    }

    // ── Load / Save Notes ──
    async function loadNotes(videoId) {
        try {
            const data = await fetchAPI("/api/notes/" + encodeURIComponent(videoId));
            if (data && data.notes) {
                notesEditor.value = data.notes || "";
                showEmptyGuide(false);
                if (data.chat_history && data.chat_history.length > 0) {
                    chatHistory = data.chat_history;
                    renderChatHistory();
                }
                if (data.ai_summary) {
                    notesSummaryText.innerHTML = renderMarkdown(data.ai_summary);
                }
            }
        } catch (e) {
            console.error("加载笔记失败:", e);
        }
    }

    notesSaveBtn.addEventListener("click", async () => {
        if (!currentVideo || isSaving) return;
        isSaving = true;
        notesSaveBtn.textContent = "⏳ 保存中...";

        const summaryContent = notesSummaryText.textContent;

        const payload = {
            video_id: currentVideo.id,
            title: currentVideo.title,
            author: currentVideo.author,
            url: currentVideo.url,
            source: currentVideo.source,
            category: currentVideo.category,
            notes: notesEditor.value,
            ai_summary: summaryContent,
            chat_history: chatHistory,
            viewed_at: [new Date().toISOString()],
        };

        try {
            const resp = await fetch("/api/notes/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (data.status === "ok") {
                markAsWatched(currentVideo.id);
                showToast("笔记已保存", "success");
            } else {
                showToast("保存失败", "error");
            }
        } catch (e) {
            showToast("保存失败，请检查网络", "error");
        }
        isSaving = false;
        notesSaveBtn.textContent = "💾 保存";
    });

    // ── Export ──
    notesExportBtn.addEventListener("click", async () => {
        if (!currentVideo) return;
        notesExportBtn.textContent = "⏳ 导出中...";

        const payload = {
            video_id: currentVideo.id,
            title: currentVideo.title,
            author: currentVideo.author,
            url: currentVideo.url,
            source: currentVideo.source,
            category: currentVideo.category,
            notes: notesEditor.value,
        };

        try {
            const resp = await fetch("/api/notes/export", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (data.status === "ok") {
                markAsWatched(currentVideo.id);
                showToast("已导出到桌面", "success");
            } else {
                showToast("导出失败", "error");
            }
        } catch (e) {
            showToast("导出失败，请检查网络", "error");
        }
        notesExportBtn.textContent = "📂 导出到桌面";
    });

    // ── Mark Watched (Done Button) ──
    notesDoneBtn.addEventListener("click", () => {
        if (!currentVideo) return;
        markAsWatched(currentVideo.id);
    });

    function markAsWatched(videoId) {
        const watched = getWatchedVideoIds();
        if (!watched.includes(videoId)) {
            watched.push(videoId);
            localStorage.setItem("vc-watched", JSON.stringify(watched.slice(-200)));
        }
        isWatched = true;
        updateDoneButton();
        updateWatchedBadges();
    }

    function isVideoWatched(videoId) {
        return getWatchedVideoIds().includes(videoId);
    }

    function getWatchedVideoIds() {
        try { return JSON.parse(localStorage.getItem("vc-watched") || "[]"); } catch { return []; }
    }

    function updateDoneButton() {
        if (isWatched) {
            notesDoneBtn.textContent = "✅ 已看完";
            notesDoneBtn.classList.add("marked");
        } else {
            notesDoneBtn.textContent = "✅ 标记已看完";
            notesDoneBtn.classList.remove("marked");
        }
    }

    function updateWatchedBadges() {
        const watched = getWatchedVideoIds();
        document.querySelectorAll(".video-card").forEach(card => {
            const vid = card.dataset.videoId;
            const badge = card.querySelector(".card-viewed-badge");
            if (watched.includes(vid)) {
                if (!badge) {
                    const b = document.createElement("span");
                    b.className = "card-viewed-badge";
                    b.textContent = "✅ 已看";
                    const thumb = card.querySelector(".card-thumb");
                    if (thumb) thumb.appendChild(b);
                }
            } else if (badge) {
                badge.remove();
            }
        });
    }
    window.updateWatchedBadges = updateWatchedBadges;

    // ── View History (no badge, just tracking) ──
    function recordViewHistory(videoId) {
        try {
            const history = JSON.parse(localStorage.getItem("vc-history") || "[]");
            if (!history.some(h => h.id === videoId)) {
                history.unshift({ id: videoId, time: new Date().toISOString() });
                localStorage.setItem("vc-history", JSON.stringify(history.slice(-100)));
            }
        } catch { /* ignore */ }
    }

    // ── Follow / Subscribe ──
    function getFollowedAuthors() {
        try { return JSON.parse(localStorage.getItem("vc-following") || "[]"); } catch { return []; }
    }

    function isFollowing(author) {
        return getFollowedAuthors().includes(author);
    }

    function setupFollowButton(author) {
        if (!author || !followBtn) return;
        followBtn.style.display = "";
        if (isFollowing(author)) {
            followBtn.textContent = "🔔 已关注";
            followBtn.classList.add("following");
        } else {
            followBtn.textContent = "🔔 关注";
            followBtn.classList.remove("following");
        }
        followBtn.onclick = () => toggleFollow(author);
    }

    function toggleFollow(author) {
        if (!author) return;
        let following = getFollowedAuthors();
        if (following.includes(author)) {
            following = following.filter(a => a !== author);
            showToast("已取消关注 " + author);
        } else {
            following.push(author);
            showToast("已关注 " + author, "success");
        }
        localStorage.setItem("vc-following", JSON.stringify(following));
        setupFollowButton(author);
    }

    window.getFollowedAuthors = getFollowedAuthors;
    window.isFollowing = isFollowing;

    // ── Subtitle Fetch ──
    async function fetchSubtitle(video) {
        currentSubtitle = "";
        const embedId = video.embed_id || video.youtube_id || "";
        if (!embedId) return;
        try {
            const params = new URLSearchParams({
                source: video.source || "",
                embed_id: embedId,
            });
            const data = await fetchAPI("/api/transcript?" + params.toString());
            if (data && data.text) {
                currentSubtitle = data.text;
            }
        } catch (e) {
            console.error("字幕获取失败:", e);
        }
    }
    async function fetchDeepAnalysis(video) {
        try {
            const params = new URLSearchParams({
                title: video.title, description: video.description || "",
                author: video.author, category: video.category || "",
                duration: video.duration || "", duration_sec: video.duration_seconds || 0,
                subtitle_text: currentSubtitle || "",
            });
            const data = await fetchAPI("/api/analyze?" + params.toString());
            if (data && data.analysis) {
                notesSummaryText.innerHTML = renderMarkdown(data.analysis);
                switchTab("analysis");  // 自动跳转到分析Tab展示结果
            } else {
                fetchQuickSummary(video);
            }
        } catch (e) {
            fetchQuickSummary(video);
        }
    }

    async function fetchQuickSummary(video) {
        try {
            const params = new URLSearchParams({
                video_id: video.id, source: video.source,
                title: video.title, description: video.description || "", author: video.author,
            });
            const data = await fetchAPI("/api/summarize?" + params.toString());
            if (data && data.summary) {
                notesSummaryText.textContent = data.summary;
            } else {
                notesSummaryText.textContent = "摘要暂不可用";
            }
        } catch (e) {
            notesSummaryText.textContent = "摘要生成失败";
        }
    }

    // ── Subtitle Time Sync ──
    function renderSubtitleSegments(segments, translation) {
        subtitleSegments = segments;
        isSubtitleLoaded = true;
        if (!segments.length) {
            subtitleList.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px">无可同步的字幕数据</div>';
            return;
        }
        let html = '';
        if (translation) {
            html += '<div class="subtitle-translation">' + translation.replace(/\n/g, '<br>') + '</div>';
            html += '<div class="subtitle-divider">━━ 时间轴字幕 ━━</div>';
        }
        segments.forEach((seg, i) => {
            const time = formatTime(seg.start);
            html += `<div class="subtitle-row" data-index="${i}" data-start="${seg.start}" data-end="${seg.start + (seg.duration || 3)}">
                <span class="subtitle-time">${time}</span>
                <span class="subtitle-text">${escapeHTML(seg.original || '')}</span>
            </div>`;
        });
        subtitleList.innerHTML = html;
        startSubtitleSync();
    }

    function escapeHTML(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
    function formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return m + ':' + String(s).padStart(2, '0');
    }

    function startSubtitleSync() {
        if (subtitleTimer) clearInterval(subtitleTimer);
        subtitleTimer = setInterval(() => {
            const time = getPlayerCurrentTime();
            if (time == null) return;
            const rows = subtitleList.querySelectorAll(".subtitle-row");
            let activeIdx = -1;
            for (const row of rows) {
                const start = parseFloat(row.dataset.start);
                const end = parseFloat(row.dataset.end);
                if (time >= start && time <= end) {
                    row.classList.add("active");
                    row.scrollIntoView({ behavior: "smooth", block: "center" });
                    activeIdx = parseInt(row.dataset.index);
                } else {
                    row.classList.remove("active");
                }
            }
        }, 500);
    }

    function getPlayerCurrentTime() {
        const iframe = videoPlayerContainer.querySelector("iframe");
        if (!iframe || !iframe.contentWindow) return null;
        try {
            iframe.contentWindow.postMessage(JSON.stringify({
                event: "command",
                func: "getCurrentTime",
                args: []
            }), "*");
        } catch (e) {}
        return window._ytCurrentTime ?? null;
    }

    // Listen for YouTube player command responses
    (function() {
        window.addEventListener("message", (e) => {
            try {
                const d = JSON.parse(e.data);
                if (d.event === "commandResult" && d.func === "getCurrentTime" && typeof d.result === "number") {
                    window._ytCurrentTime = d.result;
                }
            } catch {}
        });
    })();

    // ── Tab Switching ──
    function switchTab(tab) {
        tabBtns.forEach(b => b.classList.toggle("active", b.dataset.notesTab === tab));
        tabContents.forEach(c => c.classList.toggle("active", c.id === "notesTab" + tab.charAt(0).toUpperCase() + tab.slice(1)));
        // 切换到非字幕tab时停止时间同步
        if (tab !== "subtitle" && subtitleTimer) {
            clearInterval(subtitleTimer);
            subtitleTimer = null;
        }
    }
    tabBtns.forEach(btn => btn.addEventListener("click", () => switchTab(btn.dataset.notesTab)));

    // ── Collapsible / Old Analysis Cleanup ──
    // (已移至右侧Tab, 不再需要折叠逻辑)

    // ── Empty Guide ──
    function showEmptyGuide(show) {
        const guide = document.getElementById("notesEmptyGuide");
        const editor = document.getElementById("notesEditor");
        if (guide) guide.style.display = show ? "flex" : "none";
        if (editor) editor.style.display = show ? "none" : "block";
    }
    notesEditor.addEventListener("input", () => {
        showEmptyGuide(notesEditor.value.trim().length === 0);
    });
    // 点击空引导 → 激活编辑器
    const emptyGuide = document.getElementById("notesEmptyGuide");
    if (emptyGuide) {
        emptyGuide.addEventListener("click", () => {
            showEmptyGuide(false);
            notesEditor.focus();
        });
    }

    // ── Transcript / Subtitle ──
    notesTranslateBtn.addEventListener("click", async () => {
        if (!currentVideo) return;
        notesTranslateBtn.disabled = true;
        notesTranslateBtn.textContent = "⏳ 加载中...";
        switchTab("subtitle");
        subtitleList.innerHTML = '<span class="dot-pulse">正在获取字幕</span>';

        if (currentVideo.source === "bilibili") {
            // B站: 直接拉时间轴字幕, 无需翻译
            const params = new URLSearchParams({
                video_id: currentVideo.id,
                source: currentVideo.source,
                embed_id: currentVideo.embed_id || "",
            });
            const data = await fetchAPI("/api/translate?" + params.toString());
            if (data && data.segments && data.segments.length) {
                renderSubtitleSegments(data.segments, "");
            } else {
                subtitleList.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px">此视频无可提取的字幕（仅部分UP上传字幕）</div>';
            }
            notesTranslateBtn.textContent = "📄 查看字幕";
            notesTranslateBtn.disabled = false;
            return;
        }

        // YouTube: 翻译 + 分段
        const params = new URLSearchParams({
            video_id: currentVideo.id,
            source: currentVideo.source,
            embed_id: currentVideo.embed_id || currentVideo.youtube_id || "",
        });
        const data = await fetchAPI("/api/translate?" + params.toString());
        if (data && data.translation && data.segments) {
            renderSubtitleSegments(data.segments, data.translation);
            notesTranslateBtn.textContent = data.cached ? "🌐 已翻译(缓存)" : "🌐 翻译完成";
        } else {
            subtitleList.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px">' + (data?.error || "无可翻译字幕（可能无英文字幕）") + '</div>';
            notesTranslateBtn.textContent = "⚠️ 重试";
            notesTranslateBtn.disabled = false;
        }
    });
})();
