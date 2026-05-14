# Selecting and Using a Module

Keen's reconnaissance capabilities are driven by a highly flexible, modular architecture. Modules are categorized by their role in the intelligence lifecycle, allowing investigators to perform targeted data collection, discovery, and enrichment.

---

## Module Categories

Keen groups modules into five primary categories:

- **Analysis**: Process existing data or indicators. Check if credentials appear in known breaches or infostealer logs (e.g., Hudson Rock, LeakCheck).
- **Discovery**: Identify infrastructure and external attack surface area. Explore domain ownership, DNS records, and hidden subdomains.
- **Enumeration**: Deep-dive into specific targets. Discover social media footprints, verify email/phone deliverability, and query GitHub activity.
- **Web**: Inspect web applications, identifying Web Application Firewalls (WAFs), Content Delivery Networks (CDNs), and tech stacks.
- **Helpers**: Perform utility transformations on data, such as extracting usernames from email addresses or parsing base domains from URLs.

---

## Managing Modules in the CLI

Operating modules in the interactive terminal shell follows a standard, intuitive workflow inspired by Metasploit.

### 1. Listing Available Modules
To see all loaded modules across the framework, use the `list` or `show` command:
```bash
keen > list modules
```
*This outputs a formatted table listing each module's path and description.*

### 2. Selecting a Module
Select a module using the `use` command. You can provide the friendly short name or the complete category path:
```bash
# Using the short name
keen > use whois

# Using the full category path
keen > use discovery/whois
```
Once selected, your prompt will update to indicate the active module context: `keen[workspace](discovery/whois) >`.

### 3. Inspecting Module Information & Options
Before running a module, you can review its metadata (author, version, description) and its configurable parameters:
```bash
# View metadata and description
keen[workspace](discovery/whois) > show info

# View required and optional parameters
keen[workspace](discovery/whois) > show options
```

### 4. Configuring Parameters
Use the `set` command to configure target parameters. Most modules require a `TARGET` option (which could be a domain, IP, email, or username depending on the module):
```bash
keen[workspace](discovery/whois) > set TARGET example.com
```

### 5. Executing the Module
Launch the module with the `run` command. Keen will execute the underlying queries asynchronously, outputting results in a rich console table and automatically saving the extracted indicators (nodes and relationship edges) into your active workspace database.
```bash
keen[workspace](discovery/whois) > run
```

### 6. Deselecting a Module
To leave the current module context and return to the main workspace prompt, use the `back` command:
```bash
keen[workspace](discovery/whois) > back
```

---

## Running Modules in the Web Interface

If you are operating Keen via the Web Server (`--web`), module execution is fully integrated into the browser UI:

1. **Module Selection**: Navigate to the **Runner** sidebar in the dashboard.
2. **Dynamic Configuration**: Selecting a module automatically generates input fields corresponding to its required options.
3. **Execution & Live Monitoring**: Clicking **Run** triggers the module over an asynchronous WebSocket connection. Live debug logs and output tables stream directly into your browser console, and discovered assets immediately populate the visual investigation graph.
