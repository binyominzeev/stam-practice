# stam-practice
Practice reading mezuzot, tefillin and finding mistakes

## Overview

`generate_worksheet.py` produces hagaha (proofreading) practice worksheets for the
four mezuzah/tefillin parashot:

| Parasha | Source |
|---------|--------|
| קדש | Shemot 13:1–10 |
| והיה כי יביאך | Shemot 13:11–16 |
| שמע | Devarim 6:4–9 |
| והיה אם שמוע | Devarim 11:13–21 |

Each run generates:
- `output/images/test_01.png` … `test_20.png` — clean Hebrew images with one
  injected error each (no highlighting; the student finds the mistake).
- `output/answer_key.txt` — full answer key with error type, changed word, and
  context location.

## Setup

### 1. Font (required)

The script requires the **Culmus** font package, which provides `StamAshkenazCLM.ttf`:

```bash
sudo apt-get install culmus          # Debian/Ubuntu
sudo dnf install culmus              # Fedora/RHEL
fc-list | grep -i stam               # verify
```

### 2. Python packages

```bash
pip install pillow python-bidi
# or
pip install -r requirements.txt
```

### 3. Run

```bash
python generate_worksheet.py
```

Edit the **CONFIG** section at the top of `generate_worksheet.py` to change
`NUM_TEXTS`, `ERRORS_PER_TEXT`, `OUTPUT_DIR`, `RANDOM_SEED`, etc.

## Text sourcing & STA"M spelling

On the first run the script tries to fetch the base text from the
[Sefaria API](https://www.sefaria.org) and caches it in `parashot_cache.json`.
If the API is unreachable it falls back to the bundled `parashot_fallback.json`.

Because Sefaria follows standard Masoretic/printed Tanakh spelling, which can
differ from the plene/defective (male/chaser) conventions used on actual STA"M
parchments, the script contains a `STAM_SPELLING_OVERRIDES` dict near the top.
Fill in the known deviations after cross-checking against a trusted printed
**Tikkun Soferim**.

## Error types

| # | Code | Description |
|---|------|-------------|
| 1 | `MISSING_LETTER` | Remove one letter (prefers doubled adjacent letters) |
| 2 | `EXTRA_LETTER` | Duplicate a letter within a word |
| 3 | `MALE_CHASER_SWAP` | Toggle a ו/י in/out (plene ↔ defective) |
| 4 | `SIMILAR_LETTER_SWAP` | Replace a letter with a visually similar one (ד/ר, ה/ח, ו/ז/י, כ/ב/פ, ם/ס, ע/צ, ג/נ) |
| 5 | `LETTER_TRANSPOSITION` | Swap two adjacent letters |
| 6 | `WORD_BOUNDARY_ERROR` | Merge two words or split one word |
| 7 | `SKIP_DUE_TO_SIMILARITY` | Delete a word/phrase between two repeated words (eye-skip) |
| 8 | `WORD_DUPLICATION` | Duplicate a word or short sequence |
| 9 | `SIMILAR_FUNCTION_WORD_SWAP` | Swap a function word for a near-identical one (כי/כן, אל/על, …) |
| 10 | `SUFFIX_ERROR` | Modify a pronominal/number suffix by one letter |

Errors affecting a Name of God (יהוה, אלהינו, אלהיך, אלהיכם) are flagged
**HOLY_NAME** in the answer key.
