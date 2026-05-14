# Email To Username

---

- **Module Name:** `Email_To_Username`
- **Description:** Extracts the username from an email address.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Helper

## Description

The `Email_To_Username` module is a helper module that can be used to extract the username from an email address. It removes the domain name and returns the username only. Mostly useful when using the Web interface, as it adds the username node to the graph. 

## Options

| Option   | Description                  | Required | Default | Value Type |
| -------- | ---------------------------- | -------- | ------- | ---------- |
| `TARGET` | The email address to convert | Yes      | None    | `email`    |

## Usage

```bash
keen > use email_to_username
keen(helpers/email_to_username) > set TARGET <email>
keen(helpers/email_to_username) > run
```