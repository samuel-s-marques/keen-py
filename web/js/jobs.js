/*
 * Jobs panel: fetch/render job_history for the active workspace, cancel a
 * running job, and view a job's captured logs. Polls only while the Jobs
 * tab is actually visible, to avoid hammering the server in the background.
 */
import { showSnackbar } from "./notifications.js";

let pollTimer = null;

function statusLabel(status) {
    return (status || 'pending').charAt(0).toUpperCase() + (status || 'pending').slice(1);
}

function formatProgress(progress) {
    const pct = Math.max(0, Math.min(1, progress || 0));
    return Math.round(pct * 100) + '%';
}

export async function fetchJobs() {
    const list = document.getElementById('jobs-list');
    if (!list || !KeenStore.activeWorkspace) return;

    const showAll = document.getElementById('jobs-show-all');

    try {
        // Always fetch the full history; "Show all" filters client-side so
        // toggling it doesn't need a re-request.
        const res = await KeenAPI.get(`/workspaces/${KeenStore.activeWorkspace}/jobs`);
        if (!res.ok) return;
        const jobs = await res.json();
        renderJobs(jobs, showAll && showAll.checked);

        const pulseDot = document.getElementById('jobs-tab-pulse');
        if (pulseDot) {
            const hasActive = jobs.some(j => j.status === 'pending' || j.status === 'running');
            pulseDot.classList.toggle('hidden', !hasActive);
        }
    } catch (e) {
        console.error('Failed to fetch jobs', e);
    }
}

export function renderJobs(jobs, showAll) {
    const list = document.getElementById('jobs-list');
    const empty = document.getElementById('jobs-empty');
    if (!list) return;

    const visible = showAll ? jobs : jobs.filter(j => j.status === 'pending' || j.status === 'running');

    if (!visible.length) {
        list.innerHTML = '';
        if (empty) {
            empty.style.display = 'block';
            empty.textContent = showAll
                ? 'No jobs yet. Run a module or Magic Chain to see it here.'
                : 'No active jobs. Toggle "Show all" to see completed/failed/cancelled jobs.';
        }
        return;
    }
    if (empty) empty.style.display = 'none';

    list.innerHTML = '';
    visible.forEach(job => {
        const item = document.createElement('div');
        item.className = 'job-item';

        const safeStatus = ['pending', 'running', 'completed', 'failed', 'cancelled'].includes(job.status)
            ? job.status : 'pending';
        const isActive = safeStatus === 'pending' || safeStatus === 'running';

        item.innerHTML = `
            <div class="job-item-header">
                <div>
                    <div class="job-item-title">${escapeHtml(job.module_name)}</div>
                    <div class="job-item-target">${escapeHtml(job.target_value)}</div>
                </div>
                <div class="job-item-actions">
                    ${isActive ? `<button class="icon-btn btn-cancel-job" data-id="${job.job_id}" title="Cancel"><i class="fa-solid fa-circle-stop"></i></button>` : ''}
                    <button class="icon-btn btn-view-job-logs" data-id="${job.job_id}" title="View logs"><i class="fa-solid fa-file-lines"></i></button>
                </div>
            </div>
            <div class="job-progress-track">
                <div class="job-progress-fill" style="width: ${formatProgress(job.progress)};"></div>
            </div>
            <div class="job-item-meta">
                <span class="status-badge ${safeStatus}">${statusLabel(safeStatus)}</span>
                <span>${job.nodes_added || 0} nodes · ${job.edges_added || 0} edges</span>
            </div>
        `;

        const cancelBtn = item.querySelector('.btn-cancel-job');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => cancelJob(job.job_id));
        }
        const logsBtn = item.querySelector('.btn-view-job-logs');
        if (logsBtn) {
            logsBtn.addEventListener('click', () => openJobLogs(job.job_id));
        }

        list.appendChild(item);
    });
}

function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

export async function cancelJob(jobId) {
    if (!KeenStore.activeWorkspace) return;
    try {
        const res = await KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/jobs/${jobId}/cancel`);
        if (res.ok) {
            showSnackbar('Jobs', 'Job cancelled.', 'info', 2500);
            fetchJobs();
        } else {
            const err = await res.json();
            showSnackbar('Jobs', `Failed to cancel: ${err.error || 'Unknown error'}`, 'error', 4000);
        }
    } catch (e) {
        showSnackbar('Jobs', 'Failed to cancel job. Network error.', 'error', 4000);
    }
}

export async function openJobLogs(jobId) {
    if (!KeenStore.activeWorkspace) return;
    const modal = document.getElementById('modal-job-logs');
    const meta = document.getElementById('job-logs-meta');
    const body = document.getElementById('job-logs-body');
    if (!modal || !body) return;

    body.textContent = 'Loading...';
    modal.classList.add('active');

    try {
        const res = await KeenAPI.get(`/workspaces/${KeenStore.activeWorkspace}/jobs/${jobId}`);
        if (!res.ok) {
            body.textContent = 'Failed to load job.';
            return;
        }
        const job = await res.json();
        if (meta) {
            meta.textContent = `${job.module_name} on '${job.target_value}' — ${statusLabel(job.status)}`;
        }
        const lines = Array.isArray(job.logs) ? job.logs : [];
        body.textContent = lines.length ? lines.join('\n') : 'No logs captured for this job.';
        if (job.error_message) {
            body.textContent += `\n\nError: ${job.error_message}`;
        }
    } catch (e) {
        body.textContent = 'Failed to load job. Network error.';
    }
}

function startJobsPolling() {
    stopJobsPolling();
    fetchJobs();
    pollTimer = setInterval(fetchJobs, 4000);
}

function stopJobsPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

export function initJobsListeners() {
    const refreshBtn = document.getElementById('btn-refresh-jobs');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', fetchJobs);
    }

    const showAllToggle = document.getElementById('jobs-show-all');
    if (showAllToggle) {
        showAllToggle.addEventListener('change', fetchJobs);
    }

    // Poll only while the Jobs tab is the visible right-tab.
    document.querySelectorAll('.right-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            if (tab.dataset.target === 'tab-jobs') {
                startJobsPolling();
            } else {
                stopJobsPolling();
            }
        });
    });
}
