import os
import collections

def get_py_files(start_dir):
    py_files = []
    # Walk src directory
    for root, dirs, files in os.walk(start_dir):
        # Skip pycache
        if "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                py_files.append(os.path.join(root, file))
    
    # Also add root files if they exist
    root_files = ["dehashed_server.py", "hunterio_server.py", "keen.py", "test.py"]
    for rf in root_files:
        if os.path.exists(rf):
            py_files.append(os.path.abspath(rf))
    return py_files

def clean_and_parse(filepath):
    """
    Reads a file, and returns a list of tuples: (cleaned_line, original_line_num, original_line_content)
    """
    parsed = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            cleaned = line.strip()
            # Skip comments and empty lines
            if not cleaned or cleaned.startswith("#"):
                continue
            parsed.append((cleaned, idx, line.rstrip("\n")))
    return parsed

def find_duplicates(py_files, min_lines=5):
    """
    Finds duplicated sequences of cleaned lines of at least min_lines length.
    """
    # Map from tuple of cleaned lines to list of (filepath, start_idx, end_idx, original_lines)
    sequences = collections.defaultdict(list)
    
    file_contents = {}
    for fp in py_files:
        file_contents[fp] = clean_and_parse(fp)
        
    # We will slide a window of size min_lines across all files
    for fp, parsed in file_contents.items():
        if len(parsed) < min_lines:
            continue
        for i in range(len(parsed) - min_lines + 1):
            window = tuple(parsed[j][0] for j in range(i, i + min_lines))
            # Also keep track of the details
            start_line_num = parsed[i][1]
            end_line_num = parsed[i + min_lines - 1][1]
            orig_snippet = [parsed[j][2] for j in range(i, i + min_lines)]
            
            sequences[window].append({
                "file": fp,
                "start": start_line_num,
                "end": end_line_num,
                "snippet": orig_snippet
            })
            
    # Now, filter sequences that appear in more than one place (either different files, or different locations in same file)
    duplicate_candidates = {}
    for seq, occurrences in sequences.items():
        if len(occurrences) > 1:
            # Let's filter out occurrences that are overlapping or too close in the same file to be meaningful
            # (though normally different files or distinct sections are what we want)
            unique_places = []
            for occ in occurrences:
                # check if too close to an already added one
                overlap = False
                for existing in unique_places:
                    if existing["file"] == occ["file"] and abs(existing["start"] - occ["start"]) < min_lines:
                        overlap = True
                        break
                if not overlap:
                    unique_places.append(occ)
            if len(unique_places) > 1:
                duplicate_candidates[seq] = unique_places
                
    # Now, let's merge adjacent/overlapping duplicate blocks to form longer duplicate blocks.
    # A block is longer if we can extend the duplicate sequence.
    # To do this systematically, we can do a greedy merge or simply run the check with a larger min_lines
    # and filter subsets.
    # Let's do a simple filter: if a duplicate candidate's sequence is a subset of a longer one, we can discard the smaller one if the occurrences match.
    sorted_candidates = sorted(duplicate_candidates.items(), key=lambda x: len(x[0]), reverse=True)
    merged_duplicates = []
    
    for seq, occurrences in sorted_candidates:
        # Check if this seq is already fully covered by a merged duplicate
        covered = False
        for m_seq, m_occs in merged_duplicates:
            # m_seq is a tuple. seq is a tuple. Check if seq is in m_seq
            if len(seq) < len(m_seq):
                # Is seq a subsequence of m_seq?
                seq_str = " ".join(seq)
                m_seq_str = " ".join(m_seq)
                if seq_str in m_seq_str:
                    # Let's verify that occurrences also match in terms of locations (approximately)
                    # We can just see if the files involved in occurrences are a subset of m_occs
                    # (to be safe, let's just mark it as covered if files and start/end boundaries align)
                    matched_occs = 0
                    for occ in occurrences:
                        for m_occ in m_occs:
                            if occ["file"] == m_occ["file"] and m_occ["start"] <= occ["start"] and occ["end"] <= m_occ["end"]:
                                matched_occs += 1
                                break
                    if matched_occs == len(occurrences):
                        covered = True
                        break
        if not covered:
            merged_duplicates.append((seq, occurrences))
            
    return merged_duplicates

if __name__ == "__main__":
    start_dir = "src"
    py_files = get_py_files(start_dir)
    print(f"Found {len(py_files)} Python files to analyze.")
    
    dupes = find_duplicates(py_files, min_lines=6)
    print(f"Found {len(dupes)} duplicated code segments of 6+ lines:")
    for idx, (seq, occs) in enumerate(dupes, 1):
        print(f"\n--- DUPLICATE BLOCK #{idx} ({len(seq)} lines, {len(occs)} occurrences) ---")
        for occ in occs:
            # print relative path
            rel_path = os.path.relpath(occ['file'])
            print(f"  File: {rel_path} (Lines {occ['start']}-{occ['end']})")
        print("  Snippet:")
        for line in occs[0]["snippet"]:
            print(f"    {line}")
