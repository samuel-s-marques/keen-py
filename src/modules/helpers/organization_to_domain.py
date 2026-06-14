from src.utils.user_agents import UserAgents
from src.utils.print_utils import info, error, success
from ddgs import DDGS
import re
import socket
import ssl
import asyncio
import httpx
import unicodedata
from bs4 import BeautifulSoup
from src.utils.rdap import query_rdap

from src.core.base_module import BaseModule


class OrgToDomain(BaseModule):
    metadata = {
        "name": "Org_To_Domain",
        "description": "Converts an organization name to its verified domain name using search indexing and dynamic filtering.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The name of the organization to convert.",
                "name",
            ],
        },
    }

    # Generic filler words that don't uniquely identify a brand
    stop_words = {
        "and",
        "of",
        "in",
        "for",
        "the",
        "a",
        "an",
        "with",
        "at",
        "by",
        "on",
        "solutions",
        "technologies",
        "technology",
        "systems",
        "group",
        "services",
        "partners",
        "advanced",
        "global",
        "international",
        "holding",
        "holdings",
        "management",
        "consulting",
        "digital",
        "labs",
        "software",
        "industries",
        "networks",
        "associated",
        "associates",
        "worldwide",
        "inc",
        "llc",
        "corp",
        "ltd",
        "gmbh",
        "co",
        "company",
        "corporation",
        "limited",
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        name: str = str(self.options.get("TARGET"))
        best_domain = await self.execute(name)

        if best_domain:
            success(f"Best matched domain: {best_domain}")
            await self._save_results(name, best_domain)
        else:
            error("No verified domain could be found for this organization.")

    async def execute(self, name: str) -> str | None:
        # Strip common legal suffixes to clean up the search query
        clean_name = re.sub(
            r"\b(llc|inc|corp|corporation|ltd|gmbh|sa)\b",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()

        # Search for candidates using DuckDuckGo
        domains = await self.loading(
            f"Searching candidate domains for '{clean_name}'...",
            self._query_ddgs,
            clean_name,
        )

        if not domains:
            info("No domains found in search results.")
            return None

        info(f"Evaluating candidate domains for company '{clean_name}' concurrently...")

        # Create evaluation tasks for all candidate domains to run in parallel
        tasks = [self._evaluate_domain(domain, clean_name) for domain in domains]
        results = await asyncio.gather(*tasks)

        best_domain: str | None = None
        best_score: int = 0

        # Print matches and scores sequentially for perfect terminal readability
        for domain, score, matches in results:
            info(f"\nDomain: {domain}")
            for match in matches:
                info(f"  [MATCH] {match}")
            info(f"  Final Score for {domain}: {score}")

            # A minimum score of 3 is required to pass verification
            if score >= 3 and score > best_score:
                best_score = score
                best_domain = domain

        return best_domain

    async def _evaluate_domain(
        self, domain: str, clean_name: str
    ) -> tuple[str, int, list[str]]:
        """Evaluate a single candidate domain concurrently, gathering scores and matching logs."""
        score: int = 0
        matches: list[str] = []

        # Domain name keyword match (+2 points)
        if self._match_company_words(clean_name, domain.replace(".", " ")):
            score += 2
            matches.append(f"Domain name '{domain}' matches brand keywords (+2)")

        # HTML Title & Meta description match
        try:
            headers = {"User-Agent": UserAgents.get()}
            async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
                response = await client.get(f"https://{domain}", headers=headers)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    title: str = (soup.title.string or "") if soup.title else ""
                    meta_description_tag = soup.find(
                        "meta", attrs={"name": "description"}
                    )
                    val = (
                        meta_description_tag.get("content")
                        if meta_description_tag
                        else None
                    )
                    meta_description: str = val if isinstance(val, str) else ""

                    if self._match_company_words(clean_name, title):
                        score += 3
                        matches.append(
                            f"HTML Title '{title.strip()}' matches brand keywords (+3)"
                        )
                        # Proximity bonus
                        prox = self._calculate_phrase_proximity(clean_name, title)
                        if prox >= 0.8:
                            score += 3
                            matches.append(
                                f"HTML Title has excellent phrase proximity ({prox:.2f}) (+3)"
                            )
                        elif prox >= 0.5:
                            score += 1
                            matches.append(
                                f"HTML Title has good phrase proximity ({prox:.2f}) (+1)"
                            )

                    if self._match_company_words(clean_name, meta_description):
                        score += 1
                        matches.append(
                            "HTML Meta Description matches brand keywords (+1)"
                        )
                        # Proximity bonus
                        prox = self._calculate_phrase_proximity(
                            clean_name, meta_description
                        )
                        if prox >= 0.8:
                            score += 1
                            matches.append(
                                f"HTML Meta Description has excellent phrase proximity ({prox:.2f}) (+1)"
                            )
        except Exception:
            pass

        # SSL/TLS Certificate Check (+3 points)
        if await self._check_ssl_certificate(domain, clean_name):
            score += 3
            matches.append("SSL/TLS Certificate matches brand keywords (+3)")

        # WHOIS Registration Check (+3 points)
        if await self._check_whois(domain, clean_name):
            score += 3
            matches.append("WHOIS registrant details match brand keywords (+3)")

        return domain, score, matches

    def _sync_query_ddgs(self, query: str) -> set[str]:
        domains: set[str] = set()

        try:
            with DDGS() as ddg:
                # Grab the top 5 search results for a broader pool
                results = ddg.text(query, max_results=5)
                if results:
                    for result in results:
                        url = result.get("href")
                        if url:
                            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
                            if domain_match:
                                domains.add(domain_match.group(1))
        except Exception as e:
            error(f"Failed to query DDGS: {e}")

        return domains

    async def _query_ddgs(self, name: str) -> set[str]:
        # Exclude massive aggregators from the search results to find the actual homepage
        query = f'"{name}" -site:linkedin.com -site:wikipedia.org -site:crunchbase.com'
        return await asyncio.to_thread(self._sync_query_ddgs, query)

    async def _check_ssl_certificate(self, domain: str, clean_name: str) -> bool:
        """Check if the SSL/TLS certificate contains the company name."""

        def _check():
            try:
                context = ssl.create_default_context()
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                with socket.create_connection((domain, 443), timeout=3) as sock:
                    with context.wrap_socket(sock, server_hostname=domain) as ssock:
                        cert = ssock.getpeercert()
                        if not cert:
                            return False

                        # Check subject for commonName and organizationName
                        subject = cert.get("subject", [])
                        for sub in subject:
                            for item in sub:
                                key, val = item[0], item[1]
                                if key in ["commonName", "organizationName"]:
                                    if self._match_company_words(clean_name, str(val)):
                                        return True

                        # Check subjectAltName
                        alt_names = cert.get("subjectAltName", [])
                        for name_type, alt_name in alt_names:
                            if name_type == "DNS" and isinstance(alt_name, str):
                                if self._match_company_words(clean_name, alt_name):
                                    return True
            except Exception:
                pass
            return False

        return await asyncio.to_thread(_check)

    async def _check_whois(self, domain: str, clean_name: str) -> bool:
        """Check if RDAP registrant information contains the company name."""
        try:
            w = await query_rdap(domain)
            if not w:
                return False

            # Check registrant organization
            org = w.get("org")
            if org and self._match_company_words(clean_name, str(org)):
                return True

            # Check registrar name
            registrar = w.get("registrar")
            if registrar and self._match_company_words(clean_name, str(registrar)):
                return True
        except Exception:
            pass
        return False

    def _normalize_text(self, text: str) -> str:
        """Normalize text by converting to lowercase and stripping accents/diacritics."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFD", text)
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()

    def _match_company_words(self, name: str, target: str) -> bool:
        """Intelligently check if significant words in the company name match the target string.

        This helps match names by focusing on the core brand/identity words and filtering out
        generic company filler words.
        """
        if not name or not target:
            return False

        company_name = self._normalize_text(name)
        target = self._normalize_text(target)

        # Direct substring matches are absolute wins
        if company_name in target:
            return True

        # Tokenize both fields into alphanumeric words
        company_words = re.findall(r"\b\w+\b", company_name)
        target_words = set(re.findall(r"\b\w+\b", target))

        # Filter down to significant words that are at least 3 chars long
        significant_company_words = [
            w for w in company_words if w not in self.stop_words and len(w) >= 3
        ]

        # If all words got filtered, fall back to the first word that's >= 3 characters
        if not significant_company_words:
            non_empty = [w for w in company_words if len(w) >= 3]
            if non_empty:
                significant_company_words = [non_empty[0]]
            else:
                return False

        # The first significant word is almost always the brand identity (e.g. "Aptos")
        first_sig_word = significant_company_words[0]
        if first_sig_word in target_words or first_sig_word in target:
            return True

        # Check for any other significant word matches as a secondary fallback
        for word in significant_company_words:
            if word in target_words:
                return True

        return False

    def _calculate_phrase_proximity(self, name: str, target: str) -> float:
        """Calculate the proximity ratio of the company name's significant words in the target string.

        Returns a float between 0.0 and 1.0:
        - 1.0 means the significant words appear exactly contiguously and in the correct order.
        - 0.0 means the words do not all appear in the correct order, or don't appear at all.
        """
        if not name or not target:
            return 0.0

        name_norm = self._normalize_text(name)
        target_norm = self._normalize_text(target)

        company_words = re.findall(r"\b\w+\b", name_norm)

        sig_words = [
            w for w in company_words if w not in self.stop_words and len(w) >= 3
        ]
        if not sig_words:
            sig_words = [w for w in company_words if len(w) >= 3]

        if not sig_words:
            return 0.0

        last_idx = -1
        first_start = -1
        last_end = -1
        total_word_len = sum(len(w) for w in sig_words)

        for word in sig_words:
            idx = target_norm.find(word, last_idx + 1)
            if idx == -1:
                return 0.0

            if first_start == -1:
                first_start = idx
            last_end = idx + len(word)
            last_idx = idx

        span_len = last_end - first_start
        if span_len <= 0:
            return 0.0

        return total_word_len / span_len

    async def _save_results(self, name: str, domain: str) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        builder = ResultBuilder()
        builder.add_node(NodeFactory.organization(name))
        builder.add_node(NodeFactory.domain(domain))
        builder.add_edge(name, domain, "owns")

        await self.post_run(builder.build())
