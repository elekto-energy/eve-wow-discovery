#!/usr/bin/env python3
"""ra_extractor_v1.py - field-specific transcription of the printed
RT. ASCEN. (1950.0) field from N50CH jpg scans.

PROJECT: 043_wow_discovery (WOW v2 discovery track)
VERSION: v1 of the RA extractor. A SEPARATE instrument from
         dec_extractor_v1, which is immutable and untouched.

WHY THIS EXISTS
    Comparing the extracted declinations against the sealed B1 window
    requires the FK4(B1950) to FK5(J2000) transform, and that transform was
    shown, using the sealed WOW v1 tool itself, to depend on right
    ascension:

        same declination -26d45m B1950, transformed at five right ascensions
            RA 14h45m  ->  -26d57m29s   shift  -12.49 arcmin  south
            RA 17h00m  ->  -26d49m13s   shift   -4.21 arcmin  south
            RA 19h25m  ->  -26d38m50s   shift   +6.16 arcmin  north
            RA 21h00m  ->  -26d33m07s   shift  +11.89 arcmin  north
            RA 23h00m  ->  -26d28m50s   shift  +16.16 arcmin  north

    The spread is 28.65 arcmin, 72 percent of the 40 arcmin sealed window,
    and the shift changes sign. Right ascension is mandatory per row.

SCOPE
    Reads ONE field: the printed per-row right ascension, epoch 1950.0.
    It never reads channel numbers, intensity values, the second local
    oscillator frequency, galactic coordinates, the object field or
    annotations. Not a general-purpose archive OCR system.

ADAPTIVE COLUMN LOCALISATION
    A fixed x-window failed on this material. Print position shifts between
    pages: a narrow window truncated the leading hour digit on some pages,
    and a wider one absorbed digits from the channel column on others.

    The field is therefore located per page from image structure alone.
    Within a search band, the ink profile is computed and low-ink
    separators are found. The RA field is taken as the span between the
    widest separator on the left and the widest on the right.

    The locator uses ONLY the ink profile. It never uses expected RA
    values, the 12 second cadence, D2 eligibility, the Wow position,
    neighbouring OCR output, or scientific interest.

    If the field cannot be located unambiguously the page is reported as
    RA_COLUMN_UNRESOLVED. There is NO fallback to a guessed fixed window.

HEADER EXCLUSION
    The column header contains the literal text (1950.0), which OCRs as the
    digits 19 50 and can produce a spurious value such as 19 50 40. For
    right ascension that value is structurally VALID, so no validity gate
    can catch it.

    The header band is therefore excluded GEOMETRICALLY, before OCR, by
    skipping all row bands above the first data row. The exclusion is never
    value-based: no output is inspected for the digits 19 50 and then
    removed or repaired.

HARD RULES
    No uncertain reading is ever coerced into a value.
    Normalisation accepts only three two-digit groups, or one six-digit
    group split as HH MM SS. Anything else is discarded, never repaired.
    The 12 second cadence of the records is NEVER used to repair, choose
    between conflicting reads, reject values, or align rows.
    Rows are paired with dec_extractor_v1 output by (page, row_index).
    This file never modifies declination data.

VERSIONING
    Frozen before population execution. Any improvement is a NEW version
    with a new freeze record and its own validation.
"""
import json
import re
import sys
from collections import Counter

import numpy as np
from PIL import Image
import pytesseract

# --- frozen configuration -------------------------------------------------
SEARCH = (1000, 1260)   # x band within which the RA field is located
LEFT_LIMIT = 1110       # separators ending at or before this are left candidates
RIGHT_LIMIT = 1150      # separators starting at or after this are right candidates
MIN_FIELD_WIDTH = 60    # narrower than this means localisation failed
MIN_SEPARATOR = 8       # a low-ink run must be this wide to count as a separator
SEP_FRAC = 0.06         # low-ink threshold as a fraction of the profile maximum
DARK_THR = 30           # darkness above paper level counted as ink
ROW_FRAC = 0.08         # fraction of window that must be ink to start a row
ROW_MIN, ROW_MAX = 6, 40
HEADER_SKIP_Y = 260     # geometric header exclusion, see module docstring
VARIANTS = [
    {"scale": 4, "psm": 7, "cut": 30},
    {"scale": 3, "psm": 7, "cut": 40},
    {"scale": 4, "psm": 8, "cut": 22},
]
WHITELIST = "0123456789 "
CONSENSUS_MIN = 2

RA_COLUMN_UNRESOLVED = "RA_COLUMN_UNRESOLVED"
SOURCE_INPUT_INVALID = "SOURCE_INPUT_INVALID"
# --------------------------------------------------------------------------


def load_grey(path):
    """Load the page. Raises on anything that is not a usable image.

    A retrieval that returned an error page or a truncated response is a
    SOURCE problem, not an OCR problem, and must never be reported as
    unreadable scientific data.
    """
    im = Image.open(path)
    im.load()
    if im.width < 500 or im.height < 500:
        raise ValueError("image too small to be a scan page: %dx%d"
                         % (im.width, im.height))
    return np.asarray(im.convert("L"), dtype=float)


def separators(profile, x0):
    """Return low-ink runs as (start, end) in absolute x."""
    thr = profile.max() * SEP_FRAC
    runs, start = [], None
    for i, v in enumerate(profile):
        x = x0 + i
        if v <= thr:
            if start is None:
                start = x
        else:
            if start is not None and x - start >= MIN_SEPARATOR:
                runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, x0 + len(profile)))
    return runs


def locate_column(a):
    """Locate the RA field from the ink profile alone. None if ambiguous."""
    win = a[:, SEARCH[0]:SEARCH[1]]
    paper = np.median(win, axis=1, keepdims=True)
    dark = np.clip(paper - win, 0, None)
    prof = (dark > DARK_THR).mean(axis=0)
    if prof.max() <= 0:
        return None
    seps = separators(prof, SEARCH[0])
    left = [s for s in seps if s[1] <= LEFT_LIMIT]
    right = [s for s in seps if s[0] >= RIGHT_LIMIT]
    if not left or not right:
        return None
    lo = max(left, key=lambda t: t[1] - t[0])[1]
    hi = max(right, key=lambda t: t[1] - t[0])[0]
    if hi - lo < MIN_FIELD_WIDTH:
        return None
    return (lo, hi)


def row_bands(dark):
    prof = (dark > DARK_THR).mean(axis=1)
    on = prof > ROW_FRAC
    bands, start = [], None
    for y, v in enumerate(on):
        if v and start is None:
            start = y
        elif not v and start is not None:
            if ROW_MIN <= y - start <= ROW_MAX:
                bands.append((start, y))
            start = None
    return [b for b in bands if b[0] >= HEADER_SKIP_Y]


def read_row(dark, y0, y1):
    reads = []
    seg = dark[max(0, y0 - 3):y1 + 3]
    for v in VARIANTS:
        b = (seg > v["cut"]).astype(np.uint8) * 255
        im = Image.fromarray(255 - b)
        im = im.resize((im.width * v["scale"], im.height * v["scale"]),
                       Image.LANCZOS)
        t = pytesseract.image_to_string(
            im, config="--psm %d -c tessedit_char_whitelist=%s"
                       % (v["psm"], WHITELIST))
        reads.append(t.strip().replace("\n", " "))
    return reads


def normalise(t):
    """Return HH MM SS or None. Never repairs."""
    d = re.findall(r"\d+", t)
    if len(d) == 3 and all(len(x) == 2 for x in d):
        return "%s %s %s" % (d[0], d[1], d[2])
    if len(d) == 1 and len(d[0]) == 6:
        return "%s %s %s" % (d[0][:2], d[0][2:4], d[0][4:])
    return None


def transcribe_page(path):
    """Return (page_state, column, rows).

    page_state is None on success, otherwise SOURCE_INPUT_INVALID or
    RA_COLUMN_UNRESOLVED, and rows is empty.
    """
    try:
        a = load_grey(path)
    except Exception as e:
        return SOURCE_INPUT_INVALID, None, [{"detail": "%s: %s"
                                             % (type(e).__name__, e)}]
    col = locate_column(a)
    if col is None:
        return RA_COLUMN_UNRESOLVED, None, []
    win = a[:, col[0]:col[1]]
    paper = np.median(win, axis=1, keepdims=True)
    dark = np.clip(paper - win, 0, None)
    out = []
    for (y0, y1) in row_bands(dark):
        reads = read_row(dark, y0, y1)
        norm = [normalise(r) for r in reads]
        good = [n for n in norm if n]
        if not good:
            state, value = "UNREADABLE", None
        else:
            top, count = Counter(good).most_common(1)[0]
            if count >= CONSENSUS_MIN:
                state, value = "TRANSCRIBED", top
            else:
                state, value = "MANUAL_REVIEW_REQUIRED", None
        out.append({
            "row_y": [int(y0), int(y1)],
            "raw_reads": reads,
            "normalised": norm,
            "state": state,
            "value": value,
        })
    return None, [int(col[0]), int(col[1])], out


def main():
    if len(sys.argv) < 2:
        print("usage: ra_extractor_v1.py PAGE.jpg [PAGE.jpg ...]")
        return 2
    result = {}
    for path in sys.argv[1:]:
        state, col, rows = transcribe_page(path)
        result[path] = {"page_state": state, "ra_column": col, "rows": rows}
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
