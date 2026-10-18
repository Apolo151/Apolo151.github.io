#!/usr/bin/env python3
"""Safety checker for public site content.

Usage: check_public.py [--denylist FILE] PATH...
Scans files (directories recursively, binary files skipped) for secrets,
denylisted terms and forbidden claims. Prints file:line: reason per finding,
exits 1 on any finding. Reasons never echo the matched text, so CI logs of a
public repo cannot leak a denylist term or a secret.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path

SECRET_PATTERNS = {
    "AWS access key id": r"\bAKIA[0-9A-Z]{16}\b",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    "Docker Hub token": r"\bdckr_pat_[A-Za-z0-9_\-]{20,}\b",
    "Private key block": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY",
    "Cloudflare token": r"\bcfat_[A-Za-z0-9]{20,}\b",
    "Slack webhook": r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}",
    "Webhook signing secret": r"\bwhsec_[A-Za-z0-9+/=]{20,}",
    "Connection string with password": r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:@/]+:[^\s@/]{4,}@",
    "Google API key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "Stripe/OpenAI style key": r"\bsk-[A-Za-z0-9]{20,}\b",
}

# "password: value" style assignments; the value is judged by looks_like_credential().
ASSIGNMENT = re.compile(
    r"\b(?:api[_ -]?key|secret|passw(?:or)?d|client[_-]?secret|token)\b\s*[:=]\s*['\"]?([^\s'\"]+)",
    re.IGNORECASE,
)
LABEL_WORDS = {"required", "optional", "none", "null", "true", "false", "changeme", "example", "placeholder",
               "hidden", "secret", "password", "token", "empty", "redacted", "xxxxxxxx"}

_PCT = r"\s*%\s*"
CLAIM_PATTERNS = {
    "forbidden claim (40% faster)": r"(?:40" + _PCT + r"|forty\s+percent\s+)faster",
    "forbidden claim (100% reliability)": r"(?:100" + _PCT + r"|(?:one\s+hundred|hundred)\s+percent\s+)reliab",
    "forbidden claim (30 concurrent)": r"30\s+concurrent",
    "forbidden claim (25% review time)": r"(?:25" + _PCT + r"|twenty[- ]five\s+percent\s+)(?:\w+\s+)?review",
    "forbidden claim (30% coverage)": r"(?:30" + _PCT + r"|thirty\s+percent\s+)(?:test\s+)?coverage",
    "forbidden phrase (hire me)": r"\bhire\s+me\b",
    "forbidden word (solely)": r"\bsolely\b",
    "STP title must not be Team Lead": r"\bSTP\b.{0,60}\bTeam\s+Lead\b|\bTeam\s+Lead\b.{0,60}\bSTP\b",
}

SKIP_DIRS = {".git", "node_modules"}
_STRIP = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0x0640}


def normalize(s: str) -> str:
    """NFKC, then drop combining marks, zero-width characters and Arabic tatweel."""
    s = unicodedata.normalize("NFKC", s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if ord(c) not in _STRIP and unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", s)


def looks_like_credential(v: str) -> bool:
    v = v.rstrip(".,;:)]}>")
    if not v or v.startswith(("{{", "${", "<", "$")) or v.lower() in LABEL_WORDS:
        return False
    has_digit = any(c.isdigit() for c in v)
    has_alpha = any(c.isalpha() for c in v)
    if len(v) >= 20:
        return True
    if len(v) >= 6 and has_digit and has_alpha:
        return True
    if len(v) >= 8:
        mixed = any(c.islower() for c in v) and any(c.isupper() for c in v[1:])
        symbol = any(not c.isalnum() for c in v)
        return has_digit or mixed or symbol
    return False


def _joined(text: str, norm: bool):
    """Join lines with single spaces (so wrapped phrases match); return (string, line starts)."""
    parts, starts, pos = [], [], 0
    for line in text.splitlines():
        line = normalize(line) if norm else line
        starts.append(pos)
        parts.append(line)
        pos += len(line) + 1
    return " ".join(parts), starts


def _line_of(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid
    return lo + 1


def _scan_joined(text: str, patterns: dict[str, re.Pattern], norm: bool) -> list[tuple[int, str]]:
    joined, starts = _joined(text, norm)
    seen, hits = set(), []
    for name, pat in patterns.items():
        for m in pat.finditer(joined):
            key = (_line_of(starts, m.start()), name)
            if key not in seen:
                seen.add(key)
                hits.append(key)
    return sorted(hits)


def scan_secrets(text: str) -> list[tuple[int, str]]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for name, pat in SECRET_PATTERNS.items():
            if re.search(pat, line):
                hits.append((n, name))
        if any(looks_like_credential(m.group(1)) for m in ASSIGNMENT.finditer(line)):
            hits.append((n, "Generic secret assignment"))
    return hits


_CLAIM_RE = {k: re.compile(v, re.IGNORECASE) for k, v in CLAIM_PATTERNS.items()}


def scan_forbidden_claims(text: str) -> list[tuple[int, str]]:
    return _scan_joined(text, _CLAIM_RE, norm=False)


def scan_denylist(text: str, terms: list[str]) -> list[tuple[int, str]]:
    pats = {}
    for i, t in enumerate(terms):
        words = normalize(t).split()
        if words:
            pats["denylisted term"] = pats.get("denylisted term", []) + [
                re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words) + r"(?!\w)", re.IGNORECASE)]
    joined, starts = _joined(text, norm=True)
    lines = set()
    for p in pats.get("denylisted term", []):
        for m in p.finditer(joined):
            lines.add(_line_of(starts, m.start()))
    return [(n, "denylisted term") for n in sorted(lines)]


def load_denylist(path: Path) -> list[str]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [s for s in (line.strip() for line in raw.splitlines()) if s and not s.startswith("#")]


def load_denylist_strict(arg: str) -> list[str]:
    """CLI loader: a missing, unreadable or empty denylist is an error (fail closed)."""
    if not arg:
        raise SystemExit("check_public: --denylist needs a file path")
    try:
        raw = Path(arg).read_text(encoding="utf-8")
    except OSError:
        raise SystemExit("check_public: denylist file is missing or unreadable")
    terms = [s for s in (line.strip() for line in raw.splitlines()) if s and not s.startswith("#")]
    if not terms:
        raise SystemExit("check_public: denylist file has no terms")
    return terms


def iter_files(paths: list[str]):
    """Yield files to scan. Directories are walked recursively; SKIP_DIRS apply to names below the
    given root only, and symlinks found while walking are not followed or scanned."""
    for a in paths:
        p = Path(a)
        if p.is_dir():
            for dirpath, dirnames, filenames in os.walk(p, followlinks=False):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not os.path.islink(os.path.join(dirpath, d)))
                for name in sorted(filenames):
                    f = Path(dirpath) / name
                    if not f.is_symlink():
                        yield f
        elif p.is_file():
            yield p


def read_text(f: Path) -> str | None:
    try:
        data = f.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def main(argv: list[str]) -> int:
    terms: list[str] = []
    paths: list[str] = []
    it = iter(argv)
    for a in it:
        if a == "--denylist":
            terms = load_denylist_strict(next(it, ""))
        else:
            paths.append(a)
    missing = [a for a in paths if not os.path.exists(a)]
    if missing:
        for a in missing:
            print(f"check_public: {a}: no such file or directory", file=sys.stderr)
        return 2
    found = 0
    for f in iter_files(paths):
        text = read_text(f)
        if text is None:
            continue
        for n, why in sorted(scan_secrets(text) + scan_denylist(text, terms) + scan_forbidden_claims(text)):
            print(f"{f}:{n}: {why}")
            found += 1
    if found:
        print(f"\n{found} finding(s). Fix them before publishing.", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
