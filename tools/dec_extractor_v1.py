#!/usr/bin/env python3
"""dec_extractor_v1.py - field-specific transcription of the printed
DECLIN. (1950.0) field from N50CH jpg scans.

PROJECT: 043_wow_discovery (WOW v2 discovery track)
FROZEN:  before bulk execution over the B3-eligible population.

SCOPE
    Reads ONE field: the printed per-row declination, epoch 1950.0.
    It never reads channel numbers, intensity values, the second local
    oscillator frequency, galactic coordinates, the object field or
    annotations. The column window deliberately stops before the
    frequency column so that signal-adjacent content cannot be exposed
    during spatial screening.
    This is not a general-purpose archive OCR system and must not be
    extended into one under this version number.

METHOD (declared, version 1)
    1. Column window x 1222..1340, fixed from the ink-density column
       profile of the page geometry, stopping before 2ND LO FREQ.
    2. Paper level estimated per pixel row as the median of that window.
       An absolute threshold fails on this material: the pages are beige
       paper photographed under uneven light, and a global cut classifies
       the entire page as ink. The per-row median makes the threshold
       follow the illumination instead of fighting it.
    3. Row bands located from the darkness profile; bands 6..40 px tall
       are kept.
    4. Each row is binarised at three cuts, upscaled, and read by
       tesseract under two page-segmentation modes with a digits-and-minus
       whitelist.
    5. A value is TRANSCRIBED only when at least two variants agree after
       normalisation. Disagreement gives MANUAL_REVIEW_REQUIRED. Absence
       of ink gives UNREADABLE.

HARD RULES
    No uncertain reading is ever coerced into a number.
    Normalisation accepts only two two-digit groups, or one four-digit
    group split into degrees and arcminutes. Anything else is discarded,
    never repaired.
    The three states are the only permitted outcomes.

MEASURED VALIDATION (see DEC_EXTRACTOR_V1_FREEZE.json)
    36 pages of independently chosen manual truth: 35 agreements,
    0 incorrect values, 1 page without consensus. Row-level transcription
    rate 78.4 percent on the measured band. The failure mode is
    abstention, not error.

VERSIONING
    This file is frozen. Any improvement is a NEW version with a new
    freeze record. This version is never modified in place, because the
    bulk results it produced must remain attributable to the exact code
    that produced them.
"""
import re
import sys
import json
from collections import Counter

import numpy as np
from PIL import Image
import pytesseract

# --- frozen configuration -------------------------------------------------
COL = (1222, 1340)      # declination column window, x range
DARK_THR = 30           # darkness above paper level counted as ink
ROW_FRAC = 0.08         # fraction of window that must be ink to start a row
ROW_MIN, ROW_MAX = 6, 40
VARIANTS = [
    {"scale": 4, "psm": 7, "cut": 30},
    {"scale": 3, "psm": 7, "cut": 40},
    {"scale": 4, "psm": 8, "cut": 22},
]
WHITELIST = "-0123456789 "
CONSENSUS_MIN = 2
# --------------------------------------------------------------------------


def window(path):
    """Return the declination window and its per-row darkness map."""
    g = np.asarray(Image.open(path).convert("L"), dtype=float)
    win = g[:, COL[0]:COL[1]]
    paper = np.median(win, axis=1, keepdims=True)
    return win, np.clip(paper - win, 0, None)


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
    return bands


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
    d = re.findall(r"\d+", t)
    if len(d) == 2 and len(d[0]) == 2 and len(d[1]) == 2:
        return "-%s %s" % (d[0], d[1])
    if len(d) == 1 and len(d[0]) == 4:
        return "-%s %s" % (d[0][:2], d[0][2:])
    return None


def transcribe_page(path):
    _, dark = window(path)
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
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: dec_extractor_v1.py PAGE.jpg [PAGE.jpg ...]")
        return 2
    result = {}
    for path in sys.argv[1:]:
        result[path] = transcribe_page(path)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
