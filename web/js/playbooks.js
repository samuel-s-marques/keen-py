/*
 * Playbooks: list/CRUD over the /playbooks REST API, a vis-network-based
 * visual DAG step editor, a CodeMirror YAML editor, and a live-streaming
 * run view (WebSocket to /ws/playbooks/{id}/run).
 *
 * The visual builder and YAML editor share one in-memory `currentPlaybookData`
 * dict. Rather than keeping both views live-synced, conversion happens once
 * at tab-switch time (syncVisualToYaml / syncYamlToVisual) and once more at
 * Save -- simple "last edited tab wins" semantics instead of two-way binding.
 */
import {
    playbooksList,
    playbookEmptyState,
    playbookEditor,
    playbookNameInput,
    btnSavePlaybook,
    btnDeletePlaybook,
    playbookDagCanvas,
    playbookStepPanel,
    pbStepIdInput,
    pbStepModuleSelect,
    pbStepInputsFields,
    pbStepConditionInput,
    btnPbStepConfirm,
    btnPbStepCancel,
    playbookYamlEditor,
    playbookYamlMessages,
    playbookTriggerValue,
    btnRunPlaybook,
    playbookRunStatus,
    playbookRunLog,
} from "./dom.js";
import { showSnackbar, termPrint } from "./notifications.js";

let currentPlaybookId = null;
let currentPlaybookData = null;

let dagNetwork = null;
let dagNodes = null;
let dagEdges = null;
let pendingStepCallback = null;

let codeMirrorEditor = null;

let runSocket = null;

function slugify(name) {
    return (
        (name || "untitled")
            .toLowerCase()
            .trim()
            .replace(/[^a-z0-9_-]+/g, "_")
            .replace(/^_+|_+$/g, "") || "untitled"
    );
}

// --------------------------------------------------------------------------
// List
// --------------------------------------------------------------------------

export async function fetchPlaybooksList() {
    const res = await KeenAPI.get("/playbooks");
    if (!res.ok) return;
    const playbooks = await res.json();
    playbooksList.innerHTML = "";
    if (!playbooks.length) {
        playbooksList.innerHTML =
            '<div style="color: var(--text-secondary); font-size: 0.85rem;">No playbooks yet.</div>';
        return;
    }
    playbooks.forEach((pb) => {
        const card = document.createElement("div");
        card.className = "playbook-card" + (pb.id === currentPlaybookId ? " active" : "");
        card.innerHTML = `
            <div class="playbook-card-name">${pb.name}</div>
            <div class="playbook-card-meta">${pb.id} &middot; ${pb.step_count} step(s)${pb.trigger_type ? " &middot; " + pb.trigger_type : ""}</div>
            ${pb.error ? `<div class="playbook-card-error">${pb.error}</div>` : ""}
        `;
        card.addEventListener("click", () => openPlaybook(pb.id));
        playbooksList.appendChild(card);
    });
}

// --------------------------------------------------------------------------
// Open / New
// --------------------------------------------------------------------------

export async function openPlaybook(id) {
    const res = await KeenAPI.get(`/playbooks/${id}`);
    if (!res.ok) {
        showSnackbar("Playbooks", "Failed to load playbook.", "error", 5000);
        return;
    }
    const body = await res.json();
    currentPlaybookId = id;
    currentPlaybookData = body.playbook || { name: id, steps: [] };
    showEditor();
}

export function newPlaybook() {
    currentPlaybookId = null;
    currentPlaybookData = { name: "New Playbook", steps: [] };
    showEditor();
}

function showEditor() {
    playbookEmptyState.classList.add("hidden");
    playbookEditor.classList.remove("hidden");
    playbookNameInput.value = currentPlaybookData.name || currentPlaybookId || "";
    ensureDagNetwork();
    buildGraphFromPlaybook(currentPlaybookData);
    ensureCodeMirror();
    codeMirrorEditor.setValue(jsyaml.dump(currentPlaybookData, { sortKeys: false }));
    playbookYamlMessages.innerHTML = "";
    playbookRunLog.innerHTML = "";
    playbookRunStatus.innerHTML = "";
    activatePbTab("pb-tab-visual");
    fetchPlaybooksList();
}

