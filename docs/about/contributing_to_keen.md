# Contributing to Keen

First off, thank you for considering contributing to **Keen**! It's people like you who make open-source security tools powerful, reliable, and accessible for the community.

Whether you're fixing a bug, adding a new intelligence module, improving documentation, or suggesting a feature, all contributions are highly appreciated.

---

## How Can I Contribute?

### Reporting Bugs
If you encounter unexpected behavior, crashes, or parsing errors while running Keen, please open an issue on GitHub. Include:
- Your operating system and Python version.
- The exact command or module you were running.
- A full traceback / error log if available.
- Steps to reproduce the issue.

### Suggesting Enhancements & Features
Have an idea for a new third-party integration, UI feature, or reconnaissance technique? Open a feature request issue explaining:
- The goal of the feature.
- How it enhances the investigation workflow.
- Any relevant API documentation or third-party services involved.

### Developing New Modules
The framework is built to be highly extensible. If you want to build a new OSINT module (e.g., adding Shodan, Censys, or custom scrapers), check out our dedicated guide:
- **[Developing New Modules](../developer/developing_new_modules.md)**

### Improving Documentation
Great documentation is crucial. If you spot typos, missing instructions, or unclear explanations in our MkDocs site, feel free to submit a pull request updating the Markdown files under the `docs/` directory.

---

## Local Development Setup

To set up Keen for local development:

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/samuel-s-marques/keen-py.git
   cd keen-py
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # On Linux / macOS
   python3 -m venv venv
   source venv/bin/activate

   # On Windows
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install project dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Verify your setup by starting the interactive shell:**
   ```bash
   python keen.py --debug
   ```

---

## Pull Request Process

When you are ready to submit your changes, follow these standard guidelines:

1. **Branch cleanly:** Create a descriptive branch from `main` (e.g., `feature/add-shodan-module`, `bugfix/whois-parser-crash`).
2. **Adhere to Code Style:** Ensure your Python code follows PEP 8 conventions. We recommend using standard linters and formatters like `black` and `flake8`.
3. **Keep Commits Atomic:** Write clear, concise commit messages explaining *what* was changed and *why*.
4. **Open a Pull Request:** Describe your PR thoroughly on GitHub. Mention any issues it resolves (e.g., `Fixes #12`).
5. **Code Review:** Maintainers will review your PR, suggest any necessary adjustments, and merge it once approved!
