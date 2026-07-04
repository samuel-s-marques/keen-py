import os
import collections

def get_py_files(start_dir):
    py_files = []
    for root, dirs, files in os.walk(start_dir):
        if "__pycache__" in root or ".pytest_cache" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))
    
    root_files = ["dehashed_server.py", "hunterio_server.py", "keen.py", "test.py"]
    for rf in root_files:
        if os.path.exists(rf):
            py_files.append(os.path.abspath(rf))
    return py_files

def clean_and_parse(filepath):
    parsed = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            cleaned = line.strip()
            # Skip comments and empty lines
            if not cleaned or cleaned.startswith("#"):
                continue
            parsed.append({
                "cleaned": cleaned,
                "line_num": idx,
                "orig": line.rstrip("\n")
            })
    return parsed

def get_maximal_matches(file_a, file_b, parsed_a, parsed_b, min_lines=6):
    """
    Finds maximal matching blocks of cleaned lines between parsed_a and parsed_b.
    Returns list of dicts: {
        'len': length,
        'start_a': start index in parsed_a,
        'start_b': start index in parsed_b,
        'snippet': list of original lines from parsed_a
    }
    """
    # Quick optimization: check if they are the same file and avoid matching the exact same lines
    same_file = (file_a == file_b)
    
    len_a = len(parsed_a)
    len_b = len(parsed_b)
    
    # Store visited matching pairs (i, j) to avoid redundant work
    visited = set()
    matches = []
    
    for i in range(len_a):
        for j in range(len_b):
            if same_file and i >= j: # avoid duplicates for same file and self-matches
                continue
                
            if (i, j) in visited:
                continue
                
            if parsed_a[i]["cleaned"] == parsed_b[j]["cleaned"]:
                # Try to expand
                k = 0
                while (i + k < len_a) and (j + k < len_b) and (parsed_a[i + k]["cleaned"] == parsed_b[j + k]["cleaned"]):
                    # If same file, avoid self-overlap that is trivial
                    if same_file and (i + k >= j):
                        break
                    k += 1
                
                if k >= min_lines:
                    # Record match
                    snippet = [parsed_a[i + x]["orig"] for x in range(k)]
                    matches.append({
                        "len": k,
                        "start_line_a": parsed_a[i]["line_num"],
                        "end_line_a": parsed_a[i + k - 1]["line_num"],
                        "start_line_b": parsed_b[j]["line_num"],
                        "end_line_b": parsed_b[j + k - 1]["line_num"],
                        "snippet": snippet,
                        "cleaned_seq": tuple(parsed_a[i + x]["cleaned"] for x in range(k))
                    })
                    
                    # Mark all pairs in this match as visited
                    for x in range(k):
                        visited.add((i + x, j + x))
                        
    return matches

def run_analysis(min_lines=6):
    py_files = get_py_files("src")
    file_data = {fp: clean_and_parse(fp) for fp in py_files}
    
    # List of all pairwise matches
    all_matches = []
    
    # Compare each pair of files (including self-comparisons for internal duplication)
    for i in range(len(py_files)):
        fp_a = py_files[i]
        parsed_a = file_data[fp_a]
        # Self-match first
        self_matches = get_maximal_matches(fp_a, fp_a, parsed_a, parsed_a, min_lines)
        for m in self_matches:
            all_matches.append({
                "len": m["len"],
                "snippet": m["snippet"],
                "cleaned_seq": m["cleaned_seq"],
                "occurrences": [
                    {"file": fp_a, "start": m["start_line_a"], "end": m["end_line_a"]},
                    {"file": fp_a, "start": m["start_line_b"], "end": m["end_line_b"]}
                ]
            })
            
        for j in range(i + 1, len(py_files)):
            fp_b = py_files[j]
            parsed_b = file_data[fp_b]
            
            pair_matches = get_maximal_matches(fp_a, fp_b, parsed_a, parsed_b, min_lines)
            for m in pair_matches:
                all_matches.append({
                    "len": m["len"],
                    "snippet": m["snippet"],
                    "cleaned_seq": m["cleaned_seq"],
                    "occurrences": [
                        {"file": fp_a, "start": m["start_line_a"], "end": m["end_line_a"]},
                        {"file": fp_b, "start": m["start_line_b"], "end": m["end_line_b"]}
                    ]
                })
                
    # Now group identical duplicate blocks that appear in multiple files/places.
    # Group by `cleaned_seq`
    grouped_dupes = collections.defaultdict(list)
    for m in all_matches:
        seq = m["cleaned_seq"]
        grouped_dupes[seq].append(m)
        
    # Coalesce occurrences of the same sequence
    coalesced = []
    for seq, matches in grouped_dupes.items():
        # Get all unique occurrences
        unique_occs = []
        for m in matches:
            for occ in m["occurrences"]:
                # Check if already added
                if not any(x["file"] == occ["file"] and x["start"] == occ["start"] and x["end"] == occ["end"] for x in unique_occs):
                    unique_occs.append(occ)
        # Sort occurrences by file then start line
        unique_occs.sort(key=lambda x: (x["file"], x["start"]))
        coalesced.append({
            "len": len(seq),
            "snippet": matches[0]["snippet"],
            "occurrences": unique_occs
        })
        
    # Sort by length of duplicate block descending
    coalesced.sort(key=lambda x: x["len"], reverse=True)
    return coalesced

if __name__ == "__main__":
    dupes = run_analysis(min_lines=6)
    print(f"TOTAL COALESCED DUPLICATE BLOCKS FOUND: {len(dupes)}")
    for idx, d in enumerate(dupes, 1):
        print(f"\nBLOCK #{idx} ({d['len']} lines of cleaned code, {len(d['occurrences'])} occurrences)")
        for occ in d["occurrences"]:
            rel = os.path.relpath(occ["file"])
            print(f"  - {rel}:{occ['start']}-{occ['end']}")
        print("  Code snippet:")
        for line in d["snippet"][:15]: # Show first 15 lines of snippet
            print(f"    {line}")
        if len(d["snippet"]) > 15:
            print(f"    ... and {len(d['snippet']) - 15} more lines")
