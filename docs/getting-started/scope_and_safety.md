# Scope & Execution Safety

Keen enforces two guardrails to keep automated pivoting (Magic Chaining, playbooks) and active/intrusive modules from silently going somewhere the investigator didn't intend:

- **Scope**: a per-case list of approved domains, IP/CIDR ranges, organizations, and named individuals. Anything discovered outside it is still saved to the graph, but flagged as quarantined instead of being trusted implicitly.
- **Execution Safety**: every module declares itself `passive`, `active`, or `intrusive`. Anything but `passive` requires explicit confirmation before it runs, whether that confirmation comes from a human at the terminal, a Web UI request, or an operator opting automated chaining into it.

Neither guardrail is on by default for scope (a case with no declared scope enforces nothing), and both apply uniformly no matter how a module is invoked -- directly, via `magic`, or via `playbook`.

## Scope

### Declaring scope at workspace creation

The most natural place to declare scope is when you create the case -- `workspace create` accepts a repeatable `--scope <type>:<value>` flag, so the case never exists without a declared boundary in the first place:

```
keen > workspace create "John Doe" "Investigation of John Doe" --scope domain:example.com --scope ip:203.0.113.10
INFO     | Created and switched to workspace: John Doe
INFO     | Declared 2 scope entries.
```

This shorthand doesn't carry a consent basis (see the warning below) -- for a `person` entry, follow up with `scope add` so the consent basis is actually recorded:

```
keen[John Doe] > scope add person "Jane Smith" "Signed consent form, engagement #4471"
```

### Editing an existing workspace's scope

Use `scope add`/`scope remove` against whichever workspace is currently active. `<type>` is one of `domain`, `ip`, `cidr`, `organization`, or `person`.

```
keen[John Doe] > scope add domain example.com "Client engagement, signed SOW #4471"
SUCCESS  | Added scope entry #1: domain 'example.com'.
```

Once at least one entry exists, any newly discovered node whose value doesn't match a declared entry is quarantined instead of silently treated as in-scope. Matching rules:

- `domain`: exact match or subdomain (`mail.example.com` matches a declared `example.com`).
- `ip` / `cidr`: the discovered IP must fall inside the declared address or CIDR block.
- `organization` / `person`: exact value match.

!!! warning "person scope requires consent, not just a name"

    A `person` scope entry should always carry a `consent_basis` describing why that individual is a legitimate target (e.g. a signed engagement, informed consent, public-interest journalism basis) -- this is what BEYOND_MALTEGO's guardrails call out as the difference between an OSINT framework and a surveillance/stalking tool. Don't add a `person` entry just because a name showed up in results.

### Listing scope

```
keen[John Doe] > scope list

                                  Declared Scope
┏━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID ┃ Type       ┃ Value         ┃ Consent Basis                        ┃
┡━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│  1 │ domain     │ example.com   │ Client engagement, signed SOW #4471  │
└────┴────────────┴───────────────┴───────────────────────────────────────┘
```

### Removing a scope entry

```
keen[John Doe] > scope remove 1
SUCCESS  | Removed scope entry #1.
```

### Reviewing quarantined nodes

Nodes discovered outside the declared scope show up here rather than being dropped -- you can always review and act on them manually.

```
keen[John Doe] > scope quarantined

                                  Quarantined Nodes
┏━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID ┃ Type        ┃ Value             ┃ Reason                                       ┃
┡━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 14 │ domain-name │ unrelated-org.com │ Discovered value falls outside the case's    │
│    │             │                   │ declared scope.                              │
└────┴─────────────┴───────────────────┴───────────────────────────────────────────────┘
```

Quarantined nodes are also excluded from Magic Chaining and playbook auto-pivoting -- an out-of-scope discovery stops the crawl there instead of silently expanding it further.

### Web UI

The **New Workspace** modal has an optional **Scope** section: click the **+** next to it to add a row (type, value, and a consent-basis field for `person` entries), one row per entry. Leaving it empty behaves exactly like `workspace create` with no `--scope` flag -- enforcement stays opted out.

To view or edit an existing workspace's scope, click the shield icon on its entry in the sidebar workspace list (next to rename/delete). That opens a modal listing current entries (each removable), a form to add new ones, and the workspace's quarantined nodes below it -- the same information `scope list`/`scope quarantined` show in the CLI, kept live as you add/remove entries.

### REST API

Scope can be declared inline when creating a workspace via `POST /api/workspaces`, by including a `scope` list alongside `name`/`description`:

```json
{
  "name": "John Doe",
  "description": "Investigation of John Doe",
  "scope": [
    {"scope_type": "domain", "value": "example.com", "consent_basis": "Signed SOW #4471"}
  ]
}
```

To view or edit an existing workspace's scope:

- `GET /api/workspaces/{name}/scope` -- list declared entries.
- `POST /api/workspaces/{name}/scope` -- add an entry (`scope_type`, `value`, `consent_basis`).
- `DELETE /api/workspaces/{name}/scope/{entry_id}` -- remove an entry.
- `GET /api/workspaces/{name}/quarantined-nodes` -- list nodes flagged as out-of-scope.

## Execution Safety

### The `passive` / `active` / `intrusive` classification

Every module declares its safety tier in metadata. Most recon modules (WHOIS, DNS enumeration, breach checks) are `passive` -- they never need confirmation. A module that actively probes a target (a port scan, a bruteforce sweep) would instead declare `"execution_safety": "active"` or `"intrusive"`.

### Running an active/intrusive module

If you `run` a module classified as anything but `passive`, Keen prompts for confirmation before it executes:

```
keen[John Doe] > use discovery/some_active_module
keen[John Doe](some_active_module) > set TARGET example.com
TARGET => example.com
keen[John Doe](some_active_module) > run
Executing...

[!] 'Some Active Module' is classified as active. Run it against 'example.com'? [y/N]: y
```

To skip the interactive prompt (e.g. when scripting), pre-confirm with `--i-understand` (or `-y`/`--yes`):

```
keen[John Doe](some_active_module) > run --i-understand
Executing...
```

In the Web UI, the run request includes a `confirm` flag the frontend sets after the operator acknowledges the same prompt in a modal -- there is no way to run an active/intrusive module from the Web UI without that acknowledgment reaching the server.

### Automated chaining and active modules

By default, Magic Chaining and playbooks **never** auto-run an active/intrusive module -- they skip it and log why, since there's no human present to confirm. To explicitly opt automated chaining into running them anyway, enable the `magic_allow_active_modules` preference:

```
keen > pref set magic_allow_active_modules true
```

Leave this `false` (the default) unless you specifically intend for background chains to escalate beyond passive recon on their own.
