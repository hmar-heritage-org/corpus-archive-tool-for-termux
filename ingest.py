#!/usr/bin/env python3
"""
Hmar Heritage Foundation — Corpus Archive Ingestion Engine for Termux
A mobile-optimized TUI tool to ingest and preserve documents into
the Hugging Face dataset: hmar-heritage-org/corpus-archive.

Features:
- Deep internal memory scanning on Android (/sdcard & ~/storage/shared)
- Filter out system caches and display PDFs sorted by recent modification
- Fetch latest remote registry indexes from Hugging Face
- Determine next sequential 4-digit ID (e.g. 0013)
- Build local representative 3-tier archival directory tree
- Direct atomic commit to Hugging Face via API write token
- Remember HF token locally for frictionless repeated ingestions
"""

import os
import sys
import json
import shutil
import re
import time
from pathlib import Path
from datetime import datetime

# ANSI Color Codes
BOLD = "\033[1m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
DIM = "\033[2m"
RESET = "\033[0m"

REPO_ID = "hmar-heritage-org/corpus-archive"
TOKEN_PATH = Path.home() / ".huggingface" / "token"
CONFIG_FILE = Path.home() / ".corpus_archive_config.json"

CATEGORIES = [
    "Linguistics & Dictionaries",
    "School Textbooks & MIL",
    "History & Ethnography",
    "Religion & Theology",
    "Cultural Literature & Folklore",
    "Glossary",
    "Customary Laws & Governance"
]

LANGUAGES = [
    ("hmr", "Hmar"),
    ("lus", "Mizo"),
    ("en", "English"),
    ("pck", "Paite"),
    ("tcz", "Thadou"),
    ("vap", "Vaiphei")
]

EXCLUDE_DIRS = {
    "Android/data",
    "Android/obb",
    ".thumbnails",
    ".trash",
    ".cache",
    ".git",
    "node_modules",
    "proc",
    "sys"
}


def clear_screen():
    os.system("clear" if os.name == "posix" else "cls")


def print_banner():
    clear_screen()
    print(f"{CYAN}{BOLD}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        Hmar Heritage Foundation — Corpus Archive TUI         ║")
    print("║            Mobile & Termux Ingestion Engine (v1.1)           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{RESET}")


def check_termux_storage():
    """Checks if Termux has storage permission, prompts user if needed."""
    is_termux = "TERMUX_VERSION" in os.environ or "/data/data/com.termux" in os.environ.get("PREFIX", "")
    if not is_termux:
        print(f"{DIM}Desktop Linux / macOS environment detected.{RESET}")
        return

    storage_shared = Path.home() / "storage" / "shared"
    sdcard = Path("/sdcard")
    if not storage_shared.exists() and not sdcard.exists():
        print(f"{YELLOW}Warning: Internal storage links not detected.{RESET}")
        print("If you are running on Termux, please run:")
        print(f"  {CYAN}termux-setup-storage{RESET}")
        print("and grant storage permission in the Android popup.")
        resp = input("Have you granted storage permission? (Y/n): ").strip().lower()
        if resp in ("", "y", "yes"):
            time.sleep(1)


def get_storage_roots():
    """Identifies root directories for Android internal storage or desktop."""
    roots = []
    candidates = [
        Path.home() / "storage" / "shared",
        Path.home() / "storage" / "downloads",
        Path("/sdcard"),
        Path("/storage/emulated/0"),
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.home() / "Work",
        Path.cwd()
    ]
    for c in candidates:
        if c.exists() and c.is_dir() and c not in roots:
            roots.append(c)
    return roots


def scan_storage_for_pdfs(max_results=25):
    """Scans storage for PDF files, ignoring system directories, sorted by mtime."""
    print(f"{CYAN}Scanning internal memory for PDF documents...{RESET}")
    found = {}
    roots = get_storage_roots()

    for root in roots:
        try:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                # Prune excluded directories
                rel = os.path.relpath(dirpath, root)
                if any(ex in rel for ex in EXCLUDE_DIRS) or any(part.startswith(".") for part in rel.split(os.sep)):
                    dirnames[:] = []
                    continue

                for fname in filenames:
                    if fname.lower().endswith(".pdf"):
                        full_path = Path(dirpath) / fname
                        try:
                            stat = full_path.stat()
                            if stat.st_size > 1024:  # > 1 KB
                                found[str(full_path.resolve())] = (full_path, stat.st_size, stat.st_mtime)
                        except (PermissionError, FileNotFoundError):
                            continue
        except (PermissionError, FileNotFoundError):
            continue

    pdf_list = list(found.values())
    # Sort descending by modification time (most recently downloaded/modified first)
    pdf_list.sort(key=lambda item: item[2], reverse=True)
    return pdf_list[:max_results]


