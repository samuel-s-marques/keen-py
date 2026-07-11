/*
 * Media import: web equivalent of the CLI's `media import <path>` command.
 * Uploads a local file to POST /api/workspaces/{name}/media, which hashes it,
 * stores the bytes under the workspace's attachments directory, and creates
 * a 'media' graph node -- the same entry point EXIF/avatar-correlation
 * modules chain off via `magic_consumes: ["media"]`. The uploaded node then
 * shows up in the existing Nodes tab/graph like any other node.
 */
import { selectWorkspace } from "./workspaces.js";
import { showSnackbar } from "./notifications.js";

/**
 * Upload a file as a media node. Returns the created/deduped node id on
 * success, or null on failure (caller decides what UI state to clean up).
 */
export async function uploadMediaFile(file) {
    if (!KeenStore.activeWorkspace) {
        showSnackbar('Media', 'Select a workspace first.', 'error', 5000);
        return null;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await KeenAPI.upload(`/workspaces/${KeenStore.activeWorkspace}/media`, formData);
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            showSnackbar('Media', `Imported '${file.name}' as node #${data.node_id}.`, 'success', 5000);
            selectWorkspace(KeenStore.activeWorkspace);
            return data.node_id;
        }
        showSnackbar('Media', data.error || 'Failed to import media file.', 'error', 5000);
        return null;
    } catch (e) {
        showSnackbar('Media', 'Failed to import media file.', 'error', 5000);
        return null;
    }
}

export function initMediaUploadListeners() {
    const btnImportMedia = document.getElementById('btn-import-media');
    const inputMediaFile = document.getElementById('input-media-file');
    if (!btnImportMedia || !inputMediaFile) return;

    btnImportMedia.addEventListener('click', () => inputMediaFile.click());
    inputMediaFile.addEventListener('change', () => {
        if (inputMediaFile.files.length) {
            uploadMediaFile(inputMediaFile.files[0]);
        }
        // Reset so selecting the same file again still fires 'change'.
        inputMediaFile.value = '';
    });
}
