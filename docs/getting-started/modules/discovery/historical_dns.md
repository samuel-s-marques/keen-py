# Historical DNS

---

- **Module Name:** `Historical_DNS`
- **Description:** Returns historical DNS data for a given domain.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Discovery

## Description
The `Historical_DNS` module analyzes historical DNS data to identify old records, infrastructure changes, and abandoned subdomains. It uses HackerTarget, ViewDNS, and SecurityTrails (optional) APIs to gather historical IP and DNS data, tracks domain-to-IP mappings over time, and detects reusable IPs that might be associated with past infrastructure, including potential cloud/CDN migrations or abandoned assets.

This module gathers information from ViewDNS, HackerTarget, SecurityTrails (when API key is provided), and crt.sh for historical DNS data and IP history. 

## Usage

```bash
keen > use historical_dns
keen(discovery/historical_dns) > set target [DOMAIN]
keen(discovery/historical_dns) > run
```

## Options

| Option                   | Description                | Default | Required | Value Type |
| ------------------------ | -------------------------- | ------- | -------- | ---------- |
| `TARGET`                 | The domain name to analyze | None    | Yes      | `domain`   |
| `SECURITYTRAILS_API_KEY` | API Key for SecurityTrails | None    | No       | None       |

## Example

```bash
keen > use historical_dns
keen(discovery/historical_dns) > set target globo.com
keen(discovery/historical_dns) > run
```

## Output

```
Potentially Abandoned / Vulnerable Subdomains
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Subdomain                             ┃ Status                                ┃ IPs            ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ api.cartolafc.globo.com               │ Resolves but returns 404              │ 35.215.214.149 │
├───────────────────────────────────────┼───────────────────────────────────────┼────────────────┤
│ comentarios.globo.com                 │ Dangling CNAME:                       │                │
│                                       │ coral-talk-beta.globo.com.            │                │
├───────────────────────────────────────┼───────────────────────────────────────┼────────────────┤
│ sp.globo.com                          │ Dangling CNAME:                       │                │
│                                       │ cgcom-1247943892.us-east-1.elb.amazo… │                │
└───────────────────────────────────────┴───────────────────────────────────────┴────────────────┘
WARNING  | Found 57 potentially abandoned/vulnerable subdomains!
```