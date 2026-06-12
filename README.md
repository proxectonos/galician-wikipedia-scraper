# galician-wikipedia-scraper
Pipeline for scraping, cleaning and exporting the Galician Wikipedia as a structured JSONL corpus.

## Overview

The pipeline performs three main steps:

1. Scrape article titles and article contents from the Galician Wikipedia.
2. Clean and normalize the extracted text.
3. Concatenate the cleaned chunks into a final JSONL corpus.

Execution chain:

```text
run_full.sh
  ├── scrape_full.py
  ├── clean_full.py
  └── concat.py
```

## Repository structure

```text
.
├── README.md
├── requirements.txt
├── run_full.sh
├── scrape_full.py
├── clean_full.py
└── concat.py
```

## Installation

Create and activate a Python environment, then install the required dependencies:

```bash
pip install -r requirements.txt
```

The expected `requirements.txt` is:

```text
requests>=2.31.0
tqdm>=4.66.0
wikipedia-api>=0.6.0
```

## User agent

Wikipedia requests should use a clear user agent. Set it with the `WIKI_USER_AGENT` environment variable:

```bash
export WIKI_USER_AGENT="GalicianWikipediaCorpusBot/1.0 (contact: your-email@example.org)"
```

For public use, replace the contact email with an appropriate project or institutional contact address.

## Quick test

Run a small test with 50 articles:

```bash
WIKI_USER_AGENT="GalicianWikipediaCorpusBot/1.0 (contact: your-email@example.org)" \
bash run_full.sh --limit 50
```

By default, the output is written under:

```text
./data/dump_YYYY/MM/
```

For example:

```text
./data/dump_2026/06/wikipedia_gl_2026-06_dump.jsonl
```

## Full run

To run the full pipeline without a limit:

```bash
WIKI_USER_AGENT="GalicianWikipediaCorpusBot/1.0 (contact: your-email@example.org)" \
bash run_full.sh
```

This will scrape the full Galician Wikipedia and write the result under the default `./data` directory.

## Custom output directory

Use `--root` to choose a specific output directory:

```bash
WIKI_USER_AGENT="GalicianWikipediaCorpusBot/1.0 (contact: your-email@example.org)" \
bash run_full.sh --root /path/to/output
```

The final corpus will be written to:

```text
/path/to/output/dump_YYYY/MM/wikipedia_gl_YYYY-MM_dump.jsonl
```

For example:

```text
/path/to/output/dump_2026/06/wikipedia_gl_2026-06_dump.jsonl
```

## Command-line options

`run_full.sh` supports the following options:

```text
--root PATH       Base output directory. Default: ./data
--year YYYY       Use this year instead of the current year.
--month MM        Use this month instead of the current month.
--limit N         Limit the number of articles. Useful for testing.
                  A value of 0 means no limit.
--keep-tmp        Keep temporary raw and cleaned chunk folders.
-h, --help        Show the help message.
```

Examples:

```bash
# Small test in the default ./data directory
bash run_full.sh --limit 50

# Small test in a custom directory
bash run_full.sh --root ./data_test --limit 50

# Full run in a custom directory
bash run_full.sh --root /path/to/output

# Full run explicitly setting no limit
bash run_full.sh --root /path/to/output --limit 0

# Keep intermediate files for debugging
bash run_full.sh --limit 50 --keep-tmp
```

## Output format

The final corpus is written as JSONL, with one article per line.

Each entry follows this structure:

```json
{
  "pageid": 12345,
  "id": 1,
  "title": "Example title",
  "text": "Cleaned article text...",
  "related_articles": [],
  "num_tokens": 123,
  "url": "https://gl.wikipedia.org/wiki/Example"
}
```

Field description:

- `pageid`: original Wikipedia page identifier.
- `id`: sequential corpus identifier assigned during cleaning.
- `title`: article title.
- `text`: cleaned article text.
- `related_articles`: related article titles extracted when available.
- `num_tokens`: whitespace-based token count.
- `url`: original Wikipedia article URL.

## Output directory structure

For a run with root directory `./data`, year `2026`, and month `06`, the structure is:

```text
data/
└── dump_2026/
    ├── titles_glwiki.json
    └── 06/
        ├── wikipedia_gl_2026-06_dump.jsonl
        └── full_YYYYMMDD_HHMMSS.log
```

Temporary folders are created during execution:

```text
.tmp_jsonl/
jsonl_clean/
```

By default, these temporary folders are deleted after a successful run. Use `--keep-tmp` to preserve them for debugging.

## Cleaning process

The cleaning step removes or normalizes:

- Wikipedia heading markers such as `== Section ==`.
- Common non-content sections such as references, bibliography and external links.
- Repeated whitespace.
- Spacing around punctuation.
- Empty entries.
- Invalid JSON lines in intermediate chunks.

The final corpus is reindexed with sequential `id` values.

## Title cache

The pipeline caches the Wikipedia title list in:

```text
dump_YYYY/titles_glwiki.json
```

When `--limit` is used, the partial title list is not saved as a full cache. This avoids accidentally reusing a small test title list in a later full run.

## Logs

Each run creates a log file inside the corresponding monthly output folder:

```text
dump_YYYY/MM/full_YYYYMMDD_HHMMSS.log
```

This log records the execution path, output files, progress messages and errors.

## Monthly execution with cron

The wrapper is date-aware: it automatically uses the current year and month unless `--year` or `--month` are provided.

To run the first full dump manually:

```bash
WIKI_USER_AGENT="GalicianWikipediaCorpusBot/1.0 (contact: your-email@example.org)" \
bash run_full.sh --root /path/to/output
```

To schedule future monthly runs, use an external scheduler such as `cron`.

Example cron entry to run the full pipeline on the first day of every month at 03:00:

```cron
0 3 1 * * cd /path/to/repository && WIKI_USER_AGENT="GalicianWikipediaCorpusBot/1.0 (contact: your-email@example.org)" bash run_full.sh --root /path/to/output >> /path/to/output/cron_wikipedia_full.log 2>&1
```

If the pipeline depends on a specific Python or Conda environment, it is recommended to create a small launcher script and call that script from cron.

Example launcher:

```bash
#!/bin/bash
set -euo pipefail

cd /path/to/repository

export WIKI_USER_AGENT="GalicianWikipediaCorpusBot/1.0 (contact: your-email@example.org)"

bash run_full.sh --root /path/to/output
```

Then the cron entry can be:

```cron
0 3 1 * * /path/to/repository/cron_full.sh >> /path/to/output/cron_wikipedia_full.log 2>&1
```

## License

The source code in this repository is released under the Apache License 2.0.

This license applies only to the code of the scraper and processing pipeline. It does not apply to the textual content extracted from Wikipedia.

## Data licensing

The generated corpus contains text extracted from the Galician Wikipedia. Wikipedia content is subject to its own licensing terms, primarily Creative Commons Attribution-ShareAlike (CC BY-SA) and, where applicable, the GNU Free Documentation License.

Users of the generated corpus are responsible for complying with the applicable Wikipedia licensing requirements, including attribution and share-alike obligations.

This repository provides the tools to build the corpus, but it does not claim ownership over the original Wikipedia content.


## Acknowledgements

This work is funded by the Ministerio para la Transformación Digital y de la Función Pública - Funded by EU – NextGenerationEU within the framework of the project Desarrollo de Modelos ALIA. Esta publicación del proyecto Desarrollo de Modelos ALIA está financiada por el Ministerio para la Transformación Digital y de la Función Pública y por el Plan de Recuperación, Transformación y Resiliencia – Financiado por la Unión Europea – NextGenerationEU.
