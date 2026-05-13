# Leak Check

---

- **Module Name:** `Leak_Check`
- **Description:** Checks if credentials (username, email, phone) have been leaked using various databases.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Analysis

## Description

The `Leak_Check` module checks if a username, email, or phone number has been leaked using the LeakCheck, BreachVIP, and DeHashed APIs. If the target is an email address, it will also check HaveIBeenPwned.

## Usage

```bash
keen > use leak_check
keen(analysis/leak_check) > set target [EMAIL_ADDRESS]
keen(analysis/leak_check) > run
```

## Options

| Option             | Description                    | Default | Required | Value Type             |
| ------------------ | ------------------------------ | ------- | -------- | ---------------------- |
| `TARGET`           | The email address to lookup.   | None    | True     | `email`                |
| `TYPE`             | The type of the target.        | auto    | False    | `email,phone,username` |
| `HIBP_APIKEY`      | API Key for Have I Been Pwned. | None    | False    | None                   |
| `LEAKCHECK_APIKEY` | API Key for LeakCheck.         | None    | False    | None                   |
| `DEHASHED_APIKEY`  | API Key for DeHashed.          | None    | False    | None                   |

The type `auto` will automatically detect the type of the target.
- If the target is an email address, it will check **HaveIBeenPwned**, **LeakCheck**, **BreachVIP**, and **DeHashed**.
- If the target is a phone number, it will check **LeakCheck**, **BreachVIP**, and **DeHashed**.
- If the target is a username, it will check **LeakCheck**, **BreachVIP**, and **DeHashed**.

## Example

```bash
keen > use leak_check
keen(analysis/leak_check) > set target example@example.com
keen(analysis/leak_check) > run
```

## Output

```bash
example@example.com was found in Collection #1 data breach with ['combolist'] categories - Extra info: _breach_date: 2019-01-01T00:00:00Z, email: example@example.com, password: lol2k465, domain: example.com
example@example.com was found in Collection #1 data breach with ['combolist'] categories - Extra info: _breach_date: 2019-01-01T00:00:00Z, email: example@example.com, password: ill11DDEX, domain: example.com
```