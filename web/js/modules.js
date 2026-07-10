/*
 * Module catalog: dropdown building, option handling, and execution over WS.
 */
import { moduleSelect, moduleForm } from "./dom.js";
import { showSnackbar, termPrint, updateSnackbar } from "./notifications.js";
import { selectWorkspace } from "./workspaces.js";
import { pollAISuggestionsStatus } from "./settings.js";

export const NODE_TO_VALIDATOR_MAP = {
    'email-addr': ['email'],
    'email-dst': ['email'],
    'domain-name': ['domain', 'url'],
    'ipv4-addr': ['ip'],
    'ipv6-addr': ['ip'],
    'x-phone-number': ['phone'],
    'phone-number': ['phone'],
    'x-url': ['url'],
    'person': ['name', 'username'],
    'user-account': ['username'],
    'organization': ['name', 'domain'],
};

// Tracks "moduleName:targetValue" strings to prevent duplicates
const activeRuns = new Set();

export function getRunKey(modName, options) {
    // Try to find the primary target value from options for dedup
    const mod = KeenStore.modulesData[modName];
    let targetValue = '';
    if (mod && mod.options) {
        for (const [key, optMeta] of Object.entries(mod.options)) {
            const validator = optMeta[3];
            if (validator && options[key]) {
                targetValue = options[key];
                break;
            }
        }
    }
    // Fallback: if no validator-matched value, use first non-empty option value
    if (!targetValue) {
        for (const val of Object.values(options)) {
            if (val) { targetValue = val; break; }
        }
    }
    return `${modName}:${targetValue}`;
}

export function getTargetLabel(options, modName) {
    const mod = KeenStore.modulesData[modName];
    if (mod && mod.options) {
        for (const [key, optMeta] of Object.entries(mod.options)) {
            const validator = optMeta[3];
            if (validator && options[key]) {
                return options[key];
            }
        }
    }
    return null;
}

export function executeModule(modName, options) {
    const runKey = getRunKey(modName, options);
    const targetLabel = getTargetLabel(options, modName);
    const displayName = formatModuleName(modName, KeenStore.modulesData[modName] || {});

    // Duplicate prevention
    if (activeRuns.has(runKey)) {
        const msg = targetLabel
            ? `Already running on ${targetLabel}`
            : 'Already running';
        showSnackbar(displayName, msg, 'warning', 3000);
        return;
    }

    activeRuns.add(runKey);
    const snackbarId = 'run-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
    const runMsg = targetLabel ? `Running on ${targetLabel}...` : 'Running...';
    showSnackbar(displayName, runMsg, 'info', 0, snackbarId);

    termPrint(`[${modName}] Connecting...`, 'sys-msg');

    const ws = new WebSocket(KeenAPI.wsUrl(`/modules/${modName}/run`));
    KeenStore.activeSockets.push(ws);
    KeenStore.activeSocketsMap.set(snackbarId, ws);
    let gotResult = false;

    ws.onopen = () => {
        ws.send(JSON.stringify({
            workspace_name: KeenStore.activeWorkspace || "",
            options: options
        }));
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'log') {
                termPrint(`[${modName}] ${data.message}`);
            } else if (data.type === 'status') {
                gotResult = true;
                termPrint(`[${modName}] Completed: ${data.status}`, 'success');
                updateSnackbar(snackbarId, displayName, 'Completed successfully', 'success', 4000);
            } else if (data.type === 'error') {
                gotResult = true;
                termPrint(`[${modName}] Error: ${data.message}`, 'error');
                updateSnackbar(snackbarId, displayName, `Error: ${data.message}`, 'error', 5000);
            }
        } catch (e) {
            termPrint(`[${modName}] ${event.data}`);
        }
    };

    ws.onclose = () => {
        KeenStore.activeSockets = KeenStore.activeSockets.filter(s => s !== ws);
        KeenStore.activeSocketsMap.delete(snackbarId);
        activeRuns.delete(runKey);
        termPrint(`[${modName}] Connection closed.`, 'sys-msg');

        if (!gotResult) {
            updateSnackbar(snackbarId, displayName, 'Connection closed', 'warning', 4000);
        }

        // Refresh workspace to show new nodes
        if (KeenStore.activeWorkspace) {
            selectWorkspace(KeenStore.activeWorkspace);
            pollAISuggestionsStatus(KeenStore.activeWorkspace);
        }
    };
}

export function formatModuleName(key, mod) {
    let cat = mod.category ? mod.category : "Uncategorized";
    cat = cat.charAt(0).toUpperCase() + cat.slice(1);
    cat = cat.replace(/[_-]/g, ' ');
    const name = mod.name ? mod.name.replace(/[_-]/g, ' ') : key;
    return `${cat} - ${name}`;
}

