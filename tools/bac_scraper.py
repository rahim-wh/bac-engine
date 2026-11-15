#!/usr/bin/env python3
"""
Tunisian BAC archive scraper - bacweb.tn
Downloads every BAC exam PDF (sujets + corriges) from 1994 to 2026,
deduplicates identical files by SHA-256, and builds a JSON catalog.

Usage:
    python bac_scraper.py             # normal run (resumable)
    python bac_scraper.py --full      # try EVERY subject for EVERY section
    python bac_scraper.py --dry-run   # report which URLs exist without downloading bodies

Requirements: requests  (pip install requests)
"""

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
BASE_URL = "http://bacweb.tn/bac/{year}/{session}/{section}/{subject}.pdf"
ROOT = Path("BAC_TUNISIA_DATA_CORE")
FILES_DIR = ROOT / "exam_files"
CATALOG_PATH = ROOT / "_catalog" / "sections_mapping.json"
REPORT_PATH = ROOT / "_catalog" / "run_report.csv"

YEARS = range(1994, 2027)                      # 1994 .. 2026 inclusive
SESSIONS = ["principale", "controle"]

SECTIONS = ["math", "sciences_ex", "economie_gestion", "technique",
            "lettre", "sport", "informatique"]

ALL_SUBJECTS = ["math", "info", "technique", "physique", "svt", "gestion",
                "economie", "anglais", "arabe", "francais", "his_geo",
                "philo", "allemand", "espagnol", "russe", "chinois",
                "turque", "geo", "portugais", "histoire", "italien",
                "pensee", "musicale", "sport", "theatre", "algorithme", "bd"]

# Realistic section -> subjects mapping (edit freely; --full overrides it).
# NOT independently verified against bacweb.tn source; discovered coverage
# will be shown in run_report.csv after the first run.
SECTION_SUBJECTS = {
    "math":            ["math", "physique", "svt", "anglais", "arabe",
                        "francais", "philo", "pensee"],
    "sciences_ex":     ["math", "physique", "svt", "anglais", "arabe",
                        "francais", "philo", "pensee"],
    "economie_gestion":["economie", "gestion", "math", "anglais", "arabe",
                        "francais", "philo", "pensee"],
    "technique":       ["technique", "math", "physique", "anglais", "arabe",
                        "francais", "philo", "pensee"],
    "lettre":          ["arabe", "francais", "anglais", "philo", "pensee",
                        "histoire", "geo", "italien", "allemand", "espagnol",
                        "russe", "turque", "chinois", "portugais"],
    "sport":           ["sport", "arabe", "francais", "anglais", "philo", "pensee"],
    "informatique":    ["algorithme", "bd", "math", "physique", "anglais",
                        "arabe", "francais", "philo", "pensee"],
}

REQUEST_DELAY = 1.0        # seconds between requests (politeness + flaky server)
TIMEOUT = 30               # seconds per request
MAX_RETRIES = 3
USER_AGENT = "Mozilla/5.0 (BAC-archive-student-research)"

# ----------------------------------------------------------------------------
# Core helpers
# ----------------------------------------------------------------------------
session = requests.Session()
session.headers["User-Agent"] = USER_AGENT

_report_rows = []          # (url, status, size, sha256_or_empty)
_hash_index = {}           # sha256 -> relative file path (built at startup)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_hash_index():
    """Scan existing files so reruns never re-download (resume support)."""
    if not FILES_DIR.exists():
        return
    for p in FILES_DIR.rglob("*.pdf"):
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        _hash_index[h] = p


def fetch(url):
    """GET with retries/backoff. Returns (status_code, bytes) or (None, b'')."""
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return 200, r.content
            if r.status_code == 404:
                return 404, b""
            # 5xx / other: retry
        except requests.RequestException as e:
            log(f"  network error ({e.__class__.__name__}), retry {attempt}/{MAX_RETRIES}")
        time.sleep(delay)
        delay *= 2
    return None, b""


def is_pdf(content):
    return content[:5] == b"%PDF-"


