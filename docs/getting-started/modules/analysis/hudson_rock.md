# Hudson Rock

---

- **Module Name:** `Hudson_Rock`
- **Description:** Checks if email is associated with devices infected with infostealers.
- **Author:** Samuel Marques
- **Version:** 1.0.0
- **Category:** Analysis

## Description

The `Hudson_Rock` module checks if an email address is associated with devices infected with infostealers using the Hudson Rock API. It returns a list of breaches associated with the email address, along with the number of corporate and user services affected. In case the target email address is not associated with any breaches, the module will return a message indicating that no breaches were found. It will also show the top passwords (masked) and logins (email:password, masked) associated with the email address, as well as the IP address and operating system of the infected device.

## Usage

```bash
keen> run analysis/hudson_rock TARGET=[EMAIL_ADDRESS]
```

## Options

| Option   | Description                  | Default | Value Type |
| -------- | ---------------------------- | ------- | ---------- |
| `TARGET` | The email address to lookup. | None    | `email`    |

## Example

```bash
keen > use hudson_rock
keen(analysis/hudson_rock) > set target example@example.com
keen(analysis/hudson_rock) > run
```

## Output

```bash
┏━━━━━━━━━━━━━━━━━━━ Hudson Rock: example@example.com ━━━━━━━━━━━━━━━━━━━┓
┃ WARNING: Information Stealer Infection Detected!                       ┃
┃                                                                        ┃
┃ This email address is associated with a computer that was infected by  ┃
┃ an info-stealer, all the credentials saved on this computer are at     ┃
┃ risk of being accessed by cybercriminals. Visit                        ┃
┃ https://www.hudsonrock.com/free-tools to discover additional free      ┃
┃ tools and Infostealers related data.                                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
╭─────────────────────────── Overall Summary ────────────────────────────╮
│                                                                        │
│   Total Stealers Found                                      5          │
│   Total Corporate Services Affected                         89         │
│   Total User Services Affected                              1794       │
│                                                                        │
╰────────────────────────────────────────────────────────────────────────╯
╭───────────────────────────── Infection #1 ─────────────────────────────╮
│  ────────────────────────────────────────────────────────────────────  │
│   Property                    Details                                  │
│  ────────────────────────────────────────────────────────────────────  │
│   Date Compromised            2026-04-21T07:51:16.000Z                 │
│   Computer Name               DESKTOP-EBGNM2B (hp)                     │
│   Operating System            Not Found                                │
│   Malware Path                Not Found                                │
│   IP Address                  Not Found                                │
│   Top Passwords (Masked)      A******2, A*******2, H**********8,       │
│                               p**s, R***********3                      │
│   Top Logins                  a*************@gmail.com,                │
│                               a*********@gmail.com, a***n,             │
│                               a*********@aol.com                       │
│  ────────────────────────────────────────────────────────────────────  │
╰────────────────────────────────────────────────────────────────────────╯
```