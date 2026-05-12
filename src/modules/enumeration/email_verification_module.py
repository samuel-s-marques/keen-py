from src.utils.user_agents import UserAgents
import asyncio
import smtplib
import socket
import dns.resolver
import requests
from rich.table import Table
from rich.console import Console

from src.utils.print_utils import error, success, warn
from src.core.base_module import BaseModule
from src.utils.validator import InputValidator

ROLE_ACCOUNTS = {
    "admin",
    "administrator",
    "support",
    "help",
    "info",
    "contact",
    "sales",
    "billing",
    "hr",
    "careers",
    "marketing",
    "tech",
    "webmaster",
    "postmaster",
    "hostmaster",
    "abuse",
    "noc",
    "security",
    "root",
    "daemon",
    "noreply",
    "no-reply",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "guerrillamailblock.com",
    "grr.la",
    "sharklasers.com",
    "temp-mail.org",
    "tempmail.net",
    "10minutemail.com",
    "yopmail.com",
    "throwawaymail.com",
    "trashmail.com",
    "disposable-mail.com",
    "mail7.io",
    "getnada.com",
    "tempmail.com",
    "nada.ltd",
}


class EmailVerificationModule(BaseModule):
    metadata = {
        "name": "Email_Verification",
        "description": "Verifies email address validity, reachability, MX records, and categorizes it.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The email address to lookup.",
                "email",
            ],
            "TIMEOUT": [
                "10",
                False,
                "Timeout for connections in seconds.",
                "",
            ],
            "APILAYER_EMAIL_VER_APIKEY": [
                "",
                False,
                "API Key for APILayer Email Verification to get email verification results.",
                "",
            ],
        },
    }

    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).lower()
        timeout: int = int(self.options.get("TIMEOUT", 10))

        await self.loading(
            f"Verifying email {target}...", self.execute, target, timeout
        )

    async def execute(self, email: str, timeout: int) -> None:
        if not InputValidator.is_valid_email(email):
            error(f"Invalid email format: {email}")
            return

        local_part, domain = email.split("@")

        is_role = local_part in ROLE_ACCOUNTS
        is_disposable = domain in DISPOSABLE_DOMAINS

        mx_records = await self.get_mx_records(domain, timeout)

        deliverable = False
        inbox_full = False
        disabled = False
        catch_all = False
        ip_blocked = False
        vague_response = False

        if mx_records:
            res = await self.smtp_verify(domain, email, mx_records, timeout)
            deliverable = res["deliverable"]
            inbox_full = res["inbox_full"]
            disabled = res["disabled"]
            catch_all = res["catch_all"]
            ip_blocked = res["ip_blocked"]
            vague_response = res["vague_response"]

            if ip_blocked or vague_response:
                warn(
                    "Local IP might be blocked or responses were vague. Falling back to API verification."
                )
                api_res = await self.api_verify_fallback(email)
                if api_res:
                    deliverable = api_res.get("is_deliverable", deliverable)
                    inbox_full = api_res.get("is_inbox_full", inbox_full)
                    disabled = api_res.get("is_disabled", disabled)
                    catch_all = api_res.get("is_catch_all", catch_all)
                    is_role = api_res.get("is_role_account", is_role)
                    is_disposable = api_res.get("is_disposable", is_disposable)
        else:
            warn(f"No MX records found for {domain}. Deliverability is unlikely.")

        score = self.calculate_score(
            deliverable, is_role, is_disposable, catch_all, mx_records
        )

        self.display_results(
            email,
            local_part,
            domain,
            is_role,
            is_disposable,
            mx_records,
            deliverable,
            inbox_full,
            disabled,
            catch_all,
            score,
        )

        results = {
            "is_role": is_role,
            "is_disposable": is_disposable,
            "mx_records": mx_records,
            "deliverable": deliverable,
            "inbox_full": inbox_full,
            "disabled": disabled,
            "catch_all": catch_all,
            "score": score,
        }
        await self._save_results(email, results)

    async def get_mx_records(self, domain: str, timeout: int) -> list[tuple[int, str]]:
        records = []
        try:
            answers = await asyncio.to_thread(
                dns.resolver.resolve, domain, "MX", lifetime=timeout
            )
            for rdata in answers:
                records.append((rdata.preference, str(rdata.exchange).rstrip(".")))
            records.sort(key=lambda x: x[0])
        except Exception:
            pass
        return records

    async def smtp_verify(
        self, domain: str, email: str, mx_records: list[tuple[int, str]], timeout: int
    ) -> dict:
        for pref, mx in mx_records:
            try:
                res = await asyncio.to_thread(
                    self._sync_smtp_check, mx, email, domain, timeout
                )
                if res["connected"]:
                    return res
            except Exception:
                continue

        return {
            "connected": False,
            "deliverable": False,
            "inbox_full": False,
            "disabled": False,
            "catch_all": False,
            "ip_blocked": False,
            "vague_response": False,
        }

    def _sync_smtp_check(self, mx: str, email: str, domain: str, timeout: int) -> dict:
        res = {
            "connected": False,
            "deliverable": False,
            "inbox_full": False,
            "disabled": False,
            "catch_all": False,
            "ip_blocked": False,
            "vague_response": False,
        }
        try:
            server = smtplib.SMTP(timeout=timeout)
            code, msg = server.connect(mx)
            res["connected"] = True

            if code >= 500:
                res["ip_blocked"] = True
                server.quit()
                return res

            server.helo(socket.getfqdn())
            server.mail("verify@example.com")

            code, msg = server.rcpt(email)
            msg_str = msg.decode("utf-8", errors="ignore").lower()

            if code == 250:
                res["deliverable"] = True
            elif code == 550:
                if any(
                    x in msg_str for x in ["spam", "blocked", "banned", "blacklisted"]
                ):
                    res["ip_blocked"] = True
                else:
                    res["disabled"] = True
            elif code == 552 or any(x in msg_str for x in ["full", "quota"]):
                res["inbox_full"] = True
            elif code in (450, 451, 452):
                res["vague_response"] = True

            if res["deliverable"]:
                random_email = f"catchall_test_123987_{socket.getfqdn()}@{domain}"
                code_ca, msg_ca = server.rcpt(random_email)
                if code_ca == 250:
                    res["catch_all"] = True

            server.quit()
        except smtplib.SMTPServerDisconnected:
            res["ip_blocked"] = True
        except Exception:
            pass

        return res

    async def api_verify_fallback(self, email: str) -> dict | None:
        """Fallback API verification stub when local IP is blocked."""
        try:
            api_key = self.options.get("APILAYER_EMAIL_VER_APIKEY")

            if not api_key:
                warn(
                    "ApiLayer Email Verification API Key not found. Skipping API verification."
                )
                return None

            r = requests.get(
                f"https://api.apilayer.com/email_verification/{email}",
                headers={
                    "apikey": api_key,
                    "User-Agent": UserAgents.get(),
                },
                timeout=15,
            )

            if r.status_code != 200:
                return None

            return r.json()
        except Exception as e:
            error(f"API verification failed: {e}")
            return None

    def calculate_score(
        self,
        deliverable: bool,
        is_role: bool,
        is_disposable: bool,
        catch_all: bool,
        mx_records: list,
    ) -> int:
        score = 0
        if deliverable and not catch_all:
            score += 50
        elif deliverable and catch_all:
            score += 25

        if mx_records:
            score += 20

        if not is_role:
            score += 15
        else:
            score -= 10

        if not is_disposable:
            score += 15
        else:
            score -= 50

        return max(0, min(100, score))

    def display_results(
        self,
        email: str,
        local_part: str,
        domain: str,
        is_role: bool,
        is_disposable: bool,
        mx_records: list,
        deliverable: bool,
        inbox_full: bool,
        disabled: bool,
        catch_all: bool,
        score: int,
    ) -> None:
        table = Table(
            show_header=True,
            header_style="bold blue",
            title=f"Email Verification: [bold white]{email}[/bold white]",
            title_style="bold cyan",
            show_lines=True,
            expand=True,
        )

        table.add_column("Property", justify="left", style="cyan", no_wrap=True)
        table.add_column("Status", justify="left", style="white")

        table.add_row("Email", email)
        table.add_row("User (Local Part)", local_part)
        table.add_row("Domain", domain)

        status_color = "green" if score >= 70 else ("yellow" if score >= 40 else "red")
        table.add_row("Score", f"[{status_color}]{score}/100[/{status_color}]")

        table.add_row(
            "Deliverable",
            "[green]Yes[/green]" if deliverable else "[red]No/Unknown[/red]",
        )
        table.add_row(
            "Catch-All", "[yellow]Yes[/yellow]" if catch_all else "[green]No[/green]"
        )
        table.add_row("Role Account", "[yellow]Yes[/yellow]" if is_role else "No")
        table.add_row("Disposable", "[red]Yes[/red]" if is_disposable else "No")
        table.add_row("Inbox Full", "[red]Yes[/red]" if inbox_full else "No")
        table.add_row("Disabled", "[red]Yes[/red]" if disabled else "No")

        mx_str = (
            "\n".join([f"Pref: {p}, MX: {m}" for p, m in mx_records])
            if mx_records
            else "None"
        )
        table.add_row("MX Records", mx_str)

        console = Console()
        console.print(table)

        if score >= 70:
            success(f"{email} looks highly legitimate.")
        elif score >= 40:
            warn(f"{email} has mixed signals (Score: {score}).")
        else:
            error(f"{email} looks risky or undeliverable.")

    async def _save_results(self, email: str, results: dict) -> None:
        import uuid
        from typing import Any

        # STIX 2.1 Standard Email-Address Object
        STIX_EMAIL_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa2")
        email_uuid = uuid.uuid5(STIX_EMAIL_NAMESPACE, email)

        stix2_email = {
            "type": "email-addr",
            "id": f"email-addr--{email_uuid}",
            "spec_version": "2.1",
            "value": email,
        }

        # MISP representation
        misp_email = {
            "type": "email-dst",
            "value": email,
        }

        primary_node = {
            "type": "email-addr",
            "value": email,
            "metadata": {
                "stix2": stix2_email,
                "misp": misp_email,
                "is_role": results.get("is_role"),
                "is_disposable": results.get("is_disposable"),
                "deliverable": results.get("deliverable"),
                "inbox_full": results.get("inbox_full"),
                "disabled": results.get("disabled"),
                "catch_all": results.get("catch_all"),
                "score": results.get("score"),
            },
        }

        nodes: list[dict[str, Any]] = [primary_node]
        edges: list[dict[str, Any]] = []

        local_part, domain = email.split("@")

        # 1. Domain Mapping (domain-name Node)
        STIX_DOMAIN_NAMESPACE = uuid.UUID("f070f381-8b38-5fdf-9730-802526e84fa7")
        domain_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, domain)
        stix2_domain = {
            "type": "domain-name",
            "id": f"domain-name--{domain_uuid}",
            "spec_version": "2.1",
            "value": domain,
        }
        misp_domain = {
            "type": "domain",
            "value": domain,
        }
        domain_node = {
            "type": "domain-name",
            "value": domain,
            "metadata": {
                "stix2": stix2_domain,
                "misp": misp_domain,
            },
        }
        nodes.append(domain_node)
        edges.append(
            {
                "source": email,
                "target": domain,
                "relationship": "belongs-to-domain",
            }
        )

        # 2. MX Infrastructure Mapping
        mx_records = results.get("mx_records", [])
        for pref, mx_host in mx_records:
            mx_cleaned = mx_host.rstrip(".")
            mx_uuid = uuid.uuid5(STIX_DOMAIN_NAMESPACE, mx_cleaned)
            stix2_mx = {
                "type": "domain-name",
                "id": f"domain-name--{mx_uuid}",
                "spec_version": "2.1",
                "value": mx_cleaned,
            }
            misp_mx = {
                "type": "mx",
                "value": f"{pref} {mx_cleaned}",
            }
            mx_node = {
                "type": "domain-name",
                "value": mx_cleaned,
                "metadata": {
                    "stix2": stix2_mx,
                    "misp": misp_mx,
                    "preference": pref,
                },
            }
            if mx_node not in nodes:
                nodes.append(mx_node)

            edges.append(
                {
                    "source": domain,
                    "target": mx_cleaned,
                    "relationship": "has-mx-record",
                }
            )

        new_results = {
            "nodes": nodes,
            "edges": edges,
        }

        await self.post_run(new_results)
