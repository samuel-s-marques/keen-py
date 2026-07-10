/*
 * Keen DOM registry — every shared element reference used across the frontend,
 * resolved once and exported so feature modules can `import { x } from "./dom.js"`
 * and use the same names their code always used (no call-site churn).
 *
 * This is an ES module loaded via the deferred module graph (main.js), so the
 * document is fully parsed by the time these run.
 */

// Layout / theme
export const btnThemeToggle = document.getElementById("btn-theme-toggle");
export const sidebar = document.querySelector(".sidebar");
export const rightPanel = document.querySelector(".right-panel");
export const terminalContainer = document.querySelector(".terminal-container");
export const sidebarResizer = document.getElementById("sidebar-resizer");
export const rightPanelResizer = document.getElementById("right-panel-resizer");
export const terminalResizer = document.getElementById("terminal-resizer");

// Workspaces / tables / graph
export const workspaceList = document.getElementById("workspace-list");
export const activeWorkspaceTitle = document.getElementById("active-workspace-title");
export const countNodes = document.getElementById("count-nodes");
export const countEdges = document.getElementById("count-edges");
export const nodesTbody = document.getElementById("nodes-tbody");
export const edgesTbody = document.getElementById("edges-tbody");
export const networkCanvas = document.getElementById("network-canvas");

// Module panel
export const moduleSelect = document.getElementById("module-select");
export const moduleDetails = document.getElementById("module-details");
export const moduleDesc = document.getElementById("module-description");
export const moduleAuthor = document.getElementById("module-author");
export const moduleVersion = document.getElementById("module-version");
export const moduleForm = document.getElementById("module-form");
export const btnRunModule = document.getElementById("btn-run-module");

// Terminal
export const terminalBody = document.getElementById("terminal-body");
export const btnClearTerm = document.getElementById("btn-clear-term");

// Context menu
export const contextMenu = document.getElementById("context-menu");
export const contextMenuItems = document.getElementById("context-menu-items");

// New-workspace modal
export const modalNewWs = document.getElementById("modal-new-workspace");
export const btnNewWs = document.getElementById("btn-new-workspace");
export const btnCreateWs = document.getElementById("btn-create-ws");
export const inputWsName = document.getElementById("input-ws-name");
export const inputWsDesc = document.getElementById("input-ws-desc");
export const wsNameWarning = document.getElementById("ws-name-warning");

// Rename-workspace modal
export const modalRenameWs = document.getElementById("modal-rename-workspace");
export const btnConfirmRenameWs = document.getElementById("btn-confirm-rename-ws");
export const inputRenameWs = document.getElementById("input-rename-ws");

// Settings modal
export const modalSettings = document.getElementById("modal-settings");
export const btnSettings = document.getElementById("btn-settings");
export const btnUnlockSettings = document.getElementById("btn-unlock-settings");
export const inputMasterPassword = document.getElementById("input-master-password");
export const apiKeysLocked = document.getElementById("api-keys-locked");
export const apiKeysUnlocked = document.getElementById("api-keys-unlocked");
export const btnSaveApiKey = document.getElementById("btn-save-api-key");
export const apiKeysList = document.getElementById("api-keys-list");
export const prefExtractionMode = document.getElementById("pref-extraction-mode");
export const prefMagicEnabled = document.getElementById("pref-magic-enabled");
export const prefMagicMaxDepth = document.getElementById("pref-magic-max-depth");
export const prefMagicInteractive = document.getElementById("pref-magic-interactive");
export const prefMagicExcludeModules = document.getElementById("pref-magic-exclude-modules");
export const btnSavePreferences = document.getElementById("btn-save-preferences");
export const closeModals = document.querySelectorAll(".close-modal");

// Rate limit settings
export const ratelimitShodanRps = document.getElementById("ratelimit-shodan-rps");
export const ratelimitCensysRps = document.getElementById("ratelimit-censys-rps");
export const ratelimitCrtshRps = document.getElementById("ratelimit-crtsh-rps");
export const ratelimitHibpRps = document.getElementById("ratelimit-hibp-rps");
export const ratelimitMalshareRps = document.getElementById("ratelimit-malshare-rps");
export const btnSaveRateLimits = document.getElementById("btn-save-rate-limits");

