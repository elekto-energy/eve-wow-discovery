# Evidence-Chain Verification in Historical Signal Research: The EVE Wow! Case Study

**Status:** post-closure documentation for WOW v1 and progress documentation for WOW v2 Phase A.
It describes work already recorded elsewhere and modifies no sealed or pinned artifact.

**Date:** 2026-08-19
**Chain identities:** WOW v1 closure pin `679e3e48…`, WOW v2 genesis seal `17c4258d…`, D2 amendment seal `d33f79c5…`

---

## 1. What this document claims, and what it does not

This is a methods report about a verification process, not a result report about the Wow! signal.
No hypothesis about the signal is confirmed or excluded here. The Wow! signal is not explained.

The claim under examination is narrow: that binding a live research workflow to an evidence chain
changes the quality of the process in ways that are visible and auditable. The material below is
the evidence for and against that claim, drawn from a single continuous investigation.

Attribution is kept strict throughout. Three sources of correction are distinguished:

- **EVE enforced** — a mechanism in the chain refused an action or state.
- **Controller review detected** — a human reviewer rejected something before it took effect.
- **Analyst detected** — the analyst found the fault, usually while applying a rule imposed earlier.

Where a correction came from human review it is credited to human review.

---

## 2. Setting

Project 042_wow (WOW v1) evaluated whether the published follow-up literature on the Wow! signal
could constrain the sealed hypothesis taxonomy, and designed a prospective observation. It closed
as a method study, cryptographically pinned and publicly anchored.

Project 043_wow_discovery (WOW v2) asks a different question: whether a novel, testable proposition
about the signal can be identified in the historical archive. Its comparison region and its
questions were sealed before any archive content was opened. Phase A, the subject of most of
this report, determines which archive records fall inside that sealed region.

The archive is the N50CH paper record of the Ohio State survey: 918 pages of impact-printer
output within the eligible date window, photographed and published as images. The 1977 values
exist only as pictures of paper. Transcription, not analysis, is the bottleneck.

---

## 3. Eight findings

### 3.1 An aggregate representation was tested, not assumed, and failed

To decide whether a record lies in the sealed declination window, the printed declination must be
read. Reading it on every row of 918 pages is expensive. The analyst proposed a run-level
representation: read the declination once per observing run and treat it as constant within the run.

The controller required that the constancy be **tested rather than assumed**, and pre-registered the
test: three pages per run at fixed positions, sampling rule fixed before any value was seen.

The result was `CONSTANCY_SAMPLE_PASS` on **0 of 15 runs**. Within-run spans reached 16 arcminutes
against a sealed window 40 arcminutes wide. The efficiency shortcut was rejected by its own test.

Had it been assumed, every downstream eligibility decision would have rested on a false premise,
and nothing in the output would have revealed it.

*Attribution: controller review required the test. The data rejected the representation.*

### 3.2 An epoch transform is a coordinate-pair transform

The archive prints coordinates in epoch B1950; the sealed window derives from a J2000 position.
One conversion had been run, at right ascension 14h45m, giving a shift of 12.49 arcminutes south.
The temptation was to treat that as *the* declination shift.

Running the sealed WOW v1 transform tool unchanged, on the same declination at five right
ascensions, gave:

| RA | J2000 declination | shift |
|---|---|---|
| 14h45m | −26°57′29″ | −12.49′ south |
| 17h00m | −26°49′13″ | −4.21′ south |
| 19h25m | −26°38′50″ | +6.16′ **north** |
| 21h00m | −26°33′07″ | +11.89′ north |
| 23h00m | −26°28′50″ | +16.16′ north |

The spread is 28.65 arcminutes, **72 percent of the sealed window width**, and the shift changes
sign. A single offset applied across the population would have moved records into and out of the
sealed region incorrectly.

This produced a recorded method rule: *epoch transforms are coordinate-pair transforms;
declination may never be epoch-transformed independently of the row-bound right ascension unless
the sealed tool has demonstrated independence over the relevant domain.*

*Attribution: analyst detected the risk and resolved it by querying the sealed tool rather than by
reasoning from a formula.*

### 3.3 The instrument was frozen before it saw its population

The declination extractor was built, measured against 36 independently selected truth pages,
then frozen: code, configuration, dependency versions and hashes committed to version control
**before** the population run. The commit is the evidence that the instrument was fixed before the
data it would select from was known.

Measured on the truth set: 35 of 36 pages agreed, one produced no consensus, **zero incorrect values**.
The observed failure mode was abstention.

### 3.4 The population revealed a failure mode the validation set did not contain

Running the frozen extractor over 918 pages produced 82 525 rows. Among the 62 451 transcribed
values, **339 (0.54 percent) were syntactically valid but impossible as coordinates** — arcminute
components of 60 or more, degree components far outside the survey band.

The validation set had contained none. At roughly four such cases per thousand rows, a 36-page
sample can easily miss them. This is a lesson about validation-set size, not about the extractor.

The response was **not** to edit the frozen extractor. Its outputs must remain attributable to the
code that produced them. Instead a separate structural validity gate was added downstream, frozen
and hashed in its own right, with one binding rule: *the gate may reject a value from scientific
use; it may never repair, infer, round or truncate one.* An arcminute component of 64 is not read
as 04 or 44. It is rejected, with the original reading preserved, and sent to human review.

### 3.5 A header artifact that no validity gate could catch

The right-ascension column header contains the printed text `(1950.0)`. OCR reads it as the digits
`19 50`, which can yield a value such as `19 50 40`. For right ascension that is a **structurally
valid** value: 19h50m40s is a legal coordinate. No range check can reject it.

The mitigation had to be geometric: the header band is excluded before OCR, by position, never by
inspecting output for the digits and removing them afterwards. Value-based removal would have been
repair by another name.

The same artifact appears in the declination data as values near −19°50′, which the declination
gate's plausible-band rule had already rejected. The declination field was protected by accident of
range; the right-ascension field was not.

*Attribution: analyst detected, during pre-freeze validation.*

### 3.6 Source failure was kept distinct from scientific missingness

Partway through the work the archive host began returning HTTP 503 responses with a 114-byte body.
Byte-integrity checking against the publisher's own SHA1SUM flagged 24 of 34 requested pages as
mismatched. Those files were never passed to the extractor.

Had they been, they would have entered the record as pages with no readable rows — indistinguishable,
downstream, from blank or illegible scans. A network failure would have become scientific evidence
of absence.

The extractor now carries an explicit `SOURCE_INPUT_INVALID` state, separate from `UNREADABLE`.
The distinction is not cosmetic: one says the source did not arrive, the other says the record was
examined and could not be read.

*Attribution: EVE enforced. The integrity check was already a required field in the record schema.*

### 3.7 A validation result was invalidated because the scoring tool had a hidden assumption

The right-ascension extractor's first validation reported 90.2 percent accuracy: 46 correct,
3 incorrect. On inspection the three "incorrect" values on one page were each the **previous row's
correct value**. The scoring harness had aligned truth to output by matching values, which silently
absorbed a one-row offset.

The harness had committed exactly the error the controller had forbidden for the eventual
declination-to-right-ascension join: pairing by value rather than by identity.

The figure is preserved as `INVALIDATED_VALIDATION_RESULT`, reason *non-geometric value-based
alignment introduced row-shift ambiguity*, and may never be reused.

Revalidation used geometric pairing only. For each page the extractor's own row bands were computed
first, rendered as labelled strips with each band's exact pixel row marked, and truth values were
read against those labels and stored keyed by row position.

| | |
|---|---|
| truth values | 91 |
| unpaired | 0 |
| correct | 65 |
| **incorrect** | **0** |
| manual review required | 22 |
| unreadable | 2 |
| structurally invalid | 2 |
| coverage | 73.6% |
| accuracy given a gate-passing value | 100% |

Both wrong readings were caught by the structural gate. No incorrect value reached the data.

*Attribution: analyst detected, while applying the pairing rule the controller had imposed for a
different purpose. The rule caught its own author's tooling.*

### 3.8 External failure did not alter the rules

The archive host went down mid-workflow and remained unreachable. Two hostnames that had been
assumed related resolved to different networks; the surviving host does not mirror the archive.

Nothing in the sealed region, the eligibility criteria, the instrument identities or the pairing
rules changed in response. The freeze record carries an explicit open precondition —
`PENDING_OWNER_ENGINE_CONFIRMATION` — recording that the validated values were measured under one
OCR engine version while the production machine runs another, and that population results carry
that precondition until the check is run.

An unavailable server changed the schedule. It did not change what would count as evidence.

---

## 4. What the chain enforced, and what humans caught

**Enforced by the chain, without human intervention:**

- Re-derivation of every prior layer from disk before any new seal, failing hard on any byte that moved.
- Write-once seals and pins; no overwrite path exists.
- Hash verification of both frozen instruments at the start of every production run, refusing to run on mismatch.
- Value-domain validation rejecting booleans, nulls and floats, and forbidding a field named `status`
  so that lifecycle state cannot be confused with state-at-authoring.
- Byte-integrity checking of every retrieved page against the publisher's checksum.
- The structural validity gate rejecting impossible coordinates without repairing them.

**Caught by controller review, not by the system:**

- The proposal to treat a 24-arcminute gap as comfortably outside the sealed window, which the
  subsequent transform showed was consumed more than half by the epoch shift alone.
- The demand that run-level declination be tested rather than assumed.
- Four overclaims during WOW v1, including a coverage figure being reported as a confidence figure.

**Caught by the analyst, while applying earlier rules:**

- The right-ascension dependence of the epoch transform.
- The header artifact that passes range checks.
- The state collapse in the declination gate, where a missing value and a disputed value both
  report as unreadable.
- The value-based alignment in the validation harness.

The count of corrections is recorded but **no rate is claimed**: the denominator, the number of
reviewable decisions across the project, has never been defined. It is an observed pattern, not a
frequency.

---

## 5. Limitations

- Fewer than a hundred truth values underlie each accuracy figure. Neither generalises to the
  population with any stated confidence.
- Both validity gates reject impossible values only. A misreading that happens to be a possible
  coordinate passes, and this measurement does not bound how often that occurs.
- Roughly one row in four produces no value and goes to review or unreadable. That is intended
  behaviour, but it sets the size of a manual queue that has not yet been worked.
- Phase A is incomplete. No record has yet been classified as eligible or ineligible against the
  sealed region, because the right-ascension population extraction has not run.
- Cryptographic reproducibility and computational reproducibility were shown to be different
  properties: the chain verified perfectly at a point when a dependency required to re-run one of
  its own transforms was no longer installed.

---

## 6. Conclusion

The case study does not establish that EVE produces scientifically correct conclusions by itself.
It demonstrates that EVE can preserve analytical state, expose hidden assumptions, prevent silent
methodological substitution, separate source failure from scientific missingness, and make
corrections auditable across a live research workflow.

The most useful evidence in this report is not a result the process produced. It is the set of
results it declined to produce: a network closure withdrawn when the underlying representation
proved insufficient, an aggregate shortcut rejected by its own test, a validation figure
invalidated by the discovery of a flaw in the tool that measured it.

None of those corrections were expensive. All of them would have been invisible in the output.
