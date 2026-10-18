#!/usr/bin/env bash
# Builds the site and asserts basic invariants. Later tasks append assertions.
set -euo pipefail
cd "$(dirname "$0")/.."

EXPECTED_BASE_URL="https://apolo151.me/"
fail() { echo "FAIL: $1" >&2; exit 1; }
cleanup() { rm -rf "${FX:-}" "${PT:-}" "${FS:-}" "${FW:-}"; }
trap cleanup EXIT

rm -rf public
hugo --minify --gc

[ -f public/index.html ] || fail "public/index.html missing"
grep -Eq '<html lang="?en"?[ >]' public/index.html || fail 'index.html lacks <html lang=en'
grep -q "^baseURL = \"${EXPECTED_BASE_URL}\"" hugo.toml || fail "baseURL in hugo.toml is not ${EXPECTED_BASE_URL}"
[ -f public/CNAME ] || fail "public/CNAME missing"
EXPECTED_HOST="${EXPECTED_BASE_URL#https://}"; EXPECTED_HOST="${EXPECTED_HOST%/}"
[ "$(tr -d "[:space:]" < public/CNAME)" = "${EXPECTED_HOST}" ] || fail "public/CNAME content is not ${EXPECTED_HOST}"

# --- Task 2: design tokens, theme, base layout ---
CSS_FILES=$(find public -name '*.css' -type f)
[ -n "${CSS_FILES}" ] || fail "no built CSS found"
ALL_CSS=$(cat ${CSS_FILES})
ROOT_CSS=$(printf '%s' "${ALL_CSS}" | grep -oE ':root\{[^}]*\}' || true)
LIGHT_CSS=$(printf '%s' "${ALL_CSS}" | grep -oE '\[data-theme="?light"?\]\{[^}]*\}' || true)
for t in bg surface border text text-dim accent accent-2; do
  printf '%s' "${ROOT_CSS}" | grep -q -- "--${t}:" || fail "token --${t} missing in :root (dark)"
  printf '%s' "${LIGHT_CSS}" | grep -q -- "--${t}:" || fail "token --${t} missing in [data-theme=light]"
done
for t in space-1 space-2 space-3 space-4 space-5 space-6 space-7 step--1 step-0 step-1 step-2 step-3 step-4 step-5 font-mono font-serif font-sans; do
  printf '%s' "${ROOT_CSS}" | grep -q -- "--${t}:" || fail "token --${t} missing in :root"
done
if printf '%s' "${ALL_CSS}" | grep -Eq 'linear-gradient|radial-gradient|conic-gradient|box-shadow|text-shadow'; then
  fail "built CSS uses a gradient or shadow"
fi
HEAD=$(tr -d '\n' < public/index.html | grep -oE '<head>.*</head>')
TS=$(printf '%s' "${HEAD}" | grep -bo 'data-theme' | head -1 | cut -d: -f1)
LS=$(printf '%s' "${HEAD}" | grep -bo 'rel="\?stylesheet' | head -1 | cut -d: -f1)
[ -n "${TS}" ] && [ -n "${LS}" ] || fail "head lacks an inline data-theme script or a stylesheet link"
[ "${TS}" -lt "${LS}" ] || fail "theme script must come before the stylesheet"
printf '%s' "${HEAD}" | grep -Eq '<script[^>]*src=' && fail "head has an external theme script (must be inline)"
grep -Eq '<html[^>]*data-theme=' public/index.html || fail "html has no data-theme attribute by default"
if grep -Eoh '(href|src)="?https?://[^" >]+' public/index.html | grep -Ev '^(href|src)="?https://apolo151\.me(/|$)' | grep -q .; then
  fail "page references a third-party host"
fi
if printf '%s' "${ALL_CSS}" | grep -Eq 'https?://|@import'; then
  fail "built CSS has an absolute URL or @import"
fi
# Logical properties only (right-to-left support).
if printf '%s' "${ALL_CSS}" | grep -Eq '(margin|padding|border)-(left|right)|text-align:[[:space:]]*(left|right)|float:[[:space:]]*(left|right)|(^|[{;])(left|right):'; then
  fail "built CSS uses a physical (non-logical) property"
fi
# Updated in Task 9 fix round: a nav item renders only when its page is built, so a draft page has no link (About and Now are published since Task 12). Task 10: Writing joins the nav only once a post is published (asserted in the Task 10 block).
for n in Work Experience "Open source" Contact; do
  grep -q ">${n}<" public/index.html || fail "nav link ${n} missing"
done
for n in Now About; do
  f="content/$(tr '[:upper:]' '[:lower:]' <<<"${n}").md"
  if grep -qE '^draft:[[:space:]]*true' "$f"; then
    grep -q ">${n}</a>" public/index.html && fail "nav links to the draft page ${n}"
  else
    grep -q ">${n}</a>" public/index.html || fail "nav link ${n} missing"
  fi
done
grep -Eq 'id="?theme-toggle'  public/index.html || fail "theme toggle missing"
find static/fonts -name '*.woff2' | grep -q . || fail "no self-hosted woff2 fonts"

# --- Task 3: languages, direction, toggle ---
# Updated in Task 9: About has no Arabic page (English only), so the real site's translated pair is the home page,
# the untranslated pages are Contact and Experience, and Arabic inner-page checks run on the fixture site (Task 8 block).
grep -Eq '<html[^>]*lang="?ar"?' public/ar/index.html || fail "ar home lacks lang=ar"
grep -Eq '<html[^>]*dir="?rtl"?' public/ar/index.html || fail "ar home lacks dir=rtl"
grep -Eq '<html[^>]*lang="?en"?' public/contact/index.html || fail "en contact lacks lang=en"
grep -Eq '<html[^>]*dir="?ltr"?' public/contact/index.html || fail "en contact lacks dir=ltr"
grep -Eq 'class="?lang-toggle"? href="?/ar/"?[ >]' public/index.html || fail "en home has no toggle to /ar/"
grep -Eq 'class="?lang-toggle"? href="?/"?[ >]' public/ar/index.html || fail "ar home has no toggle to /"
[ -f public/contact/index.html ] || fail "public/contact/index.html missing (untranslated page)"
grep -q 'lang-toggle' public/contact/index.html && fail "untranslated page has a language toggle"
grep -q 'hreflang' public/contact/index.html && fail "untranslated page has hreflang"
# Hugo emits only a redirect stub and a sitemap under /en/; no English content lives there.
[ ! -e public/en/contact ] || fail "English content must have no /en/ prefix"
[ ! -f public/en/index.html ] || grep -q 'http-equiv=refresh' public/en/index.html || fail "/en/ must only redirect to the root"
# canonical and alternates carry the baseURL host
for f in public/contact/index.html public/experience/index.html public/index.html public/ar/index.html; do
  grep -Eq '<link rel="?canonical"? href="?https://apolo151\.me/' "$f" || fail "$f canonical missing or off-host"
  while read -r u; do
    case "$u" in https://apolo151.me/*) ;; *) fail "$f has off-host canonical/alternate: $u";; esac
  done < <(grep -Eo '<link rel="?(canonical|alternate)"?[^>]*href="?[^" >]+' "$f" | grep -Eo 'href="?[^" >]+' | sed -E 's/^href="?//')
done
grep -Eq 'rel="?alternate"? hreflang="?ar"? href="?https://apolo151\.me/ar/"?[ >]' public/index.html || fail "en home lacks ar alternate"
grep -Eq 'rel="?alternate"? hreflang="?en"? href="?https://apolo151\.me/"?[ >]' public/ar/index.html || fail "ar home lacks en alternate"
# header: i18n, language-prefixed hrefs, aria-current
# Task 9 fix round: on Arabic pages, items with no Arabic page link to the English page (prefixed links are
# checked on the fixture site, which has Arabic inner pages); see the link-resolution check in the Task 9 block.
grep -Eq 'href="?/work/"?>الأعمال<' public/ar/index.html || fail "ar nav must fall back to the English work page"
grep -Eq 'class="?brand"? href="?/ar/"?[ >]' public/ar/index.html || fail "ar brand link not /ar/"
grep -Eq '<a href="?/contact/"? aria-current="?page"?>Contact</a>' public/contact/index.html || fail "en contact: exact aria-current link missing"
grep -Eq '<a href="?/experience/"? aria-current="?page"?>Experience</a>' public/experience/index.html || fail "en experience: exact aria-current link missing"
for f in public/contact/index.html public/experience/index.html; do
  [ "$(grep -o 'aria-current' "$f" | wc -l)" -eq 1 ] || fail "$f must have aria-current on exactly one link"
