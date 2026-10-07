document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('nxt-chat-form');
    const input = document.getElementById('nxt-message');
    const messages = document.getElementById('nxt-messages');
    const sendButton = document.getElementById('nxt-send');
    const healthElement = document.getElementById('nxt-health');
    const sourcesContainer = document.getElementById('nxt-sources');
    const sourcesList = document.getElementById('nxt-sources-list');

    if (!form || !input || !messages || !sendButton) {
        return;
    }

    let sessionId = null;

    function addMessage(role, text) {
        const wrapper = document.createElement('div');
        wrapper.className = `nxt-message nxt-message-${role}`;

        const content = document.createElement('div');
        content.className = 'nxt-message-content';
        content.textContent = text;

        wrapper.appendChild(content);
        messages.appendChild(wrapper);
        messages.scrollTop = messages.scrollHeight;

        return content;
    }

    function clearSources() {
        if (!sourcesContainer || !sourcesList) {
            return;
        }

        sourcesList.innerHTML = '';
        sourcesContainer.hidden = true;
    }

    function showSources(chunks) {
        if (!sourcesContainer || !sourcesList) {
            return;
        }

        clearSources();

        if (!Array.isArray(chunks) || chunks.length === 0) {
            return;
        }

        const uniqueSources = [];
        const seen = new Set();

        for (const chunk of chunks) {
            const title = String(chunk?.document_title || '').trim();
            const source = String(chunk?.document_source || '').trim();

            if (!title && !source) {
                continue;
            }

            const key = `${title}|${source}`;

            if (seen.has(key)) {
                continue;
            }

            seen.add(key);

            uniqueSources.push({
                title: title || 'Document',
                source: source || 'Location not available'
            });
        }

        if (uniqueSources.length === 0) {
            return;
        }

        for (const item of uniqueSources) {
            const sourceItem = document.createElement('div');
            sourceItem.className = 'nxt-source-item';

            const title = document.createElement('div');
            title.className = 'nxt-source-title';
            title.textContent = item.title;

            const sourcePath = document.createElement('div');
            sourcePath.className = 'nxt-source-path';
            sourcePath.textContent = `Location: ${item.source}`;

            sourceItem.appendChild(title);
            sourceItem.appendChild(sourcePath);

            sourcesList.appendChild(sourceItem);
        }

        sourcesContainer.hidden = false;
    }

    function renderAssistantMessage(element, text) {
        element.textContent = '';

        const parts = text.split(/(\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g);

        parts.forEach((part) => {
            const match = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);

            if (match) {
                const link = document.createElement('a');
                link.href = match[2];
                link.textContent = match[1];
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                element.appendChild(link);
            } else {
                element.appendChild(document.createTextNode(part));
            }
        });
    }

    async function checkHealth() {
        if (!healthElement) {
            return;
        }

        healthElement.textContent = 'Checking AI system...';
        healthElement.className = 'nxt-health nxt-health-checking';

        try {
            const response = await fetch(
                OC.generateUrl('/apps/nxtworkspace/api/health'),
                {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json'
                    }
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data?.detail ||
                    data?.error ||
                    'AI backend is unavailable'
                );
            }

            if (data?.status === 'healthy') {
                healthElement.textContent = 'AI system is healthy';
                healthElement.className = 'nxt-health nxt-health-ok';
                return;
            }

            healthElement.textContent =
                `AI system status: ${data?.status || 'unknown'}`;
            healthElement.className = 'nxt-health nxt-health-warning';
        } catch (error) {
            healthElement.textContent =
                `AI system unavailable: ${error.message}`;
            healthElement.className = 'nxt-health nxt-health-error';
        }
    }

    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        const message = input.value.trim();

        if (!message) {
            return;
        }

        clearSources();
        addMessage('user', message);

        input.value = '';
        sendButton.disabled = true;

        const assistantMessage = addMessage(
            'assistant',
            'Thinking...'
        );

        try {
            const response = await fetch(
                OC.generateUrl('/apps/nxtworkspace/api/chat'),
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({
                        message,
                        session_id: sessionId
                    })
                }
            );

            const contentType =
                response.headers.get('content-type') || '';

            let data;

            if (contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = await response.text();
                throw new Error(
                    `Server returned ${response.status} instead of JSON`
                );
            }

            if (!response.ok) {
                throw new Error(
                    data?.error ||
                    data?.detail ||
                    'Failed to get response'
                );
            }

            sessionId = data?.session_id || sessionId;

            renderAssistantMessage(
                assistantMessage,
                data?.message || 'No response received.'
            );

            showSources(data?.retrieved_chunks || data?.sources || []);
        } catch (error) {
            assistantMessage.textContent =
                `Error: ${error.message}`;
        } finally {
            sendButton.disabled = false;
            input.focus();
        }
    });

    checkHealth();
});