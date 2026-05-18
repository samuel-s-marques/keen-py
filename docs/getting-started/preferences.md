# Preferences

Keen allows you to configure various preferences to customize the behavior of the application. Preferences are stored in the configuration manager (`~/.keen/config.db`) and can be managed using the `pref` command in the interactive shell or via the Web UI.

Unlike API keys, preferences are not encrypted and do not require unlocking the key manager to view or modify.

## Available Preferences

### Data Extraction Mode (`extraction_mode`)

This preference controls how data extracted from JSON responses (e.g., usernames, names, passwords extracted by the `PatternExtractor`) is handled when added to the graph.

Available options:

- **`merge`** (Default): Same values from different services merge into a single node. This is useful for finding connections across different leaks. (e.g., Value = `Username`)
- **`isolate`**: Same values become separate nodes to avoid false merging. A short random hash is appended to the value. (e.g., Value = `Username#a1b2`)
- **`isolate_with_service`**: Values are prefixed with the source service name to keep them separated by source. (e.g., Value = `BreachVIP:Service:Username`)

## Usage

### Listing Preferences

To list all available preferences, use the `pref list` command:

```
keen > pref list
```

Example:
```
keen > pref list

                               Preferences
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Key              ┃ Value                                                   ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ extraction_mode  │ merge                                                   │
└──────────────────┴─────────────────────────────────────────────────────────┘
```

### Getting a Preference

To get the value of a specific preference, use the `pref get` command:

```
keen > pref get <key>
```

Example:
```
keen > pref get extraction_mode
INFO     | extraction_mode = merge
```

### Setting a Preference

To set a preference value, use the `pref set` command:

```
keen > pref set <key> <value>
```

Example:
```
keen > pref set extraction_mode isolate
SUCCESS  | Preference 'extraction_mode' set to 'isolate'.
```

## Security / Blocked Keys

To prevent accidental modification or exposure of sensitive internal data, certain keys are blocked and cannot be accessed, listed, or modified via the `pref` command:

- `last_workspace`
- `api_keys_salt`
- `master_password_check`

## Web UI

You can also manage preferences in the Web UI. Open the **Settings / API Keys** modal, and you will find the **Data Extraction Mode** dropdown in the Preferences section.