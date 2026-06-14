from typing import Any, Dict, List, Set
from src.utils.user_agents import UserAgents
from src.utils.print_utils import error, success, info, warn
from src.core.base_module import BaseModule


class GitHubModule(BaseModule):
    metadata = {
        "name": "GitHub_Enumeration",
        "description": "Performs comprehensive enumeration of a GitHub user, including profile info, repositories, organizations, and potential email extraction from commits.",
        "author": "Samuel Marques",
        "version": "1.1.0",
        "options": {
            "TARGET": ["", True, "The GitHub username to enumerate.", "username"],
            "GITHUB_TOKEN": [
                "",
                False,
                "Optional GitHub Personal Access Token for higher rate limits.",
                "",
            ],
        },
    }

    async def run(self) -> None:
        if not self.pre_run():
            return

        target: str = str(self.options.get("TARGET")).strip()
        token: str = str(self.options.get("GITHUB_TOKEN")).strip()

        headers = {
            "User-Agent": UserAgents.get(),
            "Accept": "application/vnd.github+json",
        }
        if token:
            headers["Authorization"] = f"token {token}"

        self.client = self.get_http_client(headers=headers, follow_redirects=True)

        await self.execute(target)

        await self.client.aclose()

    async def execute(self, target: str) -> None:
        if not hasattr(self, "client"):
            headers = {
                "User-Agent": UserAgents.get(),
                "Accept": "application/vnd.github+json",
            }
            token = str(self.options.get("GITHUB_TOKEN", "")).strip()
            if token:
                headers["Authorization"] = f"token {token}"
            self.client = self.get_http_client(headers=headers, follow_redirects=True)
            close_client = True
        else:
            close_client = False

        try:
            # Get User Profile
            user_data = await self.loading(
                f"Fetching profile for {target}...", self.get_user_info, target
            )
            if not user_data:
                return

            self.print_user_info(user_data)

            # Get Orgs
            orgs = await self.loading(
                f"Fetching organizations for {target}...", self.get_orgs, target
            )
            if orgs:
                info(f"Organizations: {', '.join([org['login'] for org in orgs])}")

            # Get Repos
            repos = await self.loading(
                f"Fetching repositories for {target}...", self.get_repos, target
            )
            if repos:
                info(f"Public Repositories Found: {len(repos)}")
                stars = sum(repo.get("stargazers_count", 0) for repo in repos)
                if stars > 0:
                    info(f"Total Stars: {stars}")

            # Get Events and Extract Emails
            emails = await self.loading(
                "Searching for emails in public events...", self.extract_emails, target
            )
            if emails:
                success(f"Found {len(emails)} email(s) in commit history:")
                for email in emails:
                    success(f"  - {email}")
            else:
                warn("No emails found in public commit history.")

            # Save Results
            results = {
                "profile": user_data,
                "orgs": orgs or [],
                "repos": repos or [],
                "emails": list(emails or []),
            }
            await self._save_results(target, results)
        finally:
            if close_client:
                await self.client.aclose()

    async def get_user_info(self, target: str) -> Dict[str, Any] | None:
        try:
            r = await self.client.get(f"https://api.github.com/users/{target}")
            if r.status_code == 404:
                error(f"User {target} not found on GitHub.")
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            error(f"Error fetching user info: {e}")
            return None

    def print_user_info(self, data: Dict[str, Any]) -> None:
        success(f"GitHub Profile Found: {data.get('login')}")
        if data.get("name"):
            info(f"Name: {data['name']}")
        if data.get("bio"):
            info(f"Bio: {data['bio']}")
        if data.get("location"):
            info(f"Location: {data['location']}")
        if data.get("email"):
            success(f"Public Email: {data['email']}")
        if data.get("blog"):
            info(f"Blog: {data['blog']}")
        if data.get("company"):
            info(f"Company: {data['company']}")

        followers = data.get("followers", 0)
        following = data.get("following", 0)
        public_repos = data.get("public_repos", 0)
        public_gists = data.get("public_gists", 0)

        info(f"Followers: {followers} | Following: {following}")
        info(f"Public Repos: {public_repos} | Public Gists: {public_gists}")

    async def get_orgs(self, target: str) -> List[Dict[str, Any]]:
        try:
            r = await self.client.get(f"https://api.github.com/users/{target}/orgs")
            r.raise_for_status()
            return r.json()
        except Exception:
            return []

    async def get_repos(self, target: str) -> List[Dict[str, Any]]:
        try:
            # We fetch up to 100 repos, which is usually enough for a quick OSINT check
            r = await self.client.get(
                f"https://api.github.com/users/{target}/repos?per_page=100"
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return []

    async def extract_emails(self, target: str) -> Set[str]:
        emails: Set[str] = set()
        try:
            r = await self.client.get(
                f"https://api.github.com/users/{target}/events/public"
            )
            r.raise_for_status()
            events = r.json()

            for event in events:
                if event.get("type") == "PushEvent":
                    payload = event.get("payload", {})
                    commits = payload.get("commits", [])
                    for commit in commits:
                        author = commit.get("author", {})
                        email = author.get("email")
                        # Filter out GitHub's noreply emails
                        if email and "noreply.github.com" not in email:
                            emails.add(email)
        except Exception as e:
            warn(f"Error extracting emails: {e}")
        return emails

    async def _save_results(self, target: str, results: dict) -> None:
        from src.core.result_builder import ResultBuilder, NodeFactory

        profile = results.get("profile", {})
        orgs = results.get("orgs", [])
        repos = results.get("repos", [])
        emails = results.get("emails", [])

        builder = ResultBuilder()

        # Primary account node
        account_val = f"github:{target}"
        acc_node = NodeFactory.user_account(
            account_val,
            bio=profile.get("bio"),
            blog=profile.get("blog"),
            company=profile.get("company"),
            followers=profile.get("followers"),
            following=profile.get("following"),
            public_repos=profile.get("public_repos"),
            public_gists=profile.get("public_gists"),
        )
        acc_node["metadata"]["stix2"]["account_login"] = target
        acc_node["metadata"]["stix2"]["account_type"] = "github"
        acc_node["metadata"]["stix2"]["display_name"] = profile.get("name")
        acc_node["metadata"]["misp"] = {"type": "github-username", "value": target}
        builder.add_node(acc_node)

        # Public profile email
        profile_email = profile.get("email")
        if profile_email:
            builder.add_node(NodeFactory.email(profile_email))
            builder.add_edge(account_val, profile_email, "has-profile-email")

        # Commit history emails
        for email in emails:
            if email == profile_email:
                continue
            builder.add_node(NodeFactory.email(email))
            builder.add_edge(account_val, email, "committed-with-email")

        # Location
        location = profile.get("location")
        if location:
            builder.add_node(NodeFactory.location(location))
            builder.add_edge(account_val, location, "located-in")

        # Organizations
        for org in orgs:
            org_login = org.get("login")
            if org_login:
                builder.add_node(
                    NodeFactory.organization(
                        org_login,
                        description=org.get("description"),
                    )
                )
                # Override MISP to target-org
                org_node = builder._nodes[-1]
                org_node["metadata"]["misp"] = {
                    "type": "target-org",
                    "value": org_login,
                }
                builder.add_edge(account_val, org_login, "member-of-org")

        # Repositories
        for repo in repos:
            repo_name = repo.get("full_name")
            if repo_name:
                repo_url = repo.get("html_url") or f"https://github.com/{repo_name}"
                builder.add_node(
                    NodeFactory.custom(
                        "url",
                        repo_url,
                        node_type="repository",
                        misp_type="link",
                        misp_value=repo_url,
                        description=repo.get("description"),
                        stars=repo.get("stargazers_count"),
                        forks=repo.get("forks_count"),
                        language=repo.get("language"),
                    )
                )
                # Override value to be the repo name for graph display
                repo_node = builder._nodes[-1]
                repo_node["value"] = repo_name
                builder.add_edge(account_val, repo_name, "owns-repository")

        await self.post_run(builder.build())
