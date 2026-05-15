# User Scanner

---

- **Module Name:** `User_Scanner`
- **Description:** Checks for usernames and emails on various platforms.
- **Author:** Samuel Marques
- **Version:** 1.1.0
- **Category:** Enumeration

## Description

The `User_Scanner` module is an enumeration module that can be used to check for usernames and emails on various platforms. It uses the [user_scanner](https://github.com/kaifcodec/user-scanner) tool. Can be used as an alternative to the `sherlock` module.

## Options

| Option   | Description          | Required | Default | Value Type       |
| -------- | -------------------- | -------- | ------- | ---------------- |
| `TARGET` | The target to lookup | Yes      | None    | `email,username` |

## Usage

```bash
keen > use user_scanner
keen(enumeration/user_scanner) > set target <email/username>
keen(enumeration/user_scanner) > run
```