function closeEditor() {
    currentPlaybookId = null;
    currentPlaybookData = null;
    playbookEditor.classList.add("hidden");
    playbookEmptyState.classList.remove("hidden");
}

// --------------------------------------------------------------------------
// Visual DAG builder (vis-network)
// --------------------------------------------------------------------------

function ensureDagNetwork() {
    if (dagNetwork) return;
    dagNodes = new vis.DataSet([]);
    dagEdges = new vis.DataSet([]);
    dagNetwork = new vis.Network(
        playbookDagCanvas,
        { nodes: dagNodes, edges: dagEdges },
        {
            nodes: {
                shape: "box",
                margin: 10,
                color: { background: "#1f2937", border: "#4b5563", highlight: { background: "#243044", border: "#00f0ff" } },
                font: { color: "#e5e7eb", multi: false },
            },
            edges: { arrows: "to", color: { color: "#6b7280" }, smooth: { type: "cubicBezier" } },
            layout: { hierarchical: { direction: "LR", sortMethod: "directed", levelSeparation: 160, nodeSpacing: 120 } },
            physics: false,
            interaction: { multiselect: true },
            manipulation: {
                enabled: true,
                addNode: (data, callback) => openStepPanel(null, callback),
                editNode: (data, callback) => openStepPanel(data, callback),
                addEdge: (data, callback) => {
                    if (data.from === data.to) {
                        callback(null);
                        return;
                    }
                    callback(data);
                },
                deleteNode: (data, callback) => callback(data),
                deleteEdge: (data, callback) => callback(data),
            },
        }
    );
}

function buildGraphFromPlaybook(playbook) {
    dagNodes.clear();
    dagEdges.clear();
    const steps = (playbook && playbook.steps) || [];
    steps.forEach((step) => {
        dagNodes.add({
            id: step.id,
            label: step.module ? `${step.id}\n${step.module}` : step.id,
            stepData: {
                id: step.id,
                module: step.module || "",
                inputs: step.inputs || {},
                condition: step.condition || "",
            },
        });
    });
    steps.forEach((step) => {
        const deps = step.depends_on
            ? Array.isArray(step.depends_on)
                ? step.depends_on
                : [step.depends_on]
            : [];
        deps.forEach((dep) => {
            if (dagNodes.get(dep)) {
                dagEdges.add({ from: dep, to: step.id, arrows: "to" });
            }
        });
    });
    if (dagNetwork) {
        setTimeout(() => dagNetwork.fit(), 50);
    }
}

function compileGraphToPlaybook() {
    const nodes = dagNodes ? dagNodes.get() : [];
    const edges = dagEdges ? dagEdges.get() : [];
    const dependsOnMap = {};
    edges.forEach((e) => {
        (dependsOnMap[e.to] = dependsOnMap[e.to] || []).push(e.from);
    });
    const steps = nodes.map((n) => {
        const sd = n.stepData || { id: n.id, module: "", inputs: {}, condition: "" };
        const step = { id: sd.id, module: sd.module };
        if (sd.inputs && Object.keys(sd.inputs).length) step.inputs = sd.inputs;
        const deps = dependsOnMap[n.id];
        if (deps && deps.length) step.depends_on = deps.length === 1 ? deps[0] : deps;
        if (sd.condition) step.condition = sd.condition;
        return step;
    });
    return { ...(currentPlaybookData || {}), name: playbookNameInput.value.trim() || "Untitled Playbook", steps };
}

// --------------------------------------------------------------------------
// Step edit panel
// --------------------------------------------------------------------------