export function runModuleImmediately(modName, node) {
    if (!modName || !KeenStore.modulesData[modName]) return;

    const mod = KeenStore.modulesData[modName];
    const options = {};
    const validators = NODE_TO_VALIDATOR_MAP[node.type] || [];

    if (mod.options) {
        for (const [key, value] of Object.entries(mod.options)) {
            let defVal = (value[0] !== undefined && value[0] !== null) ? value[0] : '';

            // Auto-pull API keys if unlocked
            if (KeenStore.isConfigUnlocked && KeenStore.configKeys[key.toUpperCase()]) {
                defVal = KeenStore.configKeys[key.toUpperCase()];
            }

            // Check if this option should take the node's value
            const validator = value[3];
            if (validator) {
                const vals = Array.isArray(validator)
                    ? validator
                    : validator.split(',').map(v => v.trim());
                if (vals.some(v => validators.includes(v))) {
                    defVal = node.clean_value || node.value;
                }
            }

            if (defVal !== undefined && defVal !== null && defVal !== '') {
                options[key] = defVal.toString().trim();
            }
        }
    }

    executeModule(modName, options);
}

export function buildModuleDropdown(compatibleValidators = [], prefillValue = null, platform = null) {
    moduleSelect.innerHTML = '<option value="" disabled selected>-- Choose a module --</option>';

    const compatGroup = document.createElement('optgroup');
    compatGroup.label = platform ? `${platform.charAt(0).toUpperCase() + platform.slice(1)} Modules` : 'Compatible Modules';

    const allGroup = document.createElement('optgroup');
    allGroup.label = 'All Modules';

    let firstMatch = null;

    for (const key of Object.keys(KeenStore.modulesData).sort()) {
        const mod = KeenStore.modulesData[key];
        let isMatch = false;

        if (compatibleValidators.length > 0 && mod.options) {
            for (const [optName, optValue] of Object.entries(mod.options)) {
                const validator = optValue[3];
                if (validator) {
                    const vals = Array.isArray(validator)
                        ? validator
                        : validator.split(',').map(v => v.trim());
                    if (vals.some(v => compatibleValidators.includes(v))) {
                        isMatch = true;
                        break;
                    }
                }
            }
        }

        // Platform-specific filtering: prioritize modules matching the platform prefix
        if (isMatch && platform) {
            const lowerKey = key.toLowerCase();
            const lowerName = (mod.name || '').toLowerCase();
            const lowerDesc = (mod.description || '').toLowerCase();
            const lowerPlatform = platform.toLowerCase();
            const platformMatch = lowerKey.includes(lowerPlatform) || lowerName.includes(lowerPlatform) || lowerDesc.includes(lowerPlatform);
            // If platform-specific modules exist, mark non-matching ones as general
            if (!platformMatch) {
                isMatch = 'general';  // Still compatible but not platform-specific
            }
        }

        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = formatModuleName(key, mod);

        if (isMatch === true) {
            // Direct platform match or non-platform compatible
            if (!firstMatch) firstMatch = key;
            compatGroup.appendChild(opt.cloneNode(true));
        } else if (isMatch === 'general') {
            // Compatible but not platform-specific — still add to compat group
            if (!firstMatch) firstMatch = key;
            compatGroup.appendChild(opt.cloneNode(true));
        }
        allGroup.appendChild(opt);
    }

    if (compatGroup.children.length > 0) {
        moduleSelect.appendChild(compatGroup);
    }
    moduleSelect.appendChild(allGroup);

    if (firstMatch && prefillValue) {
        moduleSelect.value = firstMatch;
        moduleSelect.dispatchEvent(new Event('change'));

        setTimeout(() => {
            const inputs = moduleForm.querySelectorAll('input, select');
            for (const input of inputs) {
                const optVal = KeenStore.modulesData[firstMatch].options[input.name];
                if (optVal) {
                    const validator = optVal[3];
                    if (validator) {
                        const vals = Array.isArray(validator)
                            ? validator
                            : validator.split(',').map(v => v.trim());
                        if (vals.some(v => compatibleValidators.includes(v))) {
                            input.value = prefillValue;
                        }
                    }
                }
            }
        }, 50);
    }
}

export async function fetchModules() {
    try {
        const res = await KeenAPI.get(`/modules`);
        KeenStore.modulesData = await res.json();
        buildModuleDropdown();
        populateKnownApiServicesDatalist();
    } catch (e) {
        console.error('Failed to fetch modules', e);
    }
}

function populateKnownApiServicesDatalist() {
    const datalist = document.getElementById('known-api-services');
    if (!datalist) return;
    datalist.innerHTML = '';
    for (const name of [...getKnownApiServices()].sort()) {
        const opt = document.createElement('option');
        opt.value = name;
        datalist.appendChild(opt);
    }
}

