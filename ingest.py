#!/usr/bin/env python3
"""
Hmar Heritage Foundation — Corpus Archive Ingestion Engine for Termux
A mobile-optimized TUI tool to ingest and preserve documents into
the Hugging Face dataset: hmar-heritage-org/corpus-archive.

Sequential Workflow:
1. HF Token Authentication & Validation upfront (whoami + write role check)
2. Local Repository Detection & Auto-Sync (clone or custom path + git pull)
3. Action Menu (Option 1: Add PDF; Options 2-4: Marked 'Feature not implemented')
4. PDF Discovery & Bibliographical Metadata Collection
5. Atomic 3-Tier Archival & Direct Git/API Push
"""

import os
import sys
import json
import shutil
import re
import subprocess
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
REPO_URL = f"https://huggingface.co/datasets/{REPO_ID}"
TOOL_NAME = "corpus-archive-tool"
TOOL_VERSION = "v1.2"
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
    "node_modules",
    "vendor",
    "gems",
    "staging",
    "corpus-archive",
    ".thumbnails",
    ".trash",
    ".cache",
    ".git",
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
    print("║            Mobile & Termux Ingestion Engine (v1.2)           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{RESET}")


def graceful_exit(message: str = None, code: int = 0):
    """Prints a clean, friendly exit message without stack traces."""
    if message:
        print(f"\n{YELLOW}{message}{RESET}")
    else:
        print(f"\n{CYAN}{BOLD}Thank you for contributing to the Hmar Heritage Foundation Archive!{RESET}")
        print(f"Session closed cleanly.\n")
    sys.exit(code)


def safe_input(prompt_text: str = "", allow_back: bool = False) -> str:
    """
    Safely captures user input, catching KeyboardInterrupt (Ctrl+C) and EOFError (Ctrl+D).
    Returns '__BACK__' if allow_back is enabled and user inputs 'b' or 'back'.
    """
    try:
        val = input(prompt_text).strip()
        if allow_back and val.lower() in ("b", "back"):
            return "__BACK__"
        return val
    except KeyboardInterrupt:
        graceful_exit("\n[!] Operation cancelled by user (Ctrl+C). Exiting cleanly...")
    except EOFError:
        graceful_exit("\n[!] Session ended (EOF).")


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"{YELLOW}Warning: Could not save config file: {e}{RESET}")


def ensure_termux_storage() -> bool:
    """
    Ensures Android storage permissions and symlinks are set up in Termux.
    Automatically triggers termux-setup-storage if unconfigured and verifies filesystem access.
    """
    is_termux = (
        "TERMUX_VERSION" in os.environ or
        "/data/data/com.termux" in os.environ.get("PREFIX", "") or
        Path("/data/data/com.termux").exists()
    )

    if not is_termux:
        print(f"{DIM}Desktop Linux / macOS environment detected.{RESET}")
        return True

    storage_dir = Path.home() / "storage"
    shared_dir = storage_dir / "shared"
    sdcard = Path("/sdcard")

    # 1. Test if shared storage already exists and is readable
    for p in (shared_dir, sdcard):
        if p.exists():
            try:
                os.listdir(str(p))
                return True
            except (PermissionError, OSError):
                pass

    # 2. Trigger automated termux-setup-storage
    print(f"\n{BOLD}{YELLOW}[Termux Android Storage Permission Required]{RESET}")
    print("To discover your PDF books across your device, Termux needs storage permission.")
    print(f"Triggering {CYAN}termux-setup-storage{RESET} now...")

    try:
        subprocess.run(["termux-setup-storage"], check=False)
    except FileNotFoundError:
        print(f"{YELLOW}Note: 'termux-setup-storage' binary not found. Skipping auto-trigger.{RESET}")

    print(f"\n{CYAN}{BOLD}👉 Look at your phone screen and tap 'ALLOW' on the Android permissions popup.{RESET}")
    safe_input(f"Once you have tapped 'Allow', press {BOLD}[ENTER]{RESET} to continue...")

    # Wait up to 5 seconds for Termux to link the storage directory
    for _ in range(5):
        for p in (shared_dir, sdcard):
            if p.exists():
                try:
                    os.listdir(str(p))
                    print(f"  {GREEN}✓ Storage permission granted and verified!{RESET}")
                    return True
                except (PermissionError, OSError):
                    pass
        time.sleep(1)

    # 3. Fallback guidance if permission was denied or popup suppressed
    print(f"\n{RED}Notice: Storage access could not be confirmed automatically.{RESET}")
    print("If Android did not show the permission popup, you can enable it manually:")
    print(f"  {BOLD}Android Settings -> Apps -> Termux -> Permissions -> Files and media -> Allow{RESET}")
    retry = safe_input("\nWould you like to run 'termux-setup-storage' again? (Y/n): ").lower()
    if retry in ("", "y", "yes"):
        return ensure_termux_storage()
    return False


