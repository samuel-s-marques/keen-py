# Domain Enrichment

---

- **Module Name:** `Domain_Enrichment`
- **Description:** Enriches a domain with corporate and structural profile data using Hunter.io.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Enumeration

## Description

The `Domain_Enrichment` module is a high-fidelity intelligence gathering tool that retrieves comprehensive company profile records for a target domain using the Hunter.io API. 

This module performs passive recon on target organizations by gathering legal identity, location details, technology stacks, social footprints, public contact listings, and other company metrics. It automatically displays these records in structured terminal panels and stores the findings as standardized STIX 2.1 / MISP threat intelligence objects in the active workspace graph database.

### Features & Data Points Extracted

1. **Company Metadata**: Extracts the official legal name, founding year, type (private vs public), and a summary description.
2. **Industry Classification**: Maps the organization's Global Industry Classification Standard (GICS) category, sector, industry group, sub-industry, SIC/NAICS classification codes, and key corporate tags.
3. **Operational Metrics**: Obtains employee counts, traffic ranks, and estimated revenue.
4. **Site Contacts**: Harvests a list of public telephone numbers and corporate email addresses (`support@`, `security@`, `contact@`, etc.) exposed under the domain.
5. **Technology Stack Tracker**: Enumerates software frameworks, analytics, DNS services, security headers, programming languages, and web servers detected on the target's web assets.
6. **Social Footprint**: Resolves official corporate social accounts on platforms including LinkedIn, Twitter, Facebook, Instagram, and Crunchbase.
7. **Security & Surface Hardening Insights**: Identifies public-facing exposure vectors. Organizations can defensively analyze these footprints to restrict unintended shadow IT exposure, deprecate legacy frameworks, and harden email delivery authentication protocols (SPF, DKIM, DMARC) against email spoofing.

### UI & Terminal Output

When run in a non-web CLI context, the module renders a multi-panel visual dashboard styled using the `rich` system, organizing the information into clean, color-coded sections:

- **Green Panel**: Primary company and legal identity.
- **Blue Panel**: Detailed operational tables, categories, and metrics.
- **Yellow Panel**: Comprehensive lists of tracked technologies.
- **Magenta Panel**: Stored corporate social media handles.
- **Cyan Panel**: Collected associated contacts (emails and phones).

### Graph Schema Insertion

All parsed nodes and edges are normalized and stored inside the active workspace:
- **Nodes**:

  - `domain-name`: The main target domain node.
  - `organization`: The corporate identity node (linked by `owns` edge).
  - `location`: Company headquarters location (linked by `located-in` edge).
  - `x-phone-number`: Exhumed contact phone numbers (linked by `associated-phone` edge).
  - `email-addr`: Harvested public email addresses (linked by `belongs-to-domain` edge).
  - `user-account`: Corporate social profiles (linked by `owns-account` edge).

- **Metadata**: Standardized STIX 2.1 properties (such as `account_login`, `account_type`, and `spec_version`) along with MISP properties (e.g. `domain`, `target-location`, `phone-number`, `linkedin-url`, and `facebook-id`) are automatically attached.

## Options

| Option             | Description                   | Required | Default | Value Type |
| ------------------ | ----------------------------- | -------- | ------- | ---------- |
| `TARGET`           | The target domain to enrich.  | Yes      | None    | `domain`   |
| `HUNTER_IO_APIKEY` | The API Key for Hunter.io.    | No       | None    | `text`     |

## Usage

```bash
keen > use domain_enrichment
keen(enumeration/domain_enrichment) > set TARGET hunter.io
keen(enumeration/domain_enrichment) > run
```
