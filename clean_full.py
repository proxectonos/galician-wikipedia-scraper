#!/usr/bin/env python3
"""
Clean Galician Wikipedia raw JSONL chunks for the full corpus pipeline.

Input:
- WIKI_TMP_RAW: directory containing raw JSONL chunks produced by scrape_full.py

Output:
- WIKI_CLEAN: directory containing cleaned JSONL chunks

This script:
- removes unwanted Wikipedia section markers/headings,
- normalizes spacing and punctuation,
- cleans related_articles,
- removes empty entries,
- assigns sequential corpus IDs for the full dump.
"""

import json
import os
import re
from pathlib import Path

from tqdm import tqdm


SRC_DIR = Path(os.environ["WIKI_TMP_RAW"])
OUT_DIR = Path(os.environ["WIKI_CLEAN"])
OUT_DIR.mkdir(parents=True, exist_ok=True)

EXCLUDE_SECTIONS = {
    "notas",
    "referencias",
    "bibliografía",
    "ligazóns externas",
    "véxase tamén",
    "outros artigos",
    "outros artigos relacionados",
}


def normalize_punctuation(text: str) -> str:
    """Normalize spacing around punctuation while preserving paragraph breaks."""
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:])([^\s])", r"\1 \2", text)

    # Avoid spaces accidentally inserted inside numbers.
    text = re.sub(r"(\d)[ ]+(\d)", r"\1\2", text)

    # Collapse repeated spaces/tabs but do not destroy paragraph breaks.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def strip_headings_and_sections(text: str) -> str:
    """
    Remove Wikipedia heading markers and excluded section titles.

    Examples removed/normalized:
    - == Referencias ==
    - === Véxase tamén ===
    - stray '=' markers
    """
    text = text.replace("\r", "\n")

    # Convert headings like "== Historia ==" into "\nHistoria\n"
    # so that excluded headings can be detected cleanly afterwards.
    text = re.sub(
        r"\s*=+\s*([^=\n]{2,}?)\s*=+\s*",
        lambda m: f"\n{m.group(1).strip()}\n",
        text,
    )

    # Remove excluded section titles when they appear as standalone lines.
    for section in EXCLUDE_SECTIONS:
        pattern = rf"(?i)(^|\n)\s*{re.escape(section)}\s*:?\s*(?=\n|$)"
        text = re.sub(pattern, "\n", text)

    # Remove any remaining heading marker fragments.
    text = re.sub(r"=+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def clean_related_articles(related) -> list[str]:
    """Clean and deduplicate related article titles."""
    cleaned = []

    for item in related or []:
        if not isinstance(item, str):
            continue

        value = item.strip()
        value = re.sub(r"^=+\s*(.*?)\s*=+$", r"\1", value)
        value = value.strip()

        if not value:
            continue

        if any(section in value.lower() for section in EXCLUDE_SECTIONS):
            continue

        cleaned.append(value)

    return list(dict.fromkeys(cleaned))


def clean_text_block(text: str) -> str:
    """Apply the full text cleaning pipeline."""
    text = strip_headings_and_sections(text)
    text = normalize_punctuation(text)
    return text.strip()


def build_clean_entry(data: dict, cleaned_text: str, global_id: int) -> dict:
    """Build one cleaned full-corpus entry with sequential ID."""
    return {
        "pageid": int(data["pageid"]),
        "id": global_id,
        "title": data.get("title", ""),
        "text": cleaned_text,
        "related_articles": clean_related_articles(data.get("related_articles", [])),
        "num_tokens": len(cleaned_text.split()),
        "url": data.get("url", ""),
    }


def main() -> None:
    jsonl_files = sorted(path for path in SRC_DIR.iterdir() if path.suffix == ".jsonl")

    if not jsonl_files:
        raise RuntimeError(f"No raw JSONL files found in: {SRC_DIR}")

    global_id = 1
    total = 0

    for path in tqdm(jsonl_files, desc="Cleaning full corpus chunks"):
        cleaned_entries = []

        with path.open("r", encoding="utf-8") as fin:
            for line_no, line in enumerate(fin, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    print(f"⚠️ Skipping invalid JSON in {path.name}, line {line_no}")
                    continue

                text = data.get("text", "").strip()
                if not text:
                    continue

                cleaned_text = clean_text_block(text)
                if not cleaned_text:
                    continue

                if "pageid" not in data:
                    print(f"⚠️ Skipping entry without pageid in {path.name}, line {line_no}")
                    continue

                entry = build_clean_entry(data, cleaned_text, global_id)
                cleaned_entries.append(entry)

                global_id += 1
                total += 1

        out_path = OUT_DIR / path.name
        with out_path.open("w", encoding="utf-8") as fout:
            for entry in cleaned_entries:
                fout.write(json.dumps(entry, ensure_ascii=False) + "\n")

        print(f"💾 Cleaned {len(cleaned_entries)} entries → {out_path}")

    print(f"✅ Full cleaning done: {total} articles")
    print(f"🔢 Final sequential ID: {global_id - 1}")


if __name__ == "__main__":
    main()