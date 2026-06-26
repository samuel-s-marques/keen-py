# Workspace Management

Workspaces allow you to save your investigations and organize your findings. They are stored in `.keen` files, in the `cases` folder.

The `cases` folder is monitored by Keen. If you add or remove a `.keen` file from the `cases` folder, Keen will automatically update its list of available workspaces.

`.keen` files are sqlite3 databases, so you can open them with any sqlite3 client. **[API keys are not stored in `.keen` files.](api_keys_management.md)** These files only store nodes and edges, so usernames, domains, and other information you gathered using that workspace is stored there.

Workspaces are not required to use Keen. You can use Keen without any workspace, but it is **highly recommended** to use workspaces to keep your investigations organized. Otherwise, **no information will be saved** and everything will be lost when you close Keen.

## Usage

### Creating a workspace

To create a new workspace, use the `workspace create` command:
```
keen > workspace create <workspace-name> <optional description>
```

Example:
```
keen > workspace create "John Doe" "Investigation of John Doe"

keen > workspace create demo
INFO     | Created and switched to workspace: John Doe
keen[John Doe] >
```

### Listing workspaces

To list all available workspaces, use the `workspace list` command. The active workspace is marked with a `●`.
```bash
keen > workspace list
```

Example:
```
keen[John Doe] > workspace list

                                       Available Workspaces
┏━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┓
┃  Active  ┃ Name       ┃  Nodes ┃  Edges ┃ Description                   ┃ Path                  ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━┩
│    ●     │ John Doe   │      0 │      0 │ Investigation of John Doe     │ cases/John_Doe.keen   │
└──────────┴────────────┴────────┴────────┴───────────────────────────────┴───────────────────────┘
```

### Switching workspaces

To switch to a different workspace, use the `workspace select` command. Or simply `workspace <workspace-name>`.
```
keen > workspace select <workspace-name>
```

Example:
```
keen > workspace "John Doe"
INFO     | Switched to workspace: John Doe.
```

### Deleting workspaces

To delete a workspace, use the `workspace delete` command. The active workspace will be unregistered, but the database file will be kept.
```
keen > workspace delete <workspace-name>
```

Example:
```
keen > workspace delete "John Doe"
INFO     | Unregistered workspace: 'John Doe'. (Database file 'cases/John_Doe.keen' was kept).
```

### Renaming workspaces

To rename a workspace, use the `workspace rename` command.
```
keen > workspace rename <old-name> <new-name>
```

Example:
```
keen > workspace rename "John Doe" "John Doe v2"
INFO     | Renamed workspace: 'John Doe' to 'John Doe v2'.
```

### Setting the active workspace's description

To set the active workspace's description, use the `workspace set-desc` command.
```
keen > workspace set-desc <description>
```

Example:
```
keen > workspace set-desc "New description for John Doe"
INFO     | Set description for active workspace: 'New description for John Doe'.
```

### Exporting the active workspace

You can export your workspaces to multiple formats for reporting and integration:

- **PDF**: Renders a highly professional multi-page intelligence report containing executive statistics, categorized entity tables, and relationship maps.
- **HTML**: Renders a gorgeous dark-mode interactive dashboard summary of the workspace.
- **Markdown**: Generates a structured Markdown file detailing the workspace summary, all node categories in markdown tables, and relationships.
- **STIX 2.1 JSON**: Produces a standardized STIX 2.1 Bundle containing cyber observable objects (SDOs) and relationship objects (SROs).
- **JSON**: Produces a raw JSON backup of the workspace nodes, edges, positions, and metadata.

#### Using the Web UI
1. Select an active workspace from the left sidebar.
2. Click the **Export** button next to the workspace title in the center panel header.
3. Select your desired format from the dropdown menu.
4. The file will be generated on the server and downloaded automatically. Any errors during generation will be reported via notification snackbars.

#### Using the CLI
Use the `workspace export` command:
```
keen > workspace export <type> <path>
```

Where `<type>` is one of: `pdf`, `html`, `markdown`, `json`, `stix2`.

Example:
```
keen[John Doe] > workspace export html reports/john-doe.html
INFO     | Exported workspace: 'John Doe' to 'reports/john-doe.html'.
```