done
grep -Eq '<a href="?/work/"?>Work</a>' public/experience/index.html || fail "non-current nav link should have no aria-current"
# cta_contact: the real home-page button, distinct from the nav link
grep -Eq '<a class="?cta-contact"? href="?/contact/"?>Contact</a>' public/index.html || fail "en home lacks cta_contact button"
grep -Eq '<a class="?cta-contact"? href="?/contact/"?>تواصل معي</a>' public/ar/index.html || fail "ar home cta must fall back to the English contact page"
# x-default alternate points at the English URL
grep -Eq 'hreflang="?x-default"? href="?https://apolo151\.me/"?[ >]' public/index.html || fail "en home lacks x-default"
grep -Eq 'hreflang="?x-default"? href="?https://apolo151\.me/"?[ >]' public/ar/index.html || fail "ar home lacks x-default"
grep -q 'x-default' public/contact/index.html && fail "untranslated page has x-default"
grep -q 'الأعمال' public/ar/index.html || fail "ar nav not translated"
# full key parity between the two languages
EN_KEYS=$(grep -E '^\[' i18n/en.toml | sort); AR_KEYS=$(grep -E '^\[' i18n/ar.toml | sort)
if [ "${EN_KEYS}" != "${AR_KEYS}" ]; then
  echo "Only in en.toml:"; comm -23 <(printf '%s\n' "${EN_KEYS}") <(printf '%s\n' "${AR_KEYS}")
  echo "Only in ar.toml:"; comm -13 <(printf '%s\n' "${EN_KEYS}") <(printf '%s\n' "${AR_KEYS}")
  fail "i18n key sets differ"
fi
# Arabic plural forms for read_time, proven by rendering in a throwaway site
PT=$(mktemp -d); mkdir -p "${PT}/layouts"
cp hugo.toml "${PT}/"; cp -r i18n "${PT}/"
echo '{{ range slice 1 2 3 11 }}[{{ . }}={{ i18n "read_time" . }}]{{ end }}' > "${PT}/layouts/index.html"
hugo -s "${PT}" --quiet >/dev/null 2>&1 || fail "plural test site failed to build"
AR_RT=$(cat "${PT}/public/ar/index.html"); EN_RT=$(cat "${PT}/public/index.html"); rm -rf "${PT}"
[ "${AR_RT}" = "[1=دقيقة واحدة للقراءة][2=دقيقتان للقراءة][3=3 دقائق للقراءة][11=11 دقيقة للقراءة]" ] || fail "Arabic read_time plurals wrong: ${AR_RT}"
[ "${EN_RT}" = "[1=1 min read][2=2 min read][3=3 min read][11=11 min read]" ] || fail "English read_time wrong: ${EN_RT}"
for k in nav_work nav_writing nav_experience nav_opensource nav_now nav_about nav_contact cta_contact theme_toggle lang_toggle read_time categories latest_writing selected_work; do
  grep -q "^\[${k}\]" i18n/en.toml || fail "i18n/en.toml lacks ${k}"
  grep -q "^\[${k}\]" i18n/ar.toml || fail "i18n/ar.toml lacks ${k}"
done
if grep -Eq 'Toggle light|>Theme<|>abdallah<' layouts/partials/*.html layouts/*.html; then fail "hardcoded English UI string in layouts"; fi

# --- Task 4: mixed-language rendering ---
# The draft fixture must not reach the production build, listings or feeds.
if grep -rIl 'fixture-mixed\|mixed-language fixture' public | grep -q .; then fail "draft mixed fixture leaked into the default build"; fi
[ ! -e public/writing/_fixture-mixed ] && [ ! -e public/writing/fixture-mixed ] || fail "draft fixture page exists in public/"
# Build the fixture (drafts on) into a scratch directory, with warnings fatal.
FX=$(mktemp -d)
hugo --buildDrafts --printI18nWarnings --panicOnWarning --minify --destination "${FX}" --quiet || fail "fixture build failed or emitted warnings"
FXP=$(find "${FX}" -path '*fixture-mixed*' -name index.html | head -1)
[ -n "${FXP}" ] || fail "built fixture page not found"
# every block-level element (inside <main>; the footer paragraph is not Markdown)
FXM=$(tr -d '\n' < "${FXP}" | grep -oE '<main.*</main>' | sed 's/></>\n</g')
for tag in p h2 h3 blockquote; do
  N=$({ grep -oE "<${tag}[ >]" <<<"${FXM}" || true; } | wc -l)
  [ "${N}" -ge 1 ] || fail "fixture has no <${tag}>"
  M=$({ grep -oE "<${tag} dir=\"?auto\"?[ >]" <<<"${FXM}" || true; } | wc -l)
  [ "${N}" -eq "${M}" ] || fail "fixture: ${M} of ${N} <${tag}> carry dir=auto"
done
# the fixture covers the required constructs
grep -q 'kubectl get pods' "${FXP}" || fail "fixture lacks inline code"
grep -q '<pre' "${FXP}" || fail "fixture lacks a code block"
grep -q '<li' "${FXP}" || fail "fixture lacks a list"
# code is always LTR and isolated; list items and table cells use plaintext bidi
FX_CSS=$(cat $(find "${FX}" -name '*.css' -type f))
printf '%s' "${FX_CSS}" | grep -oE '[^}]*\{[^}]*\}' | grep -E '(^|[,}])pre[,{]' | grep -q 'direction:ltr' || fail "pre is not direction:ltr in built CSS"
for sel in code kbd pre; do
  printf '%s' "${FX_CSS}" | grep -oE '[^}]*\{[^}]*\}' | grep -E "(^|,)${sel}(,|\{)" | grep 'direction:ltr' | grep -q 'unicode-bidi:isolate' || fail "${sel} lacks direction:ltr + unicode-bidi:isolate"
done
printf '%s' "${FX_CSS}" | grep -oE '[^}]*\{[^}]*\}' | grep -E '(^|,)li(,|\{)' | grep -q 'unicode-bidi:plaintext' || fail "li lacks unicode-bidi:plaintext"
printf '%s' "${FX_CSS}" | grep -oE '[^}]*\{[^}]*\}' | grep -E '(^|,)(td|th)(,|\{)' | grep -q 'unicode-bidi:plaintext' || fail "table cells lack unicode-bidi:plaintext"

# visual-check findings: the quote bar sits on the children (dir=auto ignores children with their own dir),
# and list bullets are inline content scoped to main so they follow each item and leave the nav alone
printf '%s' "${FX_CSS}" | grep -oE '[^}]*\{[^}]*\}' | grep -E 'blockquote>\*' | grep -q 'border-inline-start' || fail "quote bar must be on blockquote children"
printf '%s' "${FX_CSS}" | grep -oE '[^}]*\{[^}]*\}' | grep -E '^blockquote\{' | grep -q 'border' && fail "blockquote itself must not carry the bar"

# --- Task 4 fix round: content convention, lists, quotes ---
# Markdown must be rendered through partials/content.html (it adds dir=auto to p, ul, ol).
BAD=$(grep -rnE '\.Content\b' layouts --include='*.html' --include='*.xml' | grep -v '^layouts/partials/content.html:' | grep -v '{{/\* content-ok: [^*]* \*/}}' || true)
[ -z "${BAD}" ] || fail "templates must use partial content.html, not .Content (add {{/* content-ok: reason */}} on the line if it is not page content): ${BAD}"
grep -q 'class="prose"' <<<"${FXM}" || grep -q 'class=prose' <<<"${FXM}" || fail "Markdown output is not wrapped in .prose"
# lists keep semantics and follow first-strong direction; bullets are scoped to .prose
# Lists keep semantics (role=list). Updated in Task 8 fix round 3: lists no longer carry dir=auto. With dir=auto on every
# <li>, a list's own dir=auto has no text left to judge by and always resolved LTR, so the list inherits the page/parent
# direction instead and each item owns its direction, marker and indentation.
[ "$({ grep -oE '<ul role="?list"?[ >]' <<<"${FXM}" || true; } | wc -l)" -eq "$({ grep -oE '<ul[ >]' <<<"${FXM}" || true; } | wc -l)" ] || fail "every Markdown <ul> needs role=list"
grep -Eq '<(ul|ol) dir=' <<<"${FXM}" && fail "Markdown lists must not carry dir (they inherit; items resolve their own)"
printf '%s' "${FX_CSS}" | grep -qE 'main ul' && fail "bullet CSS must not be scoped to main"
CSSRULES=$(printf '%s' "${FX_CSS}" | grep -oE '[^}]*\{[^}]*\}')
grep -E '\.prose ul>li:?:before' <<<"${CSSRULES}" | grep -q 'inline-block' || fail "bullet must be an inline-block fixed-width marker"
grep -E '\.prose ul>li:?:before' <<<"${CSSRULES}" | grep -q 'margin-inline' && fail "bullet gap must not use a margin (it follows page direction)"
grep -E '\.prose ul>li:?:before' <<<"${CSSRULES}" | grep -qE 'content:"[^"]*"[ ]?/[ ]?""' || fail "bullet glyph needs empty alt text for assistive tech"
grep -qE '\.prose li ul>li:?:before|\.prose li li:?:before' <<<"${CSSRULES}" || fail "nested lists need a distinct marker"
grep -qE '\.prose blockquote>blockquote' <<<"${CSSRULES}" || fail "nested blockquote must not double the bar"
grep -q 'class="*anchor-test' <<<"${FXM}" || fail "heading custom class was dropped"

