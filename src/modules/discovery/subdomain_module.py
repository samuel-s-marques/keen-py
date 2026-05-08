import requests
import re
import concurrent.futures
import socket
import os

from src.utils.print_utils import error, info
from src.core.base_module import BaseModule


class SubdomainModule(BaseModule):
    metadata = {
        "name": "Subdomain_Enum",
        "description": "Discovers subdomains of a target domain.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The domain name to lookup (e.g. google.com).",
                "domain",
            ],
            "METHOD": [
                "all",
                False,
                "Method to use (bruteforce, dns, passive, all).",
                "",
            ],
            "WORDLIST": [
                "",
                False,
                "Path to wordlist file.",
                "",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        # Initialize options with default values
        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    def run(self) -> None:
        if not self.pre_run():
            return

        target = self.options.get("TARGET")
        method = self.options.get("METHOD")

        try:
            if method.lower() == "all":
                subdomains = set()
                methods_to_run = [
                    self._find_by_dns,
                    self._find_by_bruteforce,
                    self._find_by_passive,
                ]
                with concurrent.futures.ProcessPoolExecutor() as executor:
                    futures = {
                        executor.submit(func, target): func.__name__
                        for func in methods_to_run
                    }
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            result = future.result()
                            if result:
                                subdomains |= result
                        except Exception as exc:
                            error(
                                f"Method {futures[future]} generated an exception: {exc}"
                            )
            elif method.lower() == "dns":
                subdomains = self._find_by_dns(target)
            elif method.lower() == "bruteforce":
                subdomains = self._find_by_bruteforce(target)
            elif method.lower() == "passive":
                subdomains = self._find_by_passive(target)

            info(f"Found {len(subdomains)} subdomains:")
            for subdomain in subdomains:
                print(subdomain)
        except Exception as e:
            error(f"Error: {str(e)}")
            return

    def _find_by_crt(self, target: str) -> set:
        """Get domains from crt.sh free API."""
        subdomains = set()

        try:
            r = requests.get(f"https://crt.sh/?q=%25.{target}&output=json", timeout=60)

            if r.status_code != 200:
                return set()

            certs = r.json()

            for cert in certs:
                name = cert.get("name_value", "")
                for line in name.split("\n"):
                    line = line.strip().lower()
                    if line and "*" not in line:
                        subdomains.add(line)

        except Exception:
            pass

        return subdomains

    def _find_by_dns(self, target: str) -> set:
        return set()

    def _find_by_bruteforce(self, target: str) -> set:
        """Get values from wordlist and check if the subdomain exists."""
        wordlist_path = self.options.get("WORDLIST")

        if not wordlist_path or not os.path.exists(wordlist_path):
            error(
                "Wordlist is required and must be a valid file for bruteforce method."
            )
            return set()

        subdomains = set()

        try:
            with open(wordlist_path, "r", encoding="utf-8", errors="ignore") as f:
                with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                    batch_size = 1000
                    batch = []

                    for line in f:
                        sub = line.strip()
                        if sub:
                            batch.append(f"{sub}.{target}")

                        if len(batch) >= batch_size:
                            self._process_batch(executor, batch, subdomains)
                            batch = []

                    if batch:
                        self._process_batch(executor, batch, subdomains)

        except Exception as e:
            error(f"Error during bruteforce: {str(e)}")

        return subdomains

    def _process_batch(self, executor, batch: list, subdomains: set) -> None:
        """Helper to process a batch of subdomains."""
        futures = {
            executor.submit(self._check_subdomain, domain): domain for domain in batch
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                if res:
                    subdomains.add(res)
            except Exception:
                pass

    def _check_subdomain(self, subdomain: str) -> str | None:
        """Check if a subdomain exists using DNS resolution."""
        try:
            socket.gethostbyname(subdomain)
            return subdomain
        except socket.gaierror:
            return None

    def _find_by_passive(self, target: str) -> set:
        """Get domains from passive sources."""
        subdomains = set()

        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = [
                executor.submit(self._find_by_crt, target),
                executor.submit(self._find_by_anubis, target),
                executor.submit(self._find_by_rapiddns, target),
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        subdomains |= result
                except Exception:
                    pass

        return subdomains

    def _find_by_anubis(self, target: str) -> set:
        """Get domains from anubis.db free API."""
        subdomains = set()

        try:
            r = requests.get(
                f"https://anubisdb.com/anubis/subdomains/{target}", timeout=60
            )

            if r.status_code != 200:
                return set()

            data = r.json()

            for line in data:
                subdomains.add(line)
        except Exception:
            pass

        return subdomains

    def _find_by_rapiddns(self, target: str) -> set:
        """Get domains from rapiddns.io free API."""
        subdomains = set()

        try:
            r = requests.get(
                f"https://rapiddns.io/subdomain/{target}?full=1", timeout=30
            )

            if r.status_code != 200:
                return set()

            pattern = rf"^(?:[a-zA-Z0-9-]+\.).*{re.escape(target)}$"

            subdomains = set(
                match.group(0) for match in re.finditer(pattern, r.text, re.MULTILINE)
            )
        except Exception:
            pass

        return subdomains
