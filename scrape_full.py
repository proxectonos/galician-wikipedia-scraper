#!/usr/bin/env python3
"""
Full scraper for Galician Wikipedia.

Reads all non-redirect main-namespace titles from gl.wikipedia.org and writes raw JSONL chunks.
Environment variables:
- WIKI_TMP_RAW: output directory for raw chunks
- WIKI_TITLES_CACHE: JSON cache with all titles
- WIKI_TEST_LIMIT: optional integer limit for tests; 0/unset means no limit
"""

import json
import os
import re
import signal
import time
from pathlib import Path
from typing import Optional

import requests
from tqdm import tqdm
import wikipediaapi

API_URL = "https://gl.wikipedia.org/w/api.php"
USER_AGENT = os.environ.get(
    "WIKI_USER_AGENT",
    "GalicianWikipediaScraper/1.0 (contact: set WIKI_USER_AGENT)",
)
OUT_DIR = Path(os.environ["WIKI_TMP_RAW"])
TITLES_CACHE = Path(os.environ["WIKI_TITLES_CACHE"])
CHUNK_SIZE = int(os.environ.get("WIKI_CHUNK_SIZE", "10000"))
DELAY = float(os.environ.get("WIKI_DELAY", "2.0"))
RETRIES = int(os.environ.get("WIKI_RETRIES", "3"))
FETCH_TIMEOUT = int(os.environ.get("WIKI_FETCH_TIMEOUT", "30"))

OUT_DIR.mkdir(parents=True, exist_ok=True)
TITLES_CACHE.parent.mkdir(parents=True, exist_ok=True)
wiki = wikipediaapi.Wikipedia(language="gl", user_agent=USER_AGENT)


class FetchTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise FetchTimeout()


