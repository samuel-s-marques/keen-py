# Domain To IP

---

- **Module Name:** `Domain_To_IP`
- **Description:** Resolves a domain's A/AAAA records to its IPv4/IPv6 addresses.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Helper

## Description

The `Domain_To_IP` module is a fast, single-purpose resolver that returns only a domain's A/AAAA records. It exists to close a magic-chaining gap: **[`discovery/dns_enum`](../discovery/dns_enum.md)** already resolves A/AAAA records as part of a much broader 15-record-type sweep, but it doesn't declare `magic_consumes` — so discovering a bare domain never automatically resolved to its IP(s) before this module. `Domain_To_IP` is additive to `dns_enum`, not a replacement for it, the same relationship **[`discovery/cert_transparency`](../discovery/dns_enum.md)** has to `subdomain_enum`'s inline crt.sh call.

It produces the exact same node/edge shape `dns_enum` already does for A/AAAA records (an `ipv4-addr`/`ipv6-addr` node plus a `resolves-to` edge), so a domain resolved by both modules dedups onto the same graph nodes rather than diverging.

### Graph Schema Insertion

- **Nodes:**
  - `domain-name`: the target domain.
  - `ipv4-addr` / `ipv6-addr`: one per resolved address.
- **Edges:** `resolves-to`, from the domain to each resolved IP.

## Options

| Option   | Description               | Required | Default | Value Type |
| -------- | -------------------------- | -------- | ------- | ---------- |
| `TARGET` | The domain name to resolve. | Yes      | None    | `domain`   |

## Usage

```bash
keen > use domain_to_ip
keen(helpers/domain_to_ip) > set TARGET example.com
keen(helpers/domain_to_ip) > run
```

Since the module declares `magic_consumes: ["domain-name"]`, it also runs automatically on every discovered domain when magic chaining is enabled — and its results feed directly into **[IP Geolocation](ip_geolocation.md)** for any resolved address.
