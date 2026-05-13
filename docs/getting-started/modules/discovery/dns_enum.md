# DNS Enumeration

---

- **Module Name:** `DNS_Enum`
- **Description:** Discovers DNS records of a target domain.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Discovery

## Description

The `DNS_Enum` module discovers DNS records of a target domain using the dns.py library. It returns a list of DNS records for the target domain, including A, AAAA, MX, NS, TXT, and CNAME records. It will also show ASN intelligence for the target domain.

## Usage

```bash
keen > use dns_enum
keen(discovery/dns_enum) > set target [DOMAIN]
keen(discovery/dns_enum) > run
```

## Options

| Option   | Description                   | Default | Value Type |
| -------- | ----------------------------- | ------- | ---------- |
| `TARGET` | The domain name to enumerate. | None    | `domain`   |

## Example

```bash
keen > use dns_enum
keen(discovery/dns_enum) > set target example.com
keen(discovery/dns_enum) > run
```

## Output

```bash
DNSSEC Analysis for example.com
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Record         ┃ Details                                                                  ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ DS             │ ECDSAP256SHA256 | SHA-256 | Tag: 2371                                    │
└────────────────┴──────────────────────────────────────────────────────────────────────────┘
SUCCESS  | DNSSEC is enabled for example.com.

DNS Records for example.com
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Type    ┃ Data                                                                            ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ A       │ 104.20.23.154                                                                   │
│         │ 172.66.147.243                                                                  │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ NS      │ hera.ns.cloudflare.com.                                                         │
│         │ elliott.ns.cloudflare.com.                                                      │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ SOA     │ elliott.ns.cloudflare.com. dns.cloudflare.com. 2403488901 10000 2400 604800     │
│         │ 1800                                                                            │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ MX      │ 0 .                                                                             │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ TXT     │ "_k2n1y4vw3qtb4skdx9e7dxt97qrmmq9"                                              │
│         │ "v=spf1 -all"                                                                   │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ AAAA    │ 2606:4700:10::ac42:93f3                                                         │
│         │ 2606:4700:10::6814:179a                                                         │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ DS      │ 2371 13 2 c988ec423e3880eb8dd8a46fe06ca230ee23f35b578d64e78b29c3e1c83d245a      │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ DNSKEY  │ 257 3 13 mdsswUyr3DPW132mOi8V9xESWE8jTo0d xCjjnopKl+GqJxpVXckHAeF+KkxLbxIL      │
│         │ fDLUT0rAK9iUzy1L53eKGQ==                                                        │
│         │ 256 3 13 oJMRESz5E4gYzS/q6XDrvU1qMPYIjCWz JaOau8XNEZeqCYKD5ar0IRd8KqXXFJkq      │
│         │ mVfRvMGPmM1x8fGAa2XhSA==                                                        │
│         │ 256 3 13 kxipjoIbNZDsWqEKaYaGq6fM/XThrRp1 ue6AV9R/n3eWxpGCeCWJb47PEEEj/Q6V      │
│         │ AYFW/7UFo5mXoZfxKYZa3A==                                                        │
│         │ 256 3 13 MjyZielP0GqniI1+j+wAG/3t0ImDDIlj 1CxR0oobkZQHSKH2Fqx6tm2NcYu57POJ      │
│         │ 83SzCWLkqIjZHS1mh5wbaw==                                                        │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ CDS     │ 2371 13 2 c988ec423e3880eb8dd8a46fe06ca230ee23f35b578d64e78b29c3e1c83d245a      │
├─────────┼─────────────────────────────────────────────────────────────────────────────────┤
│ CDNSKEY │ 257 3 13 mdsswUyr3DPW132mOi8V9xESWE8jTo0d xCjjnopKl+GqJxpVXckHAeF+KkxLbxIL      │
│         │ fDLUT0rAK9iUzy1L53eKGQ==                                                        │
└─────────┴─────────────────────────────────────────────────────────────────────────────────┘
SUCCESS  | Discovered 10 record types for example.com.

ASN Intelligence for example.com
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ IP Address              ┃ ASN   ┃ BGP Prefix        ┃ Provider                  ┃ Country ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ 104.20.23.154           │ 13335 │ 104.20.16.0/20    │ CLOUDFLARENET -           │ US      │
│                         │       │                   │ Cloudflare, Inc., US      │         │
├─────────────────────────┼───────┼───────────────────┼───────────────────────────┼─────────┤
│ 2606:4700:10::6814:179a │ 13335 │ 2606:4700:10::/44 │ CLOUDFLARENET -           │ US      │
│                         │       │                   │ Cloudflare, Inc., US      │         │
├─────────────────────────┼───────┼───────────────────┼───────────────────────────┼─────────┤
│ 172.66.147.243          │ 13335 │ 172.66.144.0/20   │ CLOUDFLARENET -           │ US      │
│                         │       │                   │ Cloudflare, Inc., US      │         │
├─────────────────────────┼───────┼───────────────────┼───────────────────────────┼─────────┤
│ 2606:4700:10::ac42:93f3 │ 13335 │ 2606:4700:10::/44 │ CLOUDFLARENET -           │ US      │
│                         │       │                   │ Cloudflare, Inc., US      │         │
╰─────────────────────────┴───────┴───────────────────┴───────────────────────────┴─────────╯
```