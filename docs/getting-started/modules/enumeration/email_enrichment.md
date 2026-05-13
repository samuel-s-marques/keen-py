# Email Enrichment

---

- **Module Name:** `Email_Enrichment`
- **Description:** Enriches an email address with additional information using Hunter.io and other sources.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Email_Enrichment` module allows you to retrieve all the information related to an email address of a person, such as a person's name, location, and social handles, through Hunter.io.

## Options

| Option             | Description                  | Required | Default | Value Type |
| ------------------ | ---------------------------- | -------- | ------- | ---------- |
| `TARGET`           | The email address to lookup. | Yes      | None    | `email`    |
| `HUNTER_IO_APIKEY` | API Key for Hunter.io API.   | No       | None    | None       |

## Usage

```bash
keen > use email_enrichment
keen(enumeration/email_enrichment) > set TARGET [EMAIL_ADDRESS]
keen(enumeration/email_enrichment) > run
```
