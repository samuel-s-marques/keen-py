# DNS Enumeration

---

- **Module Name:** `DNS_Enum`
- **Description:** Discovers DNS records of a target domain.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Discovery

## Description

The `DNS_Enum` module discovers DNS records of a target domain using the dns.py library. It returns a list of DNS records for the target domain, including A, AAAA, MX, NS, TXT, and CNAME records. It will also show ASN intelligence for the target domain.

## Options

| Option   | Description                   | Default | Value Type |
| -------- | ----------------------------- | ------- | ---------- |
| `TARGET` | The domain name to enumerate. | None    | `domain`   |

## Usage

```bash
keen > use dns_enum
keen(discovery/dns_enum) > set target [DOMAIN]
keen(discovery/dns_enum) > run
```