# fix round (Task 8): each Markdown <li> resolves its own direction, so the bullet sits on the right side
# for items in the other language (dir=auto on the <ul> alone takes the first item's direction)
NLI=$({ grep -oE '<li[ >]' <<<"${FXM}" || true; } | wc -l)
MLI=$({ grep -oE '<li dir="?auto"?[ >]' <<<"${FXM}" || true; } | wc -l)
[ "${NLI}" -ge 6 ] && [ "${NLI}" -eq "${MLI}" ] || fail "fixture: ${MLI} of ${NLI} <li> carry dir=auto"
grep -q 'type="\?checkbox' <<<"${FXM}" || fail "fixture lacks a task-list item"

# --- Task 5: public-content safety checker ---
DL_ARGS=()
if [ -f .denylist ]; then
  DL_ARGS=(--denylist .denylist)
else
  echo "WARNING: denylist not found, name check skipped (copy .denylist.example to .denylist)" >&2
fi
if ! UT_OUT=$(python3 -I -m unittest discover tools/tests 2>&1); then
  printf '%s\n' "${UT_OUT}" >&2
  fail "check_public unit tests failed"
fi
SCAN=()
for p in content data layouts i18n static assets hugo.toml README.md BACKLOG.md .github .hugo-version; do [ -e "$p" ] && SCAN+=("$p"); done
python3 -I tools/check_public.py "${DL_ARGS[@]}" "${SCAN[@]}" || fail "check_public found problems in sources"

