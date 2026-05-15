# SOCMINT

---

- **Module Name:** `Socmint`
- **Description:** Performs SOCMINT (Social Media Intelligence) on a target.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Socmint` module is an enumeration module that uses different modules to perform SOCMINT on a target. It can retrieve details like registered platforms, recovery emails, and phone numbers. It uses Sherlock or User_Scanner for usernames, User_Scanner for emails, and Phone Verification for phone numbers.

## Options

| Option    | Description                                                  | Required | Default | Value Type                         |
| --------- | ------------------------------------------------------------ | -------- | ------- | ---------------------------------- |
| `TARGET`  | The target to lookup                                         | Yes      | None    | `email,phone,username,domain,name` |
| `TYPE`    | The type of the target (username, name, domain, phone, auto) | No       | None    |
| `TIMEOUT` | Timeout for each module execution in seconds                 | No       | None    |

## Usage

```bash
keen > use socmint
keen(enumeration/socmint) > set target <target>
keen(enumeration/socmint) > run
```
