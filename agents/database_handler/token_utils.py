"""Token counting for the Database Handler's SEMANTIC token cap.

Uses ``tiktoken`` with the ``cl100k_base`` encoding — the tokenizer
used by ``text-embedding-3-large`` and the GPT-4 family.  When
``tiktoken`` is unavailable for any reason, falls back to a
conservative 4-chars-per-token heuristic so the DH never crashes; the
fallback over-estimates slightly, which is the safe direction.
"""

from __future__ import annotations

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover — defensive
    _ENC = None


def count_tokens(text: str) -> int:
    """Return the number of tokens in *text* under ``cl100k_base``."""
    if not text:
        return 0
    if _ENC is not None:
        return len(_ENC.encode(text))
    # Conservative fallback — over-counts slightly so the cap holds.
    return max(1, (len(text) + 3) // 4)
