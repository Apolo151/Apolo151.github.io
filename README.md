# Apolo151.github.io

Personal portfolio site, built with [Hugo](https://gohugo.io/) (extended, version in `.hugo-version`) and deployed to GitHub Pages from `master` by `.github/workflows/deploy.yml`.

```bash
hugo server            # local preview
bash tests/build_check.sh   # build and run checks
```

The address is `apolo151.me`: the custom domain is set in `static/CNAME` (kept) and `baseURL` in `hugo.toml`.

## Launch checklist

Do these in this order. The repository may still serve from its branch in the legacy Pages mode, in which case a first push would run Jekyll over the repository root.

1. In the repository settings, set the Pages source to "GitHub Actions". Do this before any push to `master`.
2. Push or merge to `master`.
3. Check the live site and that the Actions run is green.
4. Turn on "Enforce HTTPS" in the Pages settings.
5. In every clone, create the local `.denylist` (copy `.denylist.example`) and run `git config core.hooksPath .githooks`.

## Design system

Tokens live in `assets/css/tokens.css` (colour, spacing `--space-1..7`, type `--step--1..5`, font stacks); shared styles in `assets/css/base.css`. Dark is the default, light overrides colours via `[data-theme="light"]`. The theme is set by an inline script in `<head>` (`assets/js/theme.js`) before first paint: a stored choice (`localStorage.theme`) wins, then the system preference, then dark. One accent (blue-green) for labels, numbers and links; `--accent-2` (bluer) only for secondary labels. No gradients or shadows. Layout uses CSS logical properties so right-to-left works.

### Fonts (self-hosted, subset woff2 in `static/fonts/`, no third-party requests)

Obtained from the official Fontsource packages (npm `@fontsource/*`, latin or arabic subsets). All are SIL Open Font License 1.1.

| Role | Font | Weights | Licence |
|---|---|---|---|
| Monospace (labels, numbers, nav) | JetBrains Mono | 400 | SIL OFL 1.1 |
| Serif (name, headlines) | Source Serif 4 | 600 | SIL OFL 1.1 |
| Sans (body) | Inter | 400, 600 | SIL OFL 1.1 |
| Arabic companion for sans | IBM Plex Sans Arabic | 400, 600 | SIL OFL 1.1 |
| Arabic companion for serif | Noto Naskh Arabic | 600 | SIL OFL 1.1 |

Total about 236 KB on disk; Arabic files are only fetched when Arabic text is on the page (`unicode-range`).

### Measured contrast (WCAG 2.x)

| Pair | Dark | Light |
|---|---|---|
| text on bg | 11.94 | 15.34 |
| text on surface | 11.21 | 14.12 |
| text-dim on bg | 6.47 | 6.82 |
| text-dim on surface | 6.07 | 6.28 |
| accent on bg | 7.58 | 6.00 |
| accent on surface | 7.11 | 5.53 |
| accent-2 on bg | 7.34 | 6.69 |
| accent-2 on surface | 6.89 | 6.16 |

All text pairs pass AA (4.5:1). Borders are decorative (about 1.4:1 on bg).

## Safety checks

`tools/check_public.py PATH...` scans text files (directories recursively) for credential-looking strings, denylisted terms and a short list of forbidden claims. It prints `file:line: reason` per finding and exits 1 if there is any.

Enable the pre-commit hook once per clone:

```bash
git config core.hooksPath .githooks
```

The hook checks the staged version of files (added, copied, modified, renamed or type-changed) under `content/`, `data/`, `layouts/`, `i18n/`, `static/`, `assets/` and `hugo.toml`, runs the unit tests, then runs `tests/build_check.sh`.

The denylist is a local, git-ignored file: copy `.denylist.example` to `.denylist` and add one term per line. In CI the same list comes from the optional `DENYLIST` Actions secret; when it is unset that check is skipped. Run the unit tests with `python3 -I -m unittest discover tools/tests`.

Fork pull requests do not receive Actions secrets, so on them the `DENYLIST` secret is unset and the denylist check is skipped (the workflow prints a notice). That is acceptable because deploys never run for pull requests; the owner's local pre-commit hook and the secret-backed run on `master` are the real gates. A `--denylist` that is missing, unreadable or has no terms makes the checker fail rather than skip. The checker normalises Unicode (NFKC, diacritics, zero-width characters, Arabic tatweel) before matching terms, skips `.git` and `node_modules` below each scanned root, and does not follow symlinks found while walking a directory.

## Writing from Obsidian

`tools/sync_obsidian.py` turns notes in one Obsidian folder into Hugo page bundles. Copy `.sync.toml.example` to `.sync.toml` (git-ignored) and set `vault_blog_dir`, optionally `attachments_dir`, and `content_dir`. Then:

```bash
python3 tools/sync_obsidian.py --dry-run   # list what would be written, write nothing
python3 tools/sync_obsidian.py             # write content/writing/<slug>/...
```

Front matter for a note you want published (only `publish: true` publishes; everything else is ignored):

```yaml
---
publish: true
title: Post title
date: 2026-10-18
categories: [devops, notes]
language: en          # en, ar or mixed
description: One sentence for the list page and search results (optional)
---
```

`title`, `date` (YYYY-MM-DD), a non-empty `categories` list and `language` are required; a missing or invalid value stops the sync. The key is `language`, not `lang`. Front matter supports a simple YAML subset (scalars, `[a, b]` lists, `- item` lists, booleans); nested maps, block scalars, anchors and the like are rejected.

Each note becomes `content/writing/<slug>/index.md` with its images copied beside it. The slug comes from the filename, never the title: lowercased, non-alphanumeric runs become `-`, and a name with no ASCII letters or digits (for example an Arabic title) becomes `note-` plus a short hash of the filename, so it stays URL-safe and stable. Two notes that map to the same page are an error. A translation pair uses Hugo's filename convention: `foo.md` and `foo.ar.md` share the slug `foo` and become `index.md` and `index.ar.md`. Which output file a note gets follows its `language`: `ar` writes `index.ar.md`; `en` and `mixed` write `index.md` (mixed is the default-language file).

Converted: `[[note]]` and `[[note|text]]` become relative links (only to other published notes, otherwise the sync fails naming the note and link), `![[img.png]]` and `![[img.png|alt]]` become `![alt](img.png)`, `> [!note] Title` callouts become blockquotes with a bold label, and `%% comments %%` are removed. Fenced code and inline code are left untouched. Images are found only beside the note (or below it) and in `attachments_dir`; a path with `..`, an absolute path, or a symlink leaving those folders fails the run.

Safety: every published note (front matter and body, comments included) goes through `check_public.scan_secrets`, and through the denylist when a local `.denylist` exists (a stderr warning when it does not). Any hit stops the whole run with the note name and rule only, never the matched text. The run is all-or-nothing, never reads outside the configured folders, and never deletes: re-running is idempotent, and unpublishing a note leaves its generated folder in `content/writing/` for you to remove by hand. Render note Markdown through `layouts/partials/content.html` in templates.

Front-matter parser limits (all rejected with a clear error, or the note is skipped with a warning when it is not published): keys containing spaces, unquoted values starting with `[[` such as `related: [[note]]` (quote them), multi-line plain scalars, nested maps, block scalars and anchors. `publish` must be the plain boolean `true`; `"true"`, `yes` and `1` do not publish and print a stderr warning naming the note. Trailing `# comments` are allowed after values. `date` may include a time (`2026-01-01 10:00` is written as `2026-01-01T10:00`).

Generated Markdown files carry `generated_by: "sync_obsidian"`. The sync refuses (and writes nothing) to overwrite an existing file that lacks that marker, and an existing image only when identical or when its bundle was generated. If a write fails midway, files created by that run are removed and overwritten ones restored. When a vault note is not published but `content/writing/<slug>/` exists, a warning (also shown with `--dry-run`) reminds you to delete it by hand. Symlinked notes are skipped with a warning; a non-UTF-8 `.md` stops the run. Every emitted path (including sanitised image names) and the converted output are scanned too. Code masking covers fenced blocks and inline code; indented code blocks (including inside lists) are not masked, so wikilink-looking text there is converted.

A trailing Obsidian block id (` ^blk1` at the end of a prose line, or a line holding only `^blk1`) is stripped outside code. Image names are sanitised for the destination (spaces and odd characters become `-`); `![[My Photo.png]]` is looked up under its original name and written as `My-Photo.png`. Two images that sanitise to the same name in one post are an error.
