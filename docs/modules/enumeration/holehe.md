# Holehe

---

- **Module Name:** `Holehe`
- **Description:** Checks for email accounts on various platforms.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Holehe` module is an enumeration module that can be used to check for email accounts on various platforms. It can retrieve details like registered platforms, recovery emails, and phone numbers. It uses the [holehe](https://github.com/megadose/holehe) tool.

## Options

| Option   | Description         | Required | Default | Value Type |
| -------- | ------------------- | -------- | ------- | ---------- |
| `TARGET` | The email to lookup | Yes      | None    | `email`    |

## Usage

```bash
keen > use holehe
keen(enumeration/holehe) > set target <email>
keen(enumeration/holehe) > run
```
