# Phone Verification

---

- **Module Name:** `Phone_Verification`
- **Description:** Verifies phone number validity through local analysis and external APIs.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Phone_Verification` module is an enumeration module that can be used to verify phone number validity through local analysis and external APIs.

!!! info
    The use of [APILayer Number Verification](https://marketplace.apilayer.com/number_verification-api) is optional. If no API key is provided, the module will use local analysis to verify the phone number. However, the use of [APILayer Number Verification](https://marketplace.apilayer.com/number_verification-api) is recommended for more accurate results.

    The phone number must be in E.164 format (e.g., +1234567890). No spaces or hyphens. The plus signal is optional.

## Options

| Option                      | Description                               | Required | Default | Value Type |
| --------------------------- | ----------------------------------------- | -------- | ------- | ---------- |
| `TARGET`                    | The phone number to verify.               | Yes      | None    | `phone`    |
| `APILAYER_PHONE_VER_APIKEY` | API Key for APILayer Number Verification. | No       | None    | None       |

## Usage

```bash
keen > use phone_verification
keen(enumeration/phone_verification) > set target <phone>
keen(enumeration/phone_verification) > run
```