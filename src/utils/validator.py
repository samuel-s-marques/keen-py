import ipaddress
import re

import phonenumbers


class InputValidator:
    @staticmethod
    def is_valid_domain(domain: str) -> bool:
        """Validate domain name.

        Args:
            domain (str): Domain name to validate.

        Returns:
            bool: True if domain is valid, False otherwise.
        """

        # Strip scheme and "www." prefixes. Guard the split so a bare value that
        # merely contains "http" (e.g. "http.example.com") can't IndexError.
        if "://" in domain:
            domain = domain.split("://", 1)[1]
        if domain.startswith("www."):
            domain = domain[len("www.") :]

        pattern = r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$"
        return re.match(pattern, domain.lower()) is not None

    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """Validate IP address.

        Args:
            ip (str): IP address to validate.

        Returns:
            bool: True if IP address is valid, False otherwise.
        """
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def is_valid_cidr(cidr: str) -> bool:
        """Validate CIDR notation.

        Args:
            cidr (str): CIDR notation to validate.

        Returns:
            bool: True if CIDR notation is valid, False otherwise.
        """
        try:
            ipaddress.ip_network(cidr, strict=False)
            return True
        except ValueError:
            return False

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Validate URL.

        Args:
            url (str): URL to validate.

        Returns:
            bool: True if URL is valid, False otherwise.
        """

        pattern = r"^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)$"
        return re.match(pattern, url.lower()) is not None

    @staticmethod
    def is_valid_email(email: str) -> bool:
        """Validate email address.

        Args:
            email (str): Email address to validate.

        Returns:
            bool: True if email address is valid, False otherwise.
        """

        pattern = r"^[\w\.-]+@([\w-]+\.)+[\w-]{2,4}$"
        return re.match(pattern, email.lower()) is not None

    @staticmethod
    def is_valid_phone_number(number: str) -> bool:
        """Validate phone number.

        Args:
            number (str): Phone number to validate.

        Returns:
            bool: True if phone number is valid, False otherwise.
        """

        # Remove all non-numeric characters except +
        number = re.sub(r"[^0-9+]", "", number)

        if not number.startswith("+"):
            number = "+" + number

        try:
            parsed = phonenumbers.parse(number, None)
            return phonenumbers.is_valid_number(parsed)
        except Exception:
            return False

    @staticmethod
    def is_valid_username(username: str) -> bool:
        """Validate username.

        Args:
            username (str): Username to validate.

        Returns:
            bool: True if username is valid, False otherwise.
        """
        return bool(username.strip())

    @staticmethod
    def is_valid_name(name: str) -> bool:
        """Validate person name.

        Args:
            name (str): Name to validate.

        Returns:
            bool: True if name is valid, False otherwise.
        """
        # TODO: Improve this validation with NER and other approaches
        return bool(name.strip())

    @staticmethod
    def is_valid_boolean(value: str) -> bool:
        """Validate boolean value.

        Args:
            value (str): Value to validate.

        Returns:
            bool: True if value is valid, False otherwise.
        """
        value = value.strip().lower()
        return value in ["true", "false", "1", "0", "yes", "no"]

    @staticmethod
    def is_valid_hash(value: str) -> bool:
        """Validate a hex-encoded MD5/SHA-1/SHA-256/SHA-512 hash.

        Args:
            value (str): Hash string to validate.

        Returns:
            bool: True if value matches a known hash length in hex, False otherwise.
        """
        pattern = (
            r"^[a-fA-F0-9]{32}$|^[a-fA-F0-9]{40}$|^[a-fA-F0-9]{64}$|^[a-fA-F0-9]{128}$"
        )
        return re.match(pattern, value.strip()) is not None

    @staticmethod
    def is_valid_btc_address(value: str) -> bool:
        """Validate a Bitcoin address's format (legacy P2PKH/P2SH base58, or bech32 SegWit).

        Args:
            value (str): Address string to validate.

        Returns:
            bool: True if value matches a recognized Bitcoin address shape, False otherwise.
        """
        pattern = r"^(bc1[a-z0-9]{25,90}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$"
        return re.match(pattern, value.strip()) is not None

    VALIDATORS = {
        "domain": is_valid_domain,
        "ip": is_valid_ip,
        "cidr": is_valid_cidr,
        "url": is_valid_url,
        "email": is_valid_email,
        "phone": is_valid_phone_number,
        "username": is_valid_username,
        "name": is_valid_name,
        "bool": is_valid_boolean,
        "hash": is_valid_hash,
        "btc_address": is_valid_btc_address,
    }
