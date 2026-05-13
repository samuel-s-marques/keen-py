# Subdomain Enumeration

---

- **Module Name:** `Subdomain_Enum`
- **Description:** Discovers subdomains for a given domain using multiple APIs.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Discovery

## Description
The `Subdomain_Enum` module uses multiple ways to find subdomains for a given domain.

There are four diferent methods:
- **Bruteforce**: Tries every subdomain name from a wordlist and checks if it exists. (requires WORDLIST)
- **DNS**: Uses DNS techniques (AXFR, SRV).
- **Passive**: Uses passive sources (crt.sh, anubisdb, rapiddns) to find subdomains.
- **All**: Uses all the methods above.

IMPORTANT: Using the **DNS** method in a large target may take a long time.

WARNING: Using the **Bruteforce** method in a target with a large wordlist may take a long time.

## Usage

```bash
keen > use subdomain_enum
keen(discovery/subdomain_enum) > set target [DOMAIN]
keen(discovery/subdomain_enum) > run
```

## Options

| Option     | Description                                   | Default | Required | Value Type |
| ---------- | --------------------------------------------- | ------- | -------- | ---------- |
| `TARGET`   | The domain name to lookup                     | None    | Yes      | `domain`   |
| `METHOD`   | Method to use (bruteforce, dns, passive, all) | all     | No       | None       |
| `WORDLIST` | Path to wordlist file.                        | None    | No       | None       |

## Example

```bash
keen > use subdomain_enum
keen(discovery/subdomain_enum) > set target example.com
keen(discovery/subdomain_enum) > run
```

## Output

```
Found 2 subdomains:

lkiss36791.example.com
mihail.starcun.example.com
```