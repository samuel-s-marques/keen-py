import argparse
from src.core.shell import Shell
from src.utils.logger import setup_logger

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Keen - Information Gathering Tool")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    setup_logger(debug_mode=args.debug)

    shell = Shell(debug_mode=args.debug)
    shell.cmdloop()

