#!/usr/bin/env python3
"""Sync publishable notes from an Obsidian blog folder into Hugo page bundles.

Usage: sync_obsidian.py [--dry-run] [--config FILE] [--denylist FILE]

Reads .sync.toml (vault_blog_dir, optional attachments_dir, content_dir) and writes
content/writing/<slug>/index.md (+ index.ar.md, images). Only notes with `publish: true`
are touched. The run is all-or-nothing: every note is converted and scanned first, and
files are written only if nothing failed. Nothing is ever deleted. Error messages name
the note and the rule, never the matched text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_public  # noqa: E402

LANGUAGES = ("en", "ar", "mixed")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?)?$")
_PH = "\x00CODE{}\x00"
MARKER = "sync_obsidian"


class SyncError(Exception):
    pass


# ---------------------------------------------------------------- front matter

_DQ = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$')
_SQ = re.compile(r"^'((?:[^']|'')*)'\s*(?:#.*)?$")


def _scalar(raw: str):
    v = raw.strip()
    if v == "":
        return ""
    if v[0] == '"':
        m = _DQ.match(v)
        if not m:
            raise SyncError("malformed double-quoted value in front matter")
        try:
            return json.loads('"' + m.group(1) + '"')
        except ValueError:
            raise SyncError("unsupported escape in double-quoted front matter value")
    if v[0] == "'":
        m = _SQ.match(v)
        if not m:
            raise SyncError("malformed single-quoted value in front matter")
        return m.group(1).replace("''", "'")
    if v[0] in "{|>&*!%@`":
        raise SyncError("unsupported YAML construct in front matter (maps, block scalars, anchors, tags)")
    if v[0] == "[":
        raise SyncError("unexpected list in front matter scalar position")
    v = re.sub(r"\s+#.*$", "", v).strip()
    if v in ("true", "True", "TRUE"):
        return True
    if v in ("false", "False", "FALSE"):
        return False
    return v


def _inline_list(v: str) -> list:
    if not v.endswith("]"):
        raise SyncError("unterminated inline list in front matter")
    inner = v[1:-1].strip()
    if not inner:
        return []
    items, cur, quote = [], "", None
    for ch in inner:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            items.append(cur)
            cur = ""
        elif ch in "[]{}":
            raise SyncError("nested structures in front matter lists are not supported")
        else:
            cur += ch
    if quote:
        raise SyncError("unterminated quote in front matter list")
    items.append(cur)
    return [_scalar(i) for i in items]


def parse_front_matter(block: str) -> dict:
    """Parse a simple YAML subset: key: scalar | [a, b] | block list. Anything else raises."""
    out: dict = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            raise SyncError("indented or nested front matter is not supported")
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*))?$", line)
        if not m:
            raise SyncError("unsupported front matter line (expected 'key: value')")
        key, rest = m.group(1), (m.group(2) or "").strip()
        if key in out:
            raise SyncError(f"duplicate front matter key '{key}'")
        if rest.startswith("["):
            out[key] = _inline_list(re.sub(r"\]\s+#[^'\"\]]*$", "]", rest))
        elif rest == "" or rest.startswith("#"):
            items = []
            while i < len(lines) and re.match(r"^\s+-(\s|$)", lines[i]):
                items.append(_scalar(re.sub(r"^\s+-\s*", "", lines[i])))
                i += 1
            if items:
                out[key] = items
            elif i < len(lines) and lines[i][:1] in (" ", "\t") and lines[i].strip():
                raise SyncError("nested maps in front matter are not supported")
            else:
                out[key] = ""
        else:
            out[key] = _scalar(rest)
    return out


def split_front_matter(text: str) -> tuple[str | None, str]:
    text = text.lstrip("﻿").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text
    m = re.search(r"\n---[ \t]*(\n|$)", text[3:])
    if not m:
        return None, text
    end = 3 + m.start()
    return text[4:end] if end >= 4 else "", text[3 + m.end():]


def should_publish(front_matter: dict) -> bool:
    return front_matter.get("publish") is True


def validate(fmd: dict) -> dict:
    title = fmd.get("title")
    if not isinstance(title, str) or not title.strip():
        raise SyncError("front matter needs a non-empty 'title'")
    date = fmd.get("date")
    if not isinstance(date, str) or not DATE_RE.match(date):
        raise SyncError("front matter needs 'date' as YYYY-MM-DD")
    cats = fmd.get("categories")
    if not isinstance(cats, list) or not cats or not all(isinstance(c, str) and c.strip() for c in cats):
        raise SyncError("front matter needs 'categories' as a non-empty list")
    lang = fmd.get("language")
    if lang not in LANGUAGES:
        raise SyncError("front matter needs 'language' set to one of: " + ", ".join(LANGUAGES))
    desc = fmd.get("description", "")
    if not isinstance(desc, str):
        raise SyncError("'description' must be text")
    return {"title": title.strip(), "date": date, "description": desc.strip(),
            "categories": [c.strip() for c in cats], "language": lang}


def render_front_matter(v: dict) -> str:
    lines = ["---", f"title: {json.dumps(v['title'], ensure_ascii=False)}", f"date: {v['date'].replace(' ', 'T', 1)}"]
    if v["description"]:
        lines.append(f"description: {json.dumps(v['description'], ensure_ascii=False)}")
    lines.append("categories: " + json.dumps(v["categories"], ensure_ascii=False))
    lines.append(f"language: {json.dumps(v['language'])}")
    lines.append(f'generated_by: "{MARKER}"')
    lines.append("---")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------- slugs

def slugify(stem: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not s:
        s = "note-" + hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8]
    return s


def _safe_filename(name: str) -> str:
    p = Path(name)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", p.stem).strip("-.")
    if not stem:
        stem = "img-" + hashlib.sha1(p.stem.encode("utf-8")).hexdigest()[:8]
    return stem + p.suffix.lower()


# ----------------------------------------------------------------- converter

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_INLINE = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_EMBED = re.compile(r"!\[\[([^\]\n]+?)\]\]")
_WIKI = re.compile(r"\[\[([^\]\n]+?)\]\]")
_MDIMG = re.compile(r"!\[([^\]\n]*)\]\(([^)\n]+)\)")
_CALLOUT = re.compile(r"^((?:[ \t]*>)+)[ \t]*\[!([A-Za-z][\w-]*)\][+-]?[ \t]*(.*)$")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)


def _mask_code(text: str) -> tuple[str, list[str]]:
    store: list[str] = []

    def stash(s: str) -> str:
        store.append(s)
        return _PH.format(len(store) - 1)

    out, fence, buf = [], None, []
    for line in text.split("\n"):
        if fence is None:
            m = _FENCE.match(line)
            if m:
                fence, buf = m.group(1), [line]
                continue
            out.append(_INLINE.sub(lambda mm: stash(mm.group(0)), line))
        else:
            buf.append(line)
            m = _FENCE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and line.strip() == m.group(1):
                out.append(stash("\n".join(buf)))
                fence = None
    if fence is not None:  # unclosed fence runs to the end of the document
        out.append(stash("\n".join(buf)))
    return "\n".join(out), store


def convert_note(text: str, resolve_image: Callable[[str], str | None],
                 resolve_link: Callable[[str], str | None]) -> str:
    if "\x00" in text:
        raise SyncError("note contains a NUL character")
    masked, store = _mask_code(text)

    # comments first, so nothing inside them is converted
    def strip_comments(s: str) -> str:
        parts = s.split("%%")
        if len(parts) % 2 == 0:
            raise SyncError("unterminated %% comment")
        return "".join(parts[0::2])
    masked = strip_comments(masked)

    def embed(m: re.Match) -> str:
        target, _, alias = m.group(1).partition("|")
        target = target.strip()
        if Path(target.split("#")[0]).suffix.lower() not in IMAGE_EXTS:
            raise SyncError(f"embed '![[{target}]]' is not an image; only images can be embedded")
        name = resolve_image(target)
        if name is None:
            raise SyncError(f"image '{target}' not found next to the note or in the attachments folder")
        alt = alias.split("|")[0].strip()
        if alt.isdigit() or re.fullmatch(r"\d+x\d+", alt):
            alt = ""
        # stash the result so the markdown-image pass never re-resolves a sanitised name
        store.append(f"![{alt}]({name})")
        return _PH.format(len(store) - 1)

    def mdimg(m: re.Match) -> str:
        alt, target = m.group(1), m.group(2).strip()
        title = ""
        tm = re.match(r'^(.*?)\s+("[^"]*")$', target)
        if tm:
            target, title = tm.group(1), " " + tm.group(2)
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        if _EXTERNAL.match(target) and not target.startswith("#"):
            return m.group(0)
        name = resolve_image(target)
        if name is None:
            raise SyncError(f"image '{target}' not found next to the note or in the attachments folder")
        return f"![{alt}]({name}{title})"

    def wiki(m: re.Match) -> str:
        target, _, alias = m.group(1).partition("|")
        note, _, heading = target.partition("#")
        note = note.strip()
        if "^" in note:  # [[note^block]]
            note = note.split("^", 1)[0].strip()
        heading = heading.strip()
        block = heading.startswith("^")
        if note == "":
            if not heading or block:
                raise SyncError(f"link '[[{m.group(1)}]]' points into the same note without a heading; not supported")
            url = ""
        else:
            url = resolve_link(note)
            if url is None:
                raise SyncError(f"link '[[{m.group(1)}]]' points to '{note}', which is not a published note")
        if heading and not block:
            url += "#" + re.sub(r"[^\w]+", "-", heading.lower()).strip("-")
        label = alias.strip() or note or heading
        return f"[{label}]({url})"

    masked = _EMBED.sub(embed, masked)
    masked = _MDIMG.sub(mdimg, masked)
    masked = _WIKI.sub(wiki, masked)

    def callout(line: str) -> str:
        m = _CALLOUT.match(line)
        if not m:
            return line
        label = m.group(3).strip() or m.group(2).capitalize()
        return f"{m.group(1)} **{label}**"
    masked = "\n".join(callout(l) for l in masked.split("\n"))
    masked = "\n".join(re.sub(r"(?:^|[ \t]+)\^[A-Za-z0-9-]+[ \t]*$", "", l) for l in masked.split("\n"))

    return re.sub(r"\x00CODE(\d+)\x00", lambda m: store[int(m.group(1))], masked)


# --------------------------------------------------------------------- sync

class _Note:
    def __init__(self, path: Path, rel: str, fmd: dict, body: str, raw: str):
        self.path, self.rel, self.fmd, self.body, self.raw = path, rel, fmd, body, raw
        stem = path.stem
        self.stem = stem
        base = stem[:-3] if stem.lower().endswith(".ar") else stem
        self.slug = slugify(base)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _check_ref(ref: str, note: str) -> None:
    if (not ref or "\x00" in ref or ref.startswith(("/", "\\", "~")) or re.match(r"^[A-Za-z]:", ref)
            or any(p == ".." for p in re.split(r"[\\/]", ref))):
        raise SyncError(f"{note}: image path '{ref}' is absolute or leaves the note folder; not allowed")


def _path_scan_text(dest: str) -> str:
    return dest + "\n" + re.sub(r"[-_/]+", " ", dest)


def _stderr_warn(msg: str) -> None:
    print(f"sync_obsidian: warning: {msg}", file=sys.stderr)


def _write_atomic(target: Path, data: bytes) -> None:
    tmp = target.with_name(f".{target.name}.tmp{os.getpid()}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()


def _is_generated(data: bytes) -> bool:
    try:
        block, _ = split_front_matter(data.decode("utf-8"))
    except UnicodeDecodeError:
        return False
    return block is not None and re.search(rf'^generated_by:\s*"{MARKER}"\s*$', block, re.MULTILINE) is not None


def sync(vault_dir: Path, attachments_dir: Path | None, content_dir: Path, dry_run: bool,
         denylist: list[str] | None = None, warn: Callable[[str], None] | None = None) -> list[str]:
    warn = warn or _stderr_warn
    vault_dir = Path(vault_dir)
    content_dir = Path(content_dir)
    if not vault_dir.is_dir():
        raise SyncError("vault blog folder does not exist")
    att = Path(attachments_dir) if attachments_dir else None
    denylist = denylist or []

    notes: list[_Note] = []
    unpublished: list[tuple[str, str]] = []
    for path in sorted(vault_dir.rglob("*.md")):
        relp = path.relative_to(vault_dir)
        rel = str(relp)
        if any(part.startswith(".") for part in relp.parts):
            continue
        if path.is_symlink():
            warn(f"{rel}: symlinked note skipped")
            continue
        if not _inside(path, vault_dir):
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            raise SyncError(f"{rel}: cannot be read as UTF-8 text; fix or move the file")
        block, body = split_front_matter(raw)
        if block is None:
            continue
        try:
            fmd = parse_front_matter(block)
        except SyncError as e:
            if re.search(r"^publish\s*:\s*(true|yes)\b", block, re.IGNORECASE | re.MULTILINE):
                raise SyncError(f"{rel}: {e}")
            continue
        if "publish" in fmd and not isinstance(fmd["publish"], bool):
            warn(f"{rel}: 'publish' is not a plain true/false boolean; the note is NOT published")
        if should_publish(fmd):
            notes.append(_Note(path, rel, fmd, body, raw))
        else:
            unpublished.append((rel, _Note(path, rel, fmd, body, raw).slug))

    findings: list[str] = []

    def scan(owner: str, text: str, label: str) -> None:
        hits = check_public.scan_secrets(text)
        if denylist:
            hits += check_public.scan_denylist(text, denylist)
        for line, why in hits:
            findings.append(f"{owner}: {label} line {line}: {why}")

    for n in notes:
        scan(n.rel, n.raw + "\n" + n.rel, "")
    if findings:
        raise SyncError("safety scan failed, nothing was written:\n" + "\n".join(findings))

    by_stem = {n.stem: n for n in notes}
    pages: dict[str, str] = {}
    plan: dict[str, tuple[str, bytes, str]] = {}  # rel dest -> (kind, data, owner)

    def claim(dest: str, kind: str, data: bytes, owner: str) -> None:
        if dest in plan and plan[dest][:2] != (kind, data):
            raise SyncError(f"{owner}: would overwrite '{dest}' written by another note")
        plan[dest] = (kind, data, owner)

    for n in notes:
        try:
            meta = validate(n.fmd)
            bundle = f"writing/{n.slug}"

            def resolve_link(name: str, _n=n) -> str | None:
                target = by_stem.get(name)
                return f"../{target.slug}/" if target else None

            def resolve_image(ref: str, _n=n, _bundle=bundle) -> str | None:
                _check_ref(ref, _n.rel)
                scan(_n.rel, ref, "image reference")
                for root in [_n.path.parent] + ([att] if att else []):
                    cand = root / ref
                    if cand.is_file():
                        if not _inside(cand, root) or (root is _n.path.parent and not _inside(cand, vault_dir)):
                            raise SyncError(f"{_n.rel}: image '{ref}' resolves outside the allowed folders")
                        if cand.suffix.lower() not in IMAGE_EXTS:
                            raise SyncError(f"{_n.rel}: '{ref}' is not a supported image type")
                        out_name = _safe_filename(cand.name)
                        try:
                            data = cand.read_bytes()
                        except OSError:
                            raise SyncError(f"{_n.rel}: image '{ref}' cannot be read")
                        claim(f"{_bundle}/{out_name}", "file", data, _n.rel)
                        return out_name
                return None

            body = convert_note(n.body, resolve_image, resolve_link)
        except SyncError as e:
            msg = str(e)
            raise SyncError(msg if msg.startswith(n.rel) else f"{n.rel}: {msg}")
        fname = "index.ar.md" if meta["language"] == "ar" else "index.md"
        out_text = render_front_matter(meta) + "\n" + body.lstrip("\n")
        page = f"{bundle}/{fname}"
        # a second note landing on the same page is a conflict, not an overwrite
        if page in pages:
            raise SyncError(f"{n.rel}: same output page as {pages[page]} ({page}); rename one of the notes")
        pages[page] = n.rel
        claim(page, "text", out_text.encode("utf-8"), n.rel)

    # scan every emitted path and final output
    for dest, (kind, data, owner) in sorted(plan.items()):
        scan(owner, _path_scan_text(dest), "output path")
        if kind == "text":
            scan(owner, data.decode("utf-8"), "converted output")
    if findings:
        raise SyncError("safety scan failed, nothing was written:\n" + "\n".join(findings))

    # never clobber hand-written files
    for dest, (kind, data, owner) in sorted(plan.items()):
        target = content_dir / dest
        for anc in list(target.parents):
            if anc == content_dir or content_dir not in anc.parents and anc != content_dir:
                break
            if anc.exists() and not anc.is_dir():
                raise SyncError(f"{owner}: '{dest}' cannot be written; a file is in the way")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise SyncError(f"{owner}: refusing to overwrite '{dest}' (not a regular file)")
        if target.exists():
            existing = target.read_bytes()
            if kind == "text":
                ok = _is_generated(existing)
            else:
                bundle_dir = target.parent
                ok = existing == data or any(
                    (bundle_dir / f).is_file() and _is_generated((bundle_dir / f).read_bytes())
                    for f in ("index.md", "index.ar.md"))
            if not ok:
                raise SyncError(f"{owner}: refusing to overwrite '{dest}': it was not generated by sync_obsidian")

    published_slugs = {n.slug for n in notes}
    for rel, slug in unpublished:
        if slug not in published_slugs and (content_dir / "writing" / slug).is_dir():
            warn(f"note {rel} is not published but content/writing/{slug} exists; delete it to retract")

    written = sorted(plan)
    if dry_run:
        return written

    created_files: list[Path] = []
    created_dirs: list[Path] = []
    backups: dict[Path, bytes] = {}
    try:
        for dest in written:
            target = content_dir / dest
            missing = []
            d = target.parent
            while not d.exists():
                missing.append(d)
                d = d.parent
            target.parent.mkdir(parents=True, exist_ok=True)
            created_dirs.extend(reversed(missing))
            if target.exists():
                backups[target] = target.read_bytes()
            _write_atomic(target, plan[dest][1])
            created_files.append(target)
    except OSError as e:
        removed, restored = [], []
        for t in reversed(created_files):
            try:
                if t in backups:
                    t.write_bytes(backups[t])
                    restored.append(str(t.relative_to(content_dir)))
                else:
                    t.unlink()
                    removed.append(str(t.relative_to(content_dir)))
            except OSError:
                pass
        for dd in reversed(created_dirs):
            try:
                dd.rmdir()
            except OSError:
                pass
        raise SyncError(f"write failed ({type(e).__name__}); removed: {removed or 'none'}; "
                        f"restored: {restored or 'none'}")
    return written


# ---------------------------------------------------------------------- CLI

def _path(value: str, base: Path) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else base / p


def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Sync publishable Obsidian notes into Hugo content.")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    ap.add_argument("--config", default=str(repo / ".sync.toml"))
    ap.add_argument("--denylist", default=str(repo / ".denylist"))
    args = ap.parse_args(argv)

    cfg_path = Path(args.config)
    try:
        cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        print("sync_obsidian: .sync.toml is missing or invalid (copy .sync.toml.example)", file=sys.stderr)
        return 2
    if not cfg.get("vault_blog_dir"):
        print("sync_obsidian: .sync.toml needs vault_blog_dir", file=sys.stderr)
        return 2
    vault = _path(cfg["vault_blog_dir"], cfg_path.parent)
    att = _path(cfg["attachments_dir"], cfg_path.parent) if cfg.get("attachments_dir") else None
    content = _path(cfg.get("content_dir", "content"), cfg_path.parent)

    terms = check_public.load_denylist(Path(args.denylist))
    if not terms:
        print("sync_obsidian: warning: no local denylist found or it is empty; the denylist check is skipped",
              file=sys.stderr)
    try:
        done = sync(vault, att, content, args.dry_run, denylist=terms)
    except SyncError as e:
        print(f"sync_obsidian: {e}", file=sys.stderr)
        return 1
    for rel in done:
        print(rel)
    print(f"{'dry run: ' if args.dry_run else ''}{len(done)} file(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
