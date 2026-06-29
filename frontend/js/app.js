/* ═══════════════════════════════════════════════════════════════
   Bhasha Setu — Main Application Script
   Coordinates UI rendering, event handling, state, and API routing.
   ═══════════════════════════════════════════════════════════════ */

const App = {
    state: {
        darkMode: localStorage.getItem('darkMode') !== 'false',
        currentTab: 'home',
        languages: [],
        currentJob: null,
        chatHistory: JSON.parse(localStorage.getItem('chatHistory') || '[]'),
        dubHistory: JSON.parse(localStorage.getItem('dubHistory') || '[]'),
        transcript: localStorage.getItem('transcriptContext') || '', // persistent context
    },

    async init() {
        // Theme initialization
        if (!this.state.darkMode) {
            document.body.classList.add('light');
        } else {
            document.body.classList.remove('light');
        }
        this.updateThemeButton();

        // Load supported languages
        try {
            this.state.languages = await API.getLanguages();
        } catch (e) {
            console.warn('API getLanguages failed, using fallback registry:', e);
            this.state.languages = [
                { name: 'Hindi', native_name: 'हिन्दी', tts_engine: 'edge', flag: 'IN' },
                { name: 'Tamil', native_name: 'தமிழ்', tts_engine: 'edge', flag: 'IN' },
                { name: 'Telugu', native_name: 'తెలుగు', tts_engine: 'edge', flag: 'IN' },
                { name: 'Kannada', native_name: 'ಕನ್ನಡ', tts_engine: 'edge', flag: 'IN' },
                { name: 'Malayalam', native_name: 'മലയാളം', tts_engine: 'edge', flag: 'IN' },
                { name: 'Bengali', native_name: 'বাংলা', tts_engine: 'edge', flag: 'IN' },
                { name: 'Marathi', native_name: 'मराठी', tts_engine: 'edge', flag: 'IN' },
                { name: 'Gujarati', native_name: 'ગુજરાતી', tts_engine: 'edge', flag: 'IN' },
                { name: 'Punjabi', native_name: 'ਪੰਜਾਬੀ', tts_engine: 'gtts', flag: 'IN' },
                { name: 'Urdu', native_name: 'اردو', tts_engine: 'edge', flag: 'IN' },
                { name: 'Odia', native_name: 'ଓଡ଼ିଆ', tts_engine: 'gtts', flag: 'IN' },
                { name: 'Assamese', native_name: 'অসমীয়া', tts_engine: 'gtts', flag: 'IN' },
                { name: 'English', native_name: 'English', tts_engine: 'edge', flag: 'US' },
            ];
        }

        // Setup DOM event handlers
        this.setupNav();
        this.setupThemeToggle();
        this.setupFormEvents();
        this.setupDragAndDrop();
        this.setupTranslateEvents();
        this.setupChatEvents();

        // Route to deep-linked or default tab
        const initialTab = location.hash.slice(1) || 'home';
        this.navigateTo(initialTab);
    },

    setupNav() {
        document.querySelectorAll('.tab').forEach(tabBtn => {
            tabBtn.addEventListener('click', () => {
                this.navigateTo(tabBtn.dataset.tab);
            });
        });

        window.addEventListener('hashchange', () => {
            const tab = location.hash.slice(1) || 'home';
            this.navigateTo(tab);
        });
    },

    setupThemeToggle() {
        const toggleBtn = document.getElementById('theme-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                this.state.darkMode = !this.state.darkMode;
                document.body.classList.toggle('light', !this.state.darkMode);
                localStorage.setItem('darkMode', this.state.darkMode);
                this.updateThemeButton();
            });
        }
    },

    updateThemeButton() {
        const toggleBtn = document.getElementById('theme-toggle');
        if (toggleBtn) {
            toggleBtn.textContent = this.state.darkMode ? '🌙' : '☀️';
            toggleBtn.title = this.state.darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode';
        }
    },

    setupFormEvents() {
        // Voice Pitch slider value display update
        const pitchSlider = document.getElementById('voice-pitch');
        const pitchValDisplay = document.getElementById('voice-pitch-val');
        if (pitchSlider && pitchValDisplay) {
            pitchSlider.addEventListener('input', (e) => {
                const val = e.target.value;
                pitchValDisplay.textContent = val > 0 ? `+${val}%` : `${val}%`;
            });
        }

        // Vol Boost slider display update
        const volSlider = document.getElementById('vol-boost');
        const volValDisplay = document.getElementById('vol-boost-val');
        if (volSlider && volValDisplay) {
            volSlider.addEventListener('input', (e) => {
                volValDisplay.textContent = `${parseFloat(e.target.value).toFixed(1)}x`;
            });
        }

        // Background music slider display update
        const bgSlider = document.getElementById('bg-music');
        const bgValDisplay = document.getElementById('bg-music-val');
        if (bgSlider && bgValDisplay) {
            bgSlider.addEventListener('input', (e) => {
                bgValDisplay.textContent = `${Math.round(parseFloat(e.target.value) * 100)}%`;
            });
        }

        // Form submit handler
        const startBtn = document.getElementById('start-dub-btn');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.startDubbing());
        }
    },

    setupDragAndDrop() {
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('video-file');
        const fileDetails = document.getElementById('file-details');

        if (!dropZone || !fileInput) return;

        dropZone.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileSelected(e.target.files[0]);
            }
        });

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                this.handleFileSelected(e.dataTransfer.files[0]);
            }
        });
    },

    handleFileSelected(file) {
        const fileDetails = document.getElementById('file-details');
        const dropZoneText = document.getElementById('drop-zone-text');
        if (fileDetails) {
            const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
            fileDetails.innerHTML = `
                <div class="selected-file-info">
                    🎥 <strong>${file.name}</strong> (${sizeMB} MB)
                </div>`;
            if (dropZoneText) {
                dropZoneText.textContent = 'Change selected video';
            }
        }
    },

    setupTranslateEvents() {
        const transBtn = document.getElementById('translate-btn');
        if (transBtn) {
            transBtn.addEventListener('click', () => this.doTranslate());
        }
    },

    setupChatEvents() {
        const chatInput = document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-chat-btn');
        const clearBtn = document.getElementById('clear-chat-btn');

        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.sendChatMessage();
            });
        }
        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendChatMessage());
        }
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearChatHistory());
        }
    },

    navigateTo(tab) {
        this.state.currentTab = tab;
        location.hash = tab;

        // Toggle active tabs in Nav Bar
        document.querySelectorAll('.tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });

        // Toggle active content panel
        document.querySelectorAll('.tab-panel').forEach(p => {
            p.classList.toggle('active', p.id === `panel-${tab}`);
        });

        this.renderTab(tab);
    },

    renderTab(tab) {
        switch (tab) {
            case 'home':
                this.renderHome();
                break;
            case 'dub':
                this.renderDub();
                break;
            case 'translate':
                this.renderTranslate();
                break;
            case 'chat':
                this.renderChat();
                break;
            case 'history':
                this.renderHistory();
                break;
            case 'roadmap':
                this.renderRoadmap();
                break;
        }
    },

    renderHome() {
        // Home tab is statically declared mostly, but updates context chips if available.
        const summaryElement = document.getElementById('home-session-status');
        if (summaryElement) {
            if (this.state.transcript) {
                summaryElement.innerHTML = `
                    <div class="session-chip active">
                        🟢 Active Session Context Loaded (${this.state.transcript.length} chars)
                    </div>`;
            } else {
                summaryElement.innerHTML = `
                    <div class="session-chip inactive">
                        ⚪ No Video Context. Dub a video to enable AI context.
                    </div>`;
            }
        }
    },

    renderDub() {
        const langSelect = document.getElementById('target-language');
        if (langSelect && langSelect.options.length <= 1) {
            // Populate target language select
            this.state.languages.forEach(lang => {
                const opt = document.createElement('option');
                opt.value = lang.name;
                opt.textContent = `${lang.name} (${lang.native_name})`;
                langSelect.appendChild(opt);
            });
        }
    },

    renderTranslate() {
        const srcSelect = document.getElementById('translate-src');
        const tgtSelect = document.getElementById('translate-tgt');

        if (srcSelect && srcSelect.options.length <= 1) {
            // Populate source select
            this.state.languages.forEach(lang => {
                const opt = document.createElement('option');
                opt.value = lang.name;
                opt.textContent = lang.name;
                srcSelect.appendChild(opt);
            });
        }

        if (tgtSelect && tgtSelect.options.length <= 1) {
            // Populate target select
            this.state.languages.forEach(lang => {
                if (lang.name !== 'English') {
                    const opt = document.createElement('option');
                    opt.value = lang.name;
                    opt.textContent = lang.name;
                    tgtSelect.appendChild(opt);
                }
            });
        }
    },

    renderChat() {
        this.renderChatMessages();
        const chatStatus = document.getElementById('chat-context-status');
        if (chatStatus) {
            if (this.state.transcript) {
                chatStatus.innerHTML = `
                    <div class="chat-status-banner context-active">
                        🎓 <strong>Video Context Connected:</strong> AI Chat will refer to the dubbed video transcript.
                    </div>`;
            } else {
                chatStatus.innerHTML = `
                    <div class="chat-status-banner context-inactive">
                        ℹ️ <strong>General Chat Mode:</strong> No video dubbed yet. AI will respond using general knowledge.
                    </div>`;
            }
        }
    },

    renderHistory() {
        const container = document.getElementById('history-container');
        if (!container) return;

        if (this.state.dubHistory.length === 0) {
            container.innerHTML = `
                <div class="empty-history">
                    <div style="font-size: 3rem; margin-bottom: 1rem;">📋</div>
                    <h3>No dubbed videos yet</h3>
                    <p>Your dubbed videos will appear here once processed.</p>
                </div>`;
            return;
        }

        container.innerHTML = this.state.dubHistory
            .map((entry, idx) => Components.historyCard(entry, idx))
            .join('');
    },

    renderRoadmap() {
        // Roadmap content is static HTML.
    },

    async startDubbing() {
        const fileInput = document.getElementById('video-file');
        const urlInput = document.getElementById('video-url');
        const langSelect = document.getElementById('target-language');
        const startBtn = document.getElementById('start-dub-btn');
        const resultPanel = document.getElementById('dub-result');

        const file = fileInput.files[0];
        const url = urlInput.value.trim();
        const lang = langSelect.value;

        if (!file && !url) {
            alert('Please choose a video file or paste a video URL.');
            return;
        }
        if (!lang) {
            alert('Please choose a target language.');
            return;
        }

        // Prepare forms
        const fd = new FormData();
        if (file) fd.append('video', file);
        fd.append('target_language', lang);
        fd.append('video_url', url || '');
        fd.append('generate_srt', document.getElementById('gen-srt')?.checked || false);
        fd.append('voice_pitch', document.getElementById('voice-pitch')?.value || 0);
        fd.append('vol_boost', document.getElementById('vol-boost')?.value || 2.0);
        fd.append('bg_music_vol', document.getElementById('bg-music')?.value || 0.0);
        fd.append('tts_engine', document.getElementById('tts-engine')?.value || 'edge');
        fd.append('align_timing', document.getElementById('align-timing')?.checked || false);

        // Update button status
        startBtn.disabled = true;
        startBtn.textContent = '⏳ Processing...';

        // Pre-render progress bars
        const initialStages = [
            { pct: 0, msg: 'Initializing...' },
            { pct: 0, msg: 'Waiting...' },
            { pct: 0, msg: 'Waiting...' },
            { pct: 0, msg: 'Waiting...' },
            { pct: 0, msg: 'Waiting...' }
        ];
        resultPanel.innerHTML = Components.progressDashboard(initialStages, 1, 'Submitting request...', false, false);
        resultPanel.scrollIntoView({ behavior: 'smooth' });

        try {
            const resp = await API.startDubbing(fd);
            const jobId = resp.job_id;
            this.state.currentJob = jobId;

            // Connect to real-time WebSocket updates
            const ws = API.connectProgress(jobId, (data) => {
                if (data.type === 'status' || data.type === 'progress') {
                    const currentStage = data.stage || 1;
                    const stageMsg = data.message || 'Processing...';
                    const stagesData = data.stages || initialStages;
                    resultPanel.innerHTML = Components.progressDashboard(
                        stagesData, currentStage, stageMsg, false, false
                    );
                } else if (data.type === 'complete') {
                    this.onDubComplete(jobId, lang);
                    ws.close();
                } else if (data.type === 'error') {
                    resultPanel.innerHTML = Components.progressDashboard(
                        initialStages, 0, `Failed: ${data.message}`, false, true
                    );
                    this.resetDubbingButton();
                    ws.close();
                }
            });
        } catch (err) {
            resultPanel.innerHTML = `
                <div class="progress-dashboard error">
                    <div class="pdash-header">
                        <span>❌ Dubbing Request Failed</span>
                        <span>0%</span>
                    </div>
                    <div style="padding: 1.5rem; color: var(--error);">${err.message}</div>
                </div>`;
            this.resetDubbingButton();
        }
    },

    resetDubbingButton() {
        const startBtn = document.getElementById('start-dub-btn');
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.textContent = '🎬 Start Dubbing';
        }
    },

    async onDubComplete(jobId, language) {
        this.resetDubbingButton();
        const resultPanel = document.getElementById('dub-result');

        try {
            // Get final status with transcript and translations
            const job = await API.getJobStatus(jobId);

            // Update transcript context
            this.state.transcript = job.transcript || '';
            localStorage.setItem('transcriptContext', this.state.transcript);

            // Add download and preview cards
            const dlUrl = API.getDownloadUrl(jobId);
            const srtUrl = API.getSrtUrl(jobId);

            let srtLinkHtml = '';
            if (job.srt_path || document.getElementById('gen-srt')?.checked) {
                srtLinkHtml = `
                    <a href="${srtUrl}" class="btn btn-secondary srt-btn" download style="margin-left: 10px;">
                        📄 Download subtitles (SRT)
                    </a>`;
            }

            resultPanel.innerHTML = `
                ${Components.resultCard(jobId, language, dlUrl)}
                ${srtLinkHtml}
                
                <div style="margin-top: 2rem;">
                    <h4 style="margin-bottom: 0.8rem;">📺 Dubbed Preview</h4>
                    <video controls class="result-video" src="${dlUrl}"></video>
                </div>

                <div class="result-details">
                    <details class="result-expander">
                        <summary>🎙️ Speech-to-Text Transcript</summary>
                        <div class="transcript-box">${job.transcript || 'No speech transcribed.'}</div>
                    </details>
                    <details class="result-expander">
                        <summary>🌐 Target Language Translation</summary>
                        <div class="transcript-box">${job.translation || 'No translation generated.'}</div>
                    </details>
                </div>`;

            // Save to history
            const newHistoryEntry = {
                job_id: jobId,
                language: language,
                timestamp: new Date().toISOString()
            };
            this.state.dubHistory.unshift(newHistoryEntry);
            localStorage.setItem('dubHistory', JSON.stringify(this.state.dubHistory));
            this.renderHistory();

        } catch (err) {
            console.error('Error rendering completed job:', err);
            resultPanel.innerHTML += `<div class="error-msg">⚠️ Failed to retrieve job detail: ${err.message}</div>`;
        }
    },

    async doTranslate() {
        const textInput = document.getElementById('translate-input');
        const srcSelect = document.getElementById('translate-src');
        const tgtSelect = document.getElementById('translate-tgt');
        const outputField = document.getElementById('translate-output');
        const transBtn = document.getElementById('translate-btn');

        const text = textInput?.value || '';
        const src = srcSelect?.value || 'English';
        const tgt = tgtSelect?.value || 'Hindi';

        if (!text.trim()) {
            alert('Please enter some text to translate.');
            return;
        }

        if (transBtn) {
            transBtn.disabled = true;
            transBtn.textContent = '⏳ Translating...';
        }
        if (outputField) {
            outputField.value = 'Translating, please wait...';
        }

        try {
            const res = await API.translate(text, src, tgt);
            if (outputField) {
                outputField.value = res;
            }
        } catch (e) {
            if (outputField) {
                outputField.value = `Error: ${e.message}`;
            }
        } finally {
            if (transBtn) {
                transBtn.disabled = false;
                transBtn.textContent = '🌐 Translate';
            }
        }
    },

    renderChatMessages() {
        const container = document.getElementById('chat-messages');
        if (!container) return;

        if (this.state.chatHistory.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 2rem; color: var(--text-dim);">
                    💬 Ask questions about the dubbed video transcript, or general education queries.
                </div>`;
            return;
        }

        container.innerHTML = this.state.chatHistory
            .map(msg => Components.chatMessage(msg.role, msg.content, msg.time))
            .join('');

        container.scrollTop = container.scrollHeight;
    },

    async sendChatMessage() {
        const inputField = document.getElementById('chat-input');
        const sendBtn = document.getElementById('send-chat-btn');
        const langSelect = document.getElementById('chat-language');

        const message = inputField?.value?.trim() || '';
        const lang = langSelect?.value || 'English';

        if (!message) return;

        // Save and render user message
        const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const userMsg = { role: 'user', content: message, time: now };
        this.state.chatHistory.push(userMsg);
        this.renderChatMessages();

        if (inputField) inputField.value = '';
        if (sendBtn) sendBtn.disabled = true;

        // Add dummy typing loader
        const container = document.getElementById('chat-messages');
        const loader = document.createElement('div');
        loader.id = 'chat-loader';
        loader.style.padding = '1rem';
        loader.style.color = 'var(--text-dim)';
        loader.textContent = '⏳ Bhasha Setu AI is thinking...';
        container.appendChild(loader);
        container.scrollTop = container.scrollHeight;

        try {
            const reply = await API.chat(
                message,
                this.state.transcript,
                lang,
                this.state.chatHistory.slice(0, -1) // send context history excluding this user msg
            );

            // Remove loader
            const l = document.getElementById('chat-loader');
            if (l) l.remove();

            const aiMsg = { role: 'assistant', content: reply, time: now };
            this.state.chatHistory.push(aiMsg);
            localStorage.setItem('chatHistory', JSON.stringify(this.state.chatHistory));
            this.renderChatMessages();
        } catch (e) {
            const l = document.getElementById('chat-loader');
            if (l) l.remove();

            const errorMsg = { role: 'assistant', content: `Error: ${e.message}`, time: now };
            this.state.chatHistory.push(errorMsg);
            this.renderChatMessages();
        } finally {
            if (sendBtn) sendBtn.disabled = false;
        }
    },

    clearChatHistory() {
        if (confirm('Are you sure you want to clear chat history?')) {
            this.state.chatHistory = [];
            localStorage.removeItem('chatHistory');
            this.renderChatMessages();
        }
    }
};

// Initialize App once DOM content is loaded
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
