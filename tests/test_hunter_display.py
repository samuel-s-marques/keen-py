from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box

def display_hunter_results(email, person_data):
    console = Console()
    
    person = person_data.get("data", {})
    if not person:
        console.print("[yellow]No information found for this email.[/yellow]")
        return

    name_data = person.get("name", {})
    full_name = name_data.get("fullName", "Unknown")
    location = person.get("location", "Unknown")
    bio = person.get("bio", "N/A")
    site = person.get("site", "N/A")
    phone = person.get("phone", "N/A")
    
    # Header Panel
    console.print(Panel(
        f"[bold cyan]Enrichment Results for:[/bold cyan] [bold white]{email}[/bold white]\n"
        f"[bold blue]Name:[/bold blue] {full_name}\n"
        f"[bold blue]Location:[/bold blue] {location}",
        title="[bold green]Hunter.io Finder[/bold green]",
        border_style="green",
        box=box.ROUNDED
    ))

    # Details Table
    details_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    details_table.add_column("Key", style="cyan", width=15)
    details_table.add_column("Value", style="white")
    
    details_table.add_row("Bio", bio or "N/A")
    details_table.add_row("Website", site or "N/A")
    details_table.add_row("Phone", phone or "N/A")
    details_table.add_row("Provider", person.get("emailProvider", "Unknown"))
    
    console.print(Panel(details_table, title="[bold blue]Personal Details[/bold blue]", border_style="blue"))

    # Employment Table
    employment = person.get("employment", {})
    if employment:
        emp_table = Table(title="[bold yellow]Employment Information[/bold yellow]", box=box.HORIZONTALS, expand=True)
        emp_table.add_column("Company", style="yellow")
        emp_table.add_column("Title", style="white")
        emp_table.add_column("Role", style="magenta")
        emp_table.add_column("Seniority", style="cyan")
        
        emp_table.add_row(
            employment.get("name", "N/A"),
            employment.get("title", "N/A"),
            employment.get("role", "N/A"),
            employment.get("seniority", "N/A")
        )
        console.print(emp_table)

    # Social Media
    social_types = ["facebook", "github", "twitter", "linkedin", "googleplus", "gravatar"]
    social_rows = []
    for s_type in social_types:
        s_data = person.get(s_type, {})
        handle = s_data.get("handle")
        if handle:
            social_rows.append(f"[bold]{s_type.capitalize()}:[/bold] {handle}")
    
    if social_rows:
        console.print(Panel(
            "\n".join(social_rows),
            title="[bold magenta]Social Presence[/bold magenta]",
            border_style="magenta",
            box=box.ROUNDED
        ))

# Mock data based on the comment in email_enrichment_module.py
mock_data = {
    "data": {
        "id": "c60ef040-ce2c-56bc-9296-40ac52c18780",
        "name": {
            "fullName": "Patrick Bosmans",
            "givenName": "Patrick",
            "familyName": "Bosmans"
        },
        "email": "patrick@stripe.com",
        "location": "Madison, Wisconsin, United States",
        "timeZone": "America/Chicago",
        "utcOffset": -6,
        "bio": "IT Enthusiast & Administrator",
        "site": "https://stripe.com",
        "employment": {
            "domain": "stripe.com",
            "name": "Stripe",
            "title": "IT Administrator",
            "role": "it",
            "subRole": None,
            "seniority": "executive"
        },
        "facebook": {"handle": None},
        "github": {"handle": "pbosmans"},
        "twitter": {"handle": "@pbosmans"},
        "linkedin": {"handle": "patrick-bosmans-549746b4"},
        "googleplus": {"handle": None},
        "gravatar": {"handle": None},
        "emailProvider": "google.com",
        "phone": "+1 307 512 2554"
    }
}

if __name__ == "__main__":
    display_hunter_results("patrick@stripe.com", mock_data)
