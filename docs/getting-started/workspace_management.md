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

To export the active workspace, use the `workspace export` command. The workspace can be exported in multiple formats, such as:

- **HTML**: Exports the workspace to an HTML file.
- **PDF**: Exports the workspace to a PDF file.
- **JSON**: Exports the workspace to a JSON file.
- **Markdown**: Exports the workspace to a Markdown file.
- **STIX2**: Exports the workspace to a STIX2 file.

Currently, not implemented.

```
keen > workspace export <type> <path>
```

Example:
```
keen > workspace export html reports/john-doe.html
INFO     | Exported workspace: 'John Doe' to 'reports/john-doe.html'.
```