# --- Task 8: components and page layouts ---
# Updated in Task 9: the real site now has work pages and data/proof.yaml (see the Task 9 block for content checks).
grep -q 'class="\?work-grid' public/index.html || fail "real home lacks the work grid"
grep -q 'class="\?proof-row' public/index.html || fail "real home lacks the proof row"
# Build the fixture site (tests/fixtures/site: invented content and data) in a scratch copy.
FS=$(mktemp -d); FSRC="${FS}/src"; FOUT="${FS}/out"; mkdir -p "${FSRC}"
cp -r hugo.toml layouts assets i18n static "${FSRC}/"
cp -r tests/fixtures/site/content tests/fixtures/site/data "${FSRC}/"
hugo -s "${FSRC}" --destination "${FOUT}" --printI18nWarnings --panicOnWarning --minify --quiet || fail "component fixture site failed to build or warned"
main_of() { tr -d '\n' < "$1" | grep -oE '<main.*</main>' | sed 's/></>\n</g'; }
FH="${FOUT}/index.html"; FHA="${FOUT}/ar/index.html"
[ -f "${FH}" ] && [ -f "${FHA}" ] || fail "fixture home pages missing"
FCSS=$(cat $(find "${FOUT}" -name '*.css' -type f)); FRULES=$(printf '%s' "${FCSS}" | grep -oE '[^}]*\{[^}]*\}')
# hero: one sentence slot from front matter, start-aligned (no centred text anywhere)
grep -q 'class="\?hero-line[^>]*>Fixture hero sentence' "${FH}" || fail "home hero sentence slot missing"
printf '%s' "${FCSS}" | grep -q 'text-align:center' && fail "built CSS centres text (no centred hero)"
# proof row: one item per data/proof.yaml entry, in mono
NP=$(grep -c '^- ' tests/fixtures/site/data/proof.yaml)
[ "$(grep -o 'class="\?proof-item' "${FH}" | wc -l)" -eq "${NP}" ] || fail "proof row must render ${NP} items"
grep -q '2.2k' "${FH}" || fail "proof value missing"
grep -Eq 'class="?proof-label"? dir="?auto"?>' "${FH}" || fail "proof labels need dir=auto"
grep -Eq 'class="?proof-label"? dir="?auto"? lang="?en"?>' "${FHA}" || fail "ar proof labels from English data need lang=en"
grep -Eq 'class="?proof-label"?[^>]*lang=' "${FH}" && fail "en proof labels need no lang attribute"
grep -E '\.proof-value\{' <<<"${FRULES}" | grep -q 'font-family:var(--font-mono)' || fail "proof values must be mono"
# selected work: cards in a two-column grid at desktop, never three columns
grep -q 'class="\?work-grid' "${FH}" || fail "home has no work grid"
[ "$(grep -oE 'class="?work-card[" >]' "${FH}" | wc -l)" -ge 2 ] || fail "home needs at least two work cards"
grep -E '\.work-grid\{' <<<"${FRULES}" | grep -q 'grid-template-columns:repeat(2,' || fail "work grid is not two columns at desktop"
# no grid may have three or more columns: count top-level tracks (repeat(n, ...) counts n; auto-fit/auto-fill fail).
# Proven against minmax(0,1fr) x3, repeat(3,1fr), repeat(auto-fit,...) and 9rem repeat(2,1fr).
GRID_BAD=$(printf '%s' "${FCSS}" | python3 -I -c '
import re, sys
css = sys.stdin.read()
for v in re.findall(r"grid-template-columns:([^;}]*)", css):
    tracks, depth, cur = [], 0, ""
    for ch in v.strip():
        if ch == "(": depth += 1
        if ch == ")": depth -= 1
        if ch == " " and depth == 0:
            if cur: tracks.append(cur)
            cur = ""
        else:
            cur += ch
            if ch == ")" and depth == 0:  # the minifier drops the space after ")"
                tracks.append(cur); cur = ""
    if cur: tracks.append(cur)
    n = 0
    for t in tracks:
        m = re.match(r"repeat\((\w[\w-]*),", t)
        if m:
            if not m.group(1).isdigit(): n += 99
            else: n += int(m.group(1))
        else:
            n += 1
    if n >= 3: print(v)
')
[ -z "${GRID_BAD}" ] || fail "a grid has three or more columns: ${GRID_BAD}"
# work card: small category label, bold title link, summary, thin border, no shadow
CARD=$(main_of "${FH}" | tr -d '\n' | grep -oE '<article class="?work-card.{0,600}' | head -1)
grep -q 'class="\?label[^>]*>Fixture category' <<<"${CARD}" || fail "work card lacks its category label"
grep -Eq '<h3[^>]*><a href="?/work/alpha/"?>Fixture case Alpha</a>' <<<"${CARD}" || fail "work card lacks its title link"
grep -q 'Fixture summary for case Alpha' <<<"${CARD}" || fail "work card lacks its summary"
grep -E '\.work-card\{' <<<"${FRULES}" | grep -q 'border:1px solid var(--border)' || fail "work card needs a thin token border"
# fix round: only the title is a link, so the card itself does not react to hover; the link underlines on hover and focus
grep -qE '\.work-card:hover' <<<"${FRULES}" && fail "work card must not highlight as a whole (only the title is a link)"
grep -E '\.work-card h3 a:hover' <<<"${FRULES}" | grep -E '\.work-card h3 a:focus-visible' | grep -q 'text-decoration:underline' || fail "work card title link needs an underline on hover and focus"
# fix round: Markdown in a summary is rendered then reduced to plain text (no literal asterisks)
grep -q 'Fixture summary with emphasis and strong text\.' "${FOUT}/work/index.html" || fail "work card summary shows raw Markdown"
# latest writing and contact on the home page
grep -q 'Fixture post in English' "${FH}" || fail "home lacks latest writing"
grep -Eq '<a class="?cta-contact"? href="?/contact/"?>Contact</a>' "${FH}" || fail "fixture home lacks the contact link"
# work page: meta strip and four headed sections in order
FW="${FOUT}/work/alpha/index.html"; [ -f "${FW}" ] || fail "fixture work page missing"
FWM=$(main_of "${FW}")
grep -q 'class="\?meta-strip' <<<"${FWM}" || fail "work page lacks the meta strip"
for v in "Fixture role Alpha" "Fixture team of 3" "January 2025"; do grep -q "${v}" <<<"${FWM}" || fail "meta strip lacks ${v}"; done
grep -q 'meta-strip' "${FOUT}/work/delta/index.html" && fail "work page without role, team or date must not render a meta strip"
H2S=$(grep -oE '<h2[^>]*>[^<]*</h2>' <<<"${FWM}" | sed -E 's/<[^>]+>//g' | tr '\n' '|')
[ "${H2S}" = "The problem|The decision|The result|What went wrong|" ] || fail "work sections out of order or missing: ${H2S}"
grep -q '<strong>bold</strong>' <<<"${FWM}" || fail "work section Markdown not rendered"
grep -Eq '<p dir="?auto"?>Fixture problem text' <<<"${FWM}" || fail "work section Markdown not routed through content.html"
FWA=$(main_of "${FOUT}/ar/work/alpha/index.html")
H2A=$(grep -oE '<h2[^>]*>[^<]*</h2>' <<<"${FWA}" | sed -E 's/<[^>]+>//g' | tr '\n' '|')
[ "${H2A}" = "المشكلة|القرار|النتيجة|ما الذي لم ينجح|" ] || fail "ar work section headings wrong: ${H2A}"
# experience: one timeline item per record, no status text, localised present
FE="${FOUT}/experience/index.html"; [ -f "${FE}" ] || fail "fixture experience page missing"
NE=$(python3 -I -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' tests/fixtures/site/data/experience.json)
[ "$(grep -o 'class="\?timeline-item' "${FE}" | wc -l)" -eq "${NE}" ] || fail "timeline must render ${NE} items"
grep -Eqi '\[(verified|partial|unverified|blocked)\]' "${FE}" && fail "experience page shows status text"
grep -q '<ol class="\?timeline' "${FE}" || fail "timeline is not an ordered list"
grep -q 'Mar 2025' "${FE}" || fail "timeline start date not formatted"
grep -q '>Present<' "${FE}" || fail "timeline lacks localised present (en)"
grep -q '>حتى الآن<' "${FOUT}/ar/experience/index.html" || fail "timeline lacks localised present (ar)"
# fix round: the exported data is English, so on non-English pages the timeline is one LTR English block
grep -Eq '<ol class="?timeline"?[^>]* lang="?en"? dir="?ltr"?' "${FOUT}/ar/experience/index.html" || fail "ar timeline must be lang=en dir=ltr"
grep -Eq '<ol class="?timeline"?[^>]* dir=' "${FE}" && fail "en timeline must not force a direction"
grep -Eq 'class="?timeline-range"? dir="?rtl"? lang="?ar"?' "${FOUT}/ar/experience/index.html" || fail "ar timeline dates must keep Arabic reading order"
# visual-check finding: a fixed-width marker box aligns its glyph by the page direction, so on RTL pages
# English lines got the dash flush against the text; the timeline marker uses symmetric padding instead
TLM=$(grep -E '\.timeline-lines li:?:before\{' <<<"${FRULES}" || true)
[ -n "${TLM}" ] || fail "timeline line marker rule missing"
grep -q 'inline-size' <<<"${TLM}" && fail "timeline marker must not be a fixed-width box"
grep -Eq 'padding-inline:[0-9.]+(em|rem)[;}]|padding-inline:var\(--space-[0-9]\)[;}]' <<<"${TLM}" || fail "timeline marker needs symmetric inline padding"
# visual-check finding: a CSS-generated separator lost its trailing space; the separator is real text with spaces
grep -Eq 'Fixture Org One <span aria-hidden="?true"?>(&middot;|&#183;|·)</span> Fixture City' "${FE}" || fail "org and location need a spaced separator"
# moved from Task 3 (Task 9): Arabic inner-page header checks, on the fixture's translated experience page
FEA="${FOUT}/ar/experience/index.html"
grep -Eq '<a href="?/ar/experience/"? aria-current="?page"?>الخبرة</a>' "${FEA}" || fail "ar experience: exact aria-current link missing"
[ "$(grep -o 'aria-current' "${FEA}" | wc -l)" -eq 1 ] || fail "ar experience must have aria-current on exactly one link"
grep -Eq 'href="?/ar/work/' "${FEA}" || fail "ar inner page nav not language-prefixed"
grep -q 'الأعمال' "${FEA}" || fail "ar inner page nav not translated"
grep -Eq 'class="?lang-toggle"? href="?/experience/"?[ >]' "${FEA}" || fail "ar experience has no toggle to /experience/"
# open source: projects, items and merged/open state
FO="${FOUT}/open-source/index.html"; [ -f "${FO}" ] || fail "fixture open-source page missing"
[ "$(grep -o 'class="\?os-project' "${FO}" | wc -l)" -eq 2 ] || fail "open-source page must list 2 projects"
[ "$(grep -oE 'class="?os-item[" >]' "${FO}" | wc -l)" -eq 3 ] || fail "open-source page must list 3 items"
[ "$(grep -o 'class="\?os-state os-state-merged' "${FO}" | wc -l)" -eq 2 ] || fail "merged state not shown"
[ "$(grep -o 'class="\?os-state os-state-open' "${FO}" | wc -l)" -eq 1 ] || fail "open state not shown"
grep -q '1.1k' "${FO}" || fail "open-source stars missing"
FOT=$(tr -d '\n' < "${FO}" | sed -E 's/<[^>]+>//g')
grep -q '1.1k stars' <<<"${FOT}" || fail "en abbreviated star count wording wrong"
grep -q '42 stars' <<<"${FOT}" || fail "en numeric star count wording wrong"
grep -q '42 نجمة' <<<"$(tr -d '\n' < "${FOUT}/ar/open-source/index.html" | sed -E 's/<[^>]+>//g')" || fail "ar star count wording wrong"
for f in one two few many other; do
  sed -n '/^\[stars\]/,/^$/p' i18n/ar.toml | grep -q "^${f} = " || fail "ar stars lacks the ${f} plural form"
done
grep -q 'بالعربية والإنجليزية' i18n/ar.toml || fail "ar mixed marker wording"
# writing list: date, plural reading time, language marker for mixed/other-language posts, category chips
FL="${FOUT}/writing/index.html"; [ -f "${FL}" ] || fail "fixture writing list missing"
FLM=$(main_of "${FL}" | tr -d '\n')
[ "$(grep -o 'class="\?post-item' <<<"${FLM}" | wc -l)" -eq 2 ] || fail "en writing list must list 2 posts"
grep -q '1 min read' <<<"${FLM}" || fail "writing list lacks reading time"
grep -Eq '<time[^>]*datetime="?2026-03-02' <<<"${FLM}" || fail "writing list lacks machine-readable date"
grep -Eq '<time[^>]*datetime="?2026-03-02"?>2 Mar 2026</time>' <<<"${FLM}" || fail "en post date must read 2 Mar 2026"
grep -Eq '<time[^>]*datetime="?2026-01-05"?>5 يناير 2026</time>' "${FOUT}/ar/writing/index.html" || fail "ar post date must read 5 يناير 2026"
[ "$(grep -o 'class="\?lang-marker' <<<"${FLM}" | wc -l)" -eq 1 ] || fail "only the mixed post gets a language marker on the en list"
grep -q 'Arabic and English' <<<"${FLM}" || fail "mixed marker text missing"
[ "$(grep -o 'class="\?chip' <<<"${FLM}" | wc -l)" -eq 3 ] || fail "writing list must show 3 category chips"
grep -E '\.chip\{' <<<"${FRULES}" | grep -q 'var(--accent)' || fail "chips must use the single accent"
grep -q 'دقيقة واحدة للقراءة' "${FOUT}/ar/writing/index.html" || fail "ar writing list lacks Arabic reading time"
# work list uses the same two-column card grid
grep -q 'class="\?work-grid' "${FOUT}/work/index.html" || fail "work list lacks the card grid"
# mixed lists on an English and an Arabic page: tight and loose lists, Arabic-first and English-first;
# every item carries dir=auto, once
for f in "${FOUT}/writing/fixture-two/index.html" "${FOUT}/ar/writing/fixture-three/index.html"; do
  M=$(main_of "$f"); MF=$(tr -d '\n' <<<"${M}")
  NL=$({ grep -oE '<li[ >]' <<<"${M}" || true; } | wc -l)
  [ "${NL}" -ge 25 ] || fail "$f: expected at least 25 list items, got ${NL}"
  [ "$({ grep -oE '<li dir="?auto"?>' <<<"${M}" || true; } | wc -l)" -eq "${NL}" ] || fail "$f: every <li> needs dir=auto exactly once"
  grep -Eq '<li dir="?auto"?>[^<]' <<<"${MF}" || fail "$f: fixture lacks a tight list"
  # visual-check finding (fix round 2): dir=auto on the <li> skips children that carry their own dir, so a
  # loose item's first <p> must have no dir attribute, or the item (and its bullet) falls back to LTR
  [ "$({ grep -oE '<li dir="?auto"?><p>' <<<"${MF}" || true; } | wc -l)" -eq 4 ] || fail "$f: 4 loose items need a first <p> without dir (the <li> resolves the direction)"
  grep -Eq '<li dir="?auto"?><p>عنصر عربي أول في قائمة متباعدة' <<<"${MF}" || fail "$f: loose list lacks an Arabic-first item"
  grep -Eq '<li dir="?auto"?><p>English item with two paragraphs\.</p><p dir="?auto"?>Second paragraph of the same item\.</p><ul' <<<"${MF}" || fail "$f: loose item with two paragraphs and a nested list missing"
done
# unminified output: no whitespace between a loose item's <li> and its first <p> (it would render as an extra gap)
FRAW="${FS}/raw"
hugo -s "${FSRC}" --destination "${FRAW}" --quiet || fail "unminified fixture build failed"
grep -q '<li dir="auto"><p>عنصر عربي أول في قائمة متباعدة' "${FRAW}/ar/writing/fixture-three/index.html" || fail "loose item: whitespace or dir between <li> and its first <p> (unminified)"
# fix round 3: lists inherit direction (no dir on <ul>/<ol>); ordered lists use a counter marker owned by each item
for f in "${FOUT}/writing/fixture-two/index.html" "${FOUT}/ar/writing/fixture-three/index.html"; do
  M=$(main_of "$f")
  grep -Eq '<(ul|ol)[^>]* dir=' <<<"${M}" && fail "$f: Markdown lists must not carry dir"
  NO=$({ grep -oE '<ol[ >]' <<<"${M}" || true; } | wc -l); [ "${NO}" -ge 1 ] || fail "$f: fixture lacks an ordered list"
  [ "$({ grep -oE '<ol role="?list"?' <<<"${M}" || true; } | wc -l)" -eq "${NO}" ] || fail "$f: every <ol> needs role=list (list-style is none)"
  grep -q 'بند تجريبي في قائمة مرقمة' <<<"${M}" || fail "$f: fixture lacks the Arabic ordered list"
done
grep -Eq '<ol role="?list"? style="?counter-reset: ?prose-ol 8"?>' "${FOUT}/writing/fixture-two/index.html" || fail "an ordered list starting at 9 must reset its counter to 8"
grep -q 'First English step' "${FOUT}/ar/writing/fixture-three/index.html" || fail "ar page lacks an English ordered list"
grep -q 'Nested English item one' "${FOUT}/ar/writing/fixture-three/index.html" || fail "ar page lacks a nested English list in an Arabic item"
grep -q 'عنصر عربي متداخل أول' "${FOUT}/ar/writing/fixture-three/index.html" || fail "ar page lacks a nested Arabic list"
grep -E '\.prose ol\{' <<<"${FRULES}" | grep -q 'list-style:none' || fail "ordered lists need list-style:none (the item draws its number)"
grep -E '(^|,)\.prose ol(,|\{)' <<<"${FRULES}" | grep -q 'padding:0' || fail "ordered lists need zero padding (the item owns its indentation)"
OLM=$(grep -E '\.prose ol>li:?:before\{' <<<"${FRULES}" || true)
grep -q 'counter(prose-ol)' <<<"${OLM}" || fail "ordered list marker must use counter(prose-ol)"
grep -q 'display:inline-block' <<<"${OLM}" || fail "ordered list marker must be an inline-block in the item's flow"
grep -q 'min-inline-size' <<<"${OLM}" || fail "ordered list marker needs a minimum width (grows, never clips)"
grep -q 'tabular-nums' <<<"${OLM}" || fail "ordered list numbers need tabular numerals"
# visual-check finding (fix round 3): two-digit numbers filled the minimum width and touched the text; the marker
# inherits the item's direction, so padding-inline-end always faces the text and guarantees a gap
grep -q 'padding-inline-end' <<<"${OLM}" || fail "ordered list marker needs an inline-end gap toward the text"
grep -E '\.prose ol>li\{' <<<"${FRULES}" | grep -q 'counter-increment:prose-ol' || fail "ordered list items must increment prose-ol"
# fix round 2: in a loose list (<li><p>) the first paragraph runs inline after the bullet; later blocks stay blocks
grep -E '\.prose li>p:first-child\{' <<<"${FRULES}" | grep -q 'display:inline' || fail "first paragraph in a list item must be inline (bullet shares its line)"
# visual-check finding (fix round 2): <p> is unicode-bidi:isolate in the UA stylesheet; inline, it becomes a neutral
# to the <li>'s plaintext paragraph, which then falls back to LTR. The inline first paragraph must join the item's flow.
grep -E '\.prose li>p:first-child\{' <<<"${FRULES}" | grep -q 'unicode-bidi:normal' || fail "inline first paragraph must use unicode-bidi:normal (UA isolate breaks the item direction)"
grep -E '\.prose li:has\(>p\)\{' <<<"${FRULES}" | grep -q 'margin-block' || fail "loose list items need logical block spacing"
grep -E '\.prose li>p\+p\{' <<<"${FRULES}" | grep -q 'display:block' || fail "following paragraphs in a list item must stay blocks"
# components are styled from tokens only: no raw colours outside tokens.css
COMP_COLOURS=$(grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(' assets/css/components.css || true)
[ -z "${COMP_COLOURS}" ] || fail "components.css uses raw colours: ${COMP_COLOURS}"
# fixture text stays fake: run the safety scan over it too
python3 -I tools/check_public.py "${DL_ARGS[@]}" tests/fixtures || fail "check_public found problems in tests/fixtures"

# --- Task 9: launch content ---
# hero: exactly the approved sentence, and nothing else in the hero slot
HERO_EN="Infrastructure and backend engineer, with product thinking to match."
grep -q "^hero: \"${HERO_EN}\"$" content/_index.md || fail "content/_index.md hero is not the approved sentence"
grep -q "class=\"\?hero-line\"\?>${HERO_EN}</p>" public/index.html || fail "built home hero is not the approved sentence"
[ "$(grep -o 'class="\?hero-line' public/index.html | wc -l)" -eq 1 ] || fail "home must have exactly one hero line"
# drafts never reach the build: every content file with draft: true has no page in public/
DRAFTS=$(grep -rlE '^draft:[[:space:]]*true[[:space:]]*$' content || true)
for d in ${DRAFTS}; do
  rel="${d#content/}"; rel="${rel%.md}"; lang=""
  case "${rel}" in *.ar) rel="${rel%.ar}"; lang="ar/";; esac
  case "${rel}" in */index) rel="${rel%/index}";; esac
  [ ! -e "public/${lang}${rel}" ] || fail "draft ${d} was built into public/${lang}${rel}"
  T=$(sed -n 's/^title:[[:space:]]*"\(.*\)"[[:space:]]*$/\1/p' "${d}" | head -1)
  # page titles render as "<title>Title | Site</title>"; nav labels such as "About" are not page titles
  if [ -n "${T}" ] && grep -rqF "<title>${T} |" public --include='*.html'; then fail "draft page ${d} was built under another path"; fi
done
for d in content/work/machathon-and-stp.md; do
  grep -qE '^draft:[[:space:]]*true' "${d}" || fail "${d} must stay draft: true until the owner approves it"
done
[ ! -e public/work/machathon-and-stp ] || fail "draft case study built"
for sm in public/en/sitemap.xml public/ar/sitemap.xml; do [ -f "${sm}" ] || fail "${sm} missing"; done
for u in work/machathon-and-stp/; do
  grep -q "apolo151.me/${u}<" public/en/sitemap.xml && fail "draft ${u} in the en sitemap"
  grep -q "apolo151.me/ar/${u}<" public/ar/sitemap.xml && fail "draft ${u} in the ar sitemap"
done
for u in "" work/ work/eks-migration/ work/event-driven-migration/ work/freelance-systems/ experience/ open-source/ contact/; do
  grep -q "<loc>https://apolo151.me/${u}</loc>" public/en/sitemap.xml || fail "live page /${u} missing from the en sitemap"
done
grep -q "<loc>https://apolo151.me/ar/</loc>" public/ar/sitemap.xml || fail "ar home missing from the ar sitemap"
# live case studies: problem first, no "what went wrong" section unless the source has one
for c in eks-migration event-driven-migration freelance-systems; do
  F="public/work/${c}/index.html"; [ -f "${F}" ] || fail "case study ${c} not built"
  H=$(main_of "${F}" | grep -oE '<h2[^>]*>[^<]*</h2>' | sed -E 's/<[^>]+>//g' | head -1)
  [ "${H}" = "The problem" ] || fail "case study ${c} must lead with the problem"
done
for f in content/work/*.md; do
  case "$f" in */_index.md) continue;; esac
  for k in title category summary problem decision result; do grep -q "^${k}:" "$f" || fail "$f lacks ${k}"; done
done
# proof row: every item carries a neutral reference id (P1, ...) in a comment, never a private path; labels are English
NPV=$(grep -cE '^- value:' data/proof.yaml)
NPS=$(grep -cE '^[[:space:]]*# source: verified career record, item P[0-9]+$' data/proof.yaml)
[ "${NPV}" -ge 1 ] && [ "${NPV}" -eq "${NPS}" ] || fail "data/proof.yaml: ${NPS} source comments for ${NPV} items"
python3 -I - data/proof.yaml <<'PY' || fail "data/proof.yaml: every item needs a source comment directly above it"
import re, sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
for i, l in enumerate(lines):
    if l.startswith("- value:"):
        j = i - 1
        while j >= 0 and lines[j].lstrip().startswith("#") and "source:" not in lines[j]:
            j -= 1
        if j < 0 or not re.match(r"\s*# source: verified career record, item P\d+$", lines[j]):
            sys.exit(1)
PY
grep -P '^\s*label:.*[\x{0600}-\x{06FF}]' data/proof.yaml && fail "proof labels must be English"
[ "$(grep -o 'class="\?proof-item' public/index.html | wc -l)" -eq "${NPV}" ] || fail "home proof row must render ${NPV} items"
# experience: generated by the career repo's exporter, one timeline item per record
NEX=$(python3 -I -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' data/experience.json)
[ "${NEX}" -ge 1 ] || fail "data/experience.json is empty"
[ "$(grep -o 'class="\?timeline-item' public/experience/index.html | wc -l)" -eq "${NEX}" ] || fail "experience page must render ${NEX} items"
# full dates from the exporter (YYYY-MM-DD) read as month and year, like YYYY-MM
grep -Eq '<time datetime="?[0-9]{4}-[0-9]{2}-[0-9]{2}"?>[0-9]{4}-' public/experience/index.html && fail "experience page shows a raw YYYY-MM-DD date"
# open source: every item has a link and a known state (or none)
python3 -I - data/opensource.yaml <<'PY' || fail "data/opensource.yaml: an item lacks an https link or has an unknown state"
import re, sys
txt = open(sys.argv[1], encoding="utf-8").read()
items = re.split(r"\n\s+- title:", txt)[1:]
assert items, "no items"
for it in items:
    assert re.search(r'\n\s+url: "https://', it), it
    m = re.search(r"\n\s+state: (\S+)", it)
    assert m is None or m.group(1) in ("merged", "open"), it
PY
[ "$(grep -oE 'class="?os-item[" >]' public/open-source/index.html | wc -l)" -ge 1 ] || fail "open-source page lists no items"
# contact: email from params.email as a mail link, GitHub and LinkedIn, no phone number
EMAIL=$(sed -n 's/^email = "\(.*\)"$/\1/p' hugo.toml)
[ -n "${EMAIL}" ] || fail "hugo.toml lacks params.email"
grep -q "href=\"\?mailto:${EMAIL}\"\?" public/contact/index.html || fail "contact page lacks the mail link"
grep -q 'href="\?https://github.com/Apolo151"\?' public/contact/index.html || fail "contact page lacks GitHub"
grep -q 'href="\?https://www.linkedin.com/in/abdallah-ismail15/\?"\?' public/contact/index.html || fail "contact page lacks LinkedIn"
if grep -rqE 'tel:|\+20[0-9 ]{6,}|\b01[0-9]{9}\b' public --include='*.html'; then fail "a phone number reached public/"; fi
# every nav, brand and CTA link on every built page resolves to a file under public/ (no 404s for drafts or
# untranslated pages)
while IFS= read -r f; do
  HDR=$(tr -d '\n' < "$f" | grep -oE '<header class="?site-header.*</header>' || true)
  CTA=$(tr -d '\n' < "$f" | grep -oE '<a class="?cta-contact"? href="?[^" >]+' || true)
  for h in $( { grep -oE 'href="?/[^" >]*' <<<"${HDR}${CTA}" || true; } | sed -E 's/^href="?//' ); do
    t="public${h}"; case "$t" in */) t="${t}index.html";; esac
    [ -f "$t" ] || fail "$f links to ${h}, which is not built"
  done
done < <(find public -name index.html -not -path 'public/en/*')
# no Task 3 placeholder text survives
if grep -rqiE 'placeholder page|under construction|صفحة تجريبية|قيد الإنشاء' content public --include='*.md' --include='*.html'; then fail "placeholder text left in content or build"; fi
# --- Task 10: writing section, categories, RSS ---
# Feed URLs (default language is served at the root with no prefix, so the layout is deliberate):
#   /index.xml        combined feed: every published post, both languages
#   /feed.en.xml      English feed: posts with language en or mixed
#   /ar/index.xml     Arabic feed: posts with language ar or mixed
# Per-category and per-section feeds are not generated.
BASE="${EXPECTED_BASE_URL}"
for f in index.xml feed.en.xml ar/index.xml; do [ -f "public/${f}" ] || fail "real build lacks public/${f}"; done
# Task 12 follow-up: the real site now has one published post (the staging-outage stub): the combined and English feeds hold exactly it, the Arabic feed stays empty and valid.
python3 -I tests/check_feed.py public/index.xml en "${BASE}" /writing/staging-outage/ || fail "real combined feed invalid or not exactly the stub"
python3 -I tests/check_feed.py public/feed.en.xml en "${BASE}" /writing/staging-outage/ || fail "real English feed invalid or not exactly the stub"
python3 -I tests/check_feed.py public/ar/index.xml ar "${BASE}" || fail "real Arabic feed invalid or not empty"
for f in index.xml feed.en.xml; do [ "$(grep -o '<item>' "public/${f}" | wc -l)" -eq 1 ] || fail "public/${f} must hold exactly one item"; done
grep -q '<item>' public/ar/index.xml && fail "real Arabic feed must have no items"
for f in index.xml feed.en.xml; do grep -q '<lastBuildDate>Sun, 18 Oct 2026 00:00:00 +0000</lastBuildDate>' "public/${f}" || fail "public/${f} lastBuildDate must equal the post date"; done
{ [ ! -e public/writing/index.xml ] && [ ! -e public/categories/index.xml ] && [ ! -e public/ar/writing/index.xml ]; } || fail "only the three site feeds may exist (no section or category feeds)"
# the Task 4 draft fixture appears nowhere in a default build (the staging-outage post is published since the Task 12 follow-up)
if grep -rqE 'mixed-language fixture' public; then fail "a draft post leaked into public/"; fi
# every built HTML page advertises the combined feed and its language feed
while IFS= read -r f; do
  H=$(tr -d '\n' < "$f" | grep -oE '<head>.*</head>' || true)
  [ -n "${H}" ] || continue
  grep -Eq '<link rel="?alternate"? type="?application/rss\+xml"? [^>]*href="?https://apolo151\.me/index\.xml' <<<"${H}" || fail "$f lacks the combined feed link"
  case "$f" in
    public/ar/*) grep -Eq '<link rel="?alternate"? type="?application/rss\+xml"? [^>]*href="?https://apolo151\.me/ar/index\.xml' <<<"${H}" || fail "$f lacks the Arabic feed link";;
    *) grep -Eq '<link rel="?alternate"? type="?application/rss\+xml"? [^>]*href="?https://apolo151\.me/feed\.en\.xml' <<<"${H}" || fail "$f lacks the English feed link";;
  esac
done < <(find public -name '*.html' -not -path 'public/en/*')
# writing fixtures: invented posts across the three categories, built in a scratch dir
FW=$(mktemp -d); FWS="${FW}/src"; FWO="${FW}/out"; mkdir -p "${FWS}"
cp -r hugo.toml layouts assets i18n static "${FWS}/"
cp -r tests/fixtures/site/content tests/fixtures/site/data "${FWS}/"
rm -rf "${FWS}/content/writing"; cp -r tests/fixtures/writing/content/writing "${FWS}/content/writing"
hugo -s "${FWS}" --destination "${FWO}" --printI18nWarnings --panicOnWarning --minify --quiet || fail "writing fixture site failed to build or warned"
python3 -I tests/check_feed.py "${FWO}/index.xml" en "${BASE}" /writing/en-postmortem/ /ar/writing/ar-only/ /writing/mixed/ /writing/pair/ /ar/writing/pair/ || fail "combined feed wrong"
python3 -I tests/check_feed.py "${FWO}/feed.en.xml" en "${BASE}" /writing/en-postmortem/ /writing/mixed/ /writing/pair/ || fail "English feed wrong"
python3 -I tests/check_feed.py "${FWO}/ar/index.xml" ar "${BASE}" /ar/writing/ar-only/ /writing/mixed/ /ar/writing/pair/ || fail "Arabic feed wrong"
if grep -rq 'FIXTURE DRAFT NEVER LISTED' "${FWO}"; then fail "the draft fixture post leaked into the build"; fi
# ar-only post: listed in /ar/writing/, in the Arabic feed, no language toggle
grep -q 'تدوينة عربية تجريبية فقط' "${FWO}/ar/writing/index.html" || fail "ar-only post missing from /ar/writing/"
if grep -q 'class="\?lang-toggle' "${FWO}/ar/writing/ar-only/index.html"; then fail "ar-only post must have no language toggle"; fi
grep -q 'class="\?lang-toggle' "${FWO}/ar/writing/pair/index.html" || fail "paired post lacks the language toggle"
# adding an English twin later must not move the Arabic post
find "${FWO}/ar/writing" -name index.html | sed "s#${FWO}##" | sort > "${FW}/ar-before.txt"
mkdir -p "${FW}/twin"; cp -r "${FWS}" "${FW}/twin/src"
cp "${FWS}/content/writing/pair/index.md" "${FW}/twin/src/content/writing/ar-only/index.md"
sed -i 's/Fixture pair post (English)/Fixture English twin of the Arabic-only post/' "${FW}/twin/src/content/writing/ar-only/index.md"
hugo -s "${FW}/twin/src" --destination "${FW}/twin/out" --quiet || fail "twin build failed"
find "${FW}/twin/out/ar/writing" -name index.html | sed "s#${FW}/twin/out##" | sort > "${FW}/ar-after.txt"
cmp -s "${FW}/ar-before.txt" "${FW}/ar-after.txt" || fail "adding an English twin changed the Arabic URLs"
grep -q 'class="\?lang-toggle' "${FW}/twin/out/ar/writing/ar-only/index.html" || fail "the twin should add the toggle"
python3 -I tests/check_feed.py "${FW}/twin/out/ar/index.xml" ar "${BASE}" /ar/writing/ar-only/ /writing/mixed/ /ar/writing/pair/ || fail "Arabic feed changed after the twin"
# categories: chips link to term pages; term pages list their posts and have a language-aware heading
FWL=$(main_of "${FWO}/writing/index.html" | tr -d '\n')
grep -Eq '<a class="?chip"? href="?/categories/postmortems/"?>Postmortems<' <<<"${FWL}" || fail "chip does not link to its term page with its English name"
grep -Eq '<a class="?chip"? href="?/ar/categories/learning-and-exploration/"?>' "${FWO}/ar/writing/index.html" || fail "ar chip does not link to the ar term page"
T=$(main_of "${FWO}/categories/postmortems/index.html" | tr -d '\n')
grep -Eq '<h1[^>]*>Category: Postmortems</h1>' <<<"${T}" || fail "en term heading wrong"
grep -Eq 'Fixture (&quot;|&#34;|")outage' <<<"${T}" || fail "term page lacks its post"
if grep -q 'Fixture mixed post' <<<"${T}"; then fail "term page lists a post from another category"; fi
T=$(main_of "${FWO}/categories/learning-and-exploration/index.html" | tr -d '\n')
grep -q 'Fixture mixed post' <<<"${T}" || fail "learning term page lacks the mixed post"
TA=$(main_of "${FWO}/ar/categories/learning-and-exploration/index.html" | tr -d '\n')
grep -Eq '<h1[^>]*>التصنيف: التعلم والاستكشاف</h1>' <<<"${TA}" || fail "ar term heading wrong"
grep -q 'تدوينة عربية تجريبية فقط' <<<"${TA}" || fail "ar term page lacks its post"
[ -f "${FWO}/categories/how-this-site-is-built/index.html" ] || fail "how-this-site-is-built term page missing"
# i18n parity: display names for the three starting terms, headings and feed strings in both languages
for k in cat_postmortems cat_learning_and_exploration cat_how_this_site_is_built category_heading feed_all feed_this_language feed_desc_all feed_desc_lang no_posts subscribe; do
  { grep -q "^\[${k}\]" i18n/en.toml && grep -q "^\[${k}\]" i18n/ar.toml; } || fail "i18n key ${k} missing in en or ar"
done
# the first post is a published short stub (owner chose "publish a short stub"); the long skeleton lives in the private career repo
[ -f content/writing/staging-outage/index.md ] || fail "first post missing"
grep -q '^draft' content/writing/staging-outage/index.md && fail "first post must be published (no draft key)"
grep -q '^date: 2026-10-18$' content/writing/staging-outage/index.md || fail "first post date must be 2026-10-18"
grep -qi 'TODO' content/writing/staging-outage/index.md && fail "first post carries a TODO note"
grep -qE '[0-9]' <(sed '1,/^---$/{/^---$/!d}' content/writing/staging-outage/index.md | sed '1,/^---$/d') && fail "stub body must contain no numbers"
[ -f public/writing/staging-outage/index.html ] || fail "the first post was not built"
grep -q '/writing/staging-outage/' public/en/sitemap.xml || fail "stub missing from the en sitemap"
grep -q 'staging-outage/' public/writing/index.html || fail "/writing/ does not list the stub"
grep -q 'staging-outage/' public/categories/postmortems/index.html || fail "postmortems term page does not list the stub"
grep -Eq '<a href="?/writing/"?[ >]' public/index.html || fail "real nav lacks Writing"
{ grep -q '^language: en' content/writing/staging-outage/index.md && grep -q 'postmortems' content/writing/staging-outage/index.md; } || fail "first post needs language en and category postmortems"
python3 -I tools/check_public.py "${FWO}" || fail "check_public found problems in the writing fixture build"
# fix round 1: unknown terms fall back to a spaced, title-cased slug; term page titles use the localized name
grep -Eq '<a class="?chip"? href="?/categories/my-new-topic/"?>My New Topic<' <<<"${FWL}" || fail "unknown term chip must read My New Topic"
grep -Eq '<a class="?chip"? href="?/ar/categories/my-new-topic/"?>My New Topic<' "${FWO}/ar/writing/index.html" || fail "unknown term chip (ar page) must read My New Topic"
grep -Eq '<h1[^>]*>Category: My New Topic</h1>' "${FWO}/categories/my-new-topic/index.html" || fail "unknown term heading must read My New Topic"
grep -Eq '<h1[^>]*>التصنيف: My New Topic</h1>' "${FWO}/ar/categories/my-new-topic/index.html" || fail "unknown term heading (ar) wrong"
grep -Eq '<title>Category: Postmortems \| ' "${FWO}/categories/postmortems/index.html" || fail "en term page <title> wrong"
grep -Eq '<title>التصنيف: التعلم والاستكشاف \| ' "${FWO}/ar/categories/learning-and-exploration/index.html" || fail "ar term page <title> must use the Arabic category name"
grep -Eq '<title>Category: My New Topic \| ' "${FWO}/categories/my-new-topic/index.html" || fail "unknown term <title> wrong"
# chips show a visible accent focus outline
grep -E 'a\.chip:focus-visible' <<<"${FRULES}" | grep -Eq 'outline:[^;}]*var\(--accent\)' || fail "chips need an accent focus-visible outline"
# Writing nav item only when the language has at least one published post
grep -Eq '<a href="?/writing/"?[ >]' "${FOUT}/index.html" || fail "fixture nav lacks Writing although posts exist"
grep -Eq 'href="?/ar/writing/"?[ >]' public/ar/index.html && fail "real ar nav shows Writing with no published posts"
grep -q 'id="\?latest-writing' public/index.html || fail "real home lacks the latest writing block"
sed -n '/id="\?latest-writing/,/<\/section>/p' public/index.html | grep -q 'staging-outage' || fail "latest writing block lacks the stub"
# the real feeds are byte-identical across two consecutive builds
hugo --minify --gc --destination "${FW}/real2" --quiet || fail "second real build failed"
for f in index.xml feed.en.xml ar/index.xml; do cmp -s "public/${f}" "${FW}/real2/${f}" || fail "real feed ${f} differs between builds"; done
# a published post must not carry an owner TODO note (drafts only; the real stub is now published and passes this guard). Fail-safe: only an exact `draft: true` /
# `draft = true` line marks a draft; anything else (True, "true", 1, missing, malformed) counts as published.
todo_guard() { # dir; prints offending files
  local f
  while IFS= read -r f; do
    grep -Eq '^draft[[:space:]]*[:=][[:space:]]*true[[:space:]]*$' "$f" && continue
    grep -Eiq 'TODO[[:space:]]*\([[:space:]]*owner[[:space:]]*\)' "$f" && echo "$f"
  done < <(find "$1" -name '*.md')
}
[ -z "$(todo_guard content/writing)" ] || fail "a published post still has TODO(owner) notes: $(todo_guard content/writing)"
GT="${FW}/guard"; mkdir -p "${GT}"
printf -- '---\ndraft: True\n---\n<!-- todo ( OWNER ): x -->\n' > "${GT}/a.md"
printf -- '+++\ndraft = "true"\n+++\nTODO(owner)\n' > "${GT}/b.md"
printf -- '+++\ndraft = true\n+++\nTODO(owner) fine in a draft\n' > "${GT}/c.md"
printf -- '---\ndraft: true\n---\nTODO (owner) fine\n' > "${GT}/d.md"
[ "$(todo_guard "${GT}" | sort | tr '\n' ' ')" = "${GT}/a.md ${GT}/b.md " ] || fail "TODO(owner) guard misclassifies drafts (must be case-insensitive, whitespace-tolerant, fail-safe)"
if grep -rEiq 'TODO[[:space:]]*\([[:space:]]*owner[[:space:]]*\)' public "${FWO}"; then fail "TODO(owner) reached a built page"; fi

# --- Task 11 fix round 2 ---
# deploy trigger: one deploy branch constant, shared by the workflow and the README
DEPLOY_BRANCH=master
grep -Eq "^[[:space:]]+branches: \[${DEPLOY_BRANCH}\]$" .github/workflows/deploy.yml || fail "workflow push trigger is not exactly [${DEPLOY_BRANCH}]"
grep -Eq "github\.ref == 'refs/heads/${DEPLOY_BRANCH}'" .github/workflows/deploy.yml || fail "deploy job is not gated to ${DEPLOY_BRANCH}"
grep -Eq "\bmain\b" .github/workflows/deploy.yml && fail "workflow still mentions main"
grep -q "from \`${DEPLOY_BRANCH}\`" README.md || fail "README does not name ${DEPLOY_BRANCH} as the deploy branch"
grep -Eq 'from `main`|on `main`' README.md && fail "README still names main as the deploy branch"
# launch checklist order in the README
python3 -I - README.md <<'PY' || fail "README launch checklist missing or out of order"
import re,sys
t=open(sys.argv[1],encoding="utf-8").read()
assert "## Launch checklist" in t
sec=t.split("## Launch checklist",1)[1]
keys=["set the Pages source","Push or merge","is green","Enforce HTTPS","create the local"]
pos=[sec.find(k) for k in keys]
assert all(p>=0 for p in pos) and pos==sorted(pos),pos
PY
# README, BACKLOG and workflow files are scanned (sources and staged hook)
for f in README.md BACKLOG.md .github; do grep -q -- "${f}" tools/check_staged.sh || fail "check_staged.sh does not scan ${f}"; done
grep -q 'README.md BACKLOG.md .github' tests/build_check.sh || fail "build check does not scan README.md BACKLOG.md .github"
# a denylisted fake term in BACKLOG.md is caught
DT=$(mktemp -d); mkdir "${DT}/s"; printf 'fake-zebra-term\n' > "${DT}/dl.txt"; printf '# Backlog\n\nSee fake-zebra-term here.\n' > "${DT}/s/BACKLOG.md"
if python3 -I tools/check_public.py --denylist "${DT}/dl.txt" "${DT}/s/BACKLOG.md" >/dev/null 2>&1; then rm -rf "${DT}"; fail "a denylisted term in BACKLOG.md was not caught"; fi
rm -rf "${DT}"
# private scratch folder is ignored
grep -qx '\.superpowers/' .gitignore || fail ".superpowers/ is not git-ignored"

# --- Task 11 fix round 1 ---
# open-source projects carry a neutral reference id too
NOP=$(grep -cE '^- project:' data/opensource.yaml)
[ "${NOP}" -ge 1 ] && [ "${NOP}" -eq "$(grep -cE '^# source: verified career record, item O[0-9]+$' data/opensource.yaml)" ] || fail "data/opensource.yaml: every project needs a neutral reference id comment"
# no public source file names the private repo or its folders
PRIV_REPO="experience""-""hall"  # assembled so the literal is never in a public file
if grep -rIn -e "${PRIV_REPO}" -e '/experiences/' -e '/stories/' -e '/profile/' -e 'experiences/' -e 'profile/' -e 'stories/' content data layouts i18n hugo.toml BACKLOG.md README.md assets static/CNAME 2>/dev/null | grep -v '^README.md.*Obsidian' | grep -q .; then
  fail "a public source file names the private career repo or one of its folders"
fi
# claims that no [verified] line supports must not return to the case studies
for phrase in 'every Docker flag' 'Teammates built' 'node groups' 'several hotels' "hotel system's deployment" 'production Compose stack' 'runs the orchestrator and the stage workers' 'We compared three options' 'chained Celery tasks'; do
  if grep -rIqi -e "${phrase}" content/work public/work; then fail "removed unsupported claim is back: ${phrase}"; fi
done
# the skip link target can take focus
grep -Eq '<main[^>]*id="?main"?[^>]*tabindex="?-1"?|<main[^>]*tabindex="?-1"?[^>]*id="?main"?' public/index.html || fail "main lacks tabindex=-1 (skip link would not move focus)"
grep -Eq '<main[^>]*tabindex="?-1"?' "${FOUT}/ar/index.html" || fail "Arabic main lacks tabindex=-1"

# --- Task 11: review-pass regressions (Lighthouse) ---
# every page has a non-empty meta description and a favicon link (no 404 on /favicon.ico)
for f in public/index.html public/contact/index.html public/work/eks-migration/index.html "${FOUT}/index.html" "${FOUT}/ar/index.html" "${FOUT}/writing/fixture-one/index.html"; do
  grep -Eq '<meta name="?description"? content=("[^"]+"|[^ >"][^>]*)' "$f" || fail "meta description missing or empty in $f"
  grep -Eq '<link rel="?icon"? ' "$f" || fail "favicon link missing in $f"
done
# Arabic pages preload their Arabic faces (else the font swap shifts the layout: CLS 0.26 on mobile)
for f in public/ar/index.html "${FOUT}/ar/index.html"; do
  [ "$(grep -o 'rel="\?preload"\? href="\?/fonts/[a-z0-9-]*arabic[a-z0-9-]*\.woff2' "$f" | wc -l)" -ge 3 ] || fail "Arabic font preloads missing in $f"
done
if grep -q 'rel="\?preload' public/index.html; then fail "English home preloads fonts it may not use"; fi
# the accessible name of the language toggle contains its visible text (WCAG 2.5.3)
for f in public/index.html "${FOUT}/ar/index.html"; do
  python3 -I - "$f" <<'PY' || fail "language toggle aria-label does not contain its visible text in $f"
import re,sys
h=open(sys.argv[1],encoding="utf-8").read()
m=re.search(r'<a class="?lang-toggle"?[^>]*aria-label="?([^">]*)"?[^>]*>([^<]*)</a>',h) or re.search(r'<a class="?lang-toggle"?[^>]*aria-label=("[^"]*"|[^ >]*)[^>]*>([^<]*)</a>',h)
assert m,"no toggle"
assert m.group(2).strip() and m.group(2).strip() in m.group(1).strip('"'),(m.group(1),m.group(2))
PY
done

# --- Task 12: About and Now are real pages derived from the public GitHub profile README ---
for pg in about now; do
  [ -f "content/${pg}.md" ] || fail "content/${pg}.md missing"
  grep -qE '^draft:' "content/${pg}.md" && fail "content/${pg}.md must not be a draft"
  [ ! -e "content/${pg}.ar.md" ] || fail "${pg} must stay English only"
  [ -f "public/${pg}/index.html" ] || fail "public/${pg}/ was not built"
  [ ! -e "public/ar/${pg}" ] || fail "an Arabic ${pg} page was built"
  N="$(tr '[:lower:]' '[:upper:]' <<<"${pg:0:1}")${pg:1}"
  grep -q "href=\"\?/${pg}/\"\?[ >][^<]*${N}</a>\|href=\"\?/${pg}/\"\?>${N}</a>" public/index.html || fail "nav does not link to ${N}"
  LC_ALL=C grep -nP '[^\x00-\x7F]' "content/${pg}.md" >/dev/null && fail "content/${pg}.md has non-ASCII characters (emoji?)"
  grep -nEi '!\[|<img|shields\.io|badge|<table|<svg' "content/${pg}.md" >/dev/null && fail "content/${pg}.md has image or badge markup"
  grep -nE 'github\.com/|theroboticsclub|herokuapp|vercel\.app|mailto:' "content/${pg}.md" >/dev/null && fail "content/${pg}.md has a README repository or widget URL"
  python3 -I - "public/${pg}/index.html" <<'PY' || fail "built ${pg} page has image, badge or repository URL markup in its main content"
import re,sys
h=open(sys.argv[1],encoding="utf-8").read()
m=re.search(r"<main.*?</main>",h,re.S); assert m,"no main"
t=m.group(0)
assert not re.search(r"<img|<svg|shields\.io|github\.com/|theroboticsclub|<table",t),"markup"
assert not re.search(r"[\U0001F000-\U0001FFFF\u2600-\u27BF]",t),"emoji"
PY
  python3 -I tools/check_public.py "${DL_ARGS[@]}" "content/${pg}.md" "public/${pg}" || fail "check_public found problems in ${pg}"
done
grep -q 'Kubernetes and Cloud Native Associate' public/about/index.html || fail "About lacks the KCNA line"
grep -q 'early-stage startup in stealth' public/now/index.html || fail "Now lacks the generic startup line"
if grep -rIqiE 'property-management|property management|freelance' public/about public/now; then fail "About/Now mention the freelance system"; fi

# --- Task 12 cleanup: no production-use claims on the site (owner decision) ---
# Patterns are specific so unrelated text is not tripped; "in production" is only banned in the EKS case study.
PROD_PATTERN='still runs|still uses|still run|went live'
PROD_HITS=$(grep -rniE "${PROD_PATTERN}" content data public --include='*.md' --include='*.json' --include='*.yaml' --include='*.html' --include='*.xml' || true)
[ -z "${PROD_HITS}" ] || fail "a production-use claim is on the site (still runs/uses/went live): $(cut -d: -f1,2 <<<"${PROD_HITS}" | tr '\n' ' ')"
grep -niE 'in production' content/work/eks-migration.md public/work/eks-migration/index.html >/dev/null && fail "the EKS case study must not claim production use"
grep -q 'projects I built and ran' content/about.md && fail "About says 'ran' but the profile README does not"

# the built site passes the public-content safety checker too
python3 -I tools/check_public.py "${DL_ARGS[@]}" public || fail "check_public found problems in public/"

echo "OK: build checks passed"
