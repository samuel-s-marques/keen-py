# Organization To Domain

---

- **Module Name:** `Org_To_Domain`
- **Description:** Converts an organization name to its verified domain name using search indexing and dynamic filtering.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Helper

## Description

The `Org_To_Domain` module is an intelligent helper module that automates the discovery and strict verification of an organization's primary domain name. 

Rather than relying on simple dictionary matches or arbitrary search queries, it executes a multi-stage search, concurrent verification, and mathematical score-validation framework to reliably locate the correct target homepage.

### How it Works

1. **Search Indexing**: The module sanitizes the organization's name by stripping common legal suffixes (such as LLC, Inc, Corp, Ltd, GmbH). It then executes a targeted DuckDuckGo Search excluding major social networks and aggregators (e.g., `-site:linkedin.com -site:wikipedia.org -site:crunchbase.com`) to filter results down to candidate corporate homepages.
2. **Concurrent Evaluation**: The top 5 search candidates are analyzed in parallel using asynchronous workers to gather validation metrics.
3. **Scoring Engine**: A candidate domain must score at least **3 points** to be considered verified. Scores are computed across several criteria:

   - **Domain Keyword Match (+2 points)**: Checks if the brand's core alphanumeric words are present inside the domain name itself.
   - **HTML Title Match (+3 points)**: Fetches the site homepage and validates if the HTML `<title>` contains the brand's core identity keywords.
   - **HTML Meta Description Match (+1 point)**: Validates if the page description contains the brand's core identity keywords.
   - **Phrase Proximity Ratio (Up to +4 bonus points)**: Computes how closely and contiguously the company's brand keywords appear in sequence inside the Title and Meta Description tags (e.g. Excellent proximity ratio $\ge 0.8$ adds $+3$ to Title and $+1$ to Meta; Good proximity ratio $\ge 0.5$ adds $+1$ to Title).
   - **SSL/TLS Certificate Validation (+3 points)**: Establishes a TLS connection to check if the `commonName`, `organizationName`, or `subjectAltName` fields of the certificate match the brand's core identity keywords.
   - **WHOIS Registration Check (+3 points)**: Performs an asynchronous WHOIS lookup to verify if the registrant organization or registrant name matches the brand keywords.
   
4. **Graph Persistence**: Once the best candidate meeting the score threshold is identified, the module creates a standardized `organization` node and `domain-name` node in the active workspace, linking them together with an `owns` edge.

## Options

| Option   | Description                               | Required | Default | Value Type |
| -------- | ----------------------------------------- | -------- | ------- | ---------- |
| `TARGET` | The name of the organization to convert. | Yes      | None    | `name`     |

## Usage

```bash
keen > use org_to_domain
keen(helpers/org_to_domain) > set TARGET "Hunter"
keen(helpers/org_to_domain) > run
```
