"""Slow, resumable downloader for the ReviserBac exam archive (personal study use).

    python scripts/download_sujets.py --sections informatique --matieres francais --years 2019-2019 --limit 2   # pilot
    python scripts/download_sujets.py --corriges                                                             # everything

What it does
  1. Reads each section's subject list and each subject's index page -> data/sujets_manifest.csv
  2. Downloads  files.reviserbac.tn/archives/bac/{year}/{session}/{section}/{matiere}.pdf   (+ "_c.pdf" corrections with --corriges)
     into  sujets/{section}/{matiere}/{year}_{session}.pdf

Good-citizen rules built in (there is deliberately NO option to switch them off):
  * reads robots.txt of every host it touches and stops if a URL is disallowed for this script
  * one request every --delay seconds (default 5, plus jitter), never in parallel
  * honest User-Agent, no cookies, no login, no attempt to pass a robot check
  * stops after 3 failures in a row or on HTTP 403/429/503 (the site is telling you to slow down)
  * resumable: files already downloaded are skipped
Uses only the Python standard library. Keep sujets/ out of Git (it is in .gitignore).
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

SITE = "https://www.reviserbac.tn"
FILES = "https://files.reviserbac.tn"
SECTIONS = ["mathematiques", "sciences-experimentales", "informatique", "economie-gestion", "technique", "lettre", "sport"]
UA = "bac-analytics-research/1.0 (personal study project; slow, obeys robots.txt)"
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "sujets_manifest.csv"
OUT = ROOT / "sujets"


class Stop(Exception):
    """Raised when we must stop politely (robots.txt, 403/429/503, repeated failures)."""


# ----------------------------------------------------------------------------- http
class Client:
    def __init__(self, delay: float):
        self.delay, self._last, self._robots = delay, 0.0, {}

    def _allowed(self, url: str) -> bool:
        host = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(host + "/robots.txt")
            try:
                rp.read()          # 404 -> allow all; 401/403 -> disallow all (stdlib behaviour)
            except Exception as e:  # noqa: BLE001 - cannot read robots.txt: be conservative
                raise Stop(f"cannot read {host}/robots.txt ({e}); not continuing") from e
            self._robots[host] = rp
        return self._robots[host].can_fetch(UA, url)

    def get(self, url: str) -> tuple[int, bytes]:
        if not self._allowed(url):
            raise Stop(f"robots.txt disallows {url} for this script. Stopping: ask the site owner for permission.")
        wait = self.delay + random.uniform(0, self.delay / 2) - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                self._last = time.time()
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            self._last = time.time()
            if e.code in (403, 429, 503):
                raise Stop(f"HTTP {e.code} from {url}: the site asks us to stop/slow down. Wait and retry later.") from e
            return e.code, b""
        except urllib.error.URLError as e:
            self._last = time.time()
            return 0, str(e).encode()


# ----------------------------------------------------------------------------- discovery
def file_urls(section: str, matiere: str, year: int, session: str) -> tuple[str, str]:
    base = f"{FILES}/archives/bac/{year}/{session}/{section}/{matiere}"
    return base + ".pdf", base + "_c.pdf"


def parse_matieres(html: str, section: str) -> list[str]:
    found = re.findall(rf'href="(?:{re.escape(SITE)})?/sujets/{re.escape(section)}/([a-z0-9\-]+)"', html)
    return list(dict.fromkeys(found))


def parse_papers(html: str, section: str, matiere: str) -> list[tuple[int, str]]:
    found = re.findall(rf'/sujets/{re.escape(section)}/{re.escape(matiere)}/(\d{{4}})-(principale|controle)', html)
    return sorted({(int(y), s) for y, s in found})


def discover(client: Client, sections: list[str], only: list[str] | None) -> list[dict]:
    rows = []
    for section in sections:
        code, body = client.get(f"{SITE}/sujets/{section}/francais")      # any subject page lists the section's other subjects
        if code != 200:
            print(f"  ! section {section}: seed page returned {code}, skipped")
            continue
        matieres = ["francais"] + [m for m in parse_matieres(body.decode("utf-8", "ignore"), section) if m != "francais"]
        for matiere in matieres:
            if only and matiere not in only:
                continue
            code, body = client.get(f"{SITE}/sujets/{section}/{matiere}")
            if code != 200:
                print(f"  ! {section}/{matiere}: index returned {code}, skipped")
                continue
            for year, session in parse_papers(body.decode("utf-8", "ignore"), section, matiere):
                s_url, c_url = file_urls(section, matiere, year, session)
                rows.append(dict(section=section, matiere=matiere, year=year, session=session, sujet_url=s_url, corrige_url=c_url))
            print(f"  {section}/{matiere}: {sum(1 for r in rows if r['section'] == section and r['matiere'] == matiere)} papers")
    return rows


# ----------------------------------------------------------------------------- download
def save_pdf(client: Client, url: str, dest: Path, log: list[dict], kind: str, row: dict) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        return True
    code, body = client.get(url)
    ok = code == 200 and body[:4] == b"%PDF"
    if ok:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
    log.append(dict(kind=kind, section=row["section"], matiere=row["matiere"], year=row["year"], session=row["session"],
                    url=url, http=code, ok=int(ok)))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sections", nargs="*", default=SECTIONS)
    ap.add_argument("--matieres", nargs="*", help="only these subject slugs, e.g. francais mathematiques")
    ap.add_argument("--years", default="2009-2026", help="e.g. 2015-2026")
    ap.add_argument("--corriges", action="store_true", help="also download the correction PDFs (_c.pdf)")
    ap.add_argument("--delay", type=float, default=5.0, help="seconds between requests (minimum 2)")
    ap.add_argument("--limit", type=int, help="stop after N papers (use 2-5 for a first test)")
    ap.add_argument("--refresh", action="store_true", help="rebuild the manifest even if it exists")
    a = ap.parse_args()
    y0, y1 = (int(x) for x in a.years.split("-"))
    client = Client(max(2.0, a.delay))
    try:
        if MANIFEST.exists() and not a.refresh:
            rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8-sig")))
            print(f"manifest: {len(rows)} papers (use --refresh to rebuild)")
        else:
            print("building manifest from the site's index pages...")
            rows = discover(client, a.sections, a.matieres)
            MANIFEST.parent.mkdir(exist_ok=True)
            with MANIFEST.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=["section", "matiere", "year", "session", "sujet_url", "corrige_url"])
                w.writeheader()
                w.writerows(rows)
        todo = [r for r in rows if y0 <= int(r["year"]) <= y1 and r["section"] in a.sections
                and (not a.matieres or r["matiere"] in a.matieres)]
        if a.limit:
            todo = todo[: a.limit]
        print(f"{len(todo)} papers to fetch, ~{len(todo) * (2 if a.corriges else 1) * (a.delay + a.delay / 4) / 60:.0f} min")
        log, fails = [], 0
        for i, r in enumerate(todo, 1):
            stem = OUT / r["section"] / r["matiere"] / f"{r['year']}_{r['session']}"
            ok = save_pdf(client, r["sujet_url"], stem.with_suffix(".pdf"), log, "sujet", r)
            fails = 0 if ok else fails + 1
            if a.corriges:
                save_pdf(client, r["corrige_url"], stem.with_name(stem.name + "_c.pdf"), log, "corrige", r)  # 404 = "sujet seul": normal
            print(f"[{i}/{len(todo)}] {r['section']}/{r['matiere']} {r['year']} {r['session']}: {'ok' if ok else 'FAILED'}")
            if fails >= 3:
                raise Stop("3 sujet downloads failed in a row; check the address pattern or the site, then retry.")
    except Stop as e:
        print(f"\nSTOPPED: {e}")
        return 2
    finally:
        if "log" in locals() and log:
            p = ROOT / "data" / "download_log.csv"
            new = not p.exists()
            with p.open("a", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(log[0]))
                if new:
                    w.writeheader()
                w.writerows(log)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
