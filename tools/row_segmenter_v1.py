#!/usr/bin/env python3
"""row_segmenter_v1.py - canonical physical-row identity for a scan page.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

WHY THIS EXISTS
    The declination and right ascension extractors each computed their own
    row bands, each from its own column window. Those bands were then used
    as the join key. That was wrong: a row band derived from a column is a
    property of THAT COLUMN's ink profile, not of the page. Boundaries
    differed by a pixel or two between the two fields, and an exact join
    paired only 798 rows out of 82525.

    The join rule was correct and refused to pair. The key was the error.

    This tool establishes ONE row identity per page, shared by both fields,
    so that exact equality is a meaningful test rather than a coincidence.

METHOD (declared)
    1. Compute row bands in the declination column window, using exactly the
       parameters frozen in dec_extractor_v1.
    2. Compute row bands in the right ascension column window, located per
       page exactly as frozen in ra_extractor_v1.
    3. Merge the two band lists into canonical rows by INTERVAL OVERLAP.
       Two bands that overlap by at least one pixel describe the same
       physical line and become one canonical row spanning both.
    4. Assign each field's bands to canonical rows.

    No tolerance window. No pitch model. No cadence. No assumption that the
    line spacing is regular. Overlap is the only relation used, and overlap
    is a geometric fact about the two intervals.

THE AMBIGUITY RULE
    A canonical row that receives MORE THAN ONE band from the same side is
    CANONICAL_AMBIGUOUS. Two physical lines have been merged, and which
    declination belongs to which right ascension is no longer determinable
    from geometry alone.

    Such rows are flagged, never resolved by picking one. Everything read
    from them is excluded from pairing. Measured on three development
    pages, roughly nine percent of canonical rows fall here.

    This is the failure the tool exists to make visible. A segmenter that
    merged silently would produce confident coordinate pairs that never
    existed on the paper.

STATES
    CANONICAL_CLEAN      exactly one band from each side
    CANONICAL_DEC_ONLY   one declination band, no right ascension band
    CANONICAL_RA_ONLY    one right ascension band, no declination band
    CANONICAL_AMBIGUOUS  two or more bands from at least one side

WHAT IT DOES NOT DO
    It reads no field values. It performs no OCR. It makes no scientific
    statement. It describes where the rows are, and where that question
    cannot be answered.

VERSIONING
    Frozen before use. Any change is a new version with its own record.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

# --- parameters, matching the frozen field extractors ---------------------
DEC_COL = (1222, 1340)          # frozen in dec_extractor_v1
RA_SEARCH = (1000, 1260)        # frozen in ra_extractor_v1
RA_LEFT_LIMIT = 1110
RA_RIGHT_LIMIT = 1150
RA_MIN_FIELD_WIDTH = 60
RA_MIN_SEPARATOR = 8
RA_SEP_FRAC = 0.06
DARK_THR = 30
ROW_FRAC = 0.08
ROW_MIN, ROW_MAX = 6, 40
# --------------------------------------------------------------------------

CLEAN = "CANONICAL_CLEAN"
DEC_ONLY = "CANONICAL_DEC_ONLY"
RA_ONLY = "CANONICAL_RA_ONLY"
AMBIGUOUS = "CANONICAL_AMBIGUOUS"
RA_COLUMN_UNRESOLVED = "RA_COLUMN_UNRESOLVED"
SOURCE_INPUT_INVALID = "SOURCE_INPUT_INVALID"

SEGMENTER_VERSION = "row_segmenter_v1"


def load_grey(path):
    im = Image.open(path)
    im.load()
    if im.width < 500 or im.height < 500:
        raise ValueError("image too small to be a scan page: %dx%d"
                         % (im.width, im.height))
    return np.asarray(im.convert("L"), dtype=float)


def bands(a, x0, x1):
    win = a[:, x0:x1]
    paper = np.median(win, axis=1, keepdims=True)
    dark = np.clip(paper - win, 0, None)
    prof = (dark > DARK_THR).mean(axis=1)
    on = prof > ROW_FRAC
    out, start = [], None
    for y, v in enumerate(on):
        if v and start is None:
            start = y
        elif not v and start is not None:
            if ROW_MIN <= y - start <= ROW_MAX:
                out.append((start, y))
            start = None
    return out


def locate_ra_column(a):
    win = a[:, RA_SEARCH[0]:RA_SEARCH[1]]
    paper = np.median(win, axis=1, keepdims=True)
    dark = np.clip(paper - win, 0, None)
    prof = (dark > DARK_THR).mean(axis=0)
    if prof.max() <= 0:
        return None
    thr = prof.max() * RA_SEP_FRAC
    seps, start = [], None
    for i, v in enumerate(prof):
        x = RA_SEARCH[0] + i
        if v <= thr:
            if start is None:
                start = x
        else:
            if start is not None and x - start >= RA_MIN_SEPARATOR:
                seps.append((start, x))
            start = None
    if start is not None:
        seps.append((start, RA_SEARCH[1]))
    left = [s for s in seps if s[1] <= RA_LEFT_LIMIT]
    right = [s for s in seps if s[0] >= RA_RIGHT_LIMIT]
    if not left or not right:
        return None
    lo = max(left, key=lambda t: t[1] - t[0])[1]
    hi = max(right, key=lambda t: t[1] - t[0])[0]
    if hi - lo < RA_MIN_FIELD_WIDTH:
        return None
    return (lo, hi)


def merge_by_overlap(dec_bands, ra_bands):
    """Canonical rows: intervals merged where they overlap by >= 1 pixel."""
    canonical = []
    for s, e in sorted(list(dec_bands) + list(ra_bands)):
        if canonical and s < canonical[-1][1]:
            canonical[-1] = (canonical[-1][0], max(canonical[-1][1], e))
        else:
            canonical.append((s, e))
    return canonical


def assign(band_list, canonical):
    """Map each band to the canonical row it overlaps. Overlap only."""
    mapping = {i: [] for i in range(len(canonical))}
    for b in band_list:
        for i, (cs, ce) in enumerate(canonical):
            if b[0] < ce and b[1] > cs:
                mapping[i].append(list(b))
                break
    return mapping


def segment_page(path):
    """Return (page_state, ra_column, rows). rows is empty on page failure."""
    try:
        a = load_grey(path)
    except Exception as e:
        return SOURCE_INPUT_INVALID, None, [{"detail": "%s: %s"
                                             % (type(e).__name__, e)}]
    ra_col = locate_ra_column(a)
    if ra_col is None:
        return RA_COLUMN_UNRESOLVED, None, []

    dec_bands = bands(a, DEC_COL[0], DEC_COL[1])
    ra_bands = bands(a, ra_col[0], ra_col[1])
    canonical = merge_by_overlap(dec_bands, ra_bands)
    dec_map = assign(dec_bands, canonical)
    ra_map = assign(ra_bands, canonical)

    rows = []
    for i, (cs, ce) in enumerate(canonical):
        d = dec_map[i]
        r = ra_map[i]
        if len(d) > 1 or len(r) > 1:
            state = AMBIGUOUS
        elif len(d) == 1 and len(r) == 1:
            state = CLEAN
        elif len(d) == 1:
            state = DEC_ONLY
        elif len(r) == 1:
            state = RA_ONLY
        else:
            state = AMBIGUOUS
        rows.append({
            "row_id": i,
            "canonical_y": [int(cs), int(ce)],
            "dec_bands": d,
            "ra_bands": r,
            "canonical_state": state,
            "segmenter_version": SEGMENTER_VERSION,
        })
    return None, [int(ra_col[0]), int(ra_col[1])], rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="+")
    args = ap.parse_args()
    result = {}
    for path in args.pages:
        state, col, rows = segment_page(path)
        result[path] = {"page_state": state, "ra_column": col, "rows": rows}
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