function populateModuleSelect(selectedKey) {
    pbStepModuleSelect.innerHTML = '<option value="">-- Select Module --</option>';
    const modules = (window.KeenStore && KeenStore.modulesData) || {};
    Object.keys(modules)
        .sort()
        .forEach((key) => {
            const opt = document.createElement("option");
            opt.value = key;
            const mod = modules[key];
            opt.textContent = mod && mod.name ? `${mod.name} (${key})` : key;
            if (key === selectedKey) opt.selected = true;
            pbStepModuleSelect.appendChild(opt);
        });
}

function renderStepInputsFields(existingInputs) {
    pbStepInputsFields.innerHTML = "";
    const modules = (window.KeenStore && KeenStore.modulesData) || {};
    const mod = modules[pbStepModuleSelect.value];
    if (!mod || !mod.options) return;
    Object.entries(mod.options).forEach(([optKey, optArr]) => {
        const defaultVal = optArr[0];
        const required = optArr[1];
        const description = optArr[2] || "";
        const group = document.createElement("div");
        group.className = "form-group";
        const label = document.createElement("label");
        label.textContent = optKey + (required ? "*" : "");
        label.title = description;
        const input = document.createElement("input");
        input.type = "text";
        input.className = "pb-step-input-field";
        input.dataset.optKey = optKey;
        input.placeholder = defaultVal !== undefined && defaultVal !== null ? String(defaultVal) : "";
        input.value = existingInputs && existingInputs[optKey] !== undefined ? existingInputs[optKey] : "";
        group.appendChild(label);
        group.appendChild(input);
        pbStepInputsFields.appendChild(group);
    });
}

function collectStepInputs() {
    const inputs = {};
    pbStepInputsFields.querySelectorAll(".pb-step-input-field").forEach((el) => {
        if (el.value.trim() !== "") inputs[el.dataset.optKey] = el.value;
    });
    return inputs;
}

function openStepPanel(nodeData, callback) {
    pendingStepCallback = callback;
    const isEditing = !!(nodeData && dagNodes.get(nodeData.id));
    const stepData = isEditing && nodeData.stepData
        ? nodeData.stepData
        : { id: "", module: "", inputs: {}, condition: "" };

    pbStepIdInput.value = isEditing ? nodeData.id : "";
    pbStepIdInput.disabled = isEditing;
    populateModuleSelect(stepData.module);
    renderStepInputsFields(stepData.inputs);
    pbStepConditionInput.value = stepData.condition || "";
    playbookStepPanel.dataset.editingId = isEditing ? nodeData.id : "";
    playbookStepPanel.classList.remove("hidden");
}

function closeStepPanel(cancelled) {
    playbookStepPanel.classList.add("hidden");
    if (pendingStepCallback) {
        pendingStepCallback(cancelled ? null : undefined);
    }
    pendingStepCallback = null;
}

btnPbStepConfirm.addEventListener("click", () => {
    const stepId = pbStepIdInput.value.trim();
    if (!stepId) {
        showSnackbar("Playbooks", "Step ID is required.", "error", 4000);
        return;
    }
    const editingId = playbookStepPanel.dataset.editingId || "";
    if (!editingId && dagNodes.get(stepId)) {
        showSnackbar("Playbooks", `A step with id '${stepId}' already exists.`, "error", 4000);
        return;
    }
    const moduleKey = pbStepModuleSelect.value;
    const inputs = collectStepInputs();
    const condition = pbStepConditionInput.value.trim();
    const nodeData = {
        id: stepId,
        label: moduleKey ? `${stepId}\n${moduleKey}` : stepId,
        stepData: { id: stepId, module: moduleKey, inputs, condition },
    };
    const callback = pendingStepCallback;
    playbookStepPanel.classList.add("hidden");
    pendingStepCallback = null;
    if (callback) callback(nodeData);
});

btnPbStepCancel.addEventListener("click", () => closeStepPanel(true));

// --------------------------------------------------------------------------
// pb-tab switching (Visual Builder / YAML / Run) -- distinct from the
// Settings modal's `.settings-tab` group so switching one never disturbs
// the other's active state.
// --------------------------------------------------------------------------