// Mirrors BaseModule.API_KEY_OPTION_SUFFIXES in src/core/base_module.py — the
// option-name suffixes that mark a stored-credential option.
const API_KEY_OPTION_SUFFIXES = ['_APIKEY', '_API_KEY', '_TOKEN'];

// Provider names accepted by the AI Thinking Partner settings (saved as
// lowercase service names, separate from module option names).
const AI_PROVIDER_SERVICES = ['openai', 'anthropic', 'local', 'ollama', 'koboldcpp', 'custom'];

// Every service name a module (or the AI settings) will actually pick up:
// the full option name (e.g. SHODAN_APIKEY), its short form (SHODAN), or an
// AI provider name (openai). Derived from the live module catalog so it
// can't drift out of sync as modules are added.
export function getKnownApiServices() {
    const names = new Set(AI_PROVIDER_SERVICES);
    for (const mod of Object.values(KeenStore.modulesData || {})) {
        if (!mod.options) continue;
        for (const key of Object.keys(mod.options)) {
            const upper = key.toUpperCase();
            const suffix = API_KEY_OPTION_SUFFIXES.find(s => upper.endsWith(s));
            if (suffix) {
                names.add(upper);
                names.add(upper.slice(0, -suffix.length));
            }
        }
    }
    return names;
}

export function isKnownApiService(service) {
    const upper = service.toUpperCase();
    for (const name of getKnownApiServices()) {
        if (name.toUpperCase() === upper) return true;
    }
    return false;
}

function levenshtein(a, b) {
    const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
    for (let i = 0; i <= a.length; i++) dp[i][0] = i;
    for (let j = 0; j <= b.length; j++) dp[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
        for (let j = 1; j <= b.length; j++) {
            dp[i][j] = a[i - 1] === b[j - 1]
                ? dp[i - 1][j - 1]
                : 1 + Math.min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1]);
        }
    }
    return dp[a.length][b.length];
}

// Closest known service name to a mistyped one (e.g. SHODAN_API_KEY -> SHODAN_APIKEY),
// or null if nothing is close enough to be a useful suggestion.
export function findClosestApiService(service) {
    const upper = service.toUpperCase();
    let best = null;
    let bestDist = Infinity;
    for (const name of getKnownApiServices()) {
        const dist = levenshtein(upper, name.toUpperCase());
        if (dist < bestDist) {
            bestDist = dist;
            best = name;
        }
    }
    return bestDist <= 4 ? best : null;
}

export function runMagicChainingImmediately(targetValue) {
    const runKey = `magic:${targetValue}`;
    const displayName = `✨ Magic Chaining`;

    if (activeRuns.has(runKey)) {
        showSnackbar(displayName, `Already running on ${targetValue}`, 'warning', 3000);
        return;
    }

    activeRuns.add(runKey);
    const snackbarId = 'magic-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
    showSnackbar(displayName, `Initializing on ${targetValue}...`, 'info', 0, snackbarId);

    termPrint(`[magic] Connecting for target: ${targetValue}`, 'sys-msg');

    const ws = new WebSocket(KeenAPI.wsUrl(`/magic/run`));
    KeenStore.activeSockets.push(ws);
    KeenStore.activeSocketsMap.set(snackbarId, ws);
    let gotResult = false;

    ws.onopen = () => {
        ws.send(JSON.stringify({
            target: targetValue,
            workspace_name: KeenStore.activeWorkspace || ""
        }));
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'log') {
                termPrint(`[magic] ${data.message}`);
            } else if (data.type === 'status') {
                gotResult = true;
                termPrint(`[magic] Completed: ${data.status}`, 'success');
                updateSnackbar(snackbarId, displayName, 'Completed successfully', 'success', 4000);
            } else if (data.type === 'error') {
                gotResult = true;
                termPrint(`[magic] Error: ${data.message}`, 'error');
                updateSnackbar(snackbarId, displayName, `Error: ${data.message}`, 'error', 5000);
            }
        } catch (e) {
            termPrint(`[magic] ${event.data}`);
        }
    };

    ws.onclose = () => {
        KeenStore.activeSockets = KeenStore.activeSockets.filter(s => s !== ws);
        KeenStore.activeSocketsMap.delete(snackbarId);
        activeRuns.delete(runKey);
        termPrint(`[magic] Connection closed.`, 'sys-msg');

        if (!gotResult) {
            updateSnackbar(snackbarId, displayName, 'Connection closed', 'warning', 4000);
        }

        // Refresh workspace to show new nodes and edges
        if (KeenStore.activeWorkspace) {
            selectWorkspace(KeenStore.activeWorkspace);
            pollAISuggestionsStatus(KeenStore.activeWorkspace);
        }
    };
}
