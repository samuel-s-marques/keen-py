# Url To Domain

---

- **Module Name:** `Url_To_Domain`
- **Description:** Extracts the domain name from a URL.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Helper

## Description

The `Url_To_Domain` module is a helper module that can be used to extract the domain name from a URL. It removes the scheme and the path, returning the domain only. Mostly useful when using the Web interface, as it adds the domain node to the graph.

## Options

| Option   | Description        | Required | Default | Value Type |
| -------- | ------------------ | -------- | ------- | ---------- |
| `TARGET` | The URL to convert | Yes      | None    | `url`      |

## Usage

```bash
keen > use url_to_domain
keen(helpers/url_to_domain) > set TARGET <url>
keen(helpers/url_to_domain) > run
```