function ensureCodeMirror() {
    if (codeMirrorEditor) return;
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    codeMirrorEditor = CodeMirror.fromTextArea(playbookYamlEditor, {
        mode: "yaml",
        lineNumbers: true,
        theme: isLight ? "default" : "dracula",
        indentUnit: 2,
        tabSize: 2,
    });
}

function syncVisualToYaml() {
    currentPlaybookData = compileGraphToPlaybook();
    ensureCodeMirror();
    codeMirrorEditor.setValue(jsyaml.dump(currentPlaybookData, { sortKeys: false }));
    playbookYamlMessages.innerHTML = "";
}

function syncYamlToVisual() {
    if (!codeMirrorEditor) return true;
    try {
        const parsed = jsyaml.load(codeMirrorEditor.getValue());
        currentPlaybookData = parsed;
        playbookNameInput.value = (parsed && parsed.name) || "";
        buildGraphFromPlaybook(parsed);
        playbookYamlMessages.innerHTML = "";
        return true;
    } catch (e) {
        playbookYamlMessages.innerHTML = `<div class="pb-msg-error">YAML parse error: ${e.message}</div>`;
        return false;
    }
}

function activatePbTab(target) {
    document.querySelectorAll(".pb-tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".pb-tab-content").forEach((c) => c.classList.remove("active"));
    const tab = document.querySelector(`.pb-tab[data-target="${target}"]`);
    if (tab) tab.classList.add("active");
    const content = document.getElementById(target);
    if (content) content.classList.add("active");
    if (target === "pb-tab-visual" && dagNetwork) {
        setTimeout(() => dagNetwork.redraw(), 50);
    }
    if (target === "pb-tab-yaml") {
        ensureCodeMirror();
        setTimeout(() => codeMirrorEditor.refresh(), 50);
    }
}

document.querySelectorAll(".pb-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        const target = tab.dataset.target;
        const currentlyYaml = document.getElementById("pb-tab-yaml").classList.contains("active");
        if (currentlyYaml && target !== "pb-tab-yaml") {
            if (!syncYamlToVisual()) return; // keep the user on the YAML tab until it's valid
        } else if (target === "pb-tab-yaml") {
            syncVisualToYaml();
        }
        activatePbTab(target);
    });
});

// --------------------------------------------------------------------------
// Save / Delete
// --------------------------------------------------------------------------

btnSavePlaybook.addEventListener("click", async () => {
    const yamlActive = document.getElementById("pb-tab-yaml").classList.contains("active");
    if (yamlActive && !syncYamlToVisual()) {
        showSnackbar("Playbooks", "Fix the YAML parse error before saving.", "error", 5000);
        return;
    }
    const playbook = compileGraphToPlaybook();
    if (!playbook.steps.length) {
        showSnackbar("Playbooks", "Add at least one step before saving.", "error", 5000);
        return;
    }

    const id = currentPlaybookId || slugify(playbook.name);
    const isCreate = !currentPlaybookId;
    const res = isCreate
        ? await KeenAPI.post(`/playbooks/${id}`, { playbook })
        : await KeenAPI.put(`/playbooks/${id}`, { playbook });
    const body = await res.json();

    if (res.ok && body.success) {
        currentPlaybookId = id;
        currentPlaybookData = playbook;
        showSnackbar("Playbooks", "Playbook saved.", "success", 3000);
        if (body.warnings && body.warnings.length) {
            showSnackbar("Playbooks", `Warnings: ${body.warnings.join("; ")}`, "warning", 7000);
        }
        fetchPlaybooksList();
    } else {
        const details = (body.errors || []).join("; ");
        showSnackbar("Playbooks", details || body.error || "Failed to save playbook.", "error", 7000);
    }
});

btnDeletePlaybook.addEventListener("click", async () => {
    if (!currentPlaybookId) {
        closeEditor();
        return;
    }
    if (!confirm(`Delete playbook '${currentPlaybookId}'? This cannot be undone.`)) return;
    const res = await KeenAPI.del(`/playbooks/${currentPlaybookId}`);
    if (res.ok) {
        showSnackbar("Playbooks", "Playbook deleted.", "success", 3000);
        closeEditor();
        fetchPlaybooksList();
    } else {
        showSnackbar("Playbooks", "Failed to delete playbook.", "error", 5000);
    }
});

