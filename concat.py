#!/usr/bin/env python3
"""Concatenate cleaned Galician Wikipedia JSONL chunks into one JSONL file."""

import json
import os
from pathlib import Path

from tqdm import tqdm

IN_DIR = Path(os.environ["WIKI_CLEAN"])
OUT_FILE = Path(os.environ["WIKI_FINAL"])
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    files = sorted(p for p in IN_DIR.iterdir() if p.suffix == ".jsonl")
    total = 0
    last_id = 0
    tmp_file = OUT_FILE.with_suffix(OUT_FILE.suffix + ".tmp")

    with tmp_file.open("w", encoding="utf-8") as fout:
        for path in tqdm(files, desc="Concatenating JSONL chunks"):
            with path.open("r", encoding="utf-8") as fin:
                for line in fin:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        print(f"⚠️ Invalid JSON line in {path.name}")
                        continue
                    current_id = int(obj.get("id", 0))
                    if current_id and current_id <= last_id:
                        print(f"⚠️ Non-increasing ID in {path.name}: {current_id} after {last_id}")
                    if current_id:
                        last_id = current_id
                    fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                    total += 1

    tmp_file.replace(OUT_FILE)
    print("\n✅ Concatenation complete")
    print(f"📁 Output: {OUT_FILE}")
    print(f"📄 Total articles: {total}")


if __name__ == "__main__":
    main()
