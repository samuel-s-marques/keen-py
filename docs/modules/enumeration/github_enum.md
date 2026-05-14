# Github Enumeration

---

- **Module Name:** `Github_Enum`
- **Description:** Enumerates Github information for a given username.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Github_Enum` module is an enumeration module that can be used to enumerate Github information for a given username. It can retrieve details like followers, following, repositories, stars, etc. It also retrieves email addresses if there are any available.

!!! info
    The use of [GitHub Personal Access Token](https://github.com/settings/tokens) is optional. If no API key is provided, the module will use the unauthenticated API. However, the use of [GitHub Personal Access Token](https://github.com/settings/tokens) is recommended for rate limiting purposes.

## Options

| Option         | Description                   | Required | Default | Value Type |
| -------------- | ----------------------------- | -------- | ------- | ---------- |
| `TARGET`       | The username to enumerate.    | Yes      | None    | `username` |
| `GITHUB_TOKEN` | Github Personal Access Token. | No       | None    | None       |

## Usage

```bash
keen > use github_enum
keen(enumeration/github_enum) > set target <username>
keen(enumeration/github_enum) > run
```