/*
 * Proxy pool settings UI: table rendering, add/test/toggle/delete, bulk upload.
 */

export async function fetchProxies() {
    const tbody = document.getElementById('proxies-tbody');
    if (!tbody) return;

    try {
        const res = await KeenAPI.get(`/proxies`);
        if (res.ok) {
            const proxies = await res.json();
            tbody.innerHTML = '';

            let onlineCount = 0;
            const totalCount = proxies.length;

            proxies.forEach(p => {
                const status = p.status || 'unknown';
                if (status === 'online') onlineCount++;

                let latencyText = '-';
                if (p.latency !== -1 && status === 'online') {
                    latencyText = `${Math.round(p.latency * 1000)}ms`;
                }

                const maskUrl = (url) => {
                    try {
                        const u = new URL(url);
                        if (u.username || u.password) {
                            return `${u.protocol}//${u.username}:${u.password ? '****' : ''}@${u.host}`;
                        }
                    } catch (e) { }
                    return url;
                };

                const escapeHtml = (s) =>
                    String(s).replace(/[&<>"']/g, (c) => ({
                        '&': '&amp;',
                        '<': '&lt;',
                        '>': '&gt;',
                        '"': '&quot;',
                        "'": '&#39;'
                    }[c]));

                const safeStatus = ['online', 'offline', 'unknown'].includes(status) ? status : 'unknown';

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="word-break: break-all;">${escapeHtml(maskUrl(p.url))}</td>
                    <td style="text-align: center;"><span class="status-badge ${safeStatus}">${safeStatus.toUpperCase()}</span></td>
                    <td style="text-align: right; color: var(--accent-cyan); font-family: var(--font-mono);">${escapeHtml(latencyText)}</td>
                    <td style="text-align: center;">
                        <input type="checkbox" class="proxy-row-toggle" data-id="${p.id}" ${p.is_enabled === 1 ? 'checked' : ''} style="width: auto; cursor: pointer;">
                    </td>
                    <td style="text-align: center;">
                        <button class="icon-btn btn-delete-proxy" data-id="${p.id}" style="color: var(--error);" title="Delete"><i class="fa-solid fa-trash"></i></button>
                    </td>
                `;

                // Row Toggle Event
                const toggleInput = tr.querySelector('.proxy-row-toggle');
                toggleInput.addEventListener('change', async (e) => {
                    const is_enabled = e.target.checked;
                    await KeenAPI.post(`/proxies/${p.id}/toggle`, { is_enabled });
                });

                // Row Delete Event
                const delBtn = tr.querySelector('.btn-delete-proxy');
                delBtn.addEventListener('click', async () => {
                    if (confirm('Delete this proxy?')) {
                        const dRes = await KeenAPI.del(`/proxies/${p.id}`);
                        if (dRes.ok) {
                            fetchProxies();
                        }
                    }
                });

                tbody.appendChild(tr);
            });

            const onlineCountSpan = document.getElementById('proxy-online-count');
            const totalCountSpan = document.getElementById('proxy-total-count');
            if (onlineCountSpan) onlineCountSpan.textContent = onlineCount;
            if (totalCountSpan) totalCountSpan.textContent = totalCount;

            const btnTestProxies = document.getElementById('btn-test-proxies');
            if (btnTestProxies && !btnTestProxies.innerHTML.includes('Testing...')) {
                btnTestProxies.disabled = (totalCount === 0);
            }
        }
    } catch (err) {
        console.error('Failed to fetch proxies', err);
    }
}

// Set up proxy events listeners once settings loads
export function initProxyListeners() {
    const toggleProxyRouting = document.getElementById('toggle-proxy-routing');
    const selectProxyRotation = document.getElementById('select-proxy-rotation');
    const btnAddProxy = document.getElementById('btn-add-proxy');
    const inputProxyUrl = document.getElementById('input-proxy-url');
    const btnTestProxies = document.getElementById('btn-test-proxies');

    if (toggleProxyRouting) {
        toggleProxyRouting.addEventListener('change', async (e) => {
            const checked = e.target.checked;
            await KeenAPI.post(`/config/preferences`, { proxy_enabled: String(checked) });
            const proxyStatusVal = document.getElementById('proxy-status-val');
            if (proxyStatusVal) {
                proxyStatusVal.textContent = checked ? 'Enabled' : 'Disabled';
                proxyStatusVal.style.color = checked ? 'var(--success)' : 'var(--error)';
            }
        });
    }

    if (selectProxyRotation) {
        selectProxyRotation.addEventListener('change', async (e) => {
            const val = e.target.value;
            await KeenAPI.post(`/config/preferences`, { proxy_rotation_mode: val });
            const proxyModeVal = document.getElementById('proxy-mode-val');
            if (proxyModeVal) {
                proxyModeVal.textContent = val;
            }
        });
    }

    if (btnAddProxy && inputProxyUrl) {
        btnAddProxy.addEventListener('click', async () => {
            const url = inputProxyUrl.value.trim();
            if (!url) return;

            const res = await KeenAPI.post(`/proxies`, { url });
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    inputProxyUrl.value = '';
                    fetchProxies();
                } else {
                    alert(data.error || 'Failed to add proxy');
                }
            }
        });
    }

    if (btnTestProxies) {
        btnTestProxies.addEventListener('click', async () => {
            btnTestProxies.disabled = true;
            btnTestProxies.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Testing...';
            await KeenAPI.post(`/proxies/test`);

            // Poll check every 2 seconds for up to 60 seconds to update table
            let count = 0;
            const maxPolls = 30;
            const interval = setInterval(async () => {
                await fetchProxies();
                count++;
                if (count >= maxPolls) {
                    clearInterval(interval);
                    // Re-evaluate button disabled state after testing completes
                    const totalCountSpan = document.getElementById('proxy-total-count');
                    const totalCount = totalCountSpan ? parseInt(totalCountSpan.textContent || '0', 10) : 0;
                    btnTestProxies.disabled = (totalCount === 0);
                    btnTestProxies.innerHTML = '<i class="fa-solid fa-play"></i> Test Connectivity';
                }
            }, 2000);
        });
    }

    // Drag & Drop Bulk upload list
    const dragZone = document.getElementById('proxy-drag-zone');
    const fileInput = document.getElementById('input-proxy-file');

    if (dragZone && fileInput) {
        dragZone.addEventListener('click', () => fileInput.click());

        dragZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dragZone.style.borderColor = 'var(--accent-cyan)';
            dragZone.style.background = 'rgba(0, 240, 255, 0.05)';
        });

        dragZone.addEventListener('dragleave', () => {
            dragZone.style.borderColor = 'var(--border-color)';
            dragZone.style.background = 'rgba(0,0,0,0.2)';
        });

        const uploadFile = async (file) => {
            // Prevent uploading non-TXT files
            if (!file.name.toLowerCase().endsWith('.txt')) {
                alert('Only .txt files are allowed.');
                return;
            }

            // Check file MIME type (if present)
            if (file.type && !file.type.startsWith('text/')) {
                alert('Selected file is not a valid text file.');
                return;
            }

            const reader = new FileReader();
            reader.onload = async (e) => {
                const text = e.target.result;

                // Content-based heuristic check for binary files (e.g., check for null bytes or control characters)
                if (text.includes('\0') || /[\x00-\x08\x0E-\x1F\x7F]/.test(text)) {
                    alert('Error: The file contains binary data and does not appear to be a real text file.');
                    return;
                }

                const res = await KeenAPI.post(`/proxies/load`, { content: text });
                if (res.ok) {
                    const data = await res.json();
                    alert(`Successfully loaded ${data.loaded} proxies!`);
                    fetchProxies();
                }
            };
            reader.readAsText(file);
        };

        dragZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dragZone.style.borderColor = 'var(--border-color)';
            dragZone.style.background = 'rgba(0,0,0,0.2)';
            if (e.dataTransfer.files.length) {
                uploadFile(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                uploadFile(e.target.files[0]);
            }
        });
    }
}
