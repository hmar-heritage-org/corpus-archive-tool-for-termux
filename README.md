# Corpus Archive Ingestion Tool for Termux

A mobile-first, terminal user interface (TUI) ingestion tool designed for Android (via Termux) and Linux/macOS environments to easily archive scanned books, documents, and linguistic literature into the Hugging Face dataset [**`hmar-heritage-org/corpus-archive`**](https://huggingface.co/datasets/hmar-heritage-org/corpus-archive).

---

## Key Features

- 📱 **Deep Android Storage Scanner**: Recursively scans internal storage (`/sdcard`, `~/storage/shared`) to detect PDFs in your `Downloads`, `Documents`, `WhatsApp Documents`, or any custom directory.
- 🕒 **Smart Sorting**: Files are automatically sorted by modification date so newly downloaded or scanned documents appear right at the top.
- 🔢 **Automated Sequential ID Assignment**: Reads the remote archive index to auto-assign the next sequential 4-digit ID (`0013`, `0014`, etc.).
- 🏗️ **3-Tier Representative Staging**: Automatically builds the exact 3-tier archival directory tree locally (`staging/data/pdf/{id}/file.pdf`, Tier 3 item metadata, Tier 2 format catalog, Tier 1 pointer index, viewer preview, and README table).
- ⚡ **Lightweight Atomic Upload**: Pushes only the newly added PDF and index modifications via an atomic commit directly to Hugging Face using your HF write token—no need to clone gigabytes of existing PDFs over mobile data.
- 💾 **Credential Caching**: Saves your Hugging Face token locally so you only have to enter it once.

---

## Quickstart Guide (Android Termux)

### Step 1: Install Termux
If you don't have Termux installed, download it from **[F-Droid](https://f-droid.org/packages/com.termux/)** (the Google Play Store version is deprecated).

### Step 2: Grant Storage & Clone the Tool
Open Termux and run:

```bash
# 1. Grant internal storage permission (tap 'Allow' on Android popup)
termux-setup-storage

# 2. Update packages and install Git & Python
pkg update -y && pkg install -y git python

# 3. Clone this repository and enter it
git clone https://github.com/hmar-heritage-org/corpus-archive-tool-for-termux.git
cd corpus-archive-tool-for-termux

# 4. Install dependencies
pip install -r requirements.txt
```

*(Alternatively, run `./setup.sh` inside the repo to automate steps 1, 2, and 4).*

### Step 3: Run the Ingestion Tool

```bash
python ingest.py
```

---

## Hugging Face Authentication Token

To push documents to `hmar-heritage-org/corpus-archive`, you need a **Hugging Face Access Token** with **Write** permission:

1. Sign in to your Hugging Face account at [huggingface.co](https://huggingface.co).
2. Go to **Settings** $\rightarrow$ **Access Tokens** (or direct link: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)).
3. Click **"Create new token"**.
4. Select **Type**: `Write`.
5. Name it (e.g. `Termux-Archive`) and copy the generated token (starts with `hf_...`).
6. Paste it into the prompt when running `python ingest.py`. The tool will remember it securely for subsequent runs.

---

## Step-by-Step Ingestion Workflow

When you run `python ingest.py`, it proceeds through 4 sequential phases:

### Phase 1: Hugging Face Authentication & Token Validation
- Asks for (or reads cached) Hugging Face Write Token (`hf_...`).
- Validates the token immediately against the Hugging Face API (`whoami`) and checks write role permission upfront.

### Phase 2: Local Repository Verification & Auto-Sync
- Checks if `corpus-archive` exists locally.
- If not found: Offers to clone `hmar-heritage-org/corpus-archive` (recommended) or use a custom path.
- Automatically executes `git pull --rebase` to ensure local files are 100% synchronized with the remote archive.

### Phase 3: Action Menu
- Displays the interactive menu:
  - `[1] Ingest & Archive a PDF Document` (Active)
  - `[2] Ingest Structured JSON Dataset` *(Coming in v1.3)*
  - `[3] Archive Research Repository (CSV/Git)` *(Coming in v1.3)*
  - `[4] Audit & Validate Archive Records` *(Coming in v1.3)*
  - `[5] Switch Hugging Face Account / Token`
  - `[Q] Exit`

### Phase 4: PDF Archival & Publishing
1. **Select PDF**: Choose from the detected PDFs discovered across internal storage (`/sdcard`, `~/storage/shared`, `Downloads/`, `Documents/`, etc.) or enter a custom path.
2. **Category**: Choose from 7 standardized classifications:
   - `Linguistics & Dictionaries`
   - `School Textbooks & MIL`
   - `History & Ethnography`
   - `Religion & Theology`
   - `Cultural Literature & Folklore`
   - `Glossary`
   - `Customary Laws & Governance`
3. **Primary Language**: Select content language (`hmr` for Hmar, `lus` for Mizo, `en` for English, etc.).
4. **Bibliographical Details**: Enter book/document title, author(s) or publishing body, publisher/society, publication year, and a brief description.
5. **Local 3-Tier Archival**: Automatically places `data/pdf/{id}/file.pdf` and updates Tier 3 metadata, Tier 2 format catalog, Tier 1 pointer index, viewer preview, and catalog table in README.
6. **Publish to Hugging Face**: Commits and pushes changes directly to the remote repository (or dry-run to keep changes local).

---

## License & Attribution

Maintained by the **Hmar Heritage Foundation** ([hmarheritage.pages.dev](https://hmarheritage.pages.dev)) under the Hmar Heritage Archival Project.
All archived works retain copyright with their respective original authors and publishing bodies.
