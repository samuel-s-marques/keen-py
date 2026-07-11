# IP Geolocation

---

- **Module Name:** `Ip_Geolocation`
- **Description:** Resolves an IP address to an approximate geographic location (city/region/country + coordinates) via ipapi.co.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Helper

## Description

The `Ip_Geolocation` module resolves an IPv4 or IPv6 address to an approximate location using the free [ipapi.co](https://ipapi.co/) API — no API key required. It is a `passive` lookup: it only queries a public geolocation service about the IP, never touching the target's own infrastructure.

This is the first module to produce a `location` node with real latitude/longitude coordinates for something other than an EXIF-tagged photo, so its results are what populate the **World Map** view for IP-based targets. This is distinct from `helpers/ip_to_asn.py`'s own `location` node, which is only a country-name string with no coordinates.

When the API reports an owning ISP/network, the module also creates an `organization` node — cross-referencing `ip_to_asn.py`'s independently-sourced ASN/provider data on the same IP.

Results are cached for 24 hours per IP to avoid repeatedly hitting ipapi.co for the same target.

### Graph Schema Insertion

- **Nodes:**
  - `ipv4-addr` / `ipv6-addr`: the target IP.
  - `location`: city/region/country plus latitude/longitude, when the API returns coordinates.
  - `organization`: the owning ISP/network, if reported.
- **Edges:** `geolocated-to` (IP → location), `hosted-by` (IP → organization, only if an org was found).

## Options

| Option   | Description               | Required | Default | Value Type |
| -------- | -------------------------- | -------- | ------- | ---------- |
| `TARGET` | The IP address to geolocate. | Yes      | None    | `ip`       |

## Usage

```bash
keen > use ip_geolocation
keen(helpers/ip_geolocation) > set TARGET 8.8.8.8
keen(helpers/ip_geolocation) > run
```

Since the module declares `magic_consumes: ["ipv4-addr", "ipv6-addr"]`, it also runs automatically on every discovered IP address when magic chaining is enabled.
