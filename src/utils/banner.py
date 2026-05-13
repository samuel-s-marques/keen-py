from cmd2 import Color, stylize
from pyfiglet import Figlet, FigletString
from rich.style import Style
import random

fonts: list[str] = [
    "3-d",
    "alligator",
    "alligator2",
    "banner3-D",
    "colossal",
    "cosmic",
    "letters",
    "o8",
    "univers",
]
quotes: list[str] = [
    "The eyes see only what the mind is prepared to comprehend.",
    "What is hidden in the dark shall be brought into the light.",
    "Find the thread, and the entire tapestry unravels.",
    "Dig deeper. The truth is in the details.",
    "Collect, connect, conquer.",
    "Information is the vector; Keen is the impact.",
    "Keen: Every detail, exposed.",
    "Keen: Unmasking the architecture.",
    "Keen: The end of anonymity.",
    "To know the enemy is to own the enemy.",
    "The invisible becomes legible.",
    "Information is the currency of the future.",
    "Knowledge is power. Keen is the key.",
    "See everything. Understand everything.",
    "The sharp edge of intelligence.",
    "Anonymity is a debt.",
    "Existence is evidence.",
]


def get_banner(version: str) -> str:
    font: str = random.choice(fonts)
    quote: str = random.choice(quotes)
    version_styled: str = stylize(
        f"Version: {version}",
        Style(
            color=Color.YELLOW,
        ),
    )

    banner: FigletString = Figlet(font).renderText("Keen")
    banner_styled: str = stylize(
        banner,
        Style(
            color=Color.BLUE,
        ),
    )
    welcome_styled: str = stylize(
        "Welcome to Keen, an information gathering tool.",
        Style(
            color=Color.GREEN,
        ),
    )
    quote_styled: str = stylize(
        quote,
        Style(
            color=Color.CYAN,
        ),
    )

    return f"\n{banner_styled}{quote_styled}\n\n{version_styled}\n{welcome_styled}\n"
