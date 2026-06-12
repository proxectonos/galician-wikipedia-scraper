#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${WIKI_ROOT:-${SCRIPT_DIR}/data}"
YEAR="$(date +%Y)"
MONTH="$(date +%m)"
LIMIT="${WIKI_TEST_LIMIT:-0}"
KEEP_TMP=0

usage() {
  cat <<USAGE
Usage: bash run_full.sh [options]

Build a full Galician Wikipedia JSONL corpus.

Options:
  --root PATH        Base output directory. Default: ./data inside this repository
  --year YYYY        Override output year. Default: current year
  --month MM         Override output month. Default: current month
  --limit N          Limit number of articles, useful for tests. Default: 0 (no limit)
  --keep-tmp         Keep temporary raw JSONL chunks after a successful run
  -h, --help         Show this help message

Examples:
  bash run_full.sh --limit 50
  bash run_full.sh --root /path/to/output
  WIKI_ROOT=/path/to/output bash run_full.sh
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="${2:?Missing value for --root}"
      shift 2
      ;;
    --year)
      YEAR="${2:?Missing value for --year}"
      shift 2
      ;;
    --month)
      MONTH="${2:?Missing value for --month}"
      shift 2
      ;;
    --limit)
      LIMIT="${2:?Missing value for --limit}"
      shift 2
      ;;
    --keep-tmp)
      KEEP_TMP=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! "$YEAR" =~ ^[0-9]{4}$ ]]; then
  echo "Invalid --year value: $YEAR" >&2
  exit 1
fi

if [[ ! "$MONTH" =~ ^[0-9]{1,2}$ ]]; then
  echo "Invalid --month value: $MONTH" >&2
  exit 1
fi
MONTH="$(printf '%02d' "$MONTH")"

DATE_TAG="${YEAR}-${MONTH}"
TITLES_CACHE="${ROOT}/dump_${YEAR}/titles_glwiki.json"
BASE="${ROOT}/dump_${YEAR}/${MONTH}"
TMP_RAW="${BASE}/.tmp_jsonl_full"
CLEAN="${BASE}/jsonl_clean"
FINAL="${BASE}/wikipedia_gl_${DATE_TAG}_dump.jsonl"
LAST_RUN_FILE="${ROOT}/last_successful_run.txt"
LOG_DIR="${ROOT}/logs"

mkdir -p "$TMP_RAW" "$CLEAN" "$(dirname "$TITLES_CACHE")" "$BASE" "$LOG_DIR"
LOG="${LOG_DIR}/full_${DATE_TAG}_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

export WIKI_TITLES_CACHE="$TITLES_CACHE"
export WIKI_TMP_RAW="$TMP_RAW"
export WIKI_CLEAN="$CLEAN"
export WIKI_FINAL="$FINAL"
export WIKI_TEST_LIMIT="$LIMIT"

printf '📅 FULL Galician Wikipedia dump: %s\n' "$DATE_TAG"
printf '📁 Root dir: %s\n' "$ROOT"
printf '📁 Base dir: %s\n' "$BASE"
printf '🗂️  Titles cache: %s\n' "$TITLES_CACHE"
printf '📄 Final file: %s\n' "$FINAL"
printf '🔢 Limit: %s\n' "$LIMIT"
printf '🕒 Started at: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

printf '🧲 Scraping full corpus...\n'
python "$SCRIPT_DIR/scrape_full.py"

printf '🧹 Cleaning full corpus...\n'
python "$SCRIPT_DIR/clean_full.py"

printf '🧵 Concatenating chunks...\n'
python "$SCRIPT_DIR/concat.py"

if [[ ! -s "$FINAL" ]]; then
  echo "❌ Final file missing or empty — aborting cleanup" >&2
  exit 1
fi

if [[ "$KEEP_TMP" -eq 0 ]]; then
  echo "🧽 Removing temporary folders..."
  rm -rf "$TMP_RAW" "$CLEAN"
else
  echo "🧪 Keeping temporary folders because --keep-tmp was used:"
  echo "   Raw chunks:     $TMP_RAW"
  echo "   Cleaned chunks: $CLEAN"
fi

date -u +%Y-%m-%dT%H:%M:%SZ > "$LAST_RUN_FILE"

printf '✅ FULL dump completed\n'
printf '📄 Output: %s\n' "$FINAL"
printf '📊 Articles: %s\n' "$(wc -l < "$FINAL")"
printf '🕒 Finished at: %s\n' "$(cat "$LAST_RUN_FILE")"