def store_pdf(year, sess, subject, is_correction, content):
    """Deduplicate by hash; save once; return (relative_path, sha256)."""
    sha = hashlib.sha256(content).hexdigest()
    if sha in _hash_index:
        return _hash_index[sha], sha  # already on disk from another section/year
    suffix = "_c" if is_correction else ""
    family = FILES_DIR / str(year) / sess / subject
    family.mkdir(parents=True, exist_ok=True)
    rel = family / f"{year}_{sess}_{subject}{suffix}_{sha[:12]}.pdf"
    rel.write_bytes(content)
    _hash_index[sha] = rel
    return rel, sha


def probe(url, dry_run):
    """Handle one URL: fetch, validate PDF, store, record report row."""
    status, content = fetch(url)

    if status == 200 and content and not is_pdf(content):
        log(f"  not a PDF, skipped: {url}")
        _report_rows.append((url, "not-pdf", len(content), ""))
        return status

    if status == 200 and content and not dry_run:
        year, sess, subject, is_corr = url_to_meta(url)
        rel, sha = store_pdf(year, sess, subject, is_corr, content)
        log(f"  saved {rel.name} ({len(content)/1024:.0f} KB)")
        _report_rows.append((url, 200, len(content), sha))
    elif status == 404:
        _report_rows.append((url, 404, 0, ""))
    elif status == 200 and content and dry_run:
        _report_rows.append((url, 200, len(content), ""))
    else:
        log(f"  FAILED permanently: {url}")
        _report_rows.append((url, f"fail-{status}", 0, ""))

    return status


def url_to_meta(url):
    # http://bacweb.tn/bac/2024/principale/math/math.pdf  (or math_c.pdf)
    parts = url.split("/")
    year, sess, section = parts[-4], parts[-3], parts[-2]
    fname = parts[-1]                       # e.g. math_c.pdf
    is_corr = fname.endswith("_c.pdf")
    subject = fname[:-6] if is_corr else fname[:-4]
    return year, sess, subject, is_corr


# ----------------------------------------------------------------------------
# Main crawl
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="try every subject for every section (many 404s, slow)")
    ap.add_argument("--dry-run", action="store_true",
                    help="only check URL existence, do not save PDFs")
    args = ap.parse_args()

    if args.full:
        section_map = {s: ALL_SUBJECTS for s in SECTIONS}
    else:
        section_map = SECTION_SUBJECTS

    (ROOT / "_catalog").mkdir(parents=True, exist_ok=True)
    log("Building hash index of already-downloaded files (resume)...")
    load_hash_index()
    log(f"{len(_hash_index)} unique files already on disk.")

    catalog = {}
    if CATALOG_PATH.exists():
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    total = sum(len(section_map[s]) for s in SECTIONS) * len(SESSIONS) * len(YEARS) * 2
    done = 0

    for year in YEARS:
        for sess in SESSIONS:
            for section in SECTIONS:
                for subject in section_map[section]:
                    for is_corr in (False, True):
                        subj = subject + ("_c" if is_corr else "")
                        url = BASE_URL.format(year=year, session=sess,
                                              section=section, subject=subj)
                        done += 1
                        if done % 200 == 0:
                            log(f"progress {done}/{total} "
                                f"(year {year}, {sess}, {section}, {subject})")
                            save_outputs(catalog)

                        status = probe(url, args.dry_run)

                        if status == 200 and not args.dry_run:
                            entry = catalog.setdefault(section, {}) \
                                           .setdefault(sess, {}) \
                                           .setdefault(str(year), {})
                            fname = url.split("/")[-1]
                            if is_corr:
                                entry.setdefault(subject, {})["correction"] = fname
                            else:
                                entry.setdefault(subject, {})["sujet"] = fname

                        time.sleep(REQUEST_DELAY)

    save_outputs(catalog)
    ok = sum(1 for r in _report_rows if r[1] == 200)
    log(f"DONE. {ok} files fetched, {len(_report_rows)} URLs probed. "
        f"See {REPORT_PATH}")


def save_outputs(catalog):
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    with open(REPORT_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if f.tell() == 0:
            w.writerow(["url", "status", "size_bytes", "sha256"])
        w.writerows(_report_rows)
    _report_rows.clear()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted - progress saved, rerun to resume.", file=sys.stderr)
