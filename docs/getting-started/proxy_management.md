# Proxy Management

To prevent IP rate-limiting, Web Application Firewall (WAF) blocks, and IP bans when running intensive scanning and OSINT discovery tasks, Keen integrates a **Unified Global Proxy System**. Proxies are stored in the configuration manager (`~/.keen/config.db`) and are used globally across all network-bound modules.

## Supported Protocols & Schemes

Keen supports a wide range of proxy protocols. When configuring proxy URLs, use the format: `scheme://[username:password@]host:port`.
Supported schemes are:

- `http`: Standard HTTP proxy.
- `https`: Secure HTTPS proxy.
- `socks4` / `socks4a`: SOCKS4 and SOCKS4a proxies.
- `socks5` / `socks5h`: SOCKS5 proxies (with `socks5h` forcing DNS resolution through the proxy).

---

## Rotation Modes

Keen offers three rotation modes to distribute request traffic. You can configure rotation modes via the interactive CLI or the Web UI:

- **`round-robin`** (Default): Cycles sequentially through all active (online) proxies.
- **`random`**: Randomly selects an online proxy for each outgoing request.
- **`sticky`**: Selects a proxy and uses it persistently for all requests during the current session or task run.
- **`off`**: Globally disables proxy routing (requests are made directly from your local host).

> [!NOTE]
> If a rotation mode is active but all configured proxies are offline, Keen will automatically fall back to using all enabled proxies (attempting routing regardless of their tested status) rather than failing the scan.

---

## CLI Usage (keen shell)

The interactive CLI provides a dedicated `proxy` command suite to configure, list, test, and load proxies.

### Enabling and Setting the Rotation Mode

To set the rotation mode (or disable the proxy system), use `proxy set-mode`:

```
keen > proxy set-mode <random | round-robin | sticky | off>
```

**Examples:**

```
keen > proxy set-mode round-robin
SUCCESS  | Proxy system enabled. Rotation mode set to: round-robin
```

```
keen > proxy set-mode off
SUCCESS  | Proxy system disabled globally.
```

### Adding a Proxy

To add a single proxy, use `proxy add <url>`:

```
keen > proxy add <url>
```

**Example:**

```
keen > proxy add socks5://admin:secret123@192.168.1.50:1080
SUCCESS  | Proxy 'socks5://admin:****@192.168.1.50:1080' added successfully.
```

> [!IMPORTANT]
> The proxy password is automatically masked as `****` in success messages and lists to prevent exposing credentials in your console history or logs.

### Listing Configured Proxies

To see all configured proxies, their health status, latency, and status, use `proxy list`:

```
keen > proxy list
```

**Example:**

```
keen > proxy list

                               Configured Proxies
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓
┃  ID  ┃ Proxy URL                              ┃ Status  ┃ Latency ┃ Enabled ┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩
│  1   │ http://127.0.0.1:8080                  │ Online  │ 120ms   │   Yes   │
├──────┼────────────────────────────────────────┼─────────┼─────────┼─────────┤
│  2   │ socks5://admin:****@192.168.1.50:1080  │ Offline │ -       │   Yes   │
└──────┴────────────────────────────────────────┴─────────┴─────────┴─────────┘
INFO     | Proxy Routing: ENABLED (Rotation Mode: round-robin)
```

### Concurrently Testing Proxies

To run connectivity checks on all registered proxies in parallel (using a default concurrency limit of 10), run `proxy test`. Proxies are verified against `https://httpbin.org/ip`:

```
keen > proxy test
```

**Example:**

```
keen > proxy test
INFO     | Verifying 2 proxies concurrently against https://httpbin.org/ip...
SUCCESS  | Test complete: 1 Online, 1 Offline.
```

### Bulk Loading Proxies

You can load a list of proxies from a local text file using `proxy load <path>`. The file should contain one proxy URL per line. Lines starting with `#` are treated as comments and ignored:

```
keen > proxy load <path>
```

**Example:**

```
keen > proxy load C:\Users\user\Desktop\proxies.txt
SUCCESS  | Loaded 25 new proxies from file successfully (skipped 3 duplicates).
```

### Deleting Proxies

To delete a proxy by its database ID, or bulk delete using wildcard patterns (like `*` or `?`), use `proxy delete`:

```
keen > proxy delete <id | wildcard_pattern>
```

**Examples:**

```
keen > proxy delete 2
SUCCESS  | Proxy with ID 2 deleted successfully.
```

```
keen > proxy delete socks5://*
SUCCESS  | Deleted 5 proxies matching pattern 'socks5://*'.
```

```
keen > proxy delete *
SUCCESS  | Deleted 20 proxies matching pattern '*'.
```

---

## Web UI Controls

The Keen Web UI provides a visual suite for managing your proxies. Open the **Settings** modal and select the **Proxies** tab:

- **Global Toggle**: Instantly enable or disable proxy routing.
- **Mode Selector**: Choose your rotation mode (`round-robin`, `random`, `sticky`) via a dropdown.
- **Drag & Drop Import**: Drag and drop a `.txt` file containing proxy URLs directly into the drop zone, or browse to import them.
- **Individual Toggle**: Enable or disable specific proxies individually using the checkbox in each row.
- **Delete & Test Interactively**: Delete individual entries or click **Test Connectivity** to start background checks with visual progress spinners.

---

## Security & API Design

To keep Keen secure under its permissive CORS policy (allowing Web UI integrations from any origin), the following measures are active:

- **Credential Masking**: The endpoint `GET /api/proxies` automatically redacts passwords (`user:****@host:port`) prior to transmission to prevent credential leakage in browser environments.
- **Local File Security**: The bulk import API (`POST /api/proxies/load`) rejects local file paths and accepts only raw text content to prevent arbitrary local file reads.

---

## Integration in Discovery Modules (For Developers)

For developers writing custom discovery modules, Keen makes routing outbound traffic through the proxy pool completely seamless. Instead of instantiating `httpx.AsyncClient()` directly, modules should use the built-in HTTP client factory `self.get_http_client()`:

```python
# Inside a custom discovery module
async def run(self):
    # This automatically provisions a client routed through the next proxy in the rotation
    async with self.get_http_client() as client:
        response = await client.get("https://api.example.com/data")
        # Process response...
```

The factory automatically resolves the next proxy according to rotation settings, checks if it's online, sets it as the proxy for the `httpx` client, and manages database fallback logic behind the scenes.
