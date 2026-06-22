/* ═══════════════════════════════════════════════════════════════
   Bhasha Setu — API Client
   Handles all backend communication
   ═══════════════════════════════════════════════════════════════ */

const API = {
    // Base URL (same origin in production)
    base: '',

    /**
     * Fetch the list of supported target languages.
     * @returns {Promise<Array<{name:string, native_name:string, tts_engine:string}>>}
     */
    async getLanguages() {
        const res = await fetch(`${this.base}/api/languages`);
        if (!res.ok) throw new Error('Failed to fetch languages');
        return res.json();
    },

    /**
     * Start a dubbing job.
     * @param {FormData} formData - Contains: video (File), target_language, video_url,
     *        generate_srt, voice_pitch, vol_boost, bg_music_vol
     * @returns {Promise<{job_id:string}>}
     */
    async startDubbing(formData) {
        const res = await fetch(`${this.base}/api/dub`, {
            method: 'POST',
            body: formData,
        });
        if (!res.ok) {
            let detail = 'Dubbing failed';
            try {
                const err = await res.json();
                detail = err.detail || detail;
            } catch (_) { /* ignore parse errors */ }
            throw new Error(detail);
        }
        return res.json();
    },

    /**
     * Get the current status of a dubbing job.
     * @param {string} jobId
     * @returns {Promise<Object>}
     */
    async getJobStatus(jobId) {
        const res = await fetch(`${this.base}/api/dub/${jobId}`);
        if (!res.ok) throw new Error('Failed to fetch job status');
        return res.json();
    },

    /**
     * Build the download URL for a dubbed video.
     * @param {string} jobId
     * @returns {string}
     */
    getDownloadUrl(jobId) {
        return `${this.base}/api/download/${jobId}`;
    },

    /**
     * Build the download URL for the SRT subtitle file.
     * @param {string} jobId
     * @returns {string}
     */
    getSrtUrl(jobId) {
        return `${this.base}/api/download/${jobId}/srt`;
    },

    /**
     * Open a WebSocket connection to receive real-time progress updates.
     * @param {string} jobId
     * @param {function} onMessage - Called with parsed JSON messages
     * @returns {WebSocket}
     */
    connectProgress(jobId, onMessage) {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${location.host}/ws/progress/${jobId}`);

        ws.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type !== 'heartbeat') {
                    onMessage(data);
                }
            } catch (err) {
                console.warn('WS parse error:', err);
            }
        };

        ws.onerror = (e) => {
            console.error('WebSocket error:', e);
        };

        ws.onclose = () => {
            console.log('WebSocket closed for job:', jobId);
        };

        return ws;
    },

    /**
     * Send a message to the AI chat assistant.
     * @param {string} message
     * @param {string} transcriptContext - Transcript from last dubbed video
     * @param {string} language - Reply language preference
     * @param {Array} history - Recent chat history [{role, content}, ...]
     * @returns {Promise<string>} AI reply text
     */
    async chat(message, transcriptContext, language, history) {
        const res = await fetch(`${this.base}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                transcript_context: transcriptContext || '',
                language: language || 'English',
                history: history || [],
            }),
        });
        if (!res.ok) throw new Error('Chat request failed');
        const data = await res.json();
        return data.reply;
    },

    /**
     * Translate text between languages.
     * @param {string} text
     * @param {string} sourceLang - ISO code or language name
     * @param {string} targetLang - ISO code or language name
     * @returns {Promise<string>} Translated text
     */
    async translate(text, sourceLang, targetLang) {
        const res = await fetch(`${this.base}/api/translate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                source_lang: sourceLang,
                target_lang: targetLang,
            }),
        });
        if (!res.ok) throw new Error('Translation failed');
        const data = await res.json();
        return data.translated_text;
    },
};
