#!/usr/bin/env python3
"""run_ra_population_par.py - parallel population extraction of the printed
RT. ASCEN. (1950.0) field, using the frozen RA instruments.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

RELATION TO THE DECLINATION RUN
    This is the RA counterpart of run_dec_population_par.py. It covers the
    SAME 918 pages of the fifteen B3-eligible runs, so that every declination
    row already produced has a right ascension candidate at the same page and
    row position.

    It writes to its own file. dec_rows.jsonl is never touched.

PAIRING RULE (inherited, binding)
    RA rows are paired to declination rows ONLY by (page, row_index). Never
    by value, never by cadence, never by nearest neighbour, never by inferred
    ordering. If a page yields a different row count between the two
    extractors, the affected rows become PAIRING_UNRESOLVED at join time
    rather than being matched approximately. This runner therefore records
    row_index and row_y for every row so the join can be checked, not
    assumed.

WHAT IT NEVER DOES
    It never reads channel, intensity, frequency, galactic or object fields.
    It never repairs an OCR value.
    It never modifies a frozen tool.

INTEGRITY PRECONDITIONS
    On start the SHA-256 of both frozen RA tools is recomputed and the run
    refuses to proceed on any mismatch.
    Per page, the retrieved bytes are checked against the folder SHA1SUM
    published by the origin, and a response that is too small to be a scan
    page is recorded as SOURCE_INPUT_INVALID rather than being passed to the
    extractor. The archive has been observed returning 114-byte HTTP 503
    bodies, which must never enter the data as unreadable rows.

OPEN PRECONDITION
    RA_EXTRACTOR_V1_FREEZE.json carries PENDING_OWNER_ENGINE_CONFIRMATION:
    the validated per-row values were measured under tesseract 5.3.4 and the
    owner's machine runs 5.4.0. Results from this run carry that precondition
    until tools/verify_ra_freeze.py has been run successfully.

USAGE
    venv_v2\\Scripts\\python.exe tools\\run_ra_population_par.py --out outputs\\ra_population
    Add --workers N to control parallelism, --limit N to stop early.
    Rerun the same command to resume from the checkpoint.
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ra_extractor_v1 as EX
import ra_validity_gate_v1 as GATE

BASE = "http://naapo.org/~rchilders/N50CH_data/scans/jpg"

EXPECTED_TOOL_SHA256 = {
    "ra_extractor_v1.py": "897f6a0b2b4f4b48a540d5427240e63f8ce94c954df2d8b097d984cad48aaa95",
    "ra_validity_gate_v1.py": "2c9140285ae687f5f5af41f76ad6bc0e02a836e1aabcc5720a72e0e325e19412",
}

MIN_PAGE_BYTES = 50000   # anything smaller cannot be a scan page

RUNS = [
    ("R-03", "012", 456, 552), ("R-04", "013", 2, 71),
    ("R-05", "013", 73, 83),   ("R-06", "013", 85, 87),
    ("R-07", "013", 89, 142),  ("R-08", "013", 144, 236),
    ("R-09", "013", 238, 411), ("R-10", "013", 413, 455),
    ("R-11", "013", 457, 467), ("R-12", "014", 2, 57),
    ("R-13", "014", 59, 146),  ("R-14", "014", 149, 219),
    ("R-15", "014", 221, 296), ("R-16", "014", 298, 365),
    ("R-17", "014", 367, 369),
]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def check_tools():
    here = os.path.dirname(os.path.abspath(__file__))
    problems = []
    for name, expected in EXPECTED_TOOL_SHA256.items():
        got = sha256_bytes(open(os.path.join(here, name), "rb").read())
        if got != expected:
            problems.append("%s sha256 %s != expected %s" % (name, got, expected))
        else:
            print("OK    %s sha256 matches the frozen record" % name)
    if problems:
        for p in problems:
            print("FAIL: " + p)
        print("A frozen tool has changed. Production stopped. Nothing written.")
        sys.exit(1)


def fetch_bytes(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception as e:
            last = e
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise last


def load_sha1(folder, cache_dir):
    path = os.path.join(cache_dir, "SHA1SUM.%s" % folder)
    if not os.path.exists(path):
        open(path, "wb").write(fetch_bytes("%s/folder.%s/SHA1SUM" % (BASE, folder)))
    table = {}
    for line in open(path):
        parts = line.split()
        if len(parts) == 2:
            table[parts[1]] = parts[0]
    return table


def page_list():
    pages = []
    for run, folder, a, b in RUNS:
        for n in range(a, b + 1):
            pages.append((run, folder, "%s-%03d" % (folder, n)))
    return pages


def work(task):
    run, folder, stem, published, img_dir = task
    url = "%s/folder.%s/%s.jpg" % (BASE, folder, stem)
    base = {"run": run, "folder": folder, "page": stem, "source_url": url,
            "transport": "PLAIN_HTTP_NO_TLS"}
    local = os.path.join(img_dir, stem + ".jpg")
    try:
        data = fetch_bytes(url)
    except Exception as e:
        return dict(base, ok=False, failure="DOWNLOAD", detail=str(e))

    if len(data) < MIN_PAGE_BYTES:
        return dict(base, ok=False, failure="SOURCE_INPUT_INVALID",
                    detail="response of %d bytes is too small to be a scan page"
                           % len(data))

    local_sha1 = hashlib.sha1(data).hexdigest()
    local_sha256 = sha256_bytes(data)
    if not published or published != local_sha1:
        return dict(base, ok=False, failure="INTEGRITY",
                    published_sha1=published, local_sha1=local_sha1)

    open(local, "wb").write(data)
    try:
        page_state, column, rows = EX.transcribe_page(local)
        if page_state is None:
            rows = GATE.gate_rows(rows)
    except Exception as e:
        try:
            os.remove(local)
        except OSError:
            pass
        return dict(base, ok=False, failure="EXTRACTION",
                    detail="%s: %s" % (type(e).__name__, e))
    try:
        os.remove(local)
    except OSError:
        pass

    return dict(base, ok=True, page_state=page_state, column=column,
                published_sha1=published, local_sha1=local_sha1,
                local_sha256=local_sha256, rows=rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args()

    check_tools()
    print("NOTE  results carry PENDING_OWNER_ENGINE_CONFIRMATION until")
    print("      tools/verify_ra_freeze.py has run successfully.")

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    out = os.path.abspath(args.out)
    img = os.path.join(out, "pages")
    os.makedirs(img, exist_ok=True)
    rows_path = os.path.join(out, "ra_rows.jsonl")
    ckpt_path = os.path.join(out, "checkpoint.json")
    fail_path = os.path.join(out, "failures.jsonl")

    ckpt = json.load(open(ckpt_path)) if os.path.exists(ckpt_path) else {"done": []}
    done = set(ckpt["done"])

    pages = page_list()
    todo = [p for p in pages if p[2] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("population %d pages, already done %d, processing %d with %d workers"
          % (len(pages), len(done), len(todo), workers))
    sys.stdout.flush()

    sha1_tables = {}
    tasks = []
    for run, folder, stem in todo:
        if folder not in sha1_tables:
            sha1_tables[folder] = load_sha1(folder, out)
        tasks.append((run, folder, stem, sha1_tables[folder].get(stem + ".jpg"), img))

    processed = 0
    t0 = time.time()
    with mp.Pool(processes=workers) as pool:
        for res in pool.imap_unordered(work, tasks, chunksize=1):
            if not res.get("ok"):
                with open(fail_path, "a") as f:
                    f.write(json.dumps({k: v for k, v in res.items()
                                        if k != "rows"}) + "\n")
                continue
            with open(rows_path, "a") as f:
                if res["page_state"] is not None:
                    f.write(json.dumps({
                        "run": res["run"], "folder": res["folder"],
                        "page": res["page"], "row_index": None, "row_y": None,
                        "source_url": res["source_url"],
                        "transport": "PLAIN_HTTP_NO_TLS",
                        "source_published_sha1": res["published_sha1"],
                        "source_published_sha1_semantics": "CONSISTENCY_METADATA_ONLY",
                        "local_sha1": res["local_sha1"],
                        "local_sha256": res["local_sha256"],
                        "byte_integrity": "CONSISTENT_WITH_SOURCE_PUBLISHED_CHECKSUM",
                        "source_authenticity": "UNESTABLISHED",
                        "extractor": "ra_extractor_v1",
                        "extractor_sha256": EXPECTED_TOOL_SHA256["ra_extractor_v1.py"],
                        "gate_sha256": EXPECTED_TOOL_SHA256["ra_validity_gate_v1.py"],
                        "page_state": res["page_state"],
                        "ra_column": None,
                        "extractor_state": None, "extractor_value": None,
                        "gate_state": None, "gate_reason": None,
                    }) + "\n")
                else:
                    for i, r in enumerate(res["rows"]):
                        f.write(json.dumps({
                            "run": res["run"], "folder": res["folder"],
                            "page": res["page"], "row_index": i,
                            "row_y": r["row_y"],
                            "source_url": res["source_url"],
                            "transport": "PLAIN_HTTP_NO_TLS",
                            "source_published_sha1": res["published_sha1"],
                            "source_published_sha1_semantics": "CONSISTENCY_METADATA_ONLY",
                            "local_sha1": res["local_sha1"],
                            "local_sha256": res["local_sha256"],
                            "byte_integrity": "CONSISTENT_WITH_SOURCE_PUBLISHED_CHECKSUM",
                            "source_authenticity": "UNESTABLISHED",
                            "extractor": "ra_extractor_v1",
                            "extractor_sha256": EXPECTED_TOOL_SHA256["ra_extractor_v1.py"],
                            "gate_sha256": EXPECTED_TOOL_SHA256["ra_validity_gate_v1.py"],
                            "page_state": None,
                            "ra_column": res["column"],
                            "raw_reads": r["raw_reads"],
                            "normalised": r["normalised"],
                            "extractor_state": r["state"],
                            "extractor_value": r["value"],
                            "gate_version": r["gate_version"],
                            "gate_state": r["gate_state"],
                            "gate_reason": r["gate_reason"],
                        }) + "\n")
            done.add(res["page"])
            ckpt["done"] = sorted(done)
            json.dump(ckpt, open(ckpt_path, "w"))
            processed += 1
            if processed % 10 == 0:
                el = time.time() - t0
                rate = el / processed
                print("  %d/%d this run, %.1f s/page wall, %d of %d total, "
                      "about %.0f min left"
                      % (processed, len(tasks), rate, len(done), len(pages),
                         (len(tasks) - processed) * rate / 60))
                sys.stdout.flush()

    el = time.time() - t0
    print("finished: %d pages in %.0f s (%.2f s/page wall with %d workers)"
          % (processed, el, el / processed if processed else 0, workers))
    print("total complete: %d of %d" % (len(done), len(pages)))
    print("rows file:      %s" % rows_path)
    print("checkpoint:     %s" % ckpt_path)
    print("failures file:  %s" % fail_path)


if __name__ == "__main__":
    mp.freeze_support()
    main()
