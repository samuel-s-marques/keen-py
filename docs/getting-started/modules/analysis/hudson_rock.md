# Hudson Rock

---

- **Module Name:** `Hudson_Rock`
- **Description:** Checks if email is associated with devices infected with infostealers.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Analysis

## Description

The `Hudson_Rock` module checks if an email address is associated with devices infected with infostealers using the Hudson Rock API. It returns a list of breaches associated with the email address, along with the number of corporate and user services affected. In case the target email address is not associated with any breaches, the module will return a message indicating that no breaches were found. It will also show the top passwords (masked) and logins (email:password, masked) associated with the email address, as well as the IP address and operating system of the infected device.

## Options

| Option   | Description                  | Default | Value Type |
| -------- | ---------------------------- | ------- | ---------- |
| `TARGET` | The email address to lookup. | None    | `email`    |

## Usage

```bash
keen > use hudson_rock
keen(analysis/hudson_rock) > set target [EMAIL_ADDRESS]
keen(analysis/hudson_rock) > run
```