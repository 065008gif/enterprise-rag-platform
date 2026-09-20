# chunk_documents.py
#
# Deliverable 2: turn parsed Markdown files into metadata-tagged chunks
# ready for embedding, using LlamaIndex's MarkdownNodeParser (primary split)
# + SentenceSplitter (secondary split, for oversized sections).

import pickle
import random
import re
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.core.schema import TextNode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARSED_DIR = PROJECT_ROOT / "data" / "parsed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_CHUNKS_PATH = PROJECT_ROOT / "data" / "chunks.pkl"

DEPARTMENTS = ["hr", "legal", "finance", "it"]
MAX_CHUNK_TOKENS = 512
SECONDARY_CHUNK_OVERLAP = 50

DOC_CODE_PATTERN = re.compile(r"(?:Document Code|SOP Code):\s*(\S.*?)\s*(?:\||\n|$)", re.IGNORECASE)
EFFECTIVE_DATE_PATTERN = re.compile(r"Effective Date:\s*(\S.*?)\s*(?:\||\n|$)", re.IGNORECASE)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def find_original_extension(department, stem):
    """Look in data/raw/{dept}/ for a file with this stem, to recover its
    original extension (.pdf / .docx / .xlsx) — needed for doc_type logic."""
    raw_dept_dir = RAW_DIR / department
    if not raw_dept_dir.exists():
        return None
    for ext in (".xlsx", ".docx", ".pdf"):
        candidate = raw_dept_dir / (stem + ext)
        if candidate.exists():
            return ext
    return None


def infer_doc_type(filename, original_extension):
    """policy / sop / data_sheet, per the rules in the spec."""
    if "sop" in filename.lower():
        return "sop"
    if original_extension == ".xlsx":
        return "data_sheet"
    return "policy"


def extract_field(pattern, text):
    match = pattern.search(text[:1000])  # only look near the top of the doc
    return match.group(1).strip() if match else ""


def build_heading_map(text):
    """Return a list of (char_offset, heading_text) for every heading in
    the document, in order — used to figure out which heading a chunk
    falls under."""
    return [(m.start(), m.group(2).strip()) for m in HEADING_PATTERN.finditer(text)]


def find_section_heading(chunk_text, full_text, heading_map, search_from_offset):
    """Find the heading that applies to this chunk: the closest heading at
    or before this chunk's position in the original document."""
    offset = full_text.find(chunk_text, search_from_offset)
    if offset == -1:
        offset = full_text.find(chunk_text)  # fallback: search from start
    if offset == -1:
        return "", search_from_offset

    applicable_heading = ""
    for heading_offset, heading_text in heading_map:
        if heading_offset <= offset:
            applicable_heading = heading_text
        else:
            break
    return applicable_heading, offset


def chunk_one_file(md_path, department):
    text = md_path.read_text(encoding="utf-8")
    stem = md_path.stem
    source_filename_guess = stem  # base name without extension

    original_extension = find_original_extension(department, stem)
    source_file = stem + (original_extension or "")

    doc_type = infer_doc_type(md_path.name, original_extension)
    doc_code = extract_field(DOC_CODE_PATTERN, text)
    effective_date = extract_field(EFFECTIVE_DATE_PATTERN, text)
    heading_map = build_heading_map(text)

    base_metadata = {
        "department": department,
        "source_file": source_file,
        "doc_type": doc_type,
        "doc_code": doc_code,
        "effective_date": effective_date,
    }

    document = Document(text=text, metadata=dict(base_metadata))

    md_parser = MarkdownNodeParser()
    primary_nodes = md_parser.get_nodes_from_documents([document])

    sentence_splitter = SentenceSplitter(
        chunk_size=MAX_CHUNK_TOKENS,
        chunk_overlap=SECONDARY_CHUNK_OVERLAP,
    )

    final_nodes = []
    search_offset = 0

    for node in primary_nodes:
        node_text = node.get_content()
        section_heading, found_offset = find_section_heading(
            node_text, text, heading_map, search_offset
        )
        if found_offset != -1:
            search_offset = found_offset  # keep search moving forward

        # crude token estimate: ~1.3 tokens per word is a safe overestimate
        estimated_tokens = int(len(node_text.split()) * 1.3)

        if estimated_tokens <= MAX_CHUNK_TOKENS:
            node.metadata.update(base_metadata)
            node.metadata["section_heading"] = section_heading
            final_nodes.append(node)
        else:
            # Secondary split: this section is too long, break it further
            sub_document = Document(text=node_text, metadata=dict(base_metadata))
            sub_nodes = sentence_splitter.get_nodes_from_documents([sub_document])
            for sub_node in sub_nodes:
                sub_node.metadata.update(base_metadata)
                sub_node.metadata["section_heading"] = section_heading
                final_nodes.append(sub_node)

    return final_nodes


def main():
    print("Scanning data/parsed/ for Markdown files to chunk...\n")

    all_chunks = []
    chunks_per_department = {dept: 0 for dept in DEPARTMENTS}

    for department in DEPARTMENTS:
        dept_parsed_dir = PARSED_DIR / department
        if not dept_parsed_dir.exists():
            print(f"[WARN] No parsed folder found for department '{department}' — skipping.")
            continue

        md_files = sorted(dept_parsed_dir.glob("*.md"))
        if not md_files:
            continue

        for md_path in md_files:
            print(f"Chunking {department}/{md_path.name}...")
            try:
                chunks = chunk_one_file(md_path, department)
                all_chunks.extend(chunks)
                chunks_per_department[department] += len(chunks)
                print(f"  done ({len(chunks)} chunk(s) created)")
            except Exception as e:
                print(f"  FAILED: {type(e).__name__}: {e}")
                print(f"  Skipping this file and continuing.")

    if not all_chunks:
        print("\nNo chunks were created. Check that data/parsed/ has .md files (run parse_documents.py first).")
        return

    # Assign simple sequential IDs (stable content-hash IDs come in Deliverable 3)
    for i, node in enumerate(all_chunks):
        node.id_ = f"chunk_{i:05d}"

    OUTPUT_CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CHUNKS_PATH, "wb") as f:
        pickle.dump(all_chunks, f)

    total_words = sum(len(node.get_content().split()) for node in all_chunks)
    avg_words = total_words / len(all_chunks)

    print("\n" + "=" * 50)
    print(f"Total chunks created: {len(all_chunks)}")
    for dept in DEPARTMENTS:
        print(f"  {dept}: {chunks_per_department[dept]} chunk(s)")
    print(f"Average chunk size: {avg_words:.1f} words")
    print(f"Saved to: {OUTPUT_CHUNKS_PATH.relative_to(PROJECT_ROOT)}")

    print("\n--- Sample chunks (for manual review) ---")
    sample_size = min(5, len(all_chunks))
    for node in random.sample(all_chunks, sample_size):
        print("\n" + "-" * 40)
        print(f"Metadata: {node.metadata}")
        print(f"Content preview: {node.get_content()[:300]!r}")


if __name__ == "__main__":
    main()

