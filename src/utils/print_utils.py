from cmd2 import Color, stylize
from rich.style import Style


def success(message: str) -> None:
    print(stylize(f"[+] {message}", Style(color=Color.GREEN)))


def info(message: str) -> None:
    print(stylize(f"[*] {message}", Style(color=Color.BLUE)))


def error(message: str) -> None:
    print(stylize(f"[-] {message}\n", Style(color=Color.RED)))


def warn(message: str) -> None:
    print(stylize(f"[!] {message}\n", Style(color=Color.YELLOW)))
