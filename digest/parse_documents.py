# parse_documents.py
#
# Deliverable 1: recursively parse every PDF/DOCX/XLSX under data/raw/{dept}/
# into clean Markdown files under data/parsed/{dept}/, preserving tables and
# headings, logging progress, and skipping (not crashing on) failed files.

import time
from pathlib import Path
from docling.document_converter import DocumentConverter

# Project root is one level up from this script (digest/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PARSED_DIR = PROJECT_ROOT / "data" / "parsed"

DEPARTMENTS = ["hr", "legal", "finance", "it"]
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx"}


def find_source_files():
    """Recursively collect every supported file under data/raw/{dept}/."""
    files = []
    for dept in DEPARTMENTS:
        dept_raw_dir = RAW_DIR / dept
        if not dept_raw_dir.exists():
            print(f"[WARN] No raw folder found for department '{dept}' ({dept_raw_dir}) — skipping.")
            continue
        for path in dept_raw_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append((dept, path))
    return files


def parse_one_file(converter, dept, source_path):
    """Convert a single file to Markdown and write it to data/parsed/{dept}/."""
    output_dir = PARSED_DIR / dept
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (source_path.stem + ".md")

    result = converter.convert(str(source_path))
    markdown_text = result.document.export_to_markdown()

    output_path.write_text(markdown_text, encoding="utf-8")

    num_pages = None
    if hasattr(result.document, "pages") and result.document.pages:
        num_pages = len(result.document.pages)

    num_tables = 0
    if hasattr(result.document, "tables") and result.document.tables:
        num_tables = len(result.document.tables)

    return output_path, markdown_text, num_pages, num_tables


def quality_check(output_path, markdown_text):
    """Print word/char counts so obviously broken parses are easy to spot."""
    word_count = len(markdown_text.split())
    char_count = len(markdown_text)
    flag = ""
    if word_count < 10:
        flag = "  <-- WARNING: suspiciously short output, check this file manually"
    print(f"    Quality check: {word_count} words, {char_count} characters{flag}")


def main():
    print("Scanning data/raw/ for PDF, DOCX, and XLSX files...\n")
    files = find_source_files()

    if not files:
        print("No source files found. Add PDF/DOCX/XLSX files under data/raw/<department>/ and re-run.")
        return

    print(f"Found {len(files)} file(s) to process.\n")

    converter = DocumentConverter()

    succeeded = 0
    failed = 0
    start_time = time.time()

    for dept, source_path in files:
        rel_name = f"{dept}/{source_path.name}"
        print(f"Parsing {rel_name}...")

        try:
            output_path, markdown_text, num_pages, num_tables = parse_one_file(
                converter, dept, source_path
            )
            page_info = f"{num_pages} pages, " if num_pages is not None else ""
            print(f"  done ({page_info}{num_tables} table(s) detected) -> {output_path.relative_to(PROJECT_ROOT)}")
            quality_check(output_path, markdown_text)
            succeeded += 1

        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            print(f"  Skipping this file and continuing with the rest.")
            failed += 1

        print()  # blank line between files for readability

    elapsed = time.time() - start_time
    print("=" * 50)
    print(f"Done. {succeeded} succeeded, {failed} failed, out of {len(files)} total.")
    print(f"Elapsed time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()


