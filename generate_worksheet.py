#!/usr/bin/env python3
"""
generate_worksheet.py — STA"M proofreading practice worksheet generator.

Generates hagaha (proofreading) practice worksheets for the four mezuzah/tefillin
parashot. Each worksheet is a PNG image of a Hebrew text with one injected error;
a companion answer_key.txt gives the solutions.

Run:
    python generate_worksheet.py

Requires:
    pip install pillow python-bidi
    Culmus fonts package (provides StamAshkenazCLM.ttf):
        sudo apt-get install culmus       # Debian/Ubuntu
    Verify: fc-list | grep -i stam
"""

# ============================================================
#  CONFIG — edit these values before running
# ============================================================

import os
import sys

NUM_TEXTS = 20           # How many test worksheets to generate
FONT_PATH = "/usr/share/fonts/truetype/culmus/StamAshkenazCLM.ttf"
FONT_SIZE = 40           # Points / px (increase for larger print)
IMAGE_WIDTH = 1200       # Canvas width in pixels
IMAGE_MARGIN = 60        # Left/right and top/bottom margin in pixels
LINE_SPACING = 1.6       # Line height multiplier (× FONT_SIZE)
ERRORS_PER_TEXT = 1      # Errors injected per worksheet (1 or 2 recommended)
ERROR_TYPES = None       # None → all error types enabled; or pass a list of
                         # ErrorType enum members to restrict which are used
TEXT_MODE = "MEZUZAH_ONLY"  # "ALL_PARASHOT" or "MEZUZAH_ONLY"
MEZUZAH_BREAK_BETWEEN_PARASHOT = True
HARD_MODE = True         # If True, only subtle/hard-to-spot error classes are used
HARD_ERROR_TYPES = [
    "MISSING_LETTER",
    "EXTRA_LETTER",
    "MALE_CHASER_SWAP",
    "SIMILAR_LETTER_SWAP",
    "LETTER_TRANSPOSITION",
    "SIMILAR_FUNCTION_WORD_SWAP",
    "SUFFIX_ERROR",
]
OUTPUT_DIR = "output"    # Directory for images/ and answer_key.txt
RANDOM_SEED = None       # Set to an int for reproducible output (e.g. 42)

# ============================================================
#  FONT CHECK — must pass before any other imports
# ============================================================

if not os.path.exists(FONT_PATH):
    sys.exit(
        f"ERROR: STA\"M font not found at:\n  {FONT_PATH}\n\n"
        "The Culmus fonts package is required (provides StamAshkenazCLM.ttf).\n"
        "Install it with:\n"
        "  sudo apt-get install culmus          # Debian/Ubuntu\n"
        "  sudo dnf install culmus              # Fedora/RHEL\n"
        "Then verify:\n"
        "  fc-list | grep -i stam\n"
    )

# ============================================================
#  STANDARD IMPORTS
# ============================================================

import json
import html
import random
import shutil
import pathlib
import urllib.request
import urllib.error
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Optional, Dict

from PIL import Image, ImageDraw, ImageFont
from PIL import features as pil_features

# Optional: python-bidi for proper Unicode BiDi rendering.
# Falls back to a simple reversal that works for pure Hebrew text.
try:
    from bidi.algorithm import get_display as _bidi_get_display
    _USE_BIDI = True
except ImportError:
    _USE_BIDI = False


def _has_raqm() -> bool:
    """Return True if Pillow was built with libraqm (native BiDi/RTL support)."""
    try:
        if hasattr(pil_features, "check_feature"):
            return bool(pil_features.check_feature("raqm"))
        if hasattr(pil_features, "check"):
            return bool(pil_features.check("raqm"))
    except Exception:
        return False
    return False


_USE_PIL_RTL = _has_raqm()


# ============================================================
#  PARASHA METADATA
# ============================================================

PARASHA_KEYS = ["kadesh", "vehaya_ki_yeviacha", "shema", "vehaya_im_shamoa"]

PARASHOT_NAMES = {
    "kadesh":               "קדש (שמות יג:א-י)",
    "vehaya_ki_yeviacha":   "והיה כי יביאך (שמות יג:יא-טז)",
    "shema":                "שמע (דברים ו:ד-ט)",
    "vehaya_im_shamoa":     "והיה אם שמוע (דברים יא:יג-כא)",
    "mezuzah":              "מזוזה (שמע + והיה אם שמוע)",
}

# Sefaria API references for each parasha
SEFARIA_REFS = {
    "kadesh":               "Exodus.13.1-10",
    "vehaya_ki_yeviacha":   "Exodus.13.11-16",
    "shema":                "Deuteronomy.6.4-9",
    "vehaya_im_shamoa":     "Deuteronomy.11.13-21",
}

# ============================================================
#  NIKKUD / CANTILLATION STRIPPING
# ============================================================

