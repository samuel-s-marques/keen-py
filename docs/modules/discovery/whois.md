# Whois

---

- **Module Name:** `Whois`
- **Description:** Retrieves registration details, expiration dates, and nameservers for a domain using RDAP.
- **Author:** Samuel Marques
- **Version:** 1.1.0
- **Category:** Discovery

## Description

The `whois` module is a discovery module that retrieves registration details, expiration dates, status flags, contact emails, and nameservers for a domain using the Registration Data Access Protocol (RDAP). 

It dynamically checks and caches the authoritative IANA bootstrap registry (`dns.json`) to direct queries to the corresponding registry TLD servers directly, falling back automatically to the public `rdap.org` bootstrap redirector when necessary.

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