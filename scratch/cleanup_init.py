import os
import re

target_block = """    def __init__(self) -> None:
        super().__init__()

        self.options = {k: v[0] for k, v in self.metadata["options"].items()}"""

# Alternative block if spaces/lines differ slightly
target_block_alt = """    def __init__(self) -> None:
        super().__init__()
        self.options = {k: v[0] for k, v in self.metadata["options"].items()}"""

modules_dir = "src/modules"

count = 0
for root, dirs, files in os.walk(modules_dir):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            # Skip domain_enrichment_module.py as it has custom results dict setup
            if "domain_enrichment_module.py" in file:
                continue
            
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            new_content = content
            if target_block in content:
                # Replace target block and any extra trailing newlines to keep it clean
                new_content = content.replace(target_block + "\n\n", "").replace(target_block, "")
                count += 1
            elif target_block_alt in content:
                new_content = content.replace(target_block_alt + "\n\n", "").replace(target_block_alt, "")
                count += 1
            else:
                # Let's do a regex search for any standard constructor that only maps self.options
                # to catch slight formatting differences
                pattern = r"    def __init__\(self\)\s*(?:->\s*None)?\s*:\s*\n\s*super\(\)\.__init__\(\)\s*\n\s*self\.options\s*=\s*\{k:\s*v\[0\]\s*for\s*k,\s*v\s*in\s*self\.metadata\[[\"']options[\"']\]\.items\(\)\}\s*\n?"
                match = re.search(pattern, content)
                if match:
                    new_content = re.sub(pattern, "", content)
                    count += 1
            
            if new_content != content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Cleaned redundant __init__ from: {filepath}")

print(f"Total files cleaned: {count}")
