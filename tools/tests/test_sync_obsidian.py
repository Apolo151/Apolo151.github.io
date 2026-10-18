import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import sync_obsidian as so  # noqa: E402

FM = "---\npublish: true\ntitle: Hello\ndate: 2026-10-01\ncategories: [devops]\nlanguage: en\n---\n"


def fm(**over):
    d = {"publish": "true", "title": "Hello", "date": "2026-10-01", "categories": "[devops]", "language": "en"}
    d.update(over)
    lines = [f"{k}: {v}" for k, v in d.items() if v is not None]
    return "---\n" + "\n".join(lines) + "\n---\n"


class Env(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        root = Path(self._t.name)
        self.vault = root / "vault"
        self.att = root / "att"
        self.content = root / "content"
        for d in (self.vault, self.att, self.content):
            d.mkdir()
        self.root = root

    def tearDown(self):
        self._t.cleanup()

    def note(self, name, text, folder=None):
        d = self.vault / folder if folder else self.vault
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text, encoding="utf-8")

    def run_sync(self, dry=False, att=True, **kw):
        return so.sync(self.vault, self.att if att else None, self.content, dry, **kw)

    def files(self):
        return sorted(str(p.relative_to(self.content)) for p in self.content.rglob("*") if p.is_file())


class PublishTests(Env):
    def test_should_publish(self):
        self.assertTrue(so.should_publish({"publish": True}))
        self.assertFalse(so.should_publish({"publish": False}))
        self.assertFalse(so.should_publish({}))
        self.assertFalse(so.should_publish({"publish": "true"}))

    def test_published_copied_unpublished_not(self):
        self.note("one.md", fm() + "Body one\n")
        self.note("two.md", fm(publish="false") + "Body two\n")
        self.note("three.md", "No front matter\n")
        out = self.run_sync()
        self.assertEqual(self.files(), ["writing/one/index.md"])
        self.assertEqual(out, ["writing/one/index.md"])
        text = (self.content / "writing/one/index.md").read_text()
        self.assertIn('title: "Hello"', text)
        self.assertIn('language: "en"', text)
        self.assertIn("Body one", text)
        self.assertNotIn("publish", text)

    def test_unparseable_unpublished_is_skipped_but_published_raises(self):
        self.note("a.md", "---\npublish: false\nnested:\n  k: v\n---\nx\n")
        self.assertEqual(self.run_sync(), [])
        self.note("b.md", "---\npublish: true\nnested:\n  k: v\n---\nx\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()


class FrontMatterTests(Env):
    def test_language_missing_or_invalid(self):
        self.note("a.md", fm(language=None) + "x\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync()
        self.assertIn("a.md", str(cm.exception))
        self.note("a.md", fm(language="fr") + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()

    def test_lang_key_is_not_accepted_as_language(self):
        self.note("a.md", fm(language=None, lang="en") + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()

    def test_categories_missing_or_empty(self):
        for v in (None, "[]", "x"):
            self.note("a.md", fm(categories=v) + "x\n")
            with self.assertRaises(so.SyncError, msg=str(v)):
                self.run_sync()

    def test_date_and_title_required(self):
        self.note("a.md", fm(date=None) + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.note("a.md", fm(date="yesterday") + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.note("a.md", fm(title=None) + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()

    def test_yaml_subset(self):
        fmd = so.parse_front_matter(
            "publish: true\ntitle: \"Q: a\"\ncategories:\n  - a\n  - b\ntags: [x, 'y z']\nn: 3\n# c\ndescription: plain text\n")
        self.assertIs(fmd["publish"], True)
        self.assertEqual(fmd["title"], "Q: a")
        self.assertEqual(fmd["categories"], ["a", "b"])
        self.assertEqual(fmd["tags"], ["x", "y z"])
        self.assertEqual(fmd["description"], "plain text")

    def test_unsupported_yaml_rejected(self):
        for bad in ("a:\n  b: c\n", "a: |\n  text\n", "a: {b: c}\n", "a: &x 1\n", "a: *x\n", "just text\n",
                    "a: [b, c\n", "a: 1\na: 2\n"):
            with self.assertRaises(so.SyncError, msg=bad):
                so.parse_front_matter(bad)

    def test_output_front_matter_is_escaped(self):
        self.note("a.md", fm(title='"Say \\"hi\\" #1"', description="'It''s: ok'") + "x\n")
        self.run_sync()
        text = (self.content / "writing/a/index.md").read_text()
        self.assertIn('title: "Say \\"hi\\" #1"', text)
        self.assertIn('description: "It\'s: ok"', text)


class ConvertTests(unittest.TestCase):
    def conv(self, text, image=None, link=None):
        return so.convert_note(text, image or (lambda n: n), link or (lambda n: "../" + n + "/"))

    def test_wikilink(self):
        self.assertEqual(self.conv("see [[other]] now"), "see [other](../other/) now")
        self.assertEqual(self.conv("[[other|that post]]"), "[that post](../other/)")

    def test_unresolved_link_names_note_and_link(self):
        def link(n):
            return None
        with self.assertRaises(so.SyncError) as cm:
            self.conv("[[ghost]]", link=link)
        self.assertIn("ghost", str(cm.exception))

    def test_image_embed(self):
        self.assertEqual(self.conv("![[d.png]]"), "![](d.png)")
        self.assertEqual(self.conv("![[d.png|A chart]]"), "![A chart](d.png)")
        self.assertEqual(self.conv("![[d.png|300]]"), "![](d.png)")

    def test_markdown_image_goes_through_resolver(self):
        self.assertEqual(self.conv("![x](pics/a b.png)", image=lambda n: "a-b.png"), "![x](a-b.png)")
        self.assertEqual(self.conv("![x](https://example.com/a.png)", image=lambda n: 1 / 0), "![x](https://example.com/a.png)")

    def test_unresolved_image_raises(self):
        with self.assertRaises(so.SyncError):
            self.conv("![[d.png]]", image=lambda n: None)

    def test_non_image_embed_rejected(self):
        with self.assertRaises(so.SyncError):
            self.conv("![[other note]]")

    def test_callout(self):
        self.assertEqual(self.conv("> [!note] Heads up\n> body line\n"), "> **Heads up**\n> body line\n")
        self.assertEqual(self.conv("> [!warning]\n> careful"), "> **Warning**\n> careful")
        self.assertEqual(self.conv("> [!tip]- Folded\n> x"), "> **Folded**\n> x")

    def test_code_untouched(self):
        src = "`[[a]]` and ![[b.png]]\n```\n[[c]]\n> [!note] x\n%% keep %%\n```\n~~~\n![[d.png]]\n~~~\n"
        out = self.conv(src, link=lambda n: None, image=lambda n: "IMG")
        self.assertIn("`[[a]]`", out)
        self.assertIn("![](IMG)", out)
        self.assertIn("[[c]]\n> [!note] x\n%% keep %%\n", out)
        self.assertIn("![[d.png]]", out)

    def test_comments_stripped(self):
        self.assertEqual(self.conv("a %%hidden%% b"), "a  b")
        self.assertEqual(self.conv("a\n%%\nmulti\nline\n%%\nb"), "a\n\nb")
        with self.assertRaises(so.SyncError):
            self.conv("a %% never closed")


class ImageSyncTests(Env):
    def test_image_next_to_note_copied_beside_post(self):
        (self.vault / "diagram.png").write_bytes(b"PNG1")
        self.note("p.md", fm() + "![[diagram.png|Alt]]\n")
        out = self.run_sync()
        self.assertEqual(self.files(), ["writing/p/diagram.png", "writing/p/index.md"])
        self.assertEqual(sorted(out), ["writing/p/diagram.png", "writing/p/index.md"])
        self.assertIn("![Alt](diagram.png)", (self.content / "writing/p/index.md").read_text())
        self.assertEqual((self.content / "writing/p/diagram.png").read_bytes(), b"PNG1")

    def test_image_from_attachments(self):
        (self.att / "shot.jpg").write_bytes(b"J")
        self.note("p.md", fm() + "![[shot.jpg]]\n")
        self.run_sync()
        self.assertTrue((self.content / "writing/p/shot.jpg").exists())

    def test_image_elsewhere_rejected(self):
        (self.root / "elsewhere.png").write_bytes(b"x")
        self.note("p.md", fm() + "![[elsewhere.png]]\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.assertEqual(self.files(), [])

    def test_attachments_not_used_when_unset(self):
        (self.att / "shot.jpg").write_bytes(b"J")
        self.note("p.md", fm() + "![[shot.jpg]]\n")
        with self.assertRaises(so.SyncError):
            self.run_sync(att=False)

    def test_dotdot_and_absolute_rejected(self):
        (self.root / "secret.png").write_bytes(b"x")
        for ref in ("![[../secret.png]]", "![x](../secret.png)", f"![[{self.root}/secret.png]]",
                    "![x](/etc/hosts.png)", "![[sub/../../secret.png]]"):
            self.note("p.md", fm() + ref + "\n")
            with self.assertRaises(so.SyncError, msg=ref):
                self.run_sync()
        self.assertEqual(self.files(), [])

    def test_symlink_escaping_vault_rejected(self):
        (self.root / "outside.png").write_bytes(b"x")
        (self.vault / "link.png").symlink_to(self.root / "outside.png")
        self.note("p.md", fm() + "![[link.png]]\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()

    def test_subfolder_image_in_note_folder_tree(self):
        (self.vault / "img").mkdir()
        (self.vault / "img" / "my pic.png").write_bytes(b"P")
        self.note("p.md", fm() + "![x](img/my pic.png)\n")
        self.run_sync()
        self.assertEqual(self.files(), ["writing/p/index.md", "writing/p/my-pic.png"])
        self.assertIn("![x](my-pic.png)", (self.content / "writing/p/index.md").read_text())


class LinkSyncTests(Env):
    def test_link_to_published_note(self):
        self.note("a.md", fm() + "see [[b|the b post]]\n")
        self.note("b.md", fm(title="B") + "b\n")
        self.run_sync()
        self.assertIn("[the b post](../b/)", (self.content / "writing/a/index.md").read_text())

    def test_link_to_unpublished_note_raises(self):
        self.note("a.md", fm() + "see [[b]]\n")
        self.note("b.md", fm(publish="false") + "b\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync()
        self.assertIn("a.md", str(cm.exception))
        self.assertIn("b", str(cm.exception))
        self.assertEqual(self.files(), [])


class SafetyTests(Env):
    def fake_key(self):
        return "AK" + "IA" + "ABCDEFGH" + "12345678"

    def test_secret_in_body_aborts_everything(self):
        self.note("good.md", fm() + "fine\n")
        self.note("bad.md", fm() + "key " + self.fake_key() + "\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync()
        msg = str(cm.exception)
        self.assertIn("bad.md", msg)
        self.assertNotIn(self.fake_key(), msg)
        self.assertEqual(self.files(), [])

    def test_secret_in_front_matter_aborts_everything(self):
        self.note("good.md", fm() + "fine\n")
        self.note("bad.md", fm(description=self.fake_key()) + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.assertEqual(self.files(), [])

    def test_secret_in_comment_still_aborts(self):
        self.note("bad.md", fm() + "x %%" + self.fake_key() + "%%\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()

    def test_denylist_hit_never_echoed(self):
        self.note("a.md", fm() + "worked at Zorblax Corp\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync(denylist=["zorblax corp"])
        self.assertNotIn("orblax", str(cm.exception))
        self.assertEqual(self.files(), [])

    def test_unpublished_note_is_not_scanned_or_copied(self):
        self.note("draft.md", fm(publish="false") + self.fake_key() + "\n")
        self.note("ok.md", fm() + "fine\n")
        self.assertEqual(self.run_sync(), ["writing/ok/index.md"])

    def test_dry_run_writes_nothing(self):
        (self.vault / "d.png").write_bytes(b"x")
        self.note("a.md", fm() + "![[d.png]]\n")
        out = self.run_sync(dry=True)
        self.assertEqual(sorted(out), ["writing/a/d.png", "writing/a/index.md"])
        self.assertEqual(self.files(), [])
        self.assertFalse((self.content / "writing").exists())

    def test_idempotent_and_deletes_nothing_else(self):
        (self.content / "writing").mkdir()
        other = self.content / "writing" / "handwritten.md"
        other.write_text("mine")
        (self.content / "about.md").write_text("about")
        self.note("a.md", fm() + "x\n")
        first = self.run_sync()
        snap = {p: p.read_bytes() for p in self.content.rglob("*") if p.is_file()}
        second = self.run_sync()
        self.assertEqual(first, second)
        self.assertEqual(snap, {p: p.read_bytes() for p in self.content.rglob("*") if p.is_file()})
        self.assertEqual(other.read_text(), "mine")
        # unpublishing leaves the generated bundle in place (documented)
        self.note("a.md", fm(publish="false") + "x\n")
        self.run_sync()
        self.assertTrue((self.content / "writing/a/index.md").exists())


class SlugTests(Env):
    def test_slug_rules(self):
        self.assertEqual(so.slugify("My First Post"), "my-first-post")
        self.assertEqual(so.slugify("Café_notes (v2)"), "caf-notes-v2")
        self.assertEqual(so.slugify("مرحبا"), so.slugify("مرحبا"))
        self.assertRegex(so.slugify("مرحبا"), r"^note-[0-9a-f]{8}$")
        self.assertNotEqual(so.slugify("مرحبا"), so.slugify("عالم"))

    def test_slug_from_filename_not_title(self):
        self.note("My Post.md", fm(title="Totally Different Title") + "x\n")
        self.assertEqual(self.run_sync(), ["writing/my-post/index.md"])

    def test_arabic_filename(self):
        self.note("مرحبا بالعالم.md", fm(language="ar", title="مرحبا") + "نص\n")
        out = self.run_sync()
        self.assertEqual(len(out), 1)
        self.assertRegex(out[0], r"^writing/note-[0-9a-f]{8}/index\.ar\.md$")
        self.assertEqual(out, self.run_sync())

    def test_translation_pair(self):
        self.note("foo.md", fm() + "english\n")
        self.note("foo.ar.md", fm(language="ar", title="عنوان") + "عربي\n")
        out = self.run_sync()
        self.assertEqual(sorted(out), ["writing/foo/index.ar.md", "writing/foo/index.md"])
        self.assertIn("english", (self.content / "writing/foo/index.md").read_text())
        self.assertIn("عربي", (self.content / "writing/foo/index.ar.md").read_text())

    def test_mixed_written_as_default_language_file(self):
        self.note("m.md", fm(language="mixed") + "x\n")
        self.assertEqual(self.run_sync(), ["writing/m/index.md"])
        self.assertIn('language: "mixed"', (self.content / "writing/m/index.md").read_text())

    def test_link_to_translation_by_stem(self):
        self.note("foo.md", fm() + "[[foo.ar]]\n")
        self.note("foo.ar.md", fm(language="ar") + "x\n")
        self.run_sync()
        self.assertIn("(../foo/)", (self.content / "writing/foo/index.md").read_text())

    def test_two_notes_same_output_raises(self):
        self.note("a.md", fm() + "x\n")
        self.note("a b.md", fm() + "x\n")
        self.note("a-b.md", fm() + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.assertEqual(self.files(), [])


class Round1Tests(Env):
    def warns(self, **kw):
        w = []
        out = self.run_sync(warn=w.append, **kw)
        return out, w

    # 1
    def test_publish_with_trailing_comment(self):
        self.note("a.md", fm(publish="true # go live") + "x\n")
        self.assertEqual(self.run_sync(), ["writing/a/index.md"])

    def test_quoted_comment_and_list_comment(self):
        fmd = so.parse_front_matter('title: "T" # c\nsub: \'S\' # c\ncategories: [a, b] # c\nk: v # c\n')
        self.assertEqual((fmd["title"], fmd["sub"], fmd["categories"], fmd["k"]), ("T", "S", ["a", "b"], "v"))

    def test_non_boolean_publish_warns_and_is_not_published(self):
        for v in ('"true"', "yes", "1", "'true'"):
            self.note("a.md", fm(publish=v) + "x\n")
            out, w = self.warns()
            self.assertEqual(out, [], v)
            self.assertTrue(any("a.md" in m and "publish" in m for m in w), v)
        self.note("a.md", fm(publish="false") + "x\n")
        out, w = self.warns()
        self.assertEqual(w, [])

    # 2
    def test_unpublished_but_live_warns_no_delete(self):
        (self.content / "writing" / "gone").mkdir(parents=True)
        (self.content / "writing" / "gone" / "index.md").write_text("old")
        self.note("gone.md", fm(publish="false") + "x\n")
        out, w = self.warns(dry=True)
        self.assertTrue(any("gone" in m and "content/writing/gone" in m and "retract" in m for m in w), w)
        self.warns()
        self.assertTrue((self.content / "writing/gone/index.md").exists())

    def test_no_warning_when_not_live(self):
        self.note("gone.md", fm(publish="false") + "x\n")
        self.assertEqual(self.warns()[1], [])

    # 3
    def test_generated_marker_written(self):
        self.note("a.md", fm() + "x\n")
        self.run_sync()
        self.assertIn('generated_by: "sync_obsidian"', (self.content / "writing/a/index.md").read_text())

    def test_handwritten_destination_aborts_before_any_write(self):
        (self.content / "writing/b").mkdir(parents=True)
        (self.content / "writing/b/index.md").write_text("---\ntitle: mine\n---\nhand\n")
        self.note("a.md", fm() + "x\n")
        self.note("b.md", fm() + "x\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync()
        self.assertIn("writing/b/index.md", str(cm.exception))
        self.assertEqual(self.files(), ["writing/b/index.md"])
        self.assertIn("hand", (self.content / "writing/b/index.md").read_text())

    def test_handwritten_image_destination_refused(self):
        (self.vault / "d.png").write_bytes(b"new")
        (self.content / "writing/a").mkdir(parents=True)
        (self.content / "writing/a/d.png").write_bytes(b"mine")
        self.note("a.md", fm() + "![[d.png]]\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.assertEqual((self.content / "writing/a/d.png").read_bytes(), b"mine")

    def test_rerun_overwrites_marked_files_and_images(self):
        (self.vault / "d.png").write_bytes(b"v1")
        self.note("a.md", fm() + "![[d.png]]\n")
        self.run_sync()
        (self.vault / "d.png").write_bytes(b"v2")
        self.run_sync()
        self.assertEqual((self.content / "writing/a/d.png").read_bytes(), b"v2")

    # 4
    def test_write_failure_rolls_back(self):
        self.note("a.md", fm() + "x\n")
        self.note("b.md", fm() + "x\n")
        calls = []
        real = so._write_atomic

        def flaky(target, data):
            calls.append(target)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(target, data)
        so._write_atomic = flaky
        try:
            with self.assertRaises(so.SyncError) as cm:
                self.run_sync()
        finally:
            so._write_atomic = real
        self.assertIn("writing/a/index.md", str(cm.exception))
        self.assertEqual(self.files(), [])
        self.assertEqual(list(self.content.rglob(".*tmp*")), [])

    def test_rollback_restores_overwritten_generated_file(self):
        self.note("a.md", fm() + "old\n")
        self.run_sync()
        before = (self.content / "writing/a/index.md").read_bytes()
        self.note("a.md", fm() + "new\n")
        self.note("b.md", fm() + "x\n")
        real = so._write_atomic
        n = []

        def flaky(target, data):
            n.append(1)
            if len(n) == 2:
                raise OSError("boom")
            return real(target, data)
        so._write_atomic = flaky
        try:
            with self.assertRaises(so.SyncError):
                self.run_sync()
        finally:
            so._write_atomic = real
        self.assertEqual((self.content / "writing/a/index.md").read_bytes(), before)
        self.assertFalse((self.content / "writing/b").exists())

    def test_unwritable_destination(self):
        (self.content / "writing").mkdir()
        (self.content / "writing/b").write_text("a file where a folder should be")
        self.note("a.md", fm() + "x\n")
        self.note("b.md", fm() + "x\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.assertEqual(self.files(), ["writing/b"])

    def test_image_bytes_read_during_planning(self):
        img = self.vault / "d.png"
        img.write_bytes(b"PNGDATA")
        self.note("a.md", fm() + "![[d.png]]\n")
        real = so._write_atomic

        def vanish(target, data):
            if img.exists():
                img.unlink()
            return real(target, data)
        so._write_atomic = vanish
        try:
            self.run_sync()
        finally:
            so._write_atomic = real
        self.assertEqual((self.content / "writing/a/d.png").read_bytes(), b"PNGDATA")

    # 5
    def test_denylisted_term_in_image_filename_aborts(self):
        (self.vault / "zorblax.png").write_bytes(b"x")
        self.note("a.md", fm() + "![[zorblax.png]]\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync(denylist=["zorblax"])
        self.assertNotIn("orblax", str(cm.exception))
        self.assertEqual(self.files(), [])

    def test_denylisted_term_split_by_sanitising(self):
        (self.vault / "zorblax corp.png").write_bytes(b"x")
        self.note("a.md", fm() + "![[zorblax corp.png]]\n")
        with self.assertRaises(so.SyncError):
            self.run_sync(denylist=["zorblax corp"])

    def test_secret_in_final_output_path_scanned(self):
        key = "AK" + "IA" + "ABCDEFGH" + "12345678"
        self.note(key.lower() + ".md", fm() + "x\n")
        self.note("ok.md", fm() + "x\n")
        # lowercased key no longer matches the AWS pattern; the check must at least not crash
        self.run_sync()

    # 6
    def test_non_utf8_note_raises_syncerror(self):
        (self.vault / "bad.md").write_bytes(b"---\npublish: true\n---\n\xff\xfe\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync()
        self.assertIn("bad.md", str(cm.exception))

    # 7
    def test_same_note_heading_link(self):
        c = so.convert_note("[[#My Heading]] and [[#My Heading|jump]]", lambda n: n, lambda n: None)
        self.assertEqual(c, "[My Heading](#my-heading) and [jump](#my-heading)")

    def test_block_reference_stripped(self):
        c = so.convert_note("[[other#^abc123]] [[other^abc]]", lambda n: n, lambda n: "../" + n + "/")
        self.assertEqual(c, "[other](../other/) [other](../other/)")

    def test_embed_alias_extra_pipe(self):
        self.assertEqual(so.convert_note("![[d.png|a|300]]", lambda n: n, lambda n: n), "![a](d.png)")

    # 8
    def test_date_with_space_normalised(self):
        self.note("a.md", fm(date='2026-01-01 10:00') + "x\n")
        self.run_sync()
        self.assertIn("date: 2026-01-01T10:00", (self.content / "writing/a/index.md").read_text())

    # 9
    def test_symlinked_note_skipped_with_warning(self):
        (self.root / "real.md").write_text(fm() + "x\n")
        (self.vault / "link.md").symlink_to(self.root / "real.md")
        out, w = self.warns()
        self.assertEqual(out, [])
        self.assertTrue(any("link.md" in m and "symlink" in m for m in w), w)

    # CLI
    def test_cli_prints_warnings_in_dry_run(self):
        (self.content / "writing/gone").mkdir(parents=True)
        self.note("gone.md", fm(publish="false") + "x\n")
        (self.root / ".sync.toml").write_text(f'vault_blog_dir = "{self.vault}"\ncontent_dir = "{self.content}"\n')
        r = subprocess.run([sys.executable, "-I", str(TOOLS / "sync_obsidian.py"), "--dry-run",
                            "--config", str(self.root / ".sync.toml"), "--denylist", str(self.root / ".dl")],
                           capture_output=True, text=True)
        self.assertIn("content/writing/gone", r.stderr)


class Round2Tests(Env):
    def test_dest_path_scan_image_filename(self):
        (self.vault / "zorblax!corp.png").write_bytes(b"x")
        self.note("a.md", fm() + "![](<zorblax!corp.png>)\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync(denylist=["zorblax corp"])
        self.assertIn("output path", str(cm.exception))
        self.assertNotIn("orblax", str(cm.exception))
        self.assertEqual(self.files(), [])
        real = so._path_scan_text
        so._path_scan_text = lambda dest: ""
        try:
            self.assertEqual(len(self.run_sync(denylist=["zorblax corp"])), 2)
        finally:
            so._path_scan_text = real

    def test_dest_path_scan_note_slug(self):
        self.note("zorblax_corp.md", fm() + "x\n")
        with self.assertRaises(so.SyncError) as cm:
            self.run_sync(denylist=["zorblax corp"])
        self.assertIn("output path", str(cm.exception))
        real = so._path_scan_text
        so._path_scan_text = lambda dest: ""
        try:
            self.assertEqual(self.run_sync(denylist=["zorblax corp"]), ["writing/zorblax-corp/index.md"])
        finally:
            so._path_scan_text = real

    def test_embed_names_with_spaces(self):
        (self.vault / "My Photo.png").write_bytes(b"A")
        (self.vault / "Pasted image 20260101120000.png").write_bytes(b"B")
        self.note("a.md", fm() + "![[My Photo.png]]\n![[Pasted image 20260101120000.png]]\n"
                  "![[My Photo.png|caption]]\n![](My Photo.png)\n")
        self.run_sync()
        text = (self.content / "writing/a/index.md").read_text()
        self.assertIn("![](My-Photo.png)", text)
        self.assertIn("![](Pasted-image-20260101120000.png)", text)
        self.assertIn("![caption](My-Photo.png)", text)
        self.assertEqual(text.count("(My-Photo.png)"), 3)
        self.assertEqual((self.content / "writing/a/My-Photo.png").read_bytes(), b"A")
        self.assertEqual((self.content / "writing/a/Pasted-image-20260101120000.png").read_bytes(), b"B")

    def test_sanitised_collision_raises(self):
        (self.vault / "My Photo.png").write_bytes(b"A")
        (self.vault / "My-Photo.png").write_bytes(b"B")
        self.note("a.md", fm() + "![[My Photo.png]] ![[My-Photo.png]]\n")
        with self.assertRaises(so.SyncError):
            self.run_sync()
        self.assertEqual(self.files(), [])

    def test_trailing_block_anchor_stripped(self):
        c = so.convert_note("para text ^blk1\nnext ^a-b  \n^own\nkeep `x ^no` y\n```\ncode ^no\n```\n",
                            lambda n: n, lambda n: n)
        self.assertEqual(c, "para text\nnext\n\nkeep `x ^no` y\n```\ncode ^no\n```\n")


class CliTests(Env):
    def run_cli(self, *args, cfg=True):
        env_cfg = self.root / ".sync.toml"
        if cfg:
            env_cfg.write_text(
                f'vault_blog_dir = "{self.vault}"\nattachments_dir = "{self.att}"\ncontent_dir = "{self.content}"\n')
        return subprocess.run(
            [sys.executable, "-I", str(TOOLS / "sync_obsidian.py"), "--config", str(env_cfg),
             "--denylist", str(self.root / ".denylist"), *args],
            capture_output=True, text=True)

    def test_cli_dry_run_then_real(self):
        self.note("a.md", fm() + "x\n")
        r = self.run_cli("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("writing/a/index.md", r.stdout)
        self.assertEqual(self.files(), [])
        self.assertIn("denylist", r.stderr.lower())
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files(), ["writing/a/index.md"])

    def test_cli_error_exit_code_and_no_echo(self):
        self.note("a.md", fm() + "key " + "AK" + "IA" + "ABCDEFGH" + "12345678" + "\n")
        r = self.run_cli()
        self.assertEqual(r.returncode, 1)
        self.assertIn("a.md", r.stderr)
        self.assertNotIn("ABCDEFGH", r.stderr + r.stdout)

    def test_cli_missing_config(self):
        r = self.run_cli(cfg=False)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
