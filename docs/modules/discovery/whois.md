# Whois

---

- **Module Name:** `Whois`
- **Description:** Retrieves registration details, expiration dates, and nameservers for a domain.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Discovery

## Description

The `whois` module is a discovery module that can be used to retrieve registration details, expiration dates, and nameservers for a domain.

## Options

| Option   | Description                | Default | Value Type |
| -------- | -------------------------- | ------- | ---------- |
| `TARGET` | The domain name to lookup. | None    | `domain`   |

## Usage

```bash
keen > use whois
keen(discovery/whois) > set target <domain>
keen(discovery/whois) > run
```