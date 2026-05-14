# Sherlock

---

- **Module Name:** `Sherlock`
- **Description:** Searches for a username on various social media sites.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Sherlock` module is an enumeration module that can be used to search for a username on various social media sites. It can retrieve details like registered platforms, recovery emails, and phone numbers. It uses the [sherlock](https://github.com/sherlock-project/sherlock) tool.

## Options

| Option   | Description            | Required | Default | Value Type |
| -------- | ---------------------- | -------- | ------- | ---------- |
| `TARGET` | The username to lookup | Yes      | None    | `username` |

## Usage

```bash
keen > use sherlock
keen(enumeration/sherlock) > set target <username>
keen(enumeration/sherlock) > run
```