def clean_text(text: str) -> str:
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_punctuation(text: str) -> str:
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:])([^\s])", r"\1 \2", text)
    text = re.sub(r"(\d)[ ]+(\d)", r"\1\2", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_namespace_filter() -> re.Pattern:
    params = {
        "action": "query",
        "meta": "siteinfo",
        "siprop": "namespaces|namespacealiases",
        "format": "json",
        "formatversion": "2",
    }
    r = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    data = r.json()

    namespaces_raw = data.get("query", {}).get("namespaces", {})
    aliases_raw = data.get("query", {}).get("namespacealiases", [])

    if isinstance(namespaces_raw, dict):
        namespaces = [v.get("name", "") for k, v in namespaces_raw.items() if int(k) != 0]
    else:
        namespaces = [ns.get("name", "") for ns in namespaces_raw if ns.get("id") != 0]

    alias_names = [a.get("alias", "") for a in aliases_raw]
    skip_prefixes = sorted(set(x for x in namespaces + alias_names if x))
    if not skip_prefixes:
        return re.compile(r"a^", re.IGNORECASE)
    print(f"🧩 Loaded {len(skip_prefixes)} non-article namespace prefixes.")
    return re.compile(rf"^(?:{'|'.join(map(re.escape, skip_prefixes))}):", re.IGNORECASE)


EXCLUDE_SECTIONS = {"Notas", "Referencias", "Bibliografía", "Ligazóns externas"}
RELATED_SECTION = "Véxase tamén"


def extract_sections(page, level: int = 0):
    text_parts = []
    related_articles = []

    for section in page.sections:
        title_clean = section.title.strip()
        if title_clean in EXCLUDE_SECTIONS:
            continue

        if title_clean == RELATED_SECTION:
            lines = [
                re.sub(r"^[•*\-\s]+", "", line.strip())
                for line in section.text.splitlines()
                if line.strip()
            ]
            related_mode = False
            for line in lines:
                if re.search(r"\bOutros artigos\b", line, flags=re.IGNORECASE):
                    related_mode = True
                    continue
                if related_mode:
                    related_articles.append(line)

            for sub in section.sections:
                if "Outros artigos" in sub.title:
                    sub_lines = [
                        re.sub(r"^[•*\-\s]+", "", l.strip())
                        for l in sub.text.splitlines()
                        if l.strip()
                    ]
                    related_articles.extend(sub_lines)

            related_articles = list(dict.fromkeys(a for a in related_articles if a))
            continue

        raw_text = clean_text(section.text or "").strip()
        subsections, sub_related = extract_sections(section, level + 1)
        related_articles.extend(sub_related)

        if not raw_text and not subsections:
            continue

        # Keep informative section boundaries, but without MediaWiki == markers.
        text_parts.append(title_clean)
        if raw_text:
            text_parts.append(raw_text)
        text_parts.extend(subsections)

    return text_parts, list(dict.fromkeys(a for a in related_articles if a))


def fetch_article(title: str) -> Optional[dict]:
    for attempt in range(1, RETRIES + 1):
        try:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(FETCH_TIMEOUT)

            page = wiki.page(title)
            if not page.exists() or getattr(page, "namespace", 0) != 0:
                signal.alarm(0)
                return None

            parts = []
            if page.summary:
                parts.append(clean_text(page.summary))

            sections, related_articles = extract_sections(page)
            parts.extend(sections)

            text = normalize_punctuation("\n".join(p for p in parts if p.strip()))
            signal.alarm(0)

            if not text:
                return None

            return {
                "pageid": int(page.pageid),
                "title": page.title,
                "text": text,
                "related_articles": related_articles,
                "num_tokens": len(text.split()),
                "url": page.fullurl,
            }

        except FetchTimeout:
            print(f"⏱️ Timeout fetching {title!r} ({attempt}/{RETRIES})")
        except Exception as e:
            print(f"⚠️ Error fetching {title!r} ({attempt}/{RETRIES}): {e}")
        finally:
            signal.alarm(0)

        time.sleep(5 * attempt)

    print(f"❌ Giving up on {title!r}")
    return None


def get_all_titles(limit: Optional[int] = None) -> list[str]:
    skip_re = build_namespace_filter()

    titles = None

    # Only use the title cache as a full-title cache.
    # If we are in test mode with a limit, it is still okay to load a full cache
    # if it exists, but we must not create a partial cache later.
    if TITLES_CACHE.exists():
        try:
            cached = json.loads(TITLES_CACHE.read_text(encoding="utf-8"))
            if isinstance(cached, list) and cached and all(isinstance(x, str) for x in cached):
                titles = cached
                print(f"📂 Loaded {len(titles)} cached titles from {TITLES_CACHE}")
            else:
                print("⚠️ Title cache is invalid; rebuilding.")
        except Exception as e:
            print(f"⚠️ Could not read title cache ({e}); rebuilding.")

    if titles is None:
        titles = []
        apcontinue = None
        batch = 0

        while True:
            params = {
                "action": "query",
                "list": "allpages",
                "apfilterredir": "nonredirects",
                "aplimit": "500",
                "apnamespace": 0,
                "format": "json",
            }
            if apcontinue:
                params["apcontinue"] = apcontinue

            for attempt in range(1, 6):
                r = requests.get(
                    API_URL,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=30,
                )

                if r.status_code == 429:
                    retry_after = r.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_time = int(retry_after)
                    else:
                        sleep_time = 30 * attempt

                    print(
                        f"⏳ Rate limited while fetching titles "
                        f"(HTTP 429, attempt {attempt}/5). "
                        f"Sleeping {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                    continue

                r.raise_for_status()
                data = r.json()
                break
            else:
                raise RuntimeError("Too many HTTP 429 responses while fetching title list.")

            for p in data.get("query", {}).get("allpages", []):
                title = p["title"]
                if skip_re.match(title):
                    continue

                titles.append(title)

                # IMPORTANT:
                # In test mode, stop fetching titles as soon as we reach the limit.
                # Otherwise the script fetches the entire Galician Wikipedia title list
                # before applying titles[:limit], which makes the test look stuck.
                if limit is not None and len(titles) >= limit:
                    print(f"🔢 Reached runtime limit while fetching titles: {limit}")
                    print("🧪 Test limit active — not saving partial title cache.")
                    return titles[:limit]

            batch += 1
            if batch % 10 == 0:
                print(f"Fetched {len(titles)} titles so far...")

            if "continue" not in data:
                break

            apcontinue = data["continue"]["apcontinue"]
            time.sleep(1.5)

        # Only save the title cache if we fetched the complete title list.
        if limit is None:
            TITLES_CACHE.write_text(
                json.dumps(titles, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"✅ Cached {len(titles)} titles to {TITLES_CACHE}")
        else:
            print("🧪 Test limit active — not saving partial title cache.")

    if limit is not None:
        print(f"🔢 Applying runtime limit: {limit}")
        titles = titles[:limit]

    return titles


def save_chunk(chunk_data: list[dict], chunk_index: int) -> None:
    path = OUT_DIR / f"glwiki_{chunk_index:03d}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for entry in chunk_data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"💾 Saved {len(chunk_data)} articles → {path}")


def main() -> None:
    limit = int(os.environ.get("WIKI_TEST_LIMIT", "0")) or None
    titles = get_all_titles(limit=limit)
    print(f"🔹 Total titles to process: {len(titles)}")

    chunk = []
    chunk_index = 1
    processed = 0

    for title in tqdm(titles, desc="Scraping Galician Wikipedia"):
        article = fetch_article(title)
        if not article:
            continue
        article["id"] = processed + 1
        chunk.append(article)
        processed += 1
        if len(chunk) >= CHUNK_SIZE:
            save_chunk(chunk, chunk_index)
            chunk = []
            chunk_index += 1
        time.sleep(DELAY)

    if chunk:
        save_chunk(chunk, chunk_index)

    print(f"\n✅ Full scrape done. Total processed: {processed} articles.")


if __name__ == "__main__":
    main()
