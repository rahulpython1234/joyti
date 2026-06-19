"""
Content growth pipeline for Jain Jyotish verse library.

DESIGN PRINCIPLE — READ THIS BEFORE MODIFYING:

This app makes spiritual and religious claims to real users. Every verse that
appears in the reading is presented as authentic Agamic scripture. Therefore:

  - Automatic web scraping that inserts text directly into VERSE_LIBRARY
    without human review is PROHIBITED. Scraped text cannot be guaranteed to
    be accurate, correctly attributed, or even genuinely Jain.

  - AI-generated verse text "in the style of" authentic Jain sutras is
    fabrication. Presenting it as authentic Agamic scripture would mislead
    practitioners about the provenance of spiritual teaching. This is
    explicitly prohibited.

  - Scheduled auto-publishing of pending content is PROHIBITED. Human review
    must gate every addition.

The correct workflow is:
  1. Find a verse in a reliable printed or scholarly source.
  2. Call propose_verse() with the candidate text.
  3. Review all pending verses via GET /admin/pending-content.
  4. If the verse is authentic and correctly attributed, call approve_verse()
     with the correct verse_key — this writes it to verified_verses.json.
  5. Restart the Render service — main.py loads verified_verses.json at
     startup and merges entries into the live VERSE_LIBRARY.

This pipeline exists precisely so the growth process remains slow, deliberate,
and human-verified. The app's integrity depends on it.
"""

import json
from pathlib import Path

# Path to the on-disk verified verse store, relative to this file.
VERIFIED_FILE = Path(__file__).parent / "verified_verses.json"

# In-memory queue of proposed verses awaiting human review.
# Reset on every service restart — proposals are not persisted between restarts
# by design, because they have not been verified yet.
PENDING_CONTENT: list[dict] = []


def propose_verse(
    source: str,
    transliteration: str,
    meaning: str,
    theme: str,
    submitted_by: str = "manual",
) -> dict:
    """
    Add a candidate verse to PENDING_CONTENT for human review.

    Does NOT insert into VERSE_LIBRARY. Does NOT write to disk.
    The only side effect is appending to the in-memory PENDING_CONTENT list,
    which is visible at GET /admin/pending-content until the service restarts.

    Args:
        source:           Full attribution string, e.g.
                          "Tattvartha Sutra 5.21 (Umasvati)"
        transliteration:  Romanised Prakrit or Sanskrit transliteration.
        meaning:          English explanation of the verse's doctrinal content.
        theme:            One of: Ahimsa, Karma, Leshya, Moksha, Nirjara,
                          Pudgala, Samyak-Darshana, Samyak-Jnana, or similar.
        submitted_by:     Free-form attribution for the proposal (e.g. your name,
                          "manual", or a source reference).

    Returns:
        The entry dict that was appended to PENDING_CONTENT.
    """
    entry = {
        "source": source,
        "transliteration": transliteration,
        "meaning": meaning,
        "theme": theme,
        "status": "pending_review",
        "submitted_by": submitted_by,
    }
    PENDING_CONTENT.append(entry)
    return entry


def approve_verse(index: int, verse_key: str) -> dict:
    """
    Move a pending verse into verified_verses.json after human verification.

    Call this ONLY after personally confirming:
      (a) The source is a real, citable Jain text.
      (b) The transliteration is accurate.
      (c) The meaning faithfully reflects the original doctrine.

    This function pops the entry from PENDING_CONTENT, assigns it the given
    verse_key, and writes/merges it into verified_verses.json on disk.

    The verse does NOT appear to users until the Render service is restarted,
    at which point main.py's load_verified_verses() picks it up.

    Args:
        index:     Zero-based index into PENDING_CONTENT.
        verse_key: The dict key to use in VERSE_LIBRARY, e.g. "TS_5_21".
                   Follow the existing convention: PREFIX_CHAPTER_VERSE.

    Returns:
        {verse_key: verified_entry_dict}

    Raises:
        IndexError: If index is out of range.
    """
    if index < 0 or index >= len(PENDING_CONTENT):
        raise IndexError(
            f"No pending entry at index {index}. "
            f"Total pending: {len(PENDING_CONTENT)}"
        )

    entry = PENDING_CONTENT.pop(index)
    entry["status"] = "approved"

    # Load existing verified verses (may be empty dict on first run)
    existing: dict = {}
    if VERIFIED_FILE.exists():
        with open(VERIFIED_FILE, encoding="utf-8") as f:
            existing = json.load(f)

    # Write the approved entry
    existing[verse_key] = {
        "source": entry["source"],
        "transliteration": entry["transliteration"],
        "meaning": entry["meaning"],
        "theme": entry["theme"],
    }

    with open(VERIFIED_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(
        f"[content_pipeline] Approved '{verse_key}' → "
        f"written to {VERIFIED_FILE}. "
        f"Restart the service to publish to users."
    )
    return {verse_key: existing[verse_key]}
