# Magic Engine

The Magic Engine, inspired by [CyberChef's Magic operation](https://github.com/gchq/CyberChef/wiki/Automatic-detection-of-encoded-data-using-CyberChef-Magic), automatically detects the type of a retrieved node (such as an email, username, hash, or ID) and runs the appropriate modules on it.

The engine needs a workspace to store the results. If no workspace is being used, then the nodes are created in the "magic" workspace, the default magic chaining workspace. **[This is why it's highly recommended to use workspaces.](workspace_management.md)**

## Usage

### Using the CLI

To manually trigger a magic chain from the terminal, use the `magic` command followed by the target string. The engine will automatically detect the data type (e.g., `email-addr`, `ipv4-addr`, `domain-name`) and spawn all matching modules concurrently.

```bash
keen > magic <target>
```

Example:
```
keen > magic john.doe@example.com
INFO     | Initializing Magic Chaining for: john.doe@example.com
INFO     | [magic] Magic chaining depth 0: running 'Email Verification' on 'john.doe@example.com'
INFO     | [magic] Magic chaining depth 0: running 'Email Enrichment' on 'john.doe@example.com'
```

!!! tip "Interruption"

    You can cleanly interrupt an active magic chain run at any time by pressing `CTRL+C`.

### Using the Web UI

In the Web UI, you can trigger the Magic Engine directly on any existing node in your graph.

1. Right-click any node in the visualizer to open the context menu.
2. Click the **Magic Chaining** option.
3. A real-time notification snackbar will appear in the bottom-right corner streaming the execution logs.

*Note: If you need to stop a long-running execution from the Web UI, simply click the red **Stop** button on the active run snackbar.*

## Configuration Preferences

The Magic Engine behavior can be fully customized either through the `config` CLI command or via the **Settings** panel in the Web UI.

- `magic_enabled`: (Boolean) Enable or disable automatic recursive magic engine execution after standard module runs. Default is `false`.
- `magic_max_depth`: (Integer) The maximum recursive depth the engine will chain through. For example, a depth of `2` means the engine will run modules on the initial target (depth 0), run modules on those discovered nodes (depth 1), and finally on those newly discovered nodes (depth 2), then stop. Default is `2`.
- `magic_interactive`: (Boolean) If enabled, the engine will prompt you for confirmation before executing each step in the chain when running in the terminal. Default is `false`.
- `magic_exclude_modules`: (String) A comma-separated list of module snake_case names (e.g., `sherlock,email_verification`) to exclude from automatic magic chaining runs. Default is `""` (none).

### Example Configuration (CLI)

```bash
keen > pref set magic_enabled true
keen > pref set magic_max_depth 3
keen > pref set magic_exclude_modules "sherlock"
```
