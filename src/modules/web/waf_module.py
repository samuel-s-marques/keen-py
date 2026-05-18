from src.utils.user_agents import UserAgents
import httpx
import dns.resolver
import asyncio
import re
from rich.table import Table
from rich.console import Console

from src.utils.print_utils import error, info, success
from src.core.base_module import BaseModule


class WafModule(BaseModule):
    metadata = {
        "name": "WAF_Detection",
        "description": "Detects if a target is behind a Web Application Firewall (WAF) or CDN.",
        "author": "Samuel Marques",
        "version": "1.0.0",
        "options": {
            "TARGET": [
                "",
                True,
                "The target URL or IP address (e.g. https://google.com).",
                "url",
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

        await self.loading(
            f"Executing WAF/CDN detection on {target}...", self.execute, target
        )

    async def execute(self, target: str) -> None:
        signatures = {
            "Cloudflare": {
                "dns": [r".*cloudflare\.net", r".*cloudflare\.com"],
                "headers": ["cf-ray", "cf-cache-status", "__cfduid"],
                "server": [r"cloudflare"],
            },
            "CloudFront (AWS)": {
                "dns": [r".*cloudfront\.net"],
                "headers": ["x-amz-cf-id", "x-amz-cf-pop"],
                "server": [r"cloudfront"],
            },
            "Akamai": {
                "dns": [r".*akamai(edge|zed)?\.net", r".*akamaiedge\.net"],
                "headers": ["x-akamai-transformed", "x-akamai-request-id"],
                "server": [r"akamai"],
            },
            "Imperva / Incapsula": {
                "dns": [r".*incapdns\.net", r".*imperva\.com"],
                "headers": ["x-cdn", "visid_incap", "incap_ses"],
                "server": [r"incapsula"],
            },
            "Fastly": {
                "dns": [r".*fastly\.net"],
                "headers": ["x-fastly-request-id"],
                "server": [r"fastly"],
            },
            "Sucuri": {
                "dns": [r".*sucuri\.net"],
                "headers": ["x-sucuri-id", "x-sucuri-cache"],
                "server": [r"sucuri"],
            },
            "Azure Front Door / CDN": {
                "dns": [r".*azureedge\.net", r".*azurefd\.net"],
                "headers": ["x-azure-ref", "x-cache"],
                "server": [r"azure"],
            },
            "Google Cloud CDN": {
                "dns": [r".*googleusercontent\.com", r".*googlevideo\.com"],
                "headers": ["x-goog-meta", "x-goog-generation"],
                "server": [r"google"],
            },
        }

        results = []

        # Extract domain for DNS analysis
        domain = target
        if target.startswith("http"):
            domain = target.split("//")[-1].split("/")[0]

        try:
            # DNS Analysis (CNAME)
            try:
                answers = await asyncio.to_thread(
                    dns.resolver.resolve, domain, "CNAME", lifetime=5
                )
                for rdata in answers:
                    cname = str(rdata.target).lower()
                    for provider, sigs in signatures.items():
                        for dns_sig in sigs["dns"]:
                            if re.match(dns_sig, cname):
                                results.append([provider, "DNS CNAME", cname])
            except Exception:
                pass

            # HTTP Analysis (Headers)
            url = target if target.startswith("http") else f"https://{target}"
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(
                        url,
                        timeout=10,
                        headers={"User-Agent": UserAgents.get()},
                        follow_redirects=True,
                    )
                headers = {k.lower(): v.lower() for k, v in response.headers.items()}
                server_header = headers.get("server", "")

                for provider, sigs in signatures.items():
                    # Check Headers
                    for header_sig in sigs["headers"]:
                        if header_sig in headers:
                            results.append(
                                [provider, "HTTP Header", f"{header_sig} present"]
                            )

                    # Check Server Header
                    for server_sig in sigs["server"]:
                        if re.search(server_sig, server_header):
                            results.append([provider, "Server Header", server_header])
            except Exception:
                pass

            # Display Results
            if results:
                # Remove duplicates while preserving order
                unique_results = []
                seen = set()
                for res in results:
                    tuple_res = tuple(res)
                    if tuple_res not in seen:
                        unique_results.append(res)
                        seen.add(tuple_res)

                table = Table(
                    show_header=True,
                    header_style="bold blue",
                    title=f"CDN/WAF Detection for {target}",
                    title_style="bold cyan",
                    show_lines=True,
                    expand=True,
                )
                table.add_column("Provider", style="cyan")
                table.add_column("Detection Method", style="magenta")
                table.add_column("Evidence", style="white")

                for provider, method, evidence in unique_results:
                    table.add_row(provider, method, evidence)

                console = Console()
                if not getattr(self, "is_web_context", False):
                    console.print(table)
                success(f"Detected CDN/WAF infrastructure for {target}.")

                # Save results to workspace
                await self._save_results(target, unique_results)
            else:
                info(f"No known CDN or WAF detected for {target}.")

        except Exception as e:
            error(f"Detection failed: {e}")

    async def _save_results(self, target: str, results: list) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        builder = ResultBuilder()
        builder.add_node(NodeFactory.url(target, waf_detections_count=len(results)))

        # Unique providers detected
        providers_seen = set()
        for provider, method, evidence in results:
            if provider not in providers_seen:
                builder.add_node(NodeFactory.organization(provider))
                builder.add_edge(target, provider, "protected-by")
                providers_seen.add(provider)

        await self.post_run(builder.build())