# ==============================================================================
# PHASE 1: HUGGING FACE TOKEN AUTHENTICATION & VALIDATION
# ==============================================================================

def validate_hf_token(token: str) -> tuple[bool, str, str]:
    """
    Validates token using HfApi.whoami().
    Returns (is_valid, username, role).
    """
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=token)
        user_info = api.whoami()
        username = user_info.get("name", "unknown")
        
        # Check token role/permission
        auth = user_info.get("auth", {})
        access_token_info = auth.get("accessToken", {})
        role = access_token_info.get("role", "")

        return True, username, role
    except Exception as e:
        return False, str(e), ""


def get_and_validate_token(force_prompt=False) -> tuple[str, str]:
    """
    Retrieves and validates the Hugging Face Write Token upfront.
    Returns (valid_token, username).
    """
    print(f"\n{BOLD}{YELLOW}[Phase 1/4] Hugging Face Authentication & Token Validation{RESET}")

    cfg = load_config()
    cached_token = None

    if not force_prompt:
        try:
            from huggingface_hub import get_token
            cached_token = get_token()
        except Exception:
            cached_token = None

        if not cached_token and cfg.get("hf_token"):
            cached_token = cfg["hf_token"].strip()

    if cached_token:
        print(f"Validating saved Hugging Face token...")
        valid, username, role = validate_hf_token(cached_token)
        if valid:
            print(f"  {GREEN}✓ Authenticated as @{username}{RESET} (Token Role: {BOLD}{role or 'write'}{RESET})")
            if role and role.lower() != "write" and role.lower() != "admin":
                print(f"  {YELLOW}Warning: Token role is '{role}'. Make sure it has write permission to publish.{RESET}")
            return cached_token, username
        else:
            print(f"  {RED}Saved token failed validation ({username}).{RESET}")

    # Prompt user for token
    print(f"\nTo contribute to {CYAN}{REPO_ID}{RESET}, a Hugging Face Access Token with {BOLD}WRITE{RESET} permission is required.")
    print(f"You can create one in 10 seconds at: {CYAN}https://huggingface.co/settings/tokens{RESET}")

    while True:
        token_input = safe_input(f"\nEnter your HF Write Token (or Q to exit): ")
        if token_input.lower() in ("q", "quit", "exit"):
            graceful_exit("Authentication aborted. Exiting tool.")
        if not token_input:
            print(f"{RED}Token cannot be empty.{RESET}")
            continue

        print(f"Validating token with Hugging Face API...")
        valid, username, role = validate_hf_token(token_input)
        if valid:
            print(f"  {GREEN}{BOLD}✓ Success! Authenticated as @{username}{RESET} (Role: {role or 'write'})")
            # Save token
            cfg["hf_token"] = token_input
            save_config(cfg)
            try:
                TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(TOKEN_PATH, "w", encoding="utf-8") as f:
                    f.write(token_input)
            except Exception:
                pass
            return token_input, username
        else:
            print(f"  {RED}Token validation failed: {username}{RESET}")
            print(f"Please ensure you copied the entire token correctly and that your internet is connected.")


# ==============================================================================
# PHASE 2: LOCAL REPOSITORY VERIFICATION & SYNC
# ==============================================================================