def select_pdf():
    print(f"\n{YELLOW}[1/7] Select PDF to Archive:{RESET}")
    pdfs = scan_storage_for_pdfs(max_results=20)

    if pdfs:
        print(f"\n{BOLD}Discovered Documents in Storage (Most Recent First):{RESET}")
        for idx, (p, size, mtime) in enumerate(pdfs, 1):
            size_mb = size / (1024 * 1024)
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            parent_folder = p.parent.name
            print(f"  [{CYAN}{idx:2d}{RESET}] {BOLD}{p.name[:45]:<45}{RESET} {DIM}({parent_folder}/){RESET}")
            print(f"       Size: {YELLOW}{size_mb:5.1f} MB{RESET}  | Modified: {DIM}{date_str}{RESET}")

        print(f"\n  [{CYAN} C{RESET}] Enter a custom file path manually")
        print(f"  [{CYAN} R{RESET}] Rescan storage")

        while True:
            choice = input(f"\nSelect an option (1-{len(pdfs)} or C/R): ").strip()
            if choice.lower() == "r":
                return select_pdf()
            if choice.lower() == "c":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(pdfs):
                return pdfs[int(choice) - 1][0]
            print(f"{RED}Invalid option. Enter a number between 1 and {len(pdfs)}, or 'C'.{RESET}")

    while True:
        raw_path = input("\nEnter full path to PDF file: ").strip().strip("'\"")
        p = Path(raw_path).expanduser().resolve()
        if p.exists() and p.is_file() and p.suffix.lower() == ".pdf":
            return p
        print(f"{RED}File not found or not a valid PDF: {p}{RESET}")


def select_category():
    print(f"\n{YELLOW}[2/7] Select Document Category:{RESET}")
    for idx, cat in enumerate(CATEGORIES, 1):
        print(f"  [{CYAN}{idx}{RESET}] {cat}")
    while True:
        choice = input(f"Choose category (1-{len(CATEGORIES)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(CATEGORIES):
            return CATEGORIES[int(choice) - 1]
        print(f"{RED}Invalid selection. Choose between 1 and {len(CATEGORIES)}.{RESET}")


def select_language():
    print(f"\n{YELLOW}[3/7] Select Primary Content Language:{RESET}")
    for idx, (code, name) in enumerate(LANGUAGES, 1):
        print(f"  [{CYAN}{idx}{RESET}] {name} ({code})")
    while True:
        choice = input(f"Choose language (1-{len(LANGUAGES)}, default 1 for Hmar): ").strip()
        if not choice:
            return "hmr"
        if choice.isdigit() and 1 <= int(choice) <= len(LANGUAGES):
            return LANGUAGES[int(choice) - 1][0]
        print(f"{RED}Invalid selection.{RESET}")


def prompt_details(suggested_title=""):
    print(f"\n{YELLOW}[4/7] Bibliographical Information:{RESET}")
    title = ""
    while not title:
        default_prompt = f" [{suggested_title}]" if suggested_title else ""
        title_in = input(f"Document / Book Title{default_prompt}: ").strip()
        title = title_in if title_in else suggested_title
        if not title:
            print(f"{RED}Title is required.{RESET}")

    raw_authors = input("Author(s) or Publishing Body (comma-separated, default: Hmar Heritage Foundation): ").strip()
    if not raw_authors:
        authors = ["Hmar Heritage Foundation"]
    else:
        authors = [a.strip() for a in raw_authors.split(",") if a.strip()]

    publisher = input("Publisher / Society (optional, e.g. HLS, BSI, NEHU): ").strip()
    year_str = input("Publication Year (optional, e.g. 1996): ").strip()
    year = int(year_str) if year_str.isdigit() else None

    description = input("Brief Description / Summary (optional): ").strip()
    if not description:
        description = f"Digitized document: {title}."

    return {
        "title": title,
        "authors": authors,
        "publisher": publisher,
        "year": year,
        "description": description
    }


def get_hf_token():
    """Retrieves or prompts for the Hugging Face Write Token."""
    # 1. Environment Variable
    env_token = os.environ.get("HF_TOKEN")
    if env_token:
        return env_token.strip()

    # 2. Local config
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("hf_token"):
                    return cfg["hf_token"].strip()
        except Exception:
            pass

    # 3. Standard ~/.huggingface/token
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "r", encoding="utf-8") as f:
                tok = f.read().strip()
                if tok:
                    return tok
        except Exception:
            pass

    # 4. Interactive prompt
    print(f"\n{YELLOW}[5/7] Hugging Face Authentication:{RESET}")
    print(f"To upload to {CYAN}{REPO_ID}{RESET}, you need a Hugging Face Access Token with {BOLD}WRITE{RESET} permission.")
    print("Get your token at: https://huggingface.co/settings/tokens")
    
    while True:
        token = input("\nEnter your HF Write Token (hf_...): ").strip()
        if token.startswith("hf_") or len(token) >= 20:
            save_choice = input("Save this token locally for future runs? (Y/n): ").strip().lower()
            if save_choice in ("", "y", "yes"):
                try:
                    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                        f.write(token)
                    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                        json.dump({"hf_token": token}, f)
                    print(f"  {GREEN}✓{RESET} Token saved safely to {TOKEN_PATH}")
                except Exception as e:
                    print(f"  {YELLOW}Note: Could not persist token ({e}), proceeding with memory token.{RESET}")
            return token
        print(f"{RED}Invalid token format. Hugging Face tokens typically begin with 'hf_'.{RESET}")


