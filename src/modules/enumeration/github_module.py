from typing import Any, Dict, List, Set
from src.utils.user_agents import UserAgents
from src.utils.print_utils import error, success, info, warn
from src.core.base_module import BaseModule


class GitHubModule(BaseModule):
    metadata = {
        "name": "GitHub_Enumeration",
        "description": "Performs comprehensive enumeration of a GitHub user, including profile info, repositories, organizations, and potential email extraction from commits.",
        "author": "Samuel Marques",
        "version": "1.2.0",
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

        try:
            await self.execute(target)
        finally:
            # Close in a finally so an exception out of execute() (e.g. from
            # _save_results/post_run) can't leak the client's connection pool.
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

            # Get Events
            events = await self.loading(
                f"Fetching public events for {target}...",
                self.get_public_events,
                target,
            )

            # Print Recent Activity
            self.print_recent_activity(events)

            # Extract Emails
            emails = self.extract_emails_from_events(events)
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
                "events": events or [],
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

    async def get_public_events(self, target: str) -> List[Dict[str, Any]]:
        try:
            r = await self.client.get(
                f"https://api.github.com/users/{target}/events/public?per_page=100"
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            warn(f"Error fetching public events: {e}")
            return []

    def extract_emails_from_events(self, events: List[Dict[str, Any]]) -> Set[str]:
        emails: Set[str] = set()
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
        return emails

    def print_recent_activity(self, events: List[Dict[str, Any]]) -> None:
        if not events:
            warn("No public events found.")
            return

        info(f"Recent Public Events Found: {len(events)}")
        event_counts: Dict[str, int] = {}
        for event in events:
            evt_type = event.get("type", "UnknownEvent")
            event_counts[evt_type] = event_counts.get(evt_type, 0) + 1

        counts_str = ", ".join([f"{k}: {v}" for k, v in event_counts.items()])
        info(f"Event Types: {counts_str}")

        info("Recent Activity Details:")
        for event in events[:10]:
            evt_type = event.get("type")
            repo_name = event.get("repo", {}).get("name")
            created_at = event.get("created_at", "")
            date_str = created_at.split("T")[0] if "T" in created_at else created_at

            if evt_type == "PushEvent":
                payload = event.get("payload", {})
                ref = payload.get("ref", "")
                branch = ref.replace("refs/heads/", "") if ref else "main"
                commits = payload.get("commits", [])
                commit_msg = (
                    commits[0].get("message", "").split("\n")[0]
                    if commits
                    else "No commit message"
                )
                info(
                    f"  [{date_str}] Pushed {len(commits)} commit(s) to {repo_name} ({branch}): '{commit_msg}'"
                )
            elif evt_type == "PullRequestEvent":
                payload = event.get("payload", {})
                action = payload.get("action", "")
                pr = payload.get("pull_request", {})
                pr_title = pr.get("title", "")
                info(
                    f"  [{date_str}] {action.capitalize()} PR in {repo_name}: '{pr_title}'"
                )
            elif evt_type == "IssuesEvent":
                payload = event.get("payload", {})
                action = payload.get("action", "")
                issue = payload.get("issue", {})
                issue_title = issue.get("title", "")
                info(
                    f"  [{date_str}] {action.capitalize()} issue in {repo_name}: '{issue_title}'"
                )
            elif evt_type == "IssueCommentEvent":
                info(f"  [{date_str}] Commented on issue/PR in {repo_name}")
            elif evt_type == "WatchEvent":
                info(f"  [{date_str}] Starred {repo_name}")
            elif evt_type == "ForkEvent":
                info(f"  [{date_str}] Forked {repo_name}")
            elif evt_type == "CreateEvent":
                payload = event.get("payload", {})
                ref_type = payload.get("ref_type", "")
                info(f"  [{date_str}] Created {ref_type} in {repo_name}")
            else:
                clean_type = evt_type.replace("Event", "") if evt_type else "Activity"
                info(f"  [{date_str}] {clean_type} in {repo_name}")

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
        owned_repo_names = set()
        for repo in repos:
            repo_name = repo.get("full_name")
            if repo_name:
                owned_repo_names.add(repo_name)
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

        # Repository interactions from events
        events = results.get("events", [])
        interacted_repos = {}
        for event in events:
            repo_data = event.get("repo", {})
            repo_name = repo_data.get("name")
            if repo_name and repo_name not in owned_repo_names:
                evt_type = event.get("type", "UnknownEvent")
                if repo_name not in interacted_repos:
                    interacted_repos[repo_name] = set()
                interacted_repos[repo_name].add(evt_type)

        for repo_name, event_types in interacted_repos.items():
            repo_url = f"https://github.com/{repo_name}"
            relationship = "interacted-with"
            if "PushEvent" in event_types:
                relationship = "pushed-to"
            elif "PullRequestEvent" in event_types:
                relationship = "contributed-to"
            elif "IssuesEvent" in event_types:
                relationship = "opened-issue-in"

            builder.add_node(
                NodeFactory.custom(
                    "url",
                    repo_url,
                    node_type="repository",
                    misp_type="link",
                    misp_value=repo_url,
                )
            )
            # Override value to be the repo name for graph display
            if builder._nodes and builder._nodes[-1]["value"] == repo_url:
                builder._nodes[-1]["value"] = repo_name
            builder.add_edge(account_val, repo_name, relationship)

        await self.post_run(builder.build())
