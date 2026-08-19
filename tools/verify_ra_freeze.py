#!/usr/bin/env python3
"""verify_ra_freeze.py - owner-side identity check before the RA freeze.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

PURPOSE
    Confirm that the PROJECT copy of tools/ra_extractor_v1.py on the owner's
    machine reproduces the validated behaviour. The validation measurement
    was executed in the analyst environment; this script closes that gap by
    running the project file itself on two of the pages that were part of the
    geometric truth validation.

WHAT THIS IS NOT
    Not new analysis. Not a second validation round. No page is selected by
    right ascension value or scientific interest. The two pages below are
    taken directly from the truth set.

SAFEGUARDS
    Retrieval is checked before use: an error response or truncated body is
    reported as SOURCE_INPUT_INVALID and the run stops rather than feeding
    junk to the extractor. Where the folder SHA1SUM is available the byte
    integrity of each page is checked against it.

    Nothing is deleted automatically. The downloaded pages remain under
    outputs/ra_verify so the owner can inspect them.

USAGE
    venv_v2\\Scripts\\python.exe tools\\verify_ra_freeze.py
"""
import hashlib
import os
import subprocess
import sys
import urllib.request

BASE = "http://naapo.org/~rchilders/N50CH_data/scans/jpg"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "outputs", "ra_verify")

# Two pages from the geometric truth validation set.
PAGES = [("013", "013-190"), ("014", "014-331")]

# Expected values from the validated run, keyed by exact row_y.
EXPECTED = {
    "013-190": [
        (703, "18 24 08", "TRANSCRIBED"),
        (720, "18 24 20", "TRANSCRIBED"),
        (736, "18 24 32", "TRANSCRIBED"),
        (753, "18 24 44", "TRANSCRIBED"),
        (770, "18 24 56", "TRANSCRIBED"),
        (787, None, "MANUAL_REVIEW_REQUIRED"),
        (804, "18 25 19", "TRANSCRIBED"),
        (821, None, "MANUAL_REVIEW_REQUIRED"),
    ],
    "014-331": [
        (701, "20 02 02", "TRANSCRIBED"),
        (718, "20 02 14", "TRANSCRIBED"),
        (735, "20 02 25", "TRANSCRIBED"),
        (751, "20 02 37", "TRANSCRIBED"),
        (768, "20 02 49", "TRANSCRIBED"),
        (785, None, "MANUAL_REVIEW_REQUIRED"),
        (802, "20 03 13", "TRANSCRIBED"),
        (818, "20 03 25", "TRANSCRIBED"),
    ],
}
EXPECTED_COLUMN = {"013-190": [1094, 1209], "014-331": [1097, 1210]}


def fetch(url, dest):
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    if len(data) < 50000:
        raise ValueError("response too small to be a scan page (%d bytes). "
                         "SOURCE_INPUT_INVALID." % len(data))
    open(dest, "wb").write(data)
    return data


def sha1_table(folder):
    url = "%s/folder.%s/SHA1SUM" % (BASE, folder)
    path = os.path.join(OUT, "SHA1SUM.%s" % folder)
    if not os.path.exists(path):
        with urllib.request.urlopen(url, timeout=120) as r:
            open(path, "wb").write(r.read())
    table = {}
    for line in open(path):
        parts = line.split()
        if len(parts) == 2:
            table[parts[1]] = parts[0]
    return table


def main():
    os.makedirs(OUT, exist_ok=True)
    print("RA freeze verification. Project root: %s\n" % ROOT)

    extractor = os.path.join(HERE, "ra_extractor_v1.py")
    if not os.path.exists(extractor):
        print("FAIL: %s not found." % extractor)
        return 1

    for folder, stem in PAGES:
        url = "%s/folder.%s/%s.jpg" % (BASE, folder, stem)
        dest = os.path.join(OUT, stem + ".jpg")
        print("=== %s ===" % stem)
        print("  url        %s" % url)
        try:
            data = fetch(url, dest)
        except Exception as e:
            print("  FAIL: %s" % e)
            return 1
        local_sha1 = hashlib.sha1(data).hexdigest()
        try:
            published = sha1_table(folder).get(stem + ".jpg")
        except Exception:
            published = None
        print("  bytes      %d" % len(data))
        print("  local sha1 %s" % local_sha1)
        if published:
            ok = (published == local_sha1)
            print("  published  %s  -> %s" % (published,
                  "CONSISTENT" if ok else "MISMATCH"))
            if not ok:
                print("  FAIL: byte integrity mismatch. Stopping.")
                return 1
        else:
            print("  published  not available")
        print("  saved      %s" % dest)

        proc = subprocess.run([sys.executable, extractor, dest],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print("  FAIL: extractor exited %d\n%s" % (proc.returncode, proc.stderr))
            return 1
        import json
        result = json.loads(proc.stdout)[dest]
        col = result.get("ra_column")
        print("  page_state %s" % result.get("page_state"))
        print("  ra_column  %s   expected %s   -> %s"
              % (col, EXPECTED_COLUMN[stem],
                 "MATCH" if col == EXPECTED_COLUMN[stem] else "DIFFERENT"))
        rows = {r["row_y"][0]: r for r in result.get("rows", [])}
        print("  %-6s %-11s %-11s %-24s %s"
              % ("row_y", "expected", "produced", "state", "verdict"))
        agree = 0
        for y, exp_val, exp_state in EXPECTED[stem]:
            r = rows.get(y)
            if r is None:
                print("  %-6d %-11s %-11s %-24s %s"
                      % (y, exp_val or "-", "-", "-", "NO ROW AT THIS Y"))
                continue
            same = (r["value"] == exp_val and r["state"] == exp_state)
            agree += 1 if same else 0
            print("  %-6d %-11s %-11s %-24s %s"
                  % (y, exp_val or "-", r["value"] or "-", r["state"],
                     "MATCH" if same else "DIFFERENT"))
        print("  %d of %d rows reproduced exactly\n" % (agree, len(EXPECTED[stem])))

    print("Pages are kept under %s for inspection. Nothing was deleted." % OUT)
    print("If every row shows MATCH, the project copy reproduces the validated")
    print("behaviour and the freeze may proceed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