def fetch_remote_indexes(token):
    """Downloads lightweight registry index files from HF using huggingface_hub or urllib."""
    print(f"\n{CYAN}Fetching current registry files from Hugging Face...{RESET}")
    try:
        from huggingface_hub import hf_hub_download
        
        files = {
            "viewer": hf_hub_download(repo_id=REPO_ID, filename="viewer.jsonl", repo_type="dataset", token=token),
            "tier1": hf_hub_download(repo_id=REPO_ID, filename="metadata.jsonl", repo_type="dataset", token=token),
            "tier2_pdf": hf_hub_download(repo_id=REPO_ID, filename="data/pdf/metadata.jsonl", repo_type="dataset", token=token),
            "readme": hf_hub_download(repo_id=REPO_ID, filename="README.md", repo_type="dataset", token=token)
        }
        return files
    except Exception as e:
        print(f"{RED}Error communicating with Hugging Face: {e}{RESET}")
        print("Check your internet connection and verify that your HF token is valid.")
        sys.exit(1)


def compute_next_id(viewer_file_path: str) -> str:
    """Computes next 4-digit sequential ID from viewer.jsonl."""
    max_id = 0
    with open(viewer_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    record = json.loads(line)
                    num = int(record.get("id", 0))
                    if num > max_id:
                        max_id = num
                except Exception:
                    pass
    return f"{max_id + 1:04d}"


def update_readme_content(original_content: str, new_entry: dict) -> str:
    """Inserts a new row into the markdown catalog table in README.md."""
    authors_str = ", ".join(new_entry["authors"])
    new_row = (
        f"| **{new_entry['id']}** | {new_entry['title']} "
        f"| {authors_str} | {new_entry['category']} "
        f"| `{new_entry['language']}` | PDF "
        f"| [View PDF]({new_entry['file_path']}) |"
    )

    pattern = r"(\| ID \| Title \| Authors \| Category \| Target Language \| Format \| Direct File Link \|\n\| :---: \| :--- \| :--- \| :--- \| :---: \| :---: \| :--- \|\n)([\s\S]*?)(\n---|\n\n##)"
    match = re.search(pattern, original_content)
    if match:
        table_head = match.group(1)
        table_body = match.group(2).rstrip()
        suffix = match.group(3)
        updated_table = f"{table_head}{table_body}\n{new_row}\n{suffix}"
        return original_content[:match.start()] + updated_table + original_content[match.end():]
    return original_content


def build_representative_directory(staging_dir: Path, source_pdf: Path, metadata: dict, downloaded_files: dict):
    """
    Constructs the exact representative 3-tier repository directory structure
    and updates all catalog indices.
    """
    print(f"\n{YELLOW}[6/7] Generating Representative Directory Tree...{RESET}")
    item_id = metadata["id"]
    rel_pdf_path = f"data/pdf/{item_id}/file.pdf"
    metadata["file_path"] = rel_pdf_path
    metadata["format"] = "pdf"

    # Directory layout:
    # staging_dir/
    # ├── data/pdf/{id}/file.pdf
    # ├── data/pdf/{id}/metadata.json (Tier 3)
    # ├── data/pdf/metadata.jsonl     (Tier 2)
    # ├── viewer.jsonl
    # ├── metadata.jsonl              (Tier 1)
    # └── README.md
    
    target_item_dir = staging_dir / "data" / "pdf" / item_id
    target_item_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = target_item_dir / "file.pdf"

    # 1. Copy PDF
    print(f"  Copying {source_pdf.name} -> {rel_pdf_path}...")
    shutil.copy2(source_pdf, target_pdf)

    # 2. Tier 3: metadata.json
    tier3_data = {
        "id": item_id,
        "title": metadata["title"],
        "authors": metadata["authors"],
        "category": metadata["category"],
        "language": metadata["language"],
        "format": "pdf",
        "file_path": rel_pdf_path
    }
    if metadata.get("publisher"):
        tier3_data["publisher"] = metadata["publisher"]
    if metadata.get("year"):
        tier3_data["year"] = metadata["year"]
    tier3_data["description"] = metadata["description"]

    tier3_path = target_item_dir / "metadata.json"
    with open(tier3_path, "w", encoding="utf-8") as f:
        json.dump(tier3_data, f, indent=2, ensure_ascii=False)
    print(f"  {GREEN}✓{RESET} Created Tier 3: {tier3_path.relative_to(staging_dir)}")

    # 3. Tier 2: data/pdf/metadata.jsonl
    tier2_path = staging_dir / "data" / "pdf" / "metadata.jsonl"
    shutil.copy2(downloaded_files["tier2_pdf"], tier2_path)
    tier2_entry = {
        "id": item_id,
        "title": metadata["title"],
        "authors": metadata["authors"],
        "category": metadata["category"],
        "language": metadata["language"],
        "file_path": rel_pdf_path
    }
    with open(tier2_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(tier2_entry, ensure_ascii=False) + "\n")
    print(f"  {GREEN}✓{RESET} Appended to Tier 2: {tier2_path.relative_to(staging_dir)}")

    # 4. viewer.jsonl
    viewer_path = staging_dir / "viewer.jsonl"
    shutil.copy2(downloaded_files["viewer"], viewer_path)
    viewer_entry = {
        "id": item_id,
        "title": metadata["title"],
        "category": metadata["category"],
        "language": metadata["language"],
        "format": "pdf",
        "file_path": rel_pdf_path
    }
    with open(viewer_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(viewer_entry, ensure_ascii=False) + "\n")
    print(f"  {GREEN}✓{RESET} Appended to Viewer: viewer.jsonl")

    # 5. Tier 1: metadata.jsonl (Root Pointer Index)
    tier1_path = staging_dir / "metadata.jsonl"
    shutil.copy2(downloaded_files["tier1"], tier1_path)
    tier1_lines = []
    with open(tier1_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item.get("format") == "pdf":
                    item["count"] = item.get("count", 0) + 1
                tier1_lines.append(item)
    with open(tier1_path, "w", encoding="utf-8") as f:
        for item in tier1_lines:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  {GREEN}✓{RESET} Incremented PDF count in Tier 1: metadata.jsonl")

    # 6. README.md
    readme_path = staging_dir / "README.md"
    with open(downloaded_files["readme"], "r", encoding="utf-8") as f:
        original_readme = f.read()
    updated_readme = update_readme_content(original_readme, metadata)
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated_readme)
    print(f"  {GREEN}✓{RESET} Updated Catalog Table in README.md")

    return {
        "pdf": target_pdf,
        "tier3": tier3_path,
        "tier2": tier2_path,
        "viewer": viewer_path,
        "tier1": tier1_path,
        "readme": readme_path
    }


def upload_to_huggingface(token: str, item_id: str, title: str, staged_files: dict):
    """Performs an atomic commit to the Hugging Face repository."""
    print(f"\n{YELLOW}[7/7] Committing to Hugging Face Archive...{RESET}")
    try:
        from huggingface_hub import HfApi, CommitOperationAdd

        api = HfApi(token=token)

        commit_message = f"archive: ingest Item {item_id} ({title})"
        print(f"Preparing atomic commit: {CYAN}{commit_message}{RESET}")

        operations = [
            CommitOperationAdd(
                path_in_repo=f"data/pdf/{item_id}/file.pdf",
                path_or_fileobj=str(staged_files["pdf"])
            ),
            CommitOperationAdd(
                path_in_repo=f"data/pdf/{item_id}/metadata.json",
                path_or_fileobj=str(staged_files["tier3"])
            ),
            CommitOperationAdd(
                path_in_repo="data/pdf/metadata.jsonl",
                path_or_fileobj=str(staged_files["tier2"])
            ),
            CommitOperationAdd(
                path_in_repo="viewer.jsonl",
                path_or_fileobj=str(staged_files["viewer"])
            ),
            CommitOperationAdd(
                path_in_repo="metadata.jsonl",
                path_or_fileobj=str(staged_files["tier1"])
            ),
            CommitOperationAdd(
                path_in_repo="README.md",
                path_or_fileobj=str(staged_files["readme"])
            ),
        ]

        print("Uploading new PDF and updating registries on Hugging Face...")
        api.create_commit(
            repo_id=REPO_ID,
            repo_type="dataset",
            operations=operations,
            commit_message=commit_message
        )

        print(f"\n{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
        print(f"{GREEN}{BOLD}✓ SUCCESS! Item {item_id} successfully archived and published!{RESET}")
        print(f"{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
        print(f"\nDataset URL: {CYAN}https://huggingface.co/datasets/{REPO_ID}{RESET}")
        print(f"Direct Link: {CYAN}https://huggingface.co/datasets/{REPO_ID}/tree/main/data/pdf/{item_id}{RESET}")

    except Exception as e:
        print(f"\n{RED}Upload failed: {e}{RESET}")
        print("Your staged files remain intact locally in './staging'.")
        print("You can verify your token permissions or retry.")


def main():
    print_banner()
    check_termux_storage()

    # Step 1: Scan and select PDF
    source_pdf = select_pdf()
    suggested_title = source_pdf.stem.replace("_", " ").replace("-", " ").title()

    # Step 2 & 3: Metadata selection
    category = select_category()
    language = select_language()

    # Step 4: Bibliographical details
    details = prompt_details(suggested_title)

    # Step 5: Fetch remote indexes (public) & compute ID
    downloaded_files = fetch_remote_indexes(token=None)
    next_id = compute_next_id(downloaded_files["viewer"])

    record = {
        "id": next_id,
        "title": details["title"],
        "authors": details["authors"],
        "category": category,
        "language": language,
        "publisher": details["publisher"],
        "year": details["year"],
        "description": details["description"],
    }

    # Ingestion Confirmation
    print(f"\n{CYAN}{BOLD}=== Ingestion Summary ==={RESET}")
    print(f"  Assigned Sequential ID: {GREEN}{BOLD}{record['id']}{RESET}")
    print(f"  Document Title:         {record['title']}")
    print(f"  Author(s) / Body:       {', '.join(record['authors'])}")
    print(f"  Category:               {record['category']}")
    print(f"  Language:               {record['language']}")
    print(f"  Source File:            {source_pdf.name}")
    print(f"  Target Archive Path:    data/pdf/{record['id']}/file.pdf")

    confirm = input(f"\nProceed with generating local representative staging? (Y/n): ").strip().lower()
    if confirm not in ("", "y", "yes"):
        print("Ingestion aborted.")
        sys.exit(0)

    # Build Representative Staging Tree
    staging_dir = Path.cwd() / "staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    staged_files = build_representative_directory(staging_dir, source_pdf, record, downloaded_files)

    print(f"\n{GREEN}{BOLD}✓ Local Representative Staging Generated:{RESET}")
    print(f"  Folder: {CYAN}{staging_dir.resolve()}{RESET}")

    # Prompt for Upload
    upload_choice = input(f"\nUpload to Hugging Face now? (Y/n or D for dry-run only): ").strip().lower()
    if upload_choice in ("d", "dry", "dry-run", "n", "no"):
        print(f"\n{GREEN}{BOLD}✓ DRY-RUN COMPLETE!{RESET}")
        print(f"All files have been staged cleanly in: {CYAN}{staging_dir}{RESET}")
        print("Hugging Face was NOT modified. You can inspect the staged files anytime.")
        return

    # Authenticate and Upload
    token = get_hf_token()
    upload_to_huggingface(token, record["id"], record["title"], staged_files)


if __name__ == "__main__":
    main()
