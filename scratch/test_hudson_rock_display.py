from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box

def display_hudson_rock_results(email, data):
    console = Console()
    
    message = data.get("message")
    stealers = data.get("stealers", [])
    
    if not stealers:
        console.print(f"[green]No infostealer infections found for {email}.[/green]")
        return
        
    # Main Warning Panel
    console.print(Panel(
        f"[bold red]WARNING: Information Stealer Infection Detected![/bold red]\n\n"
        f"[white]{message}[/white]",
        title=f"[bold red]Hudson Rock: {email}[/bold red]",
        border_style="red",
        box=box.HEAVY
    ))
    
    # Summary Table
    summary_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    summary_table.add_column("Key", style="cyan", width=30)
    summary_table.add_column("Value", style="white")
    
    summary_table.add_row("Total Stealers Found", str(len(stealers)))
    summary_table.add_row("Total Corporate Services Affected", str(data.get("total_corporate_services", 0)))
    summary_table.add_row("Total User Services Affected", str(data.get("total_user_services", 0)))
    
    console.print(Panel(summary_table, title="[bold blue]Overall Summary[/bold blue]", border_style="blue"))

    # Detail Stealers
    for index, stealer in enumerate(stealers, start=1):
        stealer_table = Table(box=box.HORIZONTALS, expand=True)
        stealer_table.add_column("Property", style="cyan", width=25)
        stealer_table.add_column("Details", style="white")
        
        stealer_table.add_row("Date Compromised", stealer.get("date_compromised", "Unknown"))
        stealer_table.add_row("Computer Name", stealer.get("computer_name", "Unknown"))
        stealer_table.add_row("Operating System", stealer.get("operating_system", "Unknown"))
        stealer_table.add_row("Malware Path", stealer.get("malware_path", "Unknown"))
        stealer_table.add_row("IP Address", stealer.get("ip", "Unknown"))
        
        # Passwords and Logins
        top_passwords = ", ".join(p for p in stealer.get("top_passwords", []) if p) or "None"
        top_logins = ", ".join(l for l in stealer.get("top_logins", []) if l) or "None"
        
        stealer_table.add_row("Top Passwords (Masked)", top_passwords)
        stealer_table.add_row("Top Logins", top_logins)
        
        console.print(Panel(stealer_table, title=f"[bold yellow]Infection #{index}[/bold yellow]", border_style="yellow"))


mock_data = {
    "message": "This email address is associated with a computer that was infected by an info-stealer, all the credentials saved on this computer are at risk of being accessed by cybercriminals. Visit https://www.hudsonrock.com/free-tools to discover additional free tools and Infostealers related data.",
    "stealers": [
        {
        "total_corporate_services": 817,
        "total_user_services": 56483,
        "date_compromised": "2026-05-11T18:15:40.136Z",
        "computer_name": "Not Found",
        "operating_system": "Not Found",
        "malware_path": "Not Found",
        "antiviruses": [],
        "ip": "Not Found",
        "top_passwords": [
            "a****s",
            "a*******3",
            "T***********%",
            "Q**********************g",
            "Y**********************A"
        ],
        "top_logins": [
            "a***n",
            "g**************s",
            "g*****e",
            "s*******n",
            "t***********@gmail.com"
        ]
        },
        {
        "total_corporate_services": 104,
        "total_user_services": 910,
        "date_compromised": "2026-05-10T10:25:30.000Z",
        "computer_name": "SMS (smadd)",
        "operating_system": "Windows 11 Home Single Language 25H2 (Build 26200)",
        "malware_path": " C:\\Users\\smadd\\AppData\\Roaming\\8AhaH\\LtKsodGaxsSu.exe",
        "antiviruses": [],
        "ip": "27.61.**.***",
        "top_passwords": [
            "S************F",
            "T******3",
            "S********@",
            "T********5",
            "?************c"
        ],
        "top_logins": [
            "s*************@teknikforce.com",
            "r**t",
            "c*********@teknikforce.com",
            "c*********@gmail.com",
            ""
        ]
        }
    ],
    "total_corporate_services": 817,
    "total_user_services": 56483
}

if __name__ == "__main__":
    display_hudson_rock_results("test@example.com", mock_data)
