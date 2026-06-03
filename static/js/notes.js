/**
 * 视频笔记抽屉 v3 — 极简版
 * 功能: 嵌入播放 + AI分析 + 笔记编辑 + 保存/导出
 */
(function () {
    "use strict";

    let currentVideo = null;
    let isSaving = false;

    const $ = (sel) => document.querySelector(sel);

    const notesDrawer = $("#notesDrawer");
    const notesOverlay = $("#notesOverlay");
    const notesClose = $("#notesClose");
    const notesTitle = $("#notesTitle");
    const notesAuthor = $("#notesAuthor");
    const notesDuration = $("#notesDuration");
    const notesViews = $("#notesViews");
    const notesLinkBtn = $("#notesLinkBtn");
    const notesEditor = $("#notesEditor");
    const notesSummaryText = $("#notesSummaryText");
    const notesSaveBtn = $("#notesSaveBtn");
    const notesExportBtn = $("#notesExportBtn");
    const videoPlayerContainer = $("#videoPlayerContainer");

    if (!notesDrawer) { console.error("notesDrawer not found"); return; }

    function escapeHTML(str) {
        var div = document.createElement("div");
        div.textContent = str || "";
        return div.innerHTML;
    }

    function renderMarkdown(text) {
        var html = (text || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/\n/g, '<br>');
        html = html.replace(/(<li>.*?<\/li>)/gs, '<ul>$1</ul>');
        html = html.replace(/⭐/g, '★');
        return html;
    }

    async function fetchAPI(path) {
        try {
            var resp = await fetch(path);
            if (!resp.ok) return null;
            return await resp.json();
        } catch (e) { return null; }
    }

    // ── Open ──
    window.openNotesDrawer = function (video) {
        currentVideo = video;
        notesEditor.value = "";
        notesSummaryText.innerHTML = '<span style="color:var(--text-muted)">正在生成分析...</span>';

        notesTitle.textContent = video.title || "";
        notesAuthor.textContent = (video.author || "");
        notesDuration.textContent = video.duration || "";
        notesViews.textContent = video.views || "";
        notesLinkBtn.href = video.url || "#";

        setupVideoPlayer(video);
        loadNotes(video.id);
        fetchAnalysis(video);

        notesDrawer.classList.add("open");
        if (notesOverlay) notesOverlay.classList.add("open");
        document.body.style.overflow = "hidden";
    };

    function setupVideoPlayer(video) {
        videoPlayerContainer.innerHTML = "";
        var embedId = video.embed_id || video.youtube_id || "";
        if (!embedId) {
            videoPlayerContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#999;font-size:14px">暂无嵌入播放地址</div>';
            return;
        }
        if (video.source === "bilibili") {
            videoPlayerContainer.innerHTML = '<iframe src="https://player.bilibili.com/player.html?bvid=' + embedId + '&autoplay=0" allowfullscreen frameborder="0"></iframe>';
        } else {
            videoPlayerContainer.innerHTML = '<iframe src="https://www.youtube.com/embed/' + embedId + '?autoplay=0" allowfullscreen allow="autoplay" frameborder="0"></iframe>';
        }
    }

    // ── Close ──
    function closeDrawer() {
        notesDrawer.classList.remove("open");
        if (notesOverlay) notesOverlay.classList.remove("open");
        document.body.style.overflow = "";
        videoPlayerContainer.innerHTML = "";
        currentVideo = null;
    }

    notesClose.addEventListener("click", closeDrawer);
    if (notesOverlay) notesOverlay.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && notesDrawer.classList.contains("open")) {
            closeDrawer();
        }
    });

    // ── AI Analysis ──
    async function fetchAnalysis(video) {
        var params = new URLSearchParams({
            title: video.title, description: video.description || "",
            author: video.author, category: video.category || "",
            duration: video.duration || "", duration_sec: video.duration_seconds || 0,
        });
        var data = await fetchAPI("/api/analyze?" + params.toString());
        if (data && data.analysis) {
            notesSummaryText.innerHTML = renderMarkdown(data.analysis);
        } else {
            // fallback to summary
            var sparams = new URLSearchParams({
                video_id: video.id, source: video.source,
                title: video.title, description: video.description || "", author: video.author,
            });
            var sdata = await fetchAPI("/api/summarize?" + sparams.toString());
            notesSummaryText.innerHTML = sdata && sdata.summary ? sdata.summary : "分析暂不可用";
        }
    }

    // ── Notes Persistence ──
    async function loadNotes(videoId) {
        try {
            var data = await fetchAPI("/api/notes/" + encodeURIComponent(videoId));
            if (data && data.notes) {
                notesEditor.value = data.notes;
            }
        } catch (e) { /* ignore */ }
    }

    notesSaveBtn.addEventListener("click", async function () {
        if (!currentVideo || isSaving) return;
        isSaving = true;
        notesSaveBtn.textContent = "⏳ 保存中...";
        var payload = {
            video_id: currentVideo.id, title: currentVideo.title,
            author: currentVideo.author, url: currentVideo.url,
            source: currentVideo.source, category: currentVideo.category,
            notes: notesEditor.value,
            ai_summary: notesSummaryText.textContent,
        };
        try {
            var resp = await fetch("/api/notes/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            var data = await resp.json();
            if (data && data.status === "ok") {
                notesSaveBtn.textContent = "✅ 已保存";
                setTimeout(function () { notesSaveBtn.textContent = "💾 保存"; }, 1500);
            }
        } catch (e) { /* ignore */ }
        isSaving = false;
    });

    notesExportBtn.addEventListener("click", async function () {
        if (!currentVideo) return;
        notesExportBtn.textContent = "⏳ 导出中...";
        var payload = {
            video_id: currentVideo.id, title: currentVideo.title,
            author: currentVideo.author, source: currentVideo.source,
            notes: notesEditor.value, ai_summary: notesSummaryText.textContent,
        };
        try {
            var resp = await fetch("/api/notes/export", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            var data = await resp.json();
            notesExportBtn.textContent = data && data.status === "ok" ? "✅ 已导出" : "❌ 失败";
            setTimeout(function () { notesExportBtn.textContent = "📂 导出"; }, 2000);
        } catch (e) { notesExportBtn.textContent = "📂 导出"; }
    });
})();
