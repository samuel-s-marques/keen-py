import re
import ipaddress
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

        try:
            parsed = phonenumbers.parse(number, None)
            return phonenumbers.is_valid_number(parsed)
        except Exception:
            return False

    VALIDATORS = {
        "domain": is_valid_domain,
        "ip": is_valid_ip,
        "cidr": is_valid_cidr,
        "url": is_valid_url,
        "email": is_valid_email,
        "phone": is_valid_phone_number,
    }