// Playbooks modal
export const btnPlaybooks = document.getElementById("btn-playbooks");
export const modalPlaybooks = document.getElementById("modal-playbooks");
export const playbooksList = document.getElementById("playbooks-list");
export const btnNewPlaybook = document.getElementById("btn-new-playbook");
export const playbookEmptyState = document.getElementById("playbook-empty-state");
export const playbookEditor = document.getElementById("playbook-editor");
export const playbookNameInput = document.getElementById("playbook-name-input");
export const btnSavePlaybook = document.getElementById("btn-save-playbook");
export const btnDeletePlaybook = document.getElementById("btn-delete-playbook");
export const playbookDagCanvas = document.getElementById("playbook-dag-canvas");
export const playbookStepPanel = document.getElementById("playbook-step-panel");
export const pbStepIdInput = document.getElementById("pb-step-id-input");
export const pbStepModuleSelect = document.getElementById("pb-step-module-select");
export const pbStepInputsFields = document.getElementById("pb-step-inputs-fields");
export const pbStepConditionInput = document.getElementById("pb-step-condition-input");
export const btnPbStepConfirm = document.getElementById("btn-pb-step-confirm");
export const btnPbStepCancel = document.getElementById("btn-pb-step-cancel");
export const playbookYamlEditor = document.getElementById("playbook-yaml-editor");
export const playbookYamlMessages = document.getElementById("playbook-yaml-messages");
export const playbookTriggerValue = document.getElementById("playbook-trigger-value");
export const btnRunPlaybook = document.getElementById("btn-run-playbook");
export const playbookRunStatus = document.getElementById("playbook-run-status");
export const playbookRunLog = document.getElementById("playbook-run-log");

// Create-node modal
export const modalCreateNode = document.getElementById("modal-create-node");
export const nodeTypeSelect = document.getElementById("node-type-select");
export const nodeValueInput = document.getElementById("node-value");
export const nodePropsContainer = document.getElementById("node-props-container");
export const nodePropsFields = document.getElementById("node-props-fields");
export const btnAddCustomProp = document.getElementById("btn-add-custom-prop");
export const btnConfirmCreateNode = document.getElementById("btn-confirm-create-node");

// Edit-node modal
export const modalEditNode = document.getElementById("modal-edit-node");
export const editNodeIdInput = document.getElementById("edit-node-id");
export const editNodeTypeSelect = document.getElementById("edit-node-type");
export const editNodeValueInput = document.getElementById("edit-node-value");
export const editNodePropsFields = document.getElementById("edit-node-props-fields");
export const btnAddEditNodeProp = document.getElementById("btn-add-edit-node-prop");
export const btnConfirmEditNode = document.getElementById("btn-confirm-edit-node");

// Edit-edge modal
export const modalEditEdge = document.getElementById("modal-edit-edge");
export const editEdgeIdInput = document.getElementById("edit-edge-id");
export const editEdgeRelationshipInput = document.getElementById("edit-edge-relationship");
export const editEdgePropsFields = document.getElementById("edit-edge-props-fields");
export const btnAddEditEdgeProp = document.getElementById("btn-add-edit-edge-prop");
export const btnConfirmEditEdge = document.getElementById("btn-confirm-edit-edge");

// Snackbar / status
export const snackbarContainer = document.getElementById("snackbar-container");
export const statusIndicator = document.querySelector(".status-indicator");
export const statusText = document.querySelector(".server-status span");

// Export menu
export const btnExportWs = document.getElementById("btn-export-ws");
export const exportMenu = document.getElementById("export-menu");
export const exportDropdown = document.getElementById("export-dropdown");

// Timeline
export const timelineSlider = document.getElementById("timeline-slider");
export const btnTimelinePlay = document.getElementById("btn-timeline-play");
export const timelineSpeed = document.getElementById("timeline-speed");

// AI settings / suggestions
export const prefAiProvider = document.getElementById("pref-ai-provider");
export const groupAiBaseUrl = document.getElementById("group-ai-base-url");
export const prefAiEnabled = document.getElementById("pref-ai-enabled");
export const prefAiModel = document.getElementById("pref-ai-model");
export const prefAiBaseUrl = document.getElementById("pref-ai-base-url");
export const prefAiApiKey = document.getElementById("pref-ai-api-key");
export const btnSaveAiSettings = document.getElementById("btn-save-ai-settings");
export const suggestionsList = document.getElementById("suggestions-list");
export const btnAnalyzeGraph = document.getElementById("btn-analyze-graph");
export const btnTestAiConn = document.getElementById("btn-test-ai-conn");
export const btnDetectAiModel = document.getElementById("btn-detect-ai-model");
