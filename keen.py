import argparse
import os
import subprocess
import sys
from pathlib import Path


def check_dependencies():
    """Check and install missing Python dependencies."""
    import hashlib
    import importlib.util
    import json

    if os.environ.get("KEEN_SKIP_DEP_CHECK") and "--check-deps" not in sys.argv:
        return

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
        "whois": "python-whois",
        "user_scanner": "user-scanner",
        "ddgs": "ddgs",
        "pydantic": "pydantic",
        "reportlab": "reportlab",
    }

    # Compute a hash representing the current required dependencies
    dep_data = json.dumps(sorted(required_packages.items())).encode("utf-8")
    current_hash = hashlib.sha256(dep_data).hexdigest()

    marker_dir = Path.home() / ".keen"
    marker_file = marker_dir / ".dependencies_verified"

    force_check = "--check-deps" in sys.argv
    if force_check:
        print("[*] Verifying all dependencies...")

    # Check if we can skip the dependency check
    if not force_check and marker_file.exists():
        try:
            stored_hash = marker_file.read_text().strip()
            if stored_hash == current_hash:
                # Fast verification using find_spec to ensure no package has been uninstalled
                all_present = True
                for import_name in required_packages:
                    try:
                        if importlib.util.find_spec(import_name) is None:
                            all_present = False
                            break
                    except Exception:
                        all_present = False
                        break
                if all_present:
                    return
        except Exception:
            pass

    missing_packages = []
    for import_name, install_name in required_packages.items():
        try:
            if importlib.util.find_spec(import_name) is None:
                missing_packages.append(install_name)
        except Exception:
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
            # Save the current dependency hash to the marker file
            try:
                os.makedirs(marker_dir, exist_ok=True)
                marker_file.write_text(current_hash)
            except Exception:
                pass
        except Exception as e:
            print(f"[X] Error installing dependencies: {e}")
            print(
                "Please install them manually using: pip install --user "
                + " ".join(missing_packages)
            )
            sys.exit(1)
    else:
        if force_check:
            print("[+] All dependencies are present and verified.")
        # All packages are already present, we can just save/update the current hash
        try:
            os.makedirs(marker_dir, exist_ok=True)
            marker_file.write_text(current_hash)
        except Exception:
            pass


def main():
    """Console entry point."""
    check_dependencies()

    from src.core.shell import Shell
    from src.utils.logger import setup_logger

    parser = argparse.ArgumentParser(description="Keen - Information Gathering Tool")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Force verification and re-installation of dependencies",
    )
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
