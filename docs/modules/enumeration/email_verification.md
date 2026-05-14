# Email Verification

---

- **Module Name:** `Email_Verification`
- **Description:** Verifies email address validity, reachability, MX records, and categorizes it.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Email_Verification` module is an enumeration module that can be used to verify email address validity, reachability, MX records, and categorize it.

!!! info
    The use of [APILayer Email Verification](https://marketplace.apilayer.com/email_verification-api) is optional. If no API key is provided, the module will use SMTP verification to verify the email address. However, the use of [APILayer Email Verification](https://marketplace.apilayer.com/email_verification-api) is recommended for more accurate results.

## Options

| Option                      | Description                              | Required | Default | Value Type |
| --------------------------- | ---------------------------------------- | -------- | ------- | ---------- |
| `TARGET`                    | The email address to lookup.             | Yes      | None    | `email`    |
| `APILAYER_EMAIL_VER_APIKEY` | API Key for APILayer Email Verification. | No       | None    | None       |

## Usage

```bash
keen > use email_verification
keen(enumeration/email_verification) > set target <email>
keen(enumeration/email_verification) > run
```