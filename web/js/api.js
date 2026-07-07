/*
 * Keen API client — the single place the frontend talks to the backend.
 *
 * Centralizes: base URL resolution, JSON encoding, the session auth token
 * (bearer header, used when the server runs with KEEN_REQUIRE_AUTH), and
 * WebSocket URL construction. Exposed as `window.KeenAPI` (loaded as a classic
 * script before app.js) so existing code can adopt it incrementally.
 *
 * All request methods return the raw `fetch` Response, so callers keep using
 * `res.ok` / `res.json()` / `res.blob()` exactly as before.
 */
(function () {
    "use strict";

    const API_BASE = window.location.origin + "/api";
    const WS_BASE =
        (window.location.protocol === "https:" ? "wss:" : "ws:") +
        "//" +
        window.location.host +
        "/ws";

    const TOKEN_KEY = "keenAuthToken";
    let _token = null;
    try {
        _token = sessionStorage.getItem(TOKEN_KEY) || null;
    } catch (e) {
        /* sessionStorage unavailable */
    }
    // Mirror onto window for any legacy reader.
    if (_token) window.keenAuthToken = _token;

    function _headers(extra) {
        const h = Object.assign({}, extra || {});
        if (_token) h["Authorization"] = "Bearer " + _token;
        return h;
    }

    /**
     * Perform a request against the API.
     * @param {string} method HTTP verb.
     * @param {string} path Path relative to /api (e.g. "/workspaces").
     * @param {*} [body] JSON-serializable body (omit for none).
     * @param {object} [opts] { headers } extra headers.
     * @returns {Promise<Response>}
     */
    function request(method, path, body, opts) {
        opts = opts || {};
        const headers = _headers(opts.headers);
        const init = { method: method, headers: headers };
        if (body !== undefined && body !== null) {
            headers["Content-Type"] = "application/json";
            init.body = JSON.stringify(body);
        }
        return fetch(API_BASE + path, init);
    }

    window.KeenAPI = {
        API_BASE: API_BASE,
        WS_BASE: WS_BASE,

        request: request,
        get: function (path, opts) {
            return request("GET", path, null, opts);
        },
        post: function (path, body, opts) {
            return request("POST", path, body, opts);
        },
        put: function (path, body, opts) {
            return request("PUT", path, body, opts);
        },
        del: function (path, body, opts) {
            return request("DELETE", path, body, opts);
        },

        setToken: function (token) {
            _token = token || null;
            window.keenAuthToken = _token || undefined;
            try {
                if (_token) sessionStorage.setItem(TOKEN_KEY, _token);
                else sessionStorage.removeItem(TOKEN_KEY);
            } catch (e) {
                /* ignore */
            }
        },
        clearToken: function () {
            this.setToken(null);
        },
        getToken: function () {
            return _token;
        },

        /**
         * Build a WebSocket URL under /ws, appending the auth token as a query
         * param when set (so a future auth-enabled server can authenticate the
         * socket handshake).
         */
        wsUrl: function (path) {
            let url = WS_BASE + path;
            if (_token) {
                url += (path.indexOf("?") >= 0 ? "&" : "?") +
                    "token=" + encodeURIComponent(_token);
            }
            return url;
        },
    };
})();
