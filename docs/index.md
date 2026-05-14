# Welcome to Keen

```
88      a8P
88    ,88'
88  ,88"
88,d88'      ,adPPYba,  ,adPPYba, 8b,dPPYba,
8888"88,    a8P_____88 a8P_____88 88P'   `"8a
88P   Y8b   8PP""""""" 8PP""""""" 88       88
88     "88, "8b,   ,aa "8b,   ,aa 88       88
88       Y8b `"Ybbd8"'  `"Ybbd8"' 88       88


The invisible becomes legible.
```

**Keen** is an advanced reconnaissance and Open-Source Intelligence (OSINT) framework designed for ethical hackers, penetration testers, and security researchers. Inspired by the philosophy of keen observation, the framework automates the collection, processing, and correlation of intelligence across diverse targets.

---

## Key Features

- **Modular Architecture**: Built with pluggable modules categorized across **Analysis**, **Discovery**, **Enumeration**, **Intel**, and **Web**. Gather everything from WHOIS records and subdomains to social media footprints and data leaks.
- **Interactive CLI & Web Server**: Operate seamlessly via a Metasploit-inspired interactive terminal shell or launch the built-in REST API web server for UI dashboards and automation workflows.
- **Structured Workspaces**: Compartmentalize investigations into dedicated `.keen` case files. Track intelligence graphs (nodes and edges) with built-in export capabilities to STIX 2.1 JSON, MISP, Markdown, HTML, and PDF.
- **Secure API Key Management**: Safely store third-party service credentials (e.g., HaveIbeenPwned, SecurityTrails, Hunter.io, Github) using PBKDF2-HMAC and AES-128 encryption protected by a master password.
- **Standardized Intelligence**: All extracted artifacts are mapped to standardized threat intelligence schemas, allowing effortless integration with external SIEM, MISP, and investigation platforms.

---

## Where to Go Next?

Explore the documentation to get up and running, configure your environment, or extend the framework:

### Getting Started
- **[Installation](getting-started/installation.md)**: System requirements, cloning the repository, and installing dependencies.
- **[Usage Guide](getting-started/usage.md)**: Operating the interactive shell, global settings, and launching the web server.
- **[Workspace Management](getting-started/workspace_management.md)**: Creating cases, managing graph nodes/edges, and exporting intelligence reports.
- **[API Keys Management](getting-started/api_keys_management.md)**: Unlocking the secure credential manager and registering third-party services.
- **[Web Server](getting-started/web.md)**: Launching the web server and accessing the UI dashboards.

### Modules Directory
- **[Modules Overview](modules/index.md)**: Browse all available reconnaissance modules across Analysis, Discovery, Enumeration, Web, and Helpers.

### Developer & Community
- **[Developing New Modules](developer/developing_new_modules.md)**: Guide to developing new modules for the framework.
- **[Contributing](about/contributing.md)**: Guidelines for contributing code, reporting bugs, and submitting pull requests.
- **[Roadmap](about/roadmap.md)**: Planned features, upcoming integrations, and framework milestones.
