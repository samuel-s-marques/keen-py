import argparse
import subprocess
import sys


def check_dependencies():
    """Check and install missing Python dependencies."""
    required_packages = {
        "bs4": "beautifulsoup4",
        "cmd2": "cmd2",
        "cryptography": "cryptography",
        "dns": "dnspython",
        "fastapi": "fastapi",
        "httpx": "httpx",
        "uvicorn": "uvicorn[standard]",
        "loguru": "loguru",
        "rich": "rich",
        "phonenumbers": "phonenumbers",
        "pyfiglet": "pyfiglet",
        "whois": "python_whois",
        "user_scanner": "user-scanner",
    }

    missing_packages = []
    for import_name, install_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(install_name)

    if missing_packages:
        print(f"[!] Missing dependencies: {', '.join(missing_packages)}")
        print("[!] Attempting to install...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user"] + missing_packages
            )
            print("Dependencies installed successfully.")
        except Exception as e:
            print(f"[X] Error installing dependencies: {e}")
            print(
                "Please install them manually using: pip install --user "
                + " ".join(missing_packages)
            )
            sys.exit(1)


if __name__ == "__main__":
    check_dependencies()

    from src.core.shell import Shell
    from src.utils.logger import setup_logger

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

    setup_logger(debug_mode=args.debug)

    if args.web:
        from src.api.server import start_server

        start_server(host=args.host, port=args.port, debug=args.debug)
    else:
        shell = Shell(debug_mode=args.debug)
        shell.cmdloop()
