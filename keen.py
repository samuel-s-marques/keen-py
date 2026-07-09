import argparse
import sys


def main():
    """Console entry point."""
    try:
        from src.core.shell import Shell
        from src.utils.logger import setup_logger
    except ModuleNotFoundError as exc:
        print(f"[X] Missing dependency: {exc.name}")
        print(
            "Install Keen's dependencies with `pip install -e .` (from a source "
            "checkout) or `pip install keen-osint`, then try again."
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Keen - Information Gathering Tool")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--web", action="store_true", help="Start the Keen API web server"
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host address for the web server"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for the web server"
    )
    args = parser.parse_args()

    # Clear sys.argv to prevent cmd2 from parsing application launch arguments as shell commands
    sys.argv = [sys.argv[0]]

    setup_logger(debug_mode=args.debug)

    if args.web:
        from src.api.server import start_server

        start_server(host=args.host, port=args.port, debug=args.debug)
    else:
        shell = Shell(debug_mode=args.debug)
        shell.cmdloop()


if __name__ == "__main__":
    main()
