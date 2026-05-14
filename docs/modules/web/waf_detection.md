# WAF Detection

---

- **Module Name:** `WAF_Detection`
- **Description:** Detects if a target is behind a Web Application Firewall (WAF) or CDN.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Web

## Description

The `WAF_Detection` module is a web module that can be used to detect if a target is behind a Web Application Firewall (WAF) or CDN. It uses DNS records and HTTP headers to detect the WAF.

## Options

| Option   | Description    | Required | Default | Value Type |
| -------- | -------------- | -------- | ------- | ---------- |
| `TARGET` | The target URL | Yes      | None    | `url`      |

## Usage

```bash
keen > use waf_detection
keen(web/waf_detection) > set TARGET <url>
keen(web/waf_detection) > run
```