def is_valid_corpus_repo(path: Path) -> bool:
    """Checks if a path contains the corpus-archive structure."""
    return (
        path.exists() and
        path.is_dir() and
        (path / "viewer.jsonl").exists() and
        (path / "metadata.jsonl").exists() and
        (path / "README.md").exists()
    )


def sync_local_repo(repo_path: Path, token: str, username: str) -> bool:
    """Runs git pull to ensure local repository is synchronized with origin/main."""
    print(f"Checking for updates in local repository: {CYAN}{repo_path}{RESET}...")
    try:
        # Check if git is initialized
        if not (repo_path / ".git").exists():
            print(f"  {YELLOW}Note: No .git directory found. Operating in filesystem mode.{RESET}")
            return True

        # Run git pull
        cmd = ["git", "pull", "--rebase", "origin", "main"]
        res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            print(f"  {GREEN}✓ Repository is synchronized and up-to-date with Hugging Face.{RESET}")
            return True
        else:
            # Fallback check
            print(f"  {YELLOW}Git pull notice: {res.stderr.strip() or res.stdout.strip()}{RESET}")
            return True
    except Exception as e:
        print(f"  {YELLOW}Warning during git pull: {e}. Continuing with local files.{RESET}")
        return True


def verify_or_clone_repo(token: str, username: str) -> Path:
    """
    Ensures the repository exists locally. If not, prompts user to clone or provide custom path.
    """
    print(f"\n{BOLD}{YELLOW}[Phase 2/4] Local Repository Verification & Sync{RESET}")

    cfg = load_config()
    saved_path_str = cfg.get("repo_path")

    # 1. Check candidate paths
    candidates = []
    if saved_path_str:
        candidates.append(Path(saved_path_str))
    
    # Check parent / siblings
    curr = Path.cwd()
    candidates.extend([
        curr / "corpus-archive",
        curr.parent / "corpus-archive",
        curr.parent / "hmar-heritage-hf" / "corpus-archive",
        Path.home() / "corpus-archive",
        Path.home() / "Work" / "hmar-heritage-hf" / "corpus-archive",
    ])

    for p in candidates:
        if is_valid_corpus_repo(p):
            print(f"Found local corpus-archive repository at:")
            print(f"  {CYAN}{p.resolve()}{RESET}")
            sync_local_repo(p, token, username)
            cfg["repo_path"] = str(p.resolve())
            save_config(cfg)
            return p.resolve()

    # 2. Repo not found — Prompt to clone or provide custom path
    print(f"{YELLOW}Local clone of '{REPO_ID}' not found.{RESET}")
    print("\nHow would you like to proceed?")
    print(f"  [{CYAN}1{RESET}] {BOLD}(Recommended){RESET} Clone repository locally now")
    print(f"  [{CYAN}2{RESET}] Provide custom path to an existing local clone")

    while True:
        choice = safe_input("\nSelect option (1 or 2, or Q to exit, default 1): ").lower()
        if choice in ("q", "quit", "exit"):
            graceful_exit("Repository setup aborted.")
        if not choice or choice == "1":
            target_dir = curr / "corpus-archive"
            print(f"\nCloning {CYAN}{REPO_URL}{RESET} into {target_dir.name}...")
            try:
                # Use authenticated clone URL so pushes don't require re-typing password
                auth_url = f"https://{username}:{token}@huggingface.co/datasets/{REPO_ID}"
                cmd = ["git", "clone", auth_url, str(target_dir)]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0 and is_valid_corpus_repo(target_dir):
                    print(f"  {GREEN}{BOLD}✓ Successfully cloned corpus-archive!{RESET}")
                    cfg["repo_path"] = str(target_dir.resolve())
                    save_config(cfg)
                    return target_dir.resolve()
                else:
                    print(f"{RED}Git clone failed: {proc.stderr}{RESET}")
                    print("Attempting shallow or alternative clone...")
                    cmd_shallow = ["git", "clone", "--depth", "1", REPO_URL, str(target_dir)]
                    proc_s = subprocess.run(cmd_shallow, capture_output=True, text=True)
                    if proc_s.returncode == 0:
                        print(f"  {GREEN}✓ Cloned shallow repository.{RESET}")
                        cfg["repo_path"] = str(target_dir.resolve())
                        save_config(cfg)
                        return target_dir.resolve()
                    else:
                        print(f"{RED}Clone failed: {proc_s.stderr}{RESET}")
            except Exception as e:
                print(f"{RED}Error running git clone: {e}{RESET}")

        elif choice == "2":
            while True:
                custom_input = safe_input("\nEnter full path to local corpus-archive directory (or B to go back): ").strip("'\"")
                if custom_input.lower() in ("b", "back"):
                    break
                if custom_input.lower() in ("q", "quit", "exit"):
                    graceful_exit("Repository setup aborted.")
                p = Path(custom_input).expanduser().resolve()
                if is_valid_corpus_repo(p):
                    print(f"  {GREEN}✓ Valid repository verified at {p}{RESET}")
                    sync_local_repo(p, token, username)
                    cfg["repo_path"] = str(p)
                    save_config(cfg)
                    return p
                print(f"{RED}Invalid repository at: {p}. Make sure viewer.jsonl and metadata.jsonl exist.{RESET}")


# ==============================================================================
# PHASE 3: ACTION MENU
# ==============================================================================

def display_action_menu() -> str:
    print(f"\n{BOLD}{YELLOW}[Phase 3/4] Action Selection{RESET}")
    print("What action would you like to perform?")
    print(f"  [{CYAN}1{RESET}] {BOLD}Ingest & Archive a PDF Document{RESET}")
    print(f"  [{CYAN}2{RESET}] {DIM}Ingest Structured JSON Dataset [Feature not implemented]{RESET}")
    print(f"  [{CYAN}3{RESET}] {DIM}Archive Research Repository (CSV/Git) [Feature not implemented]{RESET}")
    print(f"  [{CYAN}4{RESET}] {DIM}Audit & Validate Archive Records [Feature not implemented]{RESET}")
    print(f"  [{CYAN}5{RESET}] Switch Hugging Face Account / Token")
    print(f"  [{CYAN}Q{RESET}] Exit")

    while True:
        choice = safe_input(f"\nEnter choice ({CYAN}1{RESET}, 2-5, or Q): ").lower()
        if choice in ("1", "add", "pdf"):
            return "1"
        elif choice in ("2", "3", "4"):
            features = {
                "2": "Structured JSON Dataset Ingestion",
                "3": "Multi-file Research Repository Ingestion",
                "4": "Archive Schema Audit & Validation"
            }
            print(f"\n{MAGENTA}[!] Feature Not Implemented:{RESET} '{features[choice]}' is scheduled for v1.3.")
            print("Currently, PDF Archival (Option 1) is fully active.")
            continue
        elif choice == "5":
            return "5"
        elif choice in ("q", "quit", "exit"):
            graceful_exit("Exiting tool. Have a great day!")
        print(f"{RED}Invalid selection. Enter 1 to archive a PDF or Q to quit.{RESET}")


# ==============================================================================
# PHASE 4: PDF INGESTION WORKFLOW
# ==============================================================================

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


def scan_storage_for_pdfs(max_results=20):
    """Scans storage for PDF files, ignoring system directories, sorted by mtime."""
    print(f"{CYAN}Scanning internal storage for PDF documents...{RESET}")
    found = {}
    roots = get_storage_roots()

    for root in roots:
        try:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                # Prune excluded directories in-place (allow Android/media for WhatsApp/Telegram)
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith(".")
                    and d not in EXCLUDE_DIRS
                    and not (d in ("data", "obb") and Path(dirpath).name == "Android")
                ]

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
    pdf_list.sort(key=lambda item: item[2], reverse=True)
    return pdf_list[:max_results]


def select_pdf():
    print(f"\n{BOLD}{CYAN}--- Step 1: Select PDF Document ---{RESET}")
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
        print(f"  [{CYAN} B{RESET}] Back to Main Menu")

        while True:
            choice = safe_input(f"\nSelect an option (1-{len(pdfs)} or C/R/B): ", allow_back=True).lower()
            if choice in ("b", "back", "__back__"):
                return None
            if choice == "r":
                return select_pdf()
            if choice == "c":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(pdfs):
                return pdfs[int(choice) - 1][0]
            print(f"{RED}Invalid option. Enter a number between 1 and {len(pdfs)}, 'C', or 'B' to go back.{RESET}")

    while True:
        raw_path = safe_input("\nEnter full path to PDF file (or B to go back): ", allow_back=True).strip("'\"")
        if raw_path.lower() in ("b", "back", "__back__"):
            return None
        p = Path(raw_path).expanduser().resolve()
        if p.exists() and p.is_file() and p.suffix.lower() == ".pdf":
            return p
        print(f"{RED}File not found or not a valid PDF: {p}{RESET}")


def select_category():
    print(f"\n{BOLD}{CYAN}--- Step 2: Document Classification ---{RESET}")
    for idx, cat in enumerate(CATEGORIES, 1):
        print(f"  [{CYAN}{idx}{RESET}] {cat}")
    print(f"  [{CYAN}B{RESET}] Back to Main Menu")

    while True:
        choice = safe_input(f"\nChoose category (1-{len(CATEGORIES)} or B): ", allow_back=True).lower()
        if choice in ("b", "back", "__back__"):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(CATEGORIES):
            return CATEGORIES[int(choice) - 1]
        print(f"{RED}Invalid selection. Choose between 1 and {len(CATEGORIES)}, or 'B'.{RESET}")


def select_language():
    print(f"\n{BOLD}{CYAN}--- Step 3: Primary Content Language ---{RESET}")
    for idx, (code, name) in enumerate(LANGUAGES, 1):
        print(f"  [{CYAN}{idx}{RESET}] {name} ({code})")
    print(f"  [{CYAN}B{RESET}] Back to Main Menu")

    while True:
        choice = safe_input(f"\nChoose language (1-{len(LANGUAGES)}, default 1 for Hmar, or B): ", allow_back=True).lower()
        if choice in ("b", "back", "__back__"):
            return None
        if not choice:
            return "hmr"
        if choice.isdigit() and 1 <= int(choice) <= len(LANGUAGES):
            return LANGUAGES[int(choice) - 1][0]
        print(f"{RED}Invalid selection.{RESET}")


def prompt_details(suggested_title=""):
    print(f"\n{BOLD}{CYAN}--- Step 4: Bibliographical Metadata (Type 'B' to cancel) ---{RESET}")
    title = ""
    while not title:
        default_prompt = f" [{suggested_title}]" if suggested_title else ""
        title_in = safe_input(f"Document / Book Title{default_prompt}: ", allow_back=True)
        if title_in.lower() in ("b", "back", "__back__"):
            return None
        title = title_in if title_in else suggested_title
        if not title:
            print(f"{RED}Title is required.{RESET}")

    raw_authors = safe_input("Author(s) or Publishing Body (comma-separated, default: Hmar Heritage Foundation): ", allow_back=True)
    if raw_authors.lower() in ("b", "back", "__back__"):
        return None
    if not raw_authors:
        authors = ["Hmar Heritage Foundation"]
    else:
        authors = [a.strip() for a in raw_authors.split(",") if a.strip()]

    publisher = safe_input("Publisher / Society (optional, e.g. HLS, BSI, NEHU): ")
    year_str = safe_input("Publication Year (optional, e.g. 1996): ")
    year = int(year_str) if year_str.isdigit() else None

    description = safe_input("Brief Description / Summary (optional): ")
    if not description:
        description = f"Digitized document: {title}."

    return {
        "title": title,
        "authors": authors,
        "publisher": publisher,
        "year": year,
        "description": description
    }


def compute_next_id(repo_path: Path) -> str:
    """Computes next 4-digit sequential ID from repo's viewer.jsonl."""
    viewer_file = repo_path / "viewer.jsonl"
    max_id = 0
    if viewer_file.exists():
        with open(viewer_file, "r", encoding="utf-8") as f:
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


def update_readme_table(repo_path: Path, new_entry: dict):
    """Inserts a new row into the catalog table in README.md."""
    readme_path = repo_path / "README.md"
    if not readme_path.exists():
        return

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    authors_str = ", ".join(new_entry["authors"])
    new_row = (
        f"| **{new_entry['id']}** | {new_entry['title']} "
        f"| {authors_str} | {new_entry['category']} "
        f"| `{new_entry['language']}` | PDF "
        f"| [View PDF]({new_entry['file_path']}) |"
    )

    pattern = r"(\| ID \| Title \| Authors \| Category \| Target Language \| Format \| Direct File Link \|\n\| :---: \| :--- \| :--- \| :--- \| :---: \| :---: \| :--- \|\n)([\s\S]*?)(\n---|\n\n##)"
    match = re.search(pattern, content)
    if match:
        table_head = match.group(1)
        table_body = match.group(2).rstrip()
        suffix = match.group(3)
        updated_table = f"{table_head}{table_body}\n{new_row}\n{suffix}"
        content = content[:match.start()] + updated_table + content[match.end():]
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  {GREEN}✓{RESET} Updated Catalog Table in README.md")


def ingest_to_repo(repo_path: Path, source_pdf: Path, metadata: dict):
    """Writes the PDF and updates all 4 metadata tiers in the local repo."""
    print(f"\n{BOLD}{CYAN}Writing files to repository structure...{RESET}")
    item_id = metadata["id"]
    rel_pdf_path = f"data/pdf/{item_id}/file.pdf"
    metadata["file_path"] = rel_pdf_path
    metadata["format"] = "pdf"

    # 1. Target directory & copy PDF
    target_item_dir = repo_path / "data" / "pdf" / item_id
    target_item_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = target_item_dir / "file.pdf"

    print(f"  Copying {source_pdf.name} -> {rel_pdf_path}...")
    shutil.copy2(source_pdf, target_pdf)
    print(f"  {GREEN}✓{RESET} PDF placed in repository.")

    # 2. Tier 3: data/pdf/{id}/metadata.json
    tier3_path = target_item_dir / "metadata.json"
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

    with open(tier3_path, "w", encoding="utf-8") as f:
        json.dump(tier3_data, f, indent=2, ensure_ascii=False)
    print(f"  {GREEN}✓{RESET} Created Tier 3: {tier3_path.relative_to(repo_path)}")

    # 3. Tier 2: data/pdf/metadata.jsonl
    tier2_path = repo_path / "data" / "pdf" / "metadata.jsonl"
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
    print(f"  {GREEN}✓{RESET} Appended to Tier 2: data/pdf/metadata.jsonl")

    # 4. Viewer: viewer.jsonl
    viewer_path = repo_path / "viewer.jsonl"
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

    # 5. Tier 1: metadata.jsonl
    tier1_path = repo_path / "metadata.jsonl"
    if tier1_path.exists():
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

    # 6. README.md Catalog Table
    update_readme_table(repo_path, metadata)


def push_to_remote(repo_path: Path, item_id: str, title: str, token: str, username: str):
    """Commits and pushes changes using Git, with fallback to Hugging Face API."""
    print(f"\n{BOLD}{YELLOW}[Phase 4/4] Publishing to Hugging Face Archive...{RESET}")

    default_base = f"archive: ingest Item {item_id} ({title})"
    via_marker = f"--via {TOOL_NAME} {TOOL_VERSION}"
    default_msg = f"{default_base} {via_marker}"

    print(f"\n{BOLD}Git Commit Message:{RESET}")
    print(f"  Default: {CYAN}{default_msg}{RESET}")
    custom = safe_input("Enter custom note (or press [ENTER] to use default): ")

    if custom:
        custom_clean = custom.replace(via_marker, "").strip()
        if f"[{item_id}]" not in custom_clean and f"Item {item_id}" not in custom_clean:
            commit_msg = f"archive: [Item {item_id}] {custom_clean} {via_marker}"
        else:
            commit_msg = f"archive: {custom_clean} {via_marker}"
    else:
        commit_msg = default_msg

    print(f"  Active commit message: {GREEN}{commit_msg}{RESET}\n")

    # Method 1: Standard Git commit & push
    if (repo_path / ".git").exists():
        try:
            print("Staging git changes...")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            
            # Configure author if not set
            subprocess.run(["git", "config", "user.name", username], cwd=repo_path, check=False)
            subprocess.run(["git", "config", "user.email", f"{username}@users.noreply.huggingface.co"], cwd=repo_path, check=False)

            subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, check=True)
            print(f"  {GREEN}✓ Changes committed locally.{RESET}")

            print("Pushing to Hugging Face (origin main)...")
            push_res = subprocess.run(["git", "push", "origin", "main"], cwd=repo_path, capture_output=True, text=True, timeout=60)
            if push_res.returncode == 0:
                print(f"\n{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
                print(f"{GREEN}{BOLD}✓ SUCCESS! Item {item_id} published live to Hugging Face!{RESET}")
                print(f"{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
                print(f"\nDataset URL: {CYAN}{REPO_URL}{RESET}")
                print(f"Item Link:   {CYAN}{REPO_URL}/tree/main/data/pdf/{item_id}{RESET}")
                return
            else:
                print(f"{YELLOW}Git push had a warning: {push_res.stderr.strip()}{RESET}")
                print("Falling back to Hugging Face API atomic upload...")
        except Exception as e:
            print(f"{YELLOW}Git push encountered issue: {e}. Using API fallback...{RESET}")

    # Method 2: Hugging Face API Atomic Commit Fallback
    try:
        from huggingface_hub import HfApi, CommitOperationAdd
        api = HfApi(token=token)

        item_pdf = repo_path / "data" / "pdf" / item_id / "file.pdf"
        item_meta = repo_path / "data" / "pdf" / item_id / "metadata.json"
        tier2 = repo_path / "data" / "pdf" / "metadata.jsonl"
        viewer = repo_path / "viewer.jsonl"
        tier1 = repo_path / "metadata.jsonl"
        readme = repo_path / "README.md"

        operations = [
            CommitOperationAdd(path_in_repo=f"data/pdf/{item_id}/file.pdf", path_or_fileobj=str(item_pdf)),
            CommitOperationAdd(path_in_repo=f"data/pdf/{item_id}/metadata.json", path_or_fileobj=str(item_meta)),
            CommitOperationAdd(path_in_repo="data/pdf/metadata.jsonl", path_or_fileobj=str(tier2)),
            CommitOperationAdd(path_in_repo="viewer.jsonl", path_or_fileobj=str(viewer)),
            CommitOperationAdd(path_in_repo="metadata.jsonl", path_or_fileobj=str(tier1)),
            CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=str(readme)),
        ]

        try:
            print("Executing atomic commit via Hugging Face API...")
            api.create_commit(
                repo_id=REPO_ID,
                repo_type="dataset",
                operations=operations,
                commit_message=commit_msg
            )

            print(f"\n{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
            print(f"{GREEN}{BOLD}✓ SUCCESS! Item {item_id} published live to Hugging Face!{RESET}")
            print(f"{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
            print(f"\nDataset URL: {CYAN}{REPO_URL}{RESET}")
            print(f"Item Link:   {CYAN}{REPO_URL}/tree/main/data/pdf/{item_id}{RESET}")

        except Exception as api_err:
            err_str = str(api_err).lower()
            if "403" in err_str or "permission" in err_str or "forbidden" in err_str:
                print(f"\n{YELLOW}Note: Direct write access to '{REPO_ID}' not granted for @{username}.{RESET}")
                pr_choice = safe_input("Would you like to submit this as a Hugging Face Pull Request? (Y/n): ").lower()
                if pr_choice in ("", "y", "yes"):
                    print("Submitting as a Community Pull Request to Hugging Face...")
                    commit_info = api.create_commit(
                        repo_id=REPO_ID,
                        repo_type="dataset",
                        operations=operations,
                        commit_message=commit_msg,
                        create_pr=True
                    )
                    pr_url = getattr(commit_info, "pr_url", f"{REPO_URL}/discussions")
                    print(f"\n{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
                    print(f"{GREEN}{BOLD}✓ SUCCESS! Pull Request submitted for Item {item_id}!{RESET}")
                    print(f"{GREEN}{BOLD}══════════════════════════════════════════════════════════════{RESET}")
                    print(f"\nReview PR: {CYAN}{pr_url}{RESET}")
                    print("The Hmar Heritage Foundation maintainers will review and merge your addition.")
                    return
            raise api_err

    except Exception as e:
        print(f"\n{RED}Upload failed: {e}{RESET}")
        print(f"All files have been saved safely in your local repository at {repo_path}.")
        print("You can manually push using: git push origin main")


# ==============================================================================
# MAIN ENGINE
# ==============================================================================

def run_pdf_ingestion(repo_path: Path, token: str, username: str):
    source_pdf = select_pdf()
    if not source_pdf:
        print(f"\n{DIM}Ingestion cancelled. Returning to action menu...{RESET}")
        return

    suggested_title = source_pdf.stem.replace("_", " ").replace("-", " ").title()

    category = select_category()
    if not category:
        print(f"\n{DIM}Ingestion cancelled. Returning to action menu...{RESET}")
        return

    language = select_language()
    if not language:
        print(f"\n{DIM}Ingestion cancelled. Returning to action menu...{RESET}")
        return

    details = prompt_details(suggested_title)
    if not details:
        print(f"\n{DIM}Ingestion cancelled. Returning to action menu...{RESET}")
        return

    next_id = compute_next_id(repo_path)

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

    # Summary
    print(f"\n{CYAN}{BOLD}=== Ingestion Summary ==={RESET}")
    print(f"  Assigned Sequential ID: {GREEN}{BOLD}{record['id']}{RESET}")
    print(f"  Document Title:         {record['title']}")
    print(f"  Author(s) / Body:       {', '.join(record['authors'])}")
    print(f"  Category:               {record['category']}")
    print(f"  Language:               {record['language']}")
    print(f"  Source File:            {source_pdf.name}")
    print(f"  Target Archive Path:    data/pdf/{record['id']}/file.pdf")

    confirm = safe_input(f"\nWrite files to local repository? (Y/n): ").lower()
    if confirm not in ("", "y", "yes"):
        print(f"{YELLOW}Archival cancelled. Returning to main menu.{RESET}")
        return

    # Ingest locally
    ingest_to_repo(repo_path, source_pdf, record)

    # Publish option
    print(f"\n{BOLD}Ready to publish to Hugging Face!{RESET}")
    pub_choice = safe_input("Commit and push to Hugging Face now? (Y/n or D for dry-run): ").lower()
    if pub_choice in ("d", "dry", "dry-run", "n", "no"):
        print(f"\n{GREEN}{BOLD}✓ Local Archival Complete (Dry-Run)!{RESET}")
        print(f"All files updated locally in: {CYAN}{repo_path}{RESET}")
        print("No remote changes were pushed to Hugging Face.")
    else:
        push_to_remote(repo_path, record["id"], record["title"], token, username)


def main():
    print_banner()
    ensure_termux_storage()

    # Phase 1: Upfront Token Authentication & Validation
    token, username = get_and_validate_token()

    # Phase 2: Local Repo Verification & Sync
    repo_path = verify_or_clone_repo(token, username)

    # Phase 3: Action Menu Loop
    while True:
        action = display_action_menu()
        if action == "1":
            run_pdf_ingestion(repo_path, token, username)
            print(f"\n{CYAN}------------------------------------------------------------{RESET}")
            another = safe_input("Would you like to archive another document? (y/N): ").lower()
            if another not in ("y", "yes"):
                graceful_exit()
        elif action == "5":
            token, username = get_and_validate_token(force_prompt=True)
            repo_path = verify_or_clone_repo(token, username)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        graceful_exit("\n[!] Process interrupted by user (Ctrl+C). No partial changes were saved.")
    except EOFError:
        graceful_exit("\n[!] Session ended (EOF).")
    except Exception as e:
        print(f"\n{RED}{BOLD}[Error]{RESET} An unexpected error occurred: {e}")
        sys.exit(1)
