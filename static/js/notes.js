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

    const $ = (sel) => document.querySelector(sel);

    const notesDrawer = $("#notesDrawer");
    const notesOverlay = $("#notesOverlay");
    const notesClose = $("#notesClose");
    const notesTitle = $("#notesTitle");
    const notesAuthor = $("#notesAuthor");
    const notesSource = $("#notesSource");
    const notesSummaryText = $("#notesSummaryText");
    const notesSummaryStatus = $("#notesSummaryStatus");
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
        currentVideo = video;
        chatHistory = [];
        chatMessages.innerHTML = '<div class="chat-empty">输入问题，AI 将根据视频内容为你解答</div>';
        notesEditor.value = "";
        notesSummaryText.innerHTML = "";
        notesSummaryStatus.textContent = "正在深度分析...";
        notesSummaryStatus.style.display = "";
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

        // Focus editor after transition
        setTimeout(() => notesEditor.focus(), 300);
    }

    function closeNotesDrawer() {
        notesDrawer.classList.remove("open");
        notesOverlay.classList.remove("open");
        document.body.style.overflow = "";
        videoPlayerContainer.innerHTML = "";
        currentVideo = null;
    }

    window.openNotesDrawer = openNotesDrawer;

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
            embedHtml = '<iframe src="https://www.youtube.com/embed/' + embedId + '?autoplay=0&rel=0" allowfullscreen allow="autoplay; encrypted-media" frameborder="0"></iframe>';
        }
        videoPlayerContainer.innerHTML = embedHtml;
    }

    // ── Load / Save Notes ──
    async function loadNotes(videoId) {
        try {
            const data = await fetchAPI("/api/notes/" + encodeURIComponent(videoId));
            if (data && data.notes) {
                notesEditor.value = data.notes || "";
                if (data.chat_history && data.chat_history.length > 0) {
                    chatHistory = data.chat_history;
                    renderChatHistory();
                }
                if (data.ai_summary) {
                    notesSummaryText.innerHTML = renderMarkdown(data.ai_summary);
                    notesSummaryStatus.style.display = "none";
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
                notesSummaryStatus.style.display = "none";
            } else {
                // Fallback to short summary
                notesSummaryStatus.textContent = "深度分析不可用，尝试快速摘要...";
                fetchQuickSummary(video);
            }
        } catch (e) {
            notesSummaryStatus.textContent = "深度分析不可用，尝试快速摘要...";
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
                notesSummaryStatus.style.display = "none";
            } else {
                notesSummaryText.textContent = "摘要暂不可用";
                notesSummaryStatus.style.display = "none";
            }
        } catch (e) {
            notesSummaryText.textContent = "摘要生成失败";
            notesSummaryStatus.style.display = "none";
        }
    }

    // ── Chat ──
    chatSendBtn.addEventListener("click", sendChatMessage);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    async function sendChatMessage() {
        if (!currentVideo) return;
        const message = chatInput.value.trim();
        if (!message) return;

        chatInput.value = "";
        chatInput.disabled = true;
        chatSendBtn.disabled = true;

        addChatBubble("user", message);
        chatHistory.push({ role: "user", content: message, time: new Date().toISOString() });

        const placeholder = addChatBubble("assistant", "思考中...");
        const placeholderIdx = chatHistory.length;
        chatHistory.push({ role: "assistant", content: "", time: "" });

        try {
            const resp = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: message,
                    title: currentVideo.title,
                    description: currentVideo.description || "",
                    author: currentVideo.author || "",
                    subtitle_text: currentSubtitle || "",
                    chat_history: chatHistory.slice(0, -1),
                }),
            });
            const data = await resp.json();
            if (data && data.reply) {
                placeholder.textContent = data.reply;
                chatHistory[placeholderIdx] = { role: "assistant", content: data.reply, time: new Date().toISOString() };
            } else {
                placeholder.textContent = "抱歉，暂时无法回复。";
                chatHistory[placeholderIdx] = { role: "assistant", content: "回复失败", time: new Date().toISOString() };
            }
        } catch (e) {
            placeholder.textContent = "网络错误，请重试。";
        }

        chatInput.disabled = false;
        chatSendBtn.disabled = false;
        chatInput.focus();
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addChatBubble(role, content) {
        if (chatMessages.querySelector(".chat-empty")) {
            chatMessages.innerHTML = "";
        }
        const el = document.createElement("div");
        el.className = "chat-message " + role;
        el.textContent = content;
        chatMessages.appendChild(el);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return el;
    }

    function renderChatHistory() {
        chatMessages.innerHTML = "";
        chatHistory.forEach(h => addChatBubble(h.role, h.content));
    }

    // ── Tab Switching ──
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            switchTab(btn.dataset.notesTab);
        });
    });

    function switchTab(tab) {
        tabBtns.forEach(b => b.classList.toggle("active", b.dataset.notesTab === tab));
        tabContents.forEach(c => c.classList.toggle("active", c.id === "notesTab" + tab.charAt(0).toUpperCase() + tab.slice(1)));
    }

    // ── Close ──
    notesClose.addEventListener("click", closeNotesDrawer);
    notesOverlay.addEventListener("click", closeNotesDrawer);
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && notesDrawer.classList.contains("open")) {
            closeNotesDrawer();
        }
    });

    // ── Helpers ──
    async function fetchAPI(path) {
        try {
            const resp = await fetch(path);
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            return await resp.json();
        } catch (err) {
            console.error("API error:", err);
            return null;
        }
    }

    function showToast(msg, type) {
        const container = document.getElementById("toastContainer");
        if (!container) return;
        const toast = document.createElement("div");
        toast.className = "toast " + (type || "");
        toast.textContent = msg;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3200);
    }
})();
