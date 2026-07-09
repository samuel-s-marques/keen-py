/*
 * Terminal log printing + snackbar notification system.
 */
import { terminalBody, snackbarContainer } from "./dom.js";

export function termPrint(text, extraClass = '') {
    let finalClass = extraClass;

    // Auto-detect class based on text content if no explicit success/warning/error class is provided
    if (finalClass !== 'success' && finalClass !== 'warning' && finalClass !== 'error') {
        const lowerText = text.toLowerCase();
        if (lowerText.includes(' | success | ') || lowerText.includes('completed:') || lowerText.includes('success:')) {
            finalClass = 'success';
        } else if (lowerText.includes(' | warning | ') || lowerText.includes(' | warn | ') || lowerText.includes('warning:')) {
            finalClass = 'warning';
        } else if (lowerText.includes(' | error | ') || lowerText.includes(' | critical | ') || lowerText.includes('error:')) {
            finalClass = 'error';
        }
    }

    const line = document.createElement('div');
    line.className = `log-line ${finalClass}`;
    line.textContent = text;
    terminalBody.appendChild(line);
    terminalBody.scrollTop = terminalBody.scrollHeight;
}

// --- Snackbar System ---
export const SNACKBAR_ICONS = {
    info: '<div class="snackbar-spinner"></div>',
    success: '<i class="fa-solid fa-check"></i>',
    error: '<i class="fa-solid fa-xmark"></i>',
    warning: '<i class="fa-solid fa-exclamation"></i>',
};

export function showSnackbar(title, message, type = 'info', duration = 3000, id = null) {
    const el = document.createElement('div');
    el.className = `snackbar snackbar-${type}`;
    if (id) el.dataset.snackbarId = id;

    // Hide close button if duration is 0 (persistent/running state)
    const closeBtnStyle = duration === 0 ? 'style="display: none;"' : '';
    const cancelBtnStyle = duration === 0 ? 'style="display: block;"' : 'style="display: none;"';

    el.innerHTML = `
        <div class="snackbar-icon">${SNACKBAR_ICONS[type] || SNACKBAR_ICONS.info}</div>
        <div class="snackbar-body">
            <div class="snackbar-title"></div>
            <div class="snackbar-message"></div>
        </div>
        <button class="snackbar-cancel" ${cancelBtnStyle}><i class="fa-solid fa-circle-stop"></i></button>
        <button class="snackbar-close" ${closeBtnStyle}><i class="fa-solid fa-xmark"></i></button>
    `;

    const titleEl = el.querySelector('.snackbar-title');
    if (titleEl) { titleEl.textContent = title; titleEl.title = title; }
    const msgEl = el.querySelector('.snackbar-message');
    if (msgEl) { msgEl.textContent = message; msgEl.title = message; }

    el.querySelector('.snackbar-close').addEventListener('click', () => removeSnackbar(el));

    const cancelBtn = el.querySelector('.snackbar-cancel');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            if (id && KeenStore.activeSocketsMap.has(id)) {
                const ws = KeenStore.activeSocketsMap.get(id);
                if (ws) ws.close();
            } else {
                removeSnackbar(el);
            }
        });
    }

    snackbarContainer.appendChild(el);

    if (duration > 0) {
        el._timeout = setTimeout(() => removeSnackbar(el), duration);
    }

    return el;
}

export function updateSnackbar(id, title, message, type, duration = 4000) {
    const el = snackbarContainer.querySelector(`[data-snackbar-id="${id}"]`);
    if (!el) {
        // Snackbar was manually closed, just show a new one
        showSnackbar(title, message, type, duration);
        return;
    }

    // Update classes
    el.className = `snackbar snackbar-${type}`;

    // Update icon
    const iconEl = el.querySelector('.snackbar-icon');
    if (iconEl) iconEl.innerHTML = SNACKBAR_ICONS[type] || SNACKBAR_ICONS.info;

    // Update text
    const titleEl = el.querySelector('.snackbar-title');
    if (titleEl) { titleEl.textContent = title; titleEl.title = title; }
    const msgEl = el.querySelector('.snackbar-message');
    if (msgEl) { msgEl.textContent = message; msgEl.title = message; }

    // Update close button visibility: show if duration > 0, hide if 0
    const closeEl = el.querySelector('.snackbar-close');
    if (closeEl) {
        if (duration === 0) {
            closeEl.style.display = 'none';
        } else {
            closeEl.style.display = 'block';
        }
    }

    const cancelEl = el.querySelector('.snackbar-cancel');
    if (cancelEl) {
        if (duration === 0) {
            cancelEl.style.display = 'block';
        } else {
            cancelEl.style.display = 'none';
        }
    }

    // Clear old timeout and set new auto-dismiss
    if (el._timeout) clearTimeout(el._timeout);
    if (duration > 0) {
        el._timeout = setTimeout(() => removeSnackbar(el), duration);
    }
}

export function removeSnackbar(el) {
    if (!el || !el.parentNode) return;
    if (el._timeout) clearTimeout(el._timeout);
    el.classList.add('removing');
    el.addEventListener('animationend', () => {
        if (el.parentNode) el.parentNode.removeChild(el);
    }, { once: true });
}
