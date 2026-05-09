# keen-py

```
    __ __
   / //_/__  ___  ____ 
  / ,< / _ \/ _ \/ __ \
 / /| /  __/  __/ / / /
/_/ |_\___/\___/_/ /_/ 

```

Keen, as in keen observation, is a reconnaissance and OSINT tool for ethical hacking and penetration testing.

## Modules
### Analysis
This module process files or data you've already captured. You can check if discovered credentials appear in known breaches, or analyze data such as EXIF (GPS, camera type, metadata from images) and APKs/IPAs (find endpoints, hardcoded credentials, etc.).

Available modules:
None for now.

TODO:
- [ ] Add credentials breach checking
- [ ] Add EXIF data extraction
- [ ] Add APK/IPA parsing
- [ ] Add graph database integration for data persistence and sharing (.keen files)

### Discovery
This module focuses on identifying the infrastructure and "surface area" of a target. Think infrastructure, servers, domains, subdomains, etc. 

Available modules:
- WHOIS: Domain ownership
- Subdomains: Finding hidden sub-assets (bruteforce, passive, dns)

TODO:
- [ ] Add DNS enumeration (name servers, MX records, zone transfers)
- [ ] Add port scanning

### Enumeration
This module focuses on extracting as much detail as possible from targets.

Available modules:
- Holehe: Check if an username/email exists on social media.
- Sherlock: Find usernames across multiple social media platforms.
- SOCMINT_Enum: Combines Holehe, Sherlock and more to check for social media accounts.

TODO:
- [ ] Add email enumeration (breach checking)
- [ ] Add phone number enumeration (breach checking, carrier info, location data)
- [ ] Add username generation (if email or name provided)
- [ ] Add profile scraping (if social media found)
- [ ] Add contact scraping (if email or profile found)

### Intel
This module uses third-party databases for intelligence gathering.

Available modules:
None for now.

TODO:
- [ ] Add Shodan
- [ ] Add Censys
- [ ] Add Fofa
- [ ] Add ZoomEye
- [ ] Add IntelX
- [ ] Add GreyNoise
- [ ] Add Hunter

### Web
This module focuses on web scraping and data extraction from websites.

Available modules:
None for now.

TODO:
- [ ] Add link, comments, tech stack extraction
- [ ] Add vulnerability scanning

## To Do
- [ ] Implement full CLI framework
- [ ] Create a proper logging system
- [ ] Save ".keen" files for data persistence and sharing
- [ ] Add tests
- [ ] Add web interface
- [ ] Add notifications (Telegram, Discord, Email) for job completion/failure
- [ ] Add PDF and documents generation capabilities
- [ ] Add plugins
    - [ ] Add plugin system
    - [ ] DNS enumeration
    - [ ] Subdomain enumeration
    - [ ] Port scanning
    - [ ] Vulnerability scanning
    - [ ] Web scraping
    - [ ] Social media enumeration
    - [ ] Email enumeration
    - [ ] Phone number enumeration
    - [ ] Exif data extraction
    - [ ] Tracert
    - [ ] Dnsrecon
    - [ ] APKs/IPAs endpoints/hardcored extraction
- [ ] Integrate Shodan
- [ ] Integrate Censys
- [ ] Integrate ZoomEye
- [ ] Integrate Fofa
- [ ] Integrate Hunter
- [ ] Integrate GreyNoise
- [ ] Integrate IntelligenceX
- [ ] Implement leak checking
  - [ ] Breach Directory API
  - [ ] LeakCheck API
  - [ ] Dehashed API
  - [ ] DarkBeast API
  - [ ] Have I Been Pwned API
- [ ] Add API key management
- [ ] Add documentation
  - [ ] Add module creation guide
  - [ ] Add API integration guide
  - [ ] Add features guide
  - [ ] Add installation guide
  - [ ] Add usage guide
- [ ] Add modules
  - [x] WHOIS
  - [x] Subdomain enumeration
  - [x] Holehe
  - [x] Sherlock
  - [x] DNS enumeration