/* ═══════════════════════════════════════════════════════════════
   Bhasha Setu — Reusable UI Components
   Pure HTML string builders for dynamic content
   ═══════════════════════════════════════════════════════════════ */

const Components = {

    /* ── Language Color Map ── */
    langColors: {
        'Hindi':     '#E05C1A',
        'Tamil':     '#C0392B',
        'Telugu':    '#7B2FBE',
        'Kannada':   '#0891B2',
        'Malayalam': '#059669',
        'Bengali':   '#D97706',
        'Marathi':   '#BE185D',
        'Gujarati':  '#0D9488',
        'Punjabi':   '#4F46E5',
        'Urdu':      '#65A30D',
        'Odia':      '#0284C7',
        'Assamese':  '#EA580C',
    },

    /* ── Language Short Codes ── */
    langShort: {
        'Hindi':'HI', 'Tamil':'TA', 'Telugu':'TE', 'Kannada':'KN',
        'Malayalam':'ML', 'Bengali':'BN', 'Marathi':'MR', 'Gujarati':'GU',
        'Punjabi':'PB', 'Urdu':'UR', 'Odia':'OD', 'Assamese':'AS',
    },

    /**
     * Render a coloured language badge.
     * @param {string} name - Language name (e.g. "Hindi")
     * @param {number} size - Badge size in px (default 40)
     * @returns {string} HTML string
     */
    langBadge(name, size = 40) {
        const s = this.langShort[name] || name.slice(0, 2).toUpperCase();
        const c = this.langColors[name] || '#6366F1';
        return `<div class="lang-badge" style="--badge-color:${c};--badge-size:${size}px">${s}</div>`;
    },

    /**
     * Render the language indicator strip (Auto-detect → Target).
     * @param {string} targetName - Target language name
     * @returns {string} HTML string
     */
    langStrip(targetName) {
        if (!targetName) return '';
        const badge = this.langBadge(targetName, 32);
        return `
            <div class="lang-strip">
                <span>🌍 Auto-detect</span>
                <span class="lang-strip-arrow">→</span>
                ${badge}
                <span>${targetName}</span>
            </div>`;
    },

    /**
     * Render the 5-stage pipeline progress dashboard.
     * @param {Array} stages - Array of 5 objects: [{pct:number, msg:string}, ...]
     * @param {number} currentStage - 1-indexed current active stage
     * @param {string} label - Status label text
     * @param {boolean} done - Whether the job is complete
     * @param {boolean} error - Whether the job errored
     * @returns {string} HTML string
     */
    progressDashboard(stages, currentStage, label, done, error) {
        const stageNames  = ['Upload', 'Transcribe', 'Translate', 'Synthesize', 'Mux'];
        const stageIcons  = ['📤', '🎙️', '🌐', '🔊', '🎬'];
        const stageColors = ['f1', 'f2', 'f3', 'f4', 'f5'];
        const overall = Math.round(stages.reduce((a, s) => a + (s.pct || 0), 0) / 5);

        let stagesHtml = '';
        for (let i = 0; i < 5; i++) {
            const pct = Math.min(100, Math.round(stages[i]?.pct || 0));
            const msg = stages[i]?.msg || 'Waiting…';
            const isActive = (i + 1) === currentStage && !done && !error;
            const isDone = pct >= 100;
            stagesHtml += `
                <div class="stage-row">
                    <div class="stage-icon ${isActive ? 'active' : ''}">${isDone ? '✅' : stageIcons[i]}</div>
                    <div class="stage-info">
                        <div class="stage-header">
                            <span class="stage-name">${stageNames[i]}</span>
                            <span class="stage-pct">${pct}%</span>
                        </div>
                        <div class="stage-track">
                            <div class="stage-fill ${stageColors[i]}" style="width:${pct}%"></div>
                        </div>
                        <div class="stage-msg">${msg}</div>
                    </div>
                </div>`;
        }

        const statusIcon = done ? '✅' : (error ? '❌' : '⚙️');
        const stateClass = done ? 'done' : (error ? 'error' : '');

        let cancelBtnHtml = '';
        if (!done && !error) {
            cancelBtnHtml = `
                <div class="cancel-container" style="text-align: center; margin-top: 1.5rem; display: flex; justify-content: center;">
                    <button id="cancel-dub-btn" class="select" style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: #fca5a5; padding: 10px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; font-size: 0.9rem; transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.1);">
                        <span>🛑</span> Cancel Dubbing
                    </button>
                </div>`;
        }

        return `
            <div class="progress-dashboard ${stateClass}">
                <div class="pdash-header">
                    <span>${statusIcon} ${label}</span>
                    <span class="pdash-overall">${overall}%</span>
                </div>
                ${stagesHtml}
                ${cancelBtnHtml}
            </div>`;
    },

    /**
     * Render a chat message bubble.
     * @param {string} role - 'user' or 'assistant'
     * @param {string} content - Message text
     * @param {string} time - Display time string
     * @returns {string} HTML string
     */
    chatMessage(role, content, time) {
        const escaped = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');

        if (role === 'user') {
            return `
                <div class="chat-msg chat-msg-user">
                    <div>
                        <div class="chat-bubble user-bubble">${escaped}</div>
                        <div class="chat-meta" style="text-align:right">You · ${time}</div>
                    </div>
                </div>`;
        }

        return `
            <div class="chat-msg chat-msg-ai">
                <div class="chat-avatar">🪷</div>
                <div>
                    <div class="chat-bubble ai-bubble">${escaped}</div>
                    <div class="chat-meta">Bhasha Setu AI · ${time}</div>
                </div>
            </div>`;
    },

    /**
     * Render a feature showcase card.
     * @param {string} icon - Emoji icon
     * @param {string} title - Feature title
     * @param {string} desc - Feature description
     * @param {number} delay - Animation delay in seconds
     * @returns {string} HTML string
     */
    featureCard(icon, title, desc, delay) {
        return `
            <div class="feature-card" style="animation-delay:${delay}s">
                <div class="feature-icon">${icon}</div>
                <div class="feature-title">${title}</div>
                <div class="feature-desc">${desc}</div>
            </div>`;
    },

    /**
     * Render a success result card with download button.
     * @param {string} jobId - Job identifier
     * @param {string} language - Target language name
     * @param {string} downloadUrl - URL to download the video
     * @returns {string} HTML string
     */
    resultCard(jobId, language, downloadUrl) {
        return `
            <div class="result-card">
                <div class="result-icon">✅</div>
                <div>
                    <div class="result-title">Dubbing Complete</div>
                    <div class="result-sub">Job ${jobId} · ${language}</div>
                </div>
            </div>
            <a href="${downloadUrl}" class="btn btn-primary download-btn" download>
                ⬇️ Download Dubbed Video
            </a>`;
    },

    /**
     * Render a history entry card.
     * @param {Object} entry - {job_id, language, timestamp}
     * @param {number} index - Index for animation delay
     * @returns {string} HTML string
     */
    historyCard(entry, index) {
        const color = this.langColors[entry.language] || '#6366F1';
        const short = this.langShort[entry.language] || '??';
        const ts = (entry.timestamp || '').slice(0, 16).replace('T', ' ');
        return `
            <div class="history-card" style="animation-delay:${index * 0.03}s">
                <div class="history-left">
                    <div class="lang-badge" style="--badge-color:${color};--badge-size:36px">${short}</div>
                    <div>
                        <div class="history-lang">${entry.language}</div>
                        <div class="history-meta">Job ${entry.job_id} · ${ts}</div>
                    </div>
                </div>
                <a href="${API.getDownloadUrl(entry.job_id)}" class="btn-icon" title="Download">⬇️</a>
            </div>`;
    },
};
