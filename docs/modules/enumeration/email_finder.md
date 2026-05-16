# Email Finder

---

- **Module Name:** `Email_Finder`
- **Description:** Generates possible email addresses based on name and domain through multiple methods. Ranks them by probability and tests against common EmailVerification module.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Email_Finder` module generates possible email addresses based on a person's first name, last name, and a target domain.

The module operates in two modes:
1. **Hunter.io Integration:** If a `HUNTER_IO_APIKEY` is provided, the module will query the Hunter.io API to find the email address. This method is highly accurate and can return additional metadata such as job title, company, and social profiles.
2. **Pattern Generation:** If no API key is provided or Hunter.io fails to find a result, the module falls back to generating a list of common email patterns based on the provided name and domain (e.g., `first.last@domain.com`, `flast@domain.com`).

!!! info "Note on Pattern Generation"
    If the `VERIFY` option is set to `True`, the module will verify the generated emails using the `EmailVerification` module. This will run SMTP or API checks to determine the validity of the generated emails and rank them by probability. This might take a while depending on the number of generated emails.

## Options

| Option             | Description                                         | Required | Default | Value Type |
| ------------------ | --------------------------------------------------- | -------- | ------- | ---------- |
| `FNAME`            | First name of the target.                           | Yes      | None    | `name`     |
| `LNAME`            | Last name of the target.                            | Yes      | None    | `name`     |
| `DOMAIN`           | Domain name to generate emails for.                 | Yes      | None    | `domain`   |
| `VERIFY`           | Verify found emails using EmailVerification module. | No       | `False` | `bool`     |
| `HUNTER_IO_APIKEY` | API Key for Hunter.io API.                          | No       | None    | None       |

## Usage

```bash
keen > use email_finder
keen(enumeration/email_finder) > set FNAME John
keen(enumeration/email_finder) > set LNAME Doe
keen(enumeration/email_finder) > set DOMAIN example.com
keen(enumeration/email_finder) > run
```