# Unicode ranges to strip from Sefaria text:
#   U+0591–U+05AF  cantillation (te'amim)
#   U+05B0–U+05BC  nikkud (vowel points)
#   U+05C1–U+05C2  shin/sin dot
#   U+05C7         qamats qatan
#
# Important: keep U+05BE (maqaf) so it can later become a word boundary
# instead of fusing words together (e.g. "אל־משה" -> "אל משה").
_STRIP_CHARS = frozenset(
    list(range(0x0591, 0x05B0))
    + list(range(0x05B0, 0x05BD))
    + list(range(0x05C1, 0x05C3))
    + [0x05C7]
)


def strip_nikkud(text: str) -> str:
    """Remove nikkud and cantillation marks, keeping consonants only."""
    return "".join(ch for ch in text if ord(ch) not in _STRIP_CHARS)


# ============================================================
#  STA"M SPELLING OVERRIDES
#
#  Sefaria follows the standard Masoretic/printed Tanakh, which can differ
#  from the plene/defective (male/chaser) conventions used on actual STA"M
#  parchments. List known deviations here as { word_index: "corrected" }.
#
#  IMPORTANT: Verify every entry against a trusted printed Tikkun Soferim
#  before relying on this script for serious practice.
#  The entries below are *placeholder examples* — fill them in after
#  cross-checking your edition.
# ============================================================

STAM_SPELLING_OVERRIDES: Dict[str, Dict[int, str]] = {
    "kadesh": {
        # TODO: verify against Tikkun Soferim.
        # Example (check index and spelling):
        # 43: "יצאים",   # Shemot 13:4 — STA"M sometimes omits the vav
    },
    "vehaya_ki_yeviacha": {
        # TODO: verify against Tikkun Soferim.
    },
    "shema": {
        # TODO: verify against Tikkun Soferim.
        # Devarim 6:8 — STA"M: "לטטפת" (defective, no vav); Sefaria: "לְטֹטָפֹת"
        # The fallback already uses "לטטפת"; confirm Sefaria index if fetching live.
    },
    "vehaya_im_shamoa": {
        # TODO: verify against Tikkun Soferim.
        # Devarim 11:18 — STA"M: "לטוטפת" (plene, with vav); confirm if Sefaria differs.
    },
}

# ============================================================
#  TEXT LOADING (Sefaria API → cache → local fallback)
# ============================================================

SCRIPT_DIR   = pathlib.Path(__file__).parent
FALLBACK_FILE = SCRIPT_DIR / "parashot_fallback.json"
CACHE_FILE    = SCRIPT_DIR / "parashot_cache.json"
CACHE_FORMAT_VERSION = 5


def _load_json(path: pathlib.Path) -> Optional[Dict]:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_json(path: pathlib.Path, data: Dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _is_cache_valid(cached: Optional[Dict]) -> bool:
    """Validate cache shape/version so stale formats are automatically refreshed."""
    if not isinstance(cached, dict):
        return False
    meta = cached.get("_meta", {})
    if not isinstance(meta, dict):
        return False
    if meta.get("format_version") != CACHE_FORMAT_VERSION:
        return False
    for k in PARASHA_KEYS:
        words = cached.get(k)
        if not isinstance(words, list) or not words or not all(isinstance(w, str) for w in words):
            return False
    return True


def _fetch_sefaria(ref: str) -> List[str]:
    """Fetch one parasha from Sefaria API; return clean word list."""
    import re
    url = f"https://www.sefaria.org/api/texts/{ref}?lang=he&context=0"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    he = data.get("he", "")
    if isinstance(he, list):
        # List of verse strings
        he = " ".join(v for v in he if isinstance(v, str))

    # Remove annotation blocks entirely (not part of the verse text).
    he = re.sub(r"<sup[^>]*>.*?</sup>", " ", he, flags=re.IGNORECASE | re.DOTALL)
    he = re.sub(r"<i[^>]*>.*?</i>", " ", he, flags=re.IGNORECASE | re.DOTALL)
    he = re.sub(r"<span[^>]*>.*?</span>", " ", he, flags=re.IGNORECASE | re.DOTALL)

    # Strip nikkud/cantillation and normalize separators.
    clean = strip_nikkud(he)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = html.unescape(clean)
    clean = re.sub(r"\{[^}]*\}", " ", clean)

    # Treat maqaf and sof pasuq as explicit word boundaries.
    clean = clean.replace("־", " ")
    clean = clean.replace("׃", " ")

    # Remove all other non-Hebrew artifacts (HTML leftovers, bidi marks, punctuation)
    # without introducing extra splits inside words.
    clean = re.sub(r"[^\u05d0-\u05ea\s]", "", clean)

    clean = re.sub(r"\s+", " ", clean).strip()
    return clean.split()


def _apply_overrides(data: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Apply STAM_SPELLING_OVERRIDES to a word-list dict."""
    result = {}
    for key, words in data.items():
        overrides = STAM_SPELLING_OVERRIDES.get(key, {})
        words = list(words)
        for idx, correct in overrides.items():
            if 0 <= idx < len(words):
                words[idx] = correct
        result[key] = words
    return result


def load_parashot() -> Dict[str, List[str]]:
    """
    Load all four parashot as word lists.

    Priority order:
      1. Local cache (parashot_cache.json) — used if complete.
      2. Sefaria API — fetched on first run, then cached.
      3. Bundled fallback (parashot_fallback.json) — used if API unreachable.

    STAM_SPELLING_OVERRIDES are applied after loading.
    """
    # 1. Cache
    cached = _load_json(CACHE_FILE)
    if _is_cache_valid(cached):
        print("[INFO] Loaded parashot text from local cache.")
        return _apply_overrides({k: cached[k] for k in PARASHA_KEYS})

    # 2. Sefaria API
    fetched: Dict[str, List[str]] = {}
    try:
        for key, ref in SEFARIA_REFS.items():
            fetched[key] = _fetch_sefaria(ref)
        cache_payload = {
            "_meta": {
                "format_version": CACHE_FORMAT_VERSION,
                "source": "sefaria",
            }
        }
        cache_payload.update(fetched)
        _save_json(CACHE_FILE, cache_payload)
        print(f"[INFO] Fetched parashot from Sefaria; cached to {CACHE_FILE}")
        return _apply_overrides(fetched)
    except Exception as exc:
        print(f"[WARNING] Sefaria API unavailable ({exc}); using bundled fallback text.")

    # 3. Fallback
    fallback = _load_json(FALLBACK_FILE)
    if not fallback:
        sys.exit(f"ERROR: Bundled fallback text not found at {FALLBACK_FILE}")
    missing = [k for k in PARASHA_KEYS if k not in fallback]
    if missing:
        sys.exit(f"ERROR: Fallback file missing parashot: {missing}")
    return _apply_overrides({k: fallback[k] for k in PARASHA_KEYS})


# ============================================================
#  HOLY NAME DETECTION
# ============================================================

# Words in these parashot whose modification must be flagged as HOLY_NAME severity.
# (Note: "אלהים" in Devarim 11:16 refers to foreign gods — not included here.)
HOLY_NAMES: frozenset = frozenset({
    "יהוה",
    "אלהינו",   # Shema: our God
    "אלהיך",    # Devarim: your God (sg.)
    "אלהיכם",   # Devarim: your God (pl.)
})


def is_holy(word: str) -> bool:
    """Return True if the word is a Divine Name in these parashot."""
    return word in HOLY_NAMES


# ============================================================
#  ERROR TAXONOMY
# ============================================================

class ErrorType(Enum):
    MISSING_LETTER             = "MISSING_LETTER"
    EXTRA_LETTER               = "EXTRA_LETTER"
    MALE_CHASER_SWAP           = "MALE_CHASER_SWAP"
    SIMILAR_LETTER_SWAP        = "SIMILAR_LETTER_SWAP"
    LETTER_TRANSPOSITION       = "LETTER_TRANSPOSITION"
    WORD_BOUNDARY_ERROR        = "WORD_BOUNDARY_ERROR"
    SKIP_DUE_TO_SIMILARITY     = "SKIP_DUE_TO_SIMILARITY"
    WORD_DUPLICATION           = "WORD_DUPLICATION"
    SIMILAR_FUNCTION_WORD_SWAP = "SIMILAR_FUNCTION_WORD_SWAP"
    SUFFIX_ERROR               = "SUFFIX_ERROR"


@dataclass
class ErrorRecord:
    error_type: ErrorType
    parasha_key: str
    original_word: str        # original word or phrase
    modified_word: str        # what it became
    word_index: int           # 0-based position in the original word list
    context_before: List[str] # up to 2 words before
    context_after: List[str]  # up to 2 words after
    is_holy_name: bool = False
    extra_info: str = ""

    def describe(self) -> str:
        holy_flag  = "  ⚠  HOLY_NAME — extra care required\n" if self.is_holy_name else ""
        ctx_before = " ".join(self.context_before)
        ctx_after  = " ".join(self.context_after)
        location   = (
            f"word #{self.word_index + 1}"
            + (f", after: «{ctx_before}»" if ctx_before else "")
            + (f", before: «{ctx_after}»" if ctx_after else "")
        )
        lines = [
            f"  Error type : {self.error_type.value}",
            f"  Changed    : «{self.original_word}» → «{self.modified_word}»",
            f"  Location   : {location}",
        ]
        if self.extra_info:
            lines.append(f"  Detail     : {self.extra_info}")
        if holy_flag:
            lines.append(holy_flag.strip())
        return "\n".join(lines)


# ---- Shared helpers ----

def _context(words: List[str], idx: int, n: int = 2) -> Tuple[List[str], List[str]]:
    before = words[max(0, idx - n): idx]
    after  = words[idx + 1: idx + 1 + n]
    return before, after


def _eligible(words: List[str], min_len: int = 3) -> List[int]:
    """Indices of words with at least min_len characters."""
    return [i for i, w in enumerate(words) if len(w) >= min_len]


# ---- 1. MISSING_LETTER ----

def inject_missing_letter(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Remove one letter from a word; prefer words with duplicate adjacent letters."""
    indices = _eligible(words, min_len=3)
    rng.shuffle(indices)
    for idx in indices:
        word = words[idx]
        # Prefer positions where adjacent letters are the same
        dup_pos = [i for i in range(len(word) - 1) if word[i] == word[i + 1]]
        if HARD_MODE and not dup_pos:
            # In hard mode, avoid conspicuous deletions from arbitrary locations.
            continue
        pos = rng.choice(dup_pos) if dup_pos else rng.randint(0, len(word) - 1)
        new_word = word[:pos] + word[pos + 1:]
        if new_word and new_word != word:
            modified = list(words)
            modified[idx] = new_word
            before, after = _context(words, idx)
            return modified, ErrorRecord(
                error_type=ErrorType.MISSING_LETTER,
                parasha_key="",
                original_word=word,
                modified_word=new_word,
                word_index=idx,
                context_before=before,
                context_after=after,
                is_holy_name=is_holy(word),
                extra_info=f"removed '{word[pos]}' at position {pos + 1}",
            )
    raise RuntimeError("inject_missing_letter: no eligible word found")


# ---- 2. EXTRA_LETTER ----

def inject_extra_letter(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Duplicate one letter within a word."""
    indices = _eligible(words, min_len=2)
    rng.shuffle(indices)
    for idx in indices:
        word = words[idx]
        pos = rng.randint(0, len(word) - 1)
        new_word = word[: pos + 1] + word[pos] + word[pos + 1:]
        modified = list(words)
        modified[idx] = new_word
        before, after = _context(words, idx)
        return modified, ErrorRecord(
            error_type=ErrorType.EXTRA_LETTER,
            parasha_key="",
            original_word=word,
            modified_word=new_word,
            word_index=idx,
            context_before=before,
            context_after=after,
            is_holy_name=is_holy(word),
            extra_info=f"duplicated '{word[pos]}' at position {pos + 1}",
        )
    raise RuntimeError("inject_extra_letter: no eligible word found")


# ---- 3. MALE_CHASER_SWAP ----

def inject_male_chaser_swap(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Toggle a ו or י in/out of a word (plene ↔ defective)."""
    indices = _eligible(words, min_len=3)
    rng.shuffle(indices)
    for idx in indices:
        word = words[idx]
        # Interior positions only (not first or last character)
        interior = [
            i for i, c in enumerate(word)
            if c in ("ו", "י") and 0 < i < len(word) - 1
        ]
        if interior:
            pos = rng.choice(interior)
            new_word = word[:pos] + word[pos + 1:]
            detail = f"removed '{word[pos]}' at position {pos + 1} (plene → defective)"
        else:
            # Insert a ו or י in the interior of the word
            mid = len(word) // 2
            letter = rng.choice(["ו", "י"])
            new_word = word[:mid] + letter + word[mid:]
            detail = f"inserted '{letter}' at position {mid + 1} (defective → plene)"
        if new_word != word:
            modified = list(words)
            modified[idx] = new_word
            before, after = _context(words, idx)
            return modified, ErrorRecord(
                error_type=ErrorType.MALE_CHASER_SWAP,
                parasha_key="",
                original_word=word,
                modified_word=new_word,
                word_index=idx,
                context_before=before,
                context_after=after,
                is_holy_name=is_holy(word),
                extra_info=detail,
            )
    raise RuntimeError("inject_male_chaser_swap: no eligible word found")


# ---- 4. SIMILAR_LETTER_SWAP ----

# Visually similar Hebrew letter groups (STA"M-relevant pairs)
SIMILAR_LETTER_GROUPS = [
    ["ד", "ר"],
    ["ה", "ח"],
    ["ו", "ז", "י"],
    ["כ", "ב", "פ", "ך", "ף"],
    ["ם", "ס"],
    ["ע", "צ", "ץ"],
    ["ג", "נ", "ן"],
]

_SIMILAR_MAP: Dict[str, List[str]] = {}
for _grp in SIMILAR_LETTER_GROUPS:
    for _c in _grp:
        _SIMILAR_MAP[_c] = [x for x in _grp if x != _c]


def inject_similar_letter_swap(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Replace a letter with a visually similar one from the pair pool."""
    indices = _eligible(words, min_len=2)
    rng.shuffle(indices)
    for idx in indices:
        word = words[idx]
        swappable = [(i, c) for i, c in enumerate(word) if c in _SIMILAR_MAP]
        if not swappable:
            continue
        rng.shuffle(swappable)
        for pos, orig_ch in swappable:
            new_ch = rng.choice(_SIMILAR_MAP[orig_ch])
            new_word = word[:pos] + new_ch + word[pos + 1:]
            if new_word != word:
                modified = list(words)
                modified[idx] = new_word
                before, after = _context(words, idx)
                return modified, ErrorRecord(
                    error_type=ErrorType.SIMILAR_LETTER_SWAP,
                    parasha_key="",
                    original_word=word,
                    modified_word=new_word,
                    word_index=idx,
                    context_before=before,
                    context_after=after,
                    is_holy_name=is_holy(word),
                    extra_info=f"replaced '{orig_ch}' with '{new_ch}' at position {pos + 1}",
                )
    raise RuntimeError("inject_similar_letter_swap: no eligible word found")


# ---- 5. LETTER_TRANSPOSITION ----

def inject_letter_transposition(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Swap two adjacent, distinct letters within a word."""
    indices = _eligible(words, min_len=3)
    rng.shuffle(indices)
    for idx in indices:
        word = words[idx]
        pairs = [
            (i, i + 1) for i in range(len(word) - 1)
            if word[i] != word[i + 1]
        ]
        if not pairs:
            continue
        i, j = rng.choice(pairs)
        new_word = word[:i] + word[j] + word[i] + word[j + 1:]
        modified = list(words)
        modified[idx] = new_word
        before, after = _context(words, idx)
        return modified, ErrorRecord(
            error_type=ErrorType.LETTER_TRANSPOSITION,
            parasha_key="",
            original_word=word,
            modified_word=new_word,
            word_index=idx,
            context_before=before,
            context_after=after,
            is_holy_name=is_holy(word),
            extra_info=f"transposed '{word[i]}' and '{word[j]}' at positions {i + 1}–{j + 1}",
        )
    raise RuntimeError("inject_letter_transposition: no eligible word found")


# ---- 6. WORD_BOUNDARY_ERROR ----

def inject_word_boundary_error(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Merge two adjacent words or split one word in two."""
    if rng.random() < 0.5 and len(words) > 2:
        # Merge
        idx = rng.randint(0, len(words) - 2)
        merged = words[idx] + words[idx + 1]
        modified = words[:idx] + [merged] + words[idx + 2:]
        orig_phrase = f"{words[idx]} {words[idx + 1]}"
        before, after = _context(words, idx)
        return modified, ErrorRecord(
            error_type=ErrorType.WORD_BOUNDARY_ERROR,
            parasha_key="",
            original_word=orig_phrase,
            modified_word=merged,
            word_index=idx,
            context_before=before,
            context_after=after,
            is_holy_name=is_holy(words[idx]) or is_holy(words[idx + 1]),
            extra_info=f"merged '{words[idx]}' + '{words[idx + 1]}'",
        )
    else:
        # Split
        indices = _eligible(words, min_len=4)
        if not indices:
            raise RuntimeError("inject_word_boundary_error: no word long enough to split")
        idx = rng.choice(indices)
        word = words[idx]
        split_at = rng.randint(1, len(word) - 1)
        part1, part2 = word[:split_at], word[split_at:]
        modified = words[:idx] + [part1, part2] + words[idx + 1:]
        before, after = _context(words, idx)
        return modified, ErrorRecord(
            error_type=ErrorType.WORD_BOUNDARY_ERROR,
            parasha_key="",
            original_word=word,
            modified_word=f"{part1} {part2}",
            word_index=idx,
            context_before=before,
            context_after=after,
            is_holy_name=is_holy(word),
            extra_info=f"split at position {split_at}: '{part1}' + '{part2}'",
        )


# ---- 7. SKIP_DUE_TO_SIMILARITY ----

def inject_skip_due_to_similarity(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """
    Simulate an eye-skip (homoeoteleuton): find two occurrences of the same word
    within a window and delete the span between them (inclusive of the first copy).
    Only applied where the text actually has such repetition.
    """
    window = 15
    # Build shuffled list of candidate anchor positions
    positions = list(range(len(words)))
    rng.shuffle(positions)
    for start in positions:
        anchor = words[start]
        if len(anchor) < 2:
            continue
        end_limit = min(start + window, len(words))
        for end in range(start + 2, end_limit):
            if words[end] == anchor:
                # Delete words[start+1 : end+1], keeping the second occurrence
                span = words[start + 1: end + 1]
                modified = words[: start + 1] + words[end + 1:]
                deleted_text = " ".join(span)
                before, after = _context(words, start)
                return modified, ErrorRecord(
                    error_type=ErrorType.SKIP_DUE_TO_SIMILARITY,
                    parasha_key="",
                    original_word=deleted_text,
                    modified_word="[skipped]",
                    word_index=start,
                    context_before=before,
                    context_after=after,
                    is_holy_name=any(is_holy(w) for w in span),
                    extra_info=(
                        f"eye-skip on '{anchor}' "
                        f"(positions {start + 1} and {end + 1}); "
                        f"deleted {len(span)} word(s)"
                    ),
                )
    # Fallback: delete a single word
    idx = rng.randint(1, len(words) - 2)
    modified = list(words)
    del modified[idx]
    before, after = _context(words, idx)
    return modified, ErrorRecord(
        error_type=ErrorType.SKIP_DUE_TO_SIMILARITY,
        parasha_key="",
        original_word=words[idx],
        modified_word="[skipped]",
        word_index=idx,
        context_before=before,
        context_after=after,
        is_holy_name=is_holy(words[idx]),
        extra_info="fallback: single word deletion (no suitable repeated word found)",
    )


# ---- 8. WORD_DUPLICATION ----

def inject_word_duplication(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Duplicate a word or a short word sequence."""
    if rng.random() < 0.3 and len(words) > 3:
        # Duplicate a 2-word sequence
        idx = rng.randint(0, len(words) - 2)
        seq = words[idx: idx + 2]
        modified = words[: idx + 2] + seq + words[idx + 2:]
        phrase = " ".join(seq)
        before, after = _context(words, idx)
        return modified, ErrorRecord(
            error_type=ErrorType.WORD_DUPLICATION,
            parasha_key="",
            original_word=phrase,
            modified_word=f"{phrase} {phrase}",
            word_index=idx,
            context_before=before,
            context_after=after,
            is_holy_name=any(is_holy(w) for w in seq),
            extra_info=f"duplicated 2-word sequence: '{phrase}'",
        )
    else:
        idx = rng.randint(0, len(words) - 1)
        word = words[idx]
        modified = words[: idx + 1] + [word] + words[idx + 1:]
        before, after = _context(words, idx)
        return modified, ErrorRecord(
            error_type=ErrorType.WORD_DUPLICATION,
            parasha_key="",
            original_word=word,
            modified_word=f"{word} {word}",
            word_index=idx,
            context_before=before,
            context_after=after,
            is_holy_name=is_holy(word),
            extra_info=f"duplicated word: '{word}'",
        )


# ---- 9. SIMILAR_FUNCTION_WORD_SWAP ----

# Pairs of function words from these four parashot that differ by one letter.
# Listed as (original, replacement); both directions included.
FUNCTION_WORD_SWAP_PAIRS: List[Tuple[str, str]] = [
    ("כי",  "כן"),
    ("כן",  "כי"),
    ("אל",  "על"),
    ("על",  "אל"),
    ("לך",  "לו"),
    ("לו",  "לך"),
    ("בם",  "בן"),
    ("בן",  "בם"),
    ("לא",  "לו"),
    ("לו",  "לא"),
    ("הם",  "הן"),
    ("הן",  "הם"),
    ("אם",  "את"),
    ("את",  "אם"),
    ("מה",  "מי"),
    ("מי",  "מה"),
    ("זה",  "זו"),
    ("זו",  "זה"),
    ("בך",  "בם"),
    ("בם",  "בך"),
    ("בו",  "בך"),
    ("בך",  "בו"),
]

_FUNC_MAP: Dict[str, List[str]] = {}
for _orig, _repl in FUNCTION_WORD_SWAP_PAIRS:
    _FUNC_MAP.setdefault(_orig, []).append(_repl)


def inject_similar_function_word_swap(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Replace a short function word with a near-identical alternative."""
    candidates = [(i, w) for i, w in enumerate(words) if w in _FUNC_MAP]
    if not candidates:
        # Fallback to a letter swap
        return inject_similar_letter_swap(words, rng)
    rng.shuffle(candidates)
    idx, word = candidates[0]
    new_word = rng.choice(_FUNC_MAP[word])
    modified = list(words)
    modified[idx] = new_word
    before, after = _context(words, idx)
    return modified, ErrorRecord(
        error_type=ErrorType.SIMILAR_FUNCTION_WORD_SWAP,
        parasha_key="",
        original_word=word,
        modified_word=new_word,
        word_index=idx,
        context_before=before,
        context_after=after,
        is_holy_name=is_holy(word) or is_holy(new_word),
        extra_info=f"swapped function word '{word}' → '{new_word}'",
    )


# ---- 10. SUFFIX_ERROR ----

# (old_suffix, new_suffix) pairs — only applied when the word ends with old_suffix
# and has additional characters before it.
SUFFIX_SWAP_PAIRS: List[Tuple[str, str]] = [
    ("ך",   "כם"),   # 2nd sg m. → 2nd pl. m.
    ("כם",  "ך"),
    ("ך",   "כן"),   # 2nd sg m. → 2nd pl. f.
    ("כן",  "ך"),
    ("ם",   "ן"),    # final-mem → final-nun (masc. → fem. or sg. ending)
    ("ן",   "ם"),
    ("ים",  "ות"),   # masc. pl. → fem. pl.
    ("ות",  "ים"),
    ("נו",  "כם"),   # 1st pl. → 2nd pl.
    ("כם",  "נו"),
    ("ך",   "ו"),    # 2nd sg. → 3rd sg. m.
    ("ו",   "ך"),
    ("ה",   "י"),    # 3rd sg. f. → 1st sg.
    ("י",   "ה"),
    ("כם",  "הם"),   # 2nd pl. → 3rd pl.
    ("הם",  "כם"),
]


def inject_suffix_error(
    words: List[str], rng: random.Random
) -> Tuple[List[str], ErrorRecord]:
    """Modify a word's suffix (e.g., pronominal or number suffix)."""
    indices = _eligible(words, min_len=3)
    rng.shuffle(indices)
    # Shuffle the suffix pairs for variety
    pairs = list(SUFFIX_SWAP_PAIRS)
    rng.shuffle(pairs)
    for idx in indices:
        word = words[idx]
        for old_suf, new_suf in pairs:
            if word.endswith(old_suf) and len(word) > len(old_suf):
                new_word = word[: -len(old_suf)] + new_suf
                if new_word != word:
                    modified = list(words)
                    modified[idx] = new_word
                    before, after = _context(words, idx)
                    return modified, ErrorRecord(
                        error_type=ErrorType.SUFFIX_ERROR,
                        parasha_key="",
                        original_word=word,
                        modified_word=new_word,
                        word_index=idx,
                        context_before=before,
                        context_after=after,
                        is_holy_name=is_holy(word),
                        extra_info=f"suffix changed: '-{old_suf}' → '-{new_suf}'",
                    )
    raise RuntimeError("inject_suffix_error: no eligible word found")


# ---- Injector dispatch table ----

ERROR_INJECTORS = {
    ErrorType.MISSING_LETTER:             inject_missing_letter,
    ErrorType.EXTRA_LETTER:               inject_extra_letter,
    ErrorType.MALE_CHASER_SWAP:           inject_male_chaser_swap,
    ErrorType.SIMILAR_LETTER_SWAP:        inject_similar_letter_swap,
    ErrorType.LETTER_TRANSPOSITION:       inject_letter_transposition,
    ErrorType.WORD_BOUNDARY_ERROR:        inject_word_boundary_error,
    ErrorType.SKIP_DUE_TO_SIMILARITY:     inject_skip_due_to_similarity,
    ErrorType.WORD_DUPLICATION:           inject_word_duplication,
    ErrorType.SIMILAR_FUNCTION_WORD_SWAP: inject_similar_function_word_swap,
    ErrorType.SUFFIX_ERROR:               inject_suffix_error,
}


# ============================================================
#  RTL TEXT RENDERING
# ============================================================

def _to_visual(word: str) -> str:
    """
    Convert a single Hebrew word to its visual (display) form for PIL rendering.

    Pillow renders text left-to-right without applying the Unicode BiDi algorithm.
    For correct Hebrew display we therefore need characters in visual (reversed)
    order before handing them to PIL.

    If python-bidi is installed, use its conformant implementation.
    Otherwise, fall back to a simple character reversal which is correct for
    pure Hebrew text with no mixed scripts.
    """
    if _USE_PIL_RTL:
        return word
    if _USE_BIDI:
        return _bidi_get_display(word)
    return word[::-1]


def _wrap_words_to_lines(
    words: List[str],
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> List[str]:
    """
    Wrap *words* (in logical Hebrew reading order) into display lines that
    each fit within *max_width* pixels.

    Returns a list of strings already in visual (display) order: word order
    is reversed within each line so that PIL's left-to-right rendering
    produces correct right-to-left reading.
    """
    lines: List[str] = []
    current: List[str] = []          # accumulates words in reading order
    current_w: float = 0.0
    space_w: float = font.getlength(" ")

    for word in words:
        ww = font.getlength(word)
        add_w = ww if not current else ww + space_w
        if current and current_w + add_w > max_width:
            if _USE_PIL_RTL:
                # Keep logical order; Pillow+libraqm handles RTL display.
                lines.append(" ".join(current))
            else:
                # Manual fallback when native RTL shaping isn't available.
                lines.append(" ".join(_to_visual(w) for w in reversed(current)))
            current = [word]
            current_w = ww
        else:
            current.append(word)
            current_w += add_w

    if current:
        if _USE_PIL_RTL:
            lines.append(" ".join(current))
        else:
            lines.append(" ".join(_to_visual(w) for w in reversed(current)))

    return lines


def render_text_image(
    words: List[str],
    test_num: int,
    paragraph_break_indices: Optional[List[int]] = None,
) -> Image.Image:
    """Render a Hebrew word list as a PIL Image with a test-number header/footer."""
    font       = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    # The STA"M font may not contain Latin glyphs for the "Test NN" label.
    label_size = max(16, FONT_SIZE // 2)
    if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", label_size)
    else:
        small_font = ImageFont.truetype(FONT_PATH, label_size)

    usable_w = IMAGE_WIDTH - 2 * IMAGE_MARGIN

    # Split into display paragraphs (used for mezuzah mode: Shema + Vehaya im shamoa).
    paragraphs: List[List[str]] = []
    if paragraph_break_indices:
        points = sorted({p for p in paragraph_break_indices if 0 < p < len(words)})
        start = 0
        for p in points:
            if p > start:
                paragraphs.append(words[start:p])
            start = p
        if start < len(words):
            paragraphs.append(words[start:])
    else:
        paragraphs = [words]

    lines: List[Optional[str]] = []
    for i, paragraph in enumerate(paragraphs):
        lines.extend(_wrap_words_to_lines(paragraph, font, usable_w))
        if i < len(paragraphs) - 1:
            lines.append(None)

    line_h   = int(FONT_SIZE * LINE_SPACING)
    header_h = int(FONT_SIZE * 1.5)
    footer_h = int(FONT_SIZE * 1.2)
    paragraph_gap_h = int(line_h * 0.9)
    body_h   = sum(line_h if line is not None else paragraph_gap_h for line in lines)
    total_h  = header_h + body_h + footer_h + 2 * IMAGE_MARGIN

    img  = Image.new("RGB", (IMAGE_WIDTH, total_h), "white")
    draw = ImageDraw.Draw(img)

    label = f"Test {test_num:02d}"

    # ---- Header (centred) ----
    draw.text(
        (IMAGE_WIDTH // 2, IMAGE_MARGIN // 2 + header_h // 4),
        label,
        fill="black",
        font=small_font,
        anchor="mt",
    )

    # ---- Body (right-aligned Hebrew lines) ----
    y = IMAGE_MARGIN + header_h
    for line in lines:
        if line is None:
            y += paragraph_gap_h
            continue
        if _USE_PIL_RTL:
            draw.text(
                (IMAGE_WIDTH - IMAGE_MARGIN, y),
                line,
                fill="black",
                font=font,
                anchor="ra",
                direction="rtl",
                language="he",
            )
        else:
            line_w = font.getlength(line)
            x = IMAGE_WIDTH - IMAGE_MARGIN - line_w
            draw.text((x, y), line, fill="black", font=font, anchor="lt")
        y += line_h

    # ---- Footer (centred, gray) ----
    draw.text(
        (IMAGE_WIDTH // 2, y + footer_h // 4),
        label,
        fill=(150, 150, 150),
        font=small_font,
        anchor="mt",
    )

    return img


# ============================================================
#  ANSWER KEY
# ============================================================

def write_answer_key(
    records: List[Tuple[int, str, List[ErrorRecord]]],
    output_dir: pathlib.Path,
) -> pathlib.Path:
    key_path = output_dir / "answer_key.txt"
    with key_path.open("w", encoding="utf-8") as fh:
        fh.write('STA"M PROOFREADING PRACTICE — ANSWER KEY\n')
        fh.write("=" * 60 + "\n\n")
        for test_num, pk, errors in records:
            fh.write(f"TEST {test_num:02d}\n")
            fh.write("-" * 40 + "\n")
            fh.write(f"  Parasha : {PARASHOT_NAMES[pk]}\n")
            for rec in errors:
                fh.write(rec.describe() + "\n")
            fh.write("\n")
    return key_path


# ============================================================
#  GENERATION LOOP
# ============================================================

def generate_all(
    parashot: Dict[str, List[str]],
    rng: random.Random,
    output_dir: pathlib.Path,
) -> List[Tuple[int, str, List[ErrorRecord]]]:
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    enabled: List[ErrorType] = (
        [ErrorType(t) if isinstance(t, str) else t for t in ERROR_TYPES]
        if ERROR_TYPES is not None
        else list(ErrorType)
    )
    if HARD_MODE:
        hard_set = set(HARD_ERROR_TYPES)
        enabled = [etype for etype in enabled if etype.value in hard_set]
    if not enabled:
        sys.exit("ERROR: no enabled error types after filtering.")

    records: List[Tuple[int, str, List[ErrorRecord]]] = []

    for i in range(NUM_TEXTS):
        test_num = i + 1
        break_points: List[int] = []
        if TEXT_MODE == "MEZUZAH_ONLY":
            pk = "mezuzah"
            shema_words = list(parashot["shema"])
            vehaya_words = list(parashot["vehaya_im_shamoa"])
            words = shema_words + vehaya_words
            if MEZUZAH_BREAK_BETWEEN_PARASHOT:
                break_points = [len(shema_words)]
        else:
            # Cycle through parashot in order for balanced distribution
            pk = PARASHA_KEYS[i % len(PARASHA_KEYS)]
            words = list(parashot[pk])

        errors_applied: List[ErrorRecord] = []
        for _ in range(ERRORS_PER_TEXT):
            etype = rng.choice(enabled)
            injector = ERROR_INJECTORS[etype]
            try:
                words, rec = injector(words, rng)
            except RuntimeError as exc:
                fallback = inject_similar_letter_swap if HARD_MODE else inject_missing_letter
                print(f"  [WARN] test {test_num} — {exc}; falling back to {fallback.__name__}")
                words, rec = fallback(words, rng)
            rec.parasha_key = pk
            errors_applied.append(rec)

        img = render_text_image(words, test_num, paragraph_break_indices=break_points)
        img_path = images_dir / f"test_{test_num:02d}.png"
        img.save(str(img_path))

        records.append((test_num, pk, errors_applied))
        print(
            f"  test_{test_num:02d}.png  "
            f"[{PARASHOT_NAMES[pk]}]  "
            f"error: {errors_applied[0].error_type.value}"
        )

    return records


# ============================================================
#  MAIN
# ============================================================

def main() -> None:
    rng = random.Random(RANDOM_SEED)

    # Recreate output directory (idempotent)
    out = pathlib.Path(OUTPUT_DIR)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    print("[INFO] Loading parashot text …")
    parashot = load_parashot()
    print(
        "[INFO] Word counts: "
        + ", ".join(f"{k}={len(v)}" for k, v in parashot.items())
    )

    print(f"\n[INFO] Generating {NUM_TEXTS} worksheets …")
    records = generate_all(parashot, rng, out)

    key_path = write_answer_key(records, out)
    print(f"\n[INFO] Answer key → {key_path}")

    # Console summary
    print("\n" + "=" * 55)
    print(f"  Done!  Generated {NUM_TEXTS} worksheets.")
    print(f"  Output directory : {out.resolve()}")
    print(f"    images/        : test_01.png … test_{NUM_TEXTS:02d}.png")
    print(f"    answer_key.txt : {key_path.name}")
    print("=" * 55)


if __name__ == "__main__":
    main()
