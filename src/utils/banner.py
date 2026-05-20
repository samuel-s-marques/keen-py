from cmd2 import Color, stylize
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

PRE_RENDERED_BANNERS = {
    "3-d": " **   **                         \n/**  **                          \n/** **    *****   *****  ******* \n/****    **///** **///**//**///**\n/**/**  /*******/******* /**  /**\n/**//** /**//// /**////  /**  /**\n/** //**//******//****** ***  /**\n//   //  //////  ////// ///   // \n",
    "alligator": "      :::    :::::::::::::::::::::::::::    ::: \n     :+:   :+: :+:       :+:       :+:+:   :+:  \n    +:+  +:+  +:+       +:+       :+:+:+  +:+   \n   +#++:++   +#++:++#  +#++:++#  +#+ +:+ +#+    \n  +#+  +#+  +#+       +#+       +#+  +#+#+#     \n #+#   #+# #+#       #+#       #+#   #+#+#      \n###    ##########################    ####       \n",
    "alligator2": ":::    :::::::::::::::::::::::::::    ::: \n:+:   :+: :+:       :+:       :+:+:   :+: \n+:+  +:+  +:+       +:+       :+:+:+  +:+ \n+#++:++   +#++:++#  +#++:++#  +#+ +:+ +#+ \n+#+  +#+  +#+       +#+       +#+  +#+#+# \n#+#   #+# #+#       #+#       #+#   #+#+# \n###    ##########################    #### \n",
    "banner3-D": "'##:::'##:'########:'########:'##::: ##:\n ##::'##:: ##.....:: ##.....:: ###:: ##:\n ##:'##::: ##::::::: ##::::::: ####: ##:\n #####:::: ######::: ######::: ## ## ##:\n ##. ##::: ##...:::: ##...:::: ##. ####:\n ##:. ##:: ##::::::: ##::::::: ##:. ###:\n ##::. ##: ########: ########: ##::. ##:\n..::::..::........::........::..::::..::\n",
    "colossal": '888    d8P                          \n888   d8P                           \n888  d8P                            \n888d88K     .d88b.  .d88b. 88888b.  \n8888888b   d8P  Y8bd8P  Y8b888 "88b \n888  Y88b  8888888888888888888  888 \n888   Y88b Y8b.    Y8b.    888  888 \n888    Y88b "Y8888  "Y8888 888  888 \n                                    \n                                    \n                                    \n',
    "cosmic": ' :::  .   .,:::::: .,:::::::::.    :::.\n ;;; .;;,.;;;;\'\'\'\' ;;;;\'\'\'\'`;;;;,  `;;;\n [[[[[/\'   [[cccc   [[cccc   [[[[[. \'[[\n_$$$$,     $$""""   $$""""   $$$ "Y$c$$\n"888"88o,  888oo,__ 888oo,__ 888    Y88\n MMM "MMP" """"YUMMM""""YUMMMMMM     YM\n',
    "letters": "KK  KK                       \nKK KK    eee    eee  nn nnn  \nKKKK   ee   e ee   e nnn  nn \nKK KK  eeeee  eeeee  nn   nn \nKK  KK  eeeee  eeeee nn   nn \n                             \n",
    "o8": "oooo   oooo                                  \n 888  o88  ooooooooo8 ooooooooo8 oo oooooo   \n 888888   888oooooo8 888oooooo8   888   888  \n 888  88o 888        888          888   888  \no888o o888o 88oooo888  88oooo888 o888o o888o \n                                             \n",
    "univers": '                                               \n88      a8P                                    \n88    ,88\'                                     \n88  ,88"                                       \n88,d88\'      ,adPPYba,  ,adPPYba, 8b,dPPYba,   \n8888"88,    a8P_____88 a8P_____88 88P\'   `"8a  \n88P   Y8b   8PP""""""" 8PP""""""" 88       88  \n88     "88, "8b,   ,aa "8b,   ,aa 88       88  \n88       Y8b `"Ybbd8"\'  `"Ybbd8"\' 88       88  \n                                               \n                                               \n',
}


def get_banner(version: str) -> str:
    font: str = random.choice(fonts)
    quote: str = random.choice(quotes)
    version_styled: str = stylize(
        f"Version: {version}",
        Style(
            color=Color.YELLOW,
        ),
    )

    banner: str = PRE_RENDERED_BANNERS.get(font, PRE_RENDERED_BANNERS["univers"])
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