// --------------------------------------------------------------------------
// Run (live-streaming WebSocket)
// --------------------------------------------------------------------------

function setDagNodeStatus(stepId, status) {
    if (!dagNodes || !dagNodes.get(stepId)) return;
    const colors = {
        pending: { background: "#1f2937", border: "#4b5563" },
        running: { background: "#0e3a44", border: "#00f0ff" },
        completed: { background: "#0e3d24", border: "#00e676" },
        failed: { background: "#3d0e14", border: "#ff1744" },
    };
    dagNodes.update({ id: stepId, color: colors[status] || colors.pending });
}

function appendRunLog(text, cls = "") {
    const line = document.createElement("div");
    line.className = `log-line ${cls}`;
    line.textContent = text;
    playbookRunLog.appendChild(line);
    playbookRunLog.scrollTop = playbookRunLog.scrollHeight;
    termPrint(`[playbook:${currentPlaybookId || "?"}] ${text}`, cls);
}

btnRunPlaybook.addEventListener("click", () => {
    if (!currentPlaybookId) {
        showSnackbar("Playbooks", "Save the playbook before running it.", "error", 5000);
        return;
    }
    const triggerValue = playbookTriggerValue.value.trim();
    if (!triggerValue) {
        showSnackbar("Playbooks", "A trigger value is required.", "error", 4000);
        return;
    }
    if (runSocket) {
        showSnackbar("Playbooks", "A run is already in progress.", "warning", 4000);
        return;
    }

    if (dagNodes) {
        dagNodes.get().forEach((n) => setDagNodeStatus(n.id, "pending"));
    }
    playbookRunLog.innerHTML = "";
    playbookRunStatus.innerHTML = '<span style="color: var(--accent-cyan);">Running...</span>';
    btnRunPlaybook.disabled = true;

    const ws = new WebSocket(KeenAPI.wsUrl(`/playbooks/${currentPlaybookId}/run`));
    runSocket = ws;
    KeenStore.activeSockets.push(ws);

    ws.onopen = () => {
        ws.send(
            JSON.stringify({
                trigger_value: triggerValue,
                workspace_name: KeenStore.activeWorkspace || "",
            })
        );
        appendRunLog(`Running playbook on '${triggerValue}'...`, "sys-msg");
    };

    ws.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (e) {
            appendRunLog(event.data);
            return;
        }
        switch (data.type) {
            case "log":
                appendRunLog(data.message);
                break;
            case "step_started":
                setDagNodeStatus(data.step_id, "running");
                appendRunLog(`> Step '${data.step_id}' started`, "sys-msg");
                break;
            case "step_completed":
                setDagNodeStatus(data.step_id, data.status === "failed" ? "failed" : "completed");
                appendRunLog(
                    `> Step '${data.step_id}' ${data.status} (${data.node_count} node(s) discovered)`,
                    data.status === "failed" ? "error" : "success"
                );
                break;
            case "playbook_finished":
                appendRunLog(`Playbook finished: ${data.step_count} step(s) ran.`, "success");
                break;
            case "status":
                playbookRunStatus.innerHTML = '<span style="color: var(--success);">Completed</span>';
                break;
            case "error":
                appendRunLog(`Error: ${data.message}`, "error");
                playbookRunStatus.innerHTML = '<span style="color: var(--error);">Error</span>';
                break;
            default:
                break;
        }
    };

    ws.onclose = () => {
        KeenStore.activeSockets = KeenStore.activeSockets.filter((s) => s !== ws);
        runSocket = null;
        btnRunPlaybook.disabled = false;
        appendRunLog("Connection closed.", "sys-msg");
        if (KeenStore.activeWorkspace) {
            import("./workspaces.js").then((m) => m.selectWorkspace(KeenStore.activeWorkspace));
        }
    };
});
