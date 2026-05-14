# Usage Guide

Keen is an advanced reconnaissance and OSINT framework designed for ethical hackers, penetration testers, and security researchers. It operates primarily through an intuitive interactive command-line interface (CLI) inspired by Metasploit, as well as a Web interface.

---

## Starting Keen

You can start Keen in interactive shell mode or web server mode:

```bash
# Start the interactive shell
python keen.py

# Start with debug logging enabled
python keen.py --debug

# Start the REST API web server
python keen.py --web --host 127.0.0.1 --port 8000
```

---

## The Interactive Shell

```
      :::    :::::::::::::::::::::::::::    :::
     :+:   :+: :+:       :+:       :+:+:   :+:
    +:+  +:+  +:+       +:+       :+:+:+  +:+
   +#++:++   +#++:++#  +#++:++#  +#+ +:+ +#+
  +#+  +#+  +#+       +#+       +#+  +#+#+#
 #+#   #+# #+#       #+#       #+#   #+#+#
###    ##########################    ####
See everything. Understand everything.

Version: 1.0.0
Welcome to Keen, an information gathering tool.
```

When you enter the Keen interactive shell, you will be greeted by the ASCII banner and a prompt. The prompt dynamically updates to display your currently active workspace and selected module: `keen[workspace](module) >`.

### Workspace Management

Workspaces compartmentalize your reconnaissance investigations. All gathered intelligence, nodes, and relationships are automatically stored in structured SQLite databases under the `cases/` directory (`cases/<workspace_name>.keen`).

```bash
# Create a new workspace
keen > workspace create target_corp "Internal audit for Target Corp"

# List all available workspaces and view node/edge counts
keen > workspace list

# Switch to an existing workspace
keen > workspace select target_corp

# Update the description of the active workspace
keen > workspace set-desc "Updated scope for Phase 2"

# Rename a workspace
keen > workspace rename target_corp target_corp_v2

# Export workspace intelligence (e.g., to STIX 2.1 JSON, Markdown, HTML, or PDF)
keen > workspace export stix2 output/target_corp.json

# Unregister a workspace from the registry
keen > workspace delete target_corp_v2
```

*For more information, check the [Workspace Management](workspace_management.md) documentation.*

---

## Module Selection & Execution

Keen features modular intelligence gathering across categories such as **Analysis**, **Discovery**, **Enumeration**, **Intel**, and **Web**. 

### Step-by-Step Reconnaissance Workflow

1. **List available modules:**
   ```bash
   keen > list modules
   ```

2. **Select a module:**
   You can specify the module name directly or by its category path.
   ```bash
   keen > use whois
   ```

3. **Inspect module metadata and required options:**
   ```bash
   keen[target_corp](discovery/whois) > show info
   keen[target_corp](discovery/whois) > show options
   ```

4. **Configure target options:**
   ```bash
   keen[target_corp](discovery/whois) > set TARGET example.com
   ```

5. **Execute the module:**
   Gathered intelligence will automatically be parsed, displayed in the console, and mapped into the active workspace graph as STIX 2.1 / MISP compliant nodes and edges.
   ```bash
   keen[target_corp](discovery/whois) > run
   ```

6. **Return to the main prompt:**
   ```bash
   keen[target_corp](discovery/whois) > back
   ```

---

## API Key Management

Some enumeration and intelligence modules require third-party API keys (e.g., Hunter.io, SecurityTrails, DeHashed). Keen securely encrypts and stores your keys in `~/.keen/config.db` using a master password.

```bash
# Unlock the key manager for the active session
keen > api_keys unlock

# Add or update an API key
keen > api_keys set hunter_io_apikey your_actual_api_key_here

# List stored API key services (keys are masked for security)
keen > api_keys list

# Delete an API key
keen > api_keys delete hunter_io_apikey
```

*For more detailed information on encryption mechanisms and supported services, consult the [API Keys Management](api_keys_management.md) documentation.*

---

## Global Settings & Utilities

You can adjust global framework settings on the fly or manage your session using built-in utilities:

```bash
# Enable or disable verbose debug logging at runtime
keen > set debug true
keen > set debug false

# Clear the terminal screen
keen > clear

# Start the web server directly from the interactive shell
keen > web start --host 127.0.0.1 --port 8080

# Show banner, including current version
keen > show banner

# Exit the shell
keen > exit
```
