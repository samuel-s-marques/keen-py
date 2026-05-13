# API Keys Management

Keen uses API keys to authenticate with various services. API keys are stored in the configuration manager (`~/.keen/config.db`) and can be managed using the `api_keys` command.

Before using any module that requires API keys, you need to unlock the key manager. Keen will automatically prompt you to unlock the key manager when you try to use a module that requires API keys. But you can also unlock it manually using the `api_keys unlock` command.

The API keys are encrypted using a master password set by the user. **This master password is not stored anywhere** and will be required to unlock the key manager every time you start Keen. Only the derived `Fernet` key is held in-memory in the active `ConfigManager` instance for the duration of the session.

Keen uses `PBKDF2-HMAC` with 100,000 iterations of `SHA-256` and a unique, random 16-byte salt to derive the encryption key, which is then used by `Fernet` (which uses AES-128 in CBC mode) to encrypt and decrypt the API keys. The salt is stored along with the encrypted API keys in the configuration manager.

If there is an existing master password, Keen will prompt to unlock it up to 3 times when needed. If not, they are prompted to set one. You can skip this step by pressing **Enter** or `ctrl + c`.

## Usage

### Adding an API key

To add an API key, use the `api_keys set` command.

```
keen > api_keys set <service> <key>
```

Example:
```
keen > api_keys set hunter_io_apikey hunter-API-KEY
SUCCESS  | API key for service 'hunter_io_apikey' saved successfully!
```

### Listing API keys

To list all available API keys, use the `api_keys list` command.

```
keen > api_keys list
```

Example:
```
keen > api_keys list

                                          Stored API Keys
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Service                     ┃ API Key (Masked)                           ┃ Saved At             ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ apilayer_phone_ver_apikey   │ fdzO****************************           │ 2026-05-12 14:59:47  │
├─────────────────────────────┼────────────────────────────────────────────┼──────────────────────┤
│ hunter_io_apikey            │ 308d************************************   │ 2026-05-12 20:03:09  │
└─────────────────────────────┴────────────────────────────────────────────┴──────────────────────┘
```

### Deleting an API key

To delete an API key, use the `api_keys delete` command.

```
keen > api_keys delete <service>
```

Example:
```
keen > api_keys delete hunter_io_apikey
SUCCESS  | API key for service 'hunter_io_apikey' deleted successfully!
```

### Unlocking the key manager

To unlock the key manager, use the `api_keys unlock` command. This will prompt you to enter the master password for the key manager. The key manager will remain unlocked for the duration of the session, and you will not be prompted to enter the master password again until you restart Keen.

```
keen > api_keys unlock
```