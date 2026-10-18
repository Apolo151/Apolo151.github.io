import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import check_public as cp  # noqa: E402


class SecretTests(unittest.TestCase):
    def test_aws_key(self):
        text = "ok\nkey " + "AK" + "IA" + "ABCDEFGH" + "12345678" + " end"
        self.assertEqual([n for n, _ in cp.scan_secrets(text)], [2])

    def test_private_key_header(self):
        line = "-" * 5 + "BEGIN RSA " + "PRIVATE" + " KEY" + "-" * 5
        self.assertEqual([n for n, _ in cp.scan_secrets("a\nb\n" + line)], [3])

    def test_password_assignment(self):
        self.assertEqual(len(cp.scan_secrets("password: " + "hunter2")), 1)

    def test_prose_clean(self):
        self.assertEqual(cp.scan_secrets("I wrote about passwords and tokens in prose."), [])


class DenylistTests(unittest.TestCase):
    def test_case_insensitive_whole_word(self):
        hits = cp.scan_denylist("a\nWorked at examplestealthco today", ["ExampleStealthCo"])
        self.assertEqual([n for n, _ in hits], [2])

    def test_inside_longer_word_ok(self):
        self.assertEqual(cp.scan_denylist("Fooxyzbar and xyzs", ["xyz"]), [])

    def test_empty_terms(self):
        self.assertEqual(cp.scan_denylist("anything", []), [])

    def test_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "dl"
            p.write_text("# comment\n\nFoo Co\n  bar  \n")
            self.assertEqual(cp.load_denylist(p), ["Foo Co", "bar"])
            self.assertEqual(cp.load_denylist(Path(d) / "missing"), [])


class ClaimTests(unittest.TestCase):
    def test_each_claim(self):
        for s in ["40% faster", "100% reliability", "30 concurrent workloads", "Hire me", "built solely by me",
                  "25% review time", "30% coverage", "Team Lead at STP", "STP team lead"]:
            self.assertEqual(len(cp.scan_forbidden_claims("x\n" + s)), 1, s)
            self.assertEqual(cp.scan_forbidden_claims("x\n" + s)[0][0], 2)

    def test_clean(self):
        self.assertEqual(cp.scan_forbidden_claims("Technical Team Head at STP. Led the team."), [])
        self.assertEqual(cp.scan_forbidden_claims("A team lead elsewhere"), [])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(TOOLS / "check_public.py"), *args],
                              capture_output=True, text=True)

    def test_exit_codes_and_recursion(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sub").mkdir()
            (root / "sub" / "a.md").write_text("fine\nhire me now\n")
            (root / "b.woff2").write_bytes(b"\x00\x01hire me\xff")
            r = self.run_cli(str(root))
            self.assertEqual(r.returncode, 1)
            self.assertIn("a.md:2:", r.stdout)
            self.assertNotIn("woff2", r.stdout)
            (root / "sub" / "a.md").write_text("fine\n")
            self.assertEqual(self.run_cli(str(root)).returncode, 0)

    def test_denylist_option(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.md").write_text("see ExampleStealthCo\n")
            (root / "dl").write_text("ExampleStealthCo\n")
            self.assertEqual(self.run_cli(str(root / "a.md")).returncode, 0)
            self.assertEqual(self.run_cli("--denylist", str(root / "dl"), str(root / "a.md")).returncode, 1)


def clean_env():
    import os
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


class MoreClaimTests(unittest.TestCase):
    def test_variants(self):
        for s in ["40 % faster", "40%faster", "forty percent faster", "100 % reliability", "30 %  coverage",
                  "25 % review time", "Forty Percent Faster"]:
            self.assertEqual(len(cp.scan_forbidden_claims(s)), 1, s)

    def test_wrapped_lines_report_start_line(self):
        hits = cp.scan_forbidden_claims("a\nit was 40%\n  faster than before\nb")
        self.assertEqual([n for n, _ in hits], [2])
        hits = cp.scan_forbidden_claims("a\nSTP\nTeam\nLead")
        self.assertEqual([n for n, _ in hits], [2])


class SmarterSecretTests(unittest.TestCase):
    def test_false_positives(self):
        for s in ["Password: required", "Passwort", 'other = "Password"', 'password = "Password"',
                  "The token: a short word is fine", "secret = {{ .Site.Params.x }}", "Token: Required",
                  "password: changeme"]:
            self.assertEqual(cp.scan_secrets(s), [], s)

    def test_true_positives(self):
        for s in ["password: hunter2", "secret = abCdefgh", "api_key: aBcDeFgHiJ", "token=ab-cd-ef-gh",
                  "api key: 12345678", 'password = "x' + 'Y9' + 'zzzzzz"']:
            self.assertEqual(len(cp.scan_secrets(s)), 1, s)


class UnicodeTests(unittest.TestCase):
    TERM = "\u0643\u0644\u064a\u0628"  # Arabic letters

    def test_zero_width(self):
        t = self.TERM[:2] + "\u200b" + self.TERM[2:]
        self.assertEqual([n for n, _ in cp.scan_denylist("x\nsee " + t + " here", [self.TERM])], [2])

    def test_diacritic_and_tatweel(self):
        t = self.TERM[:2] + "\u064e" + "\u0640" + self.TERM[2:]
        self.assertEqual(len(cp.scan_denylist("a " + t + " b", [self.TERM])), 1)
        self.assertEqual(len(cp.scan_denylist("a " + self.TERM + " b", [t])), 1)

    def test_nfkc_and_latin_combining(self):
        self.assertEqual(len(cp.scan_denylist("\uff25xample Co", ["Example Co"])), 1)
        self.assertEqual(len(cp.scan_denylist("Exampl\u0065\u0301 Co", ["Example Co"])), 1)

    def test_space_runs(self):
        self.assertEqual(len(cp.scan_denylist("Example   \n Co", ["Example Co"])), 1)
        self.assertEqual(len(cp.scan_denylist("Example Co", ["Example    Co"])), 1)


class CliStrictTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-I", str(TOOLS / "check_public.py"), *args],
                              capture_output=True, text=True, cwd=cwd)

    def test_missing_denylist_fails(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.md"
            f.write_text("fine\n")
            for args in (["--denylist", str(Path(d) / "nope"), str(f)], ["--denylist"], ["--denylist", "", str(f)]):
                r = self.run_cli(*args)
                self.assertNotEqual(r.returncode, 0, args)
                self.assertIn("denylist", (r.stdout + r.stderr).lower())
            empty = Path(d) / "empty"
            empty.write_text("# only a comment\n")
            self.assertNotEqual(self.run_cli("--denylist", str(empty), str(f)).returncode, 0)

    def test_nonexistent_path_fails(self):
        r = self.run_cli("/no/such/path-xyz")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no such", (r.stdout + r.stderr).lower())

    def test_output_never_echoes_matches(self):
        secret = "AK" + "IA" + "QWERTYUIOP" + "ASDFGH"
        term = "ExampleStealthCo"
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.md"
            f.write_text("k " + secret + "\nname " + term + "\n")
            dl = Path(d) / "dl"
            dl.write_text(term + "\n")
            r = self.run_cli("--denylist", str(dl), str(f))
            self.assertEqual(r.returncode, 1)
            out = r.stdout + r.stderr
            self.assertNotIn(secret, out)
            self.assertNotIn("QWERTYUIOP", out)
            self.assertNotIn(term, out)
            self.assertIn("a.md:1:", out)
            self.assertIn("a.md:2:", out)

    def test_skip_dirs_relative_to_root_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "node_modules" / "site"
            (root / "sub").mkdir(parents=True)
            (root / "sub" / "a.md").write_text("hire" + " me\n")
            self.assertEqual(self.run_cli(str(root)).returncode, 1)
            (root / "node_modules").mkdir()
            (root / "node_modules" / "b.md").write_text("hire" + " me\n")
            (root / "sub" / "a.md").write_text("ok\n")
            self.assertEqual(self.run_cli(str(root)).returncode, 0)

    def test_symlinked_dirs_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            real = Path(d) / "real"
            real.mkdir()
            (real / "a.md").write_text("hire" + " me\n")
            root = Path(d) / "root"
            root.mkdir()
            (root / "link").symlink_to(real, target_is_directory=True)
            self.assertEqual(self.run_cli(str(root)).returncode, 0)


class StagedScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "tools").mkdir()
        for n in ("check_public.py", "check_staged.sh"):
            (self.repo / "tools" / n).write_text((TOOLS / n).read_text())
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, env=clean_env(), capture_output=True, text=True, check=True)

    def run_staged(self):
        return subprocess.run(["bash", "tools/check_staged.sh"], cwd=self.repo, env=clean_env(),
                              capture_output=True, text=True)

    def test_scans_staged_blob_not_working_tree(self):
        (self.repo / "content").mkdir()
        f = self.repo / "content" / "a.md"
        f.write_text("please hire" + " me\n")
        self.git("add", "content/a.md")
        f.write_text("clean now\n")
        r = self.run_staged()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("a.md:1:", r.stdout)

    def test_clean_staged_passes_even_if_worktree_dirty(self):
        (self.repo / "content").mkdir()
        f = self.repo / "content" / "a.md"
        f.write_text("clean\n")
        self.git("add", "content/a.md")
        f.write_text("hire" + " me\n")
        self.assertEqual(self.run_staged().returncode, 0)

    def test_filename_with_space(self):
        (self.repo / "content").mkdir()
        f = self.repo / "content" / "my page \u00e9.md"
        f.write_text("hire" + " me\n")
        self.git("add", "-A")
        r = self.run_staged()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("my page", r.stdout)

    def commit(self, msg="c"):
        self.git("commit", "-q", "-m", msg)

    def test_rename_with_appended_leak(self):
        (self.repo / "content").mkdir()
        big = self.repo / "content" / "big.md"
        big.write_text("".join("line %d of ordinary prose here\n" % i for i in range(60)))
        self.git("add", "-A")
        self.commit()
        self.git("mv", "content/big.md", "content/big2.md")
        with open(self.repo / "content" / "big2.md", "a") as f:
            f.write("and then hire" + " me\n")
        self.git("add", "-A")
        self.assertIn("R", self.git("diff", "--cached", "--name-status").stdout.split()[0])
        r = self.run_staged()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("big2.md", r.stdout)

    def test_type_change_to_symlink(self):
        (self.repo / "content").mkdir()
        f = self.repo / "content" / "a.md"
        f.write_text("plain\n")
        self.git("add", "-A")
        self.commit()
        f.unlink()
        f.symlink_to("hire" + " me")
        self.git("add", "-A")
        self.assertTrue(self.git("diff", "--cached", "--name-status").stdout.startswith("T"))
        self.assertEqual(self.run_staged().returncode, 1)

    def test_warns_when_denylist_missing(self):
        (self.repo / "content").mkdir()
        (self.repo / "content" / "a.md").write_text("fine\n")
        self.git("add", "-A")
        r = self.run_staged()
        self.assertEqual(r.returncode, 0)
        self.assertIn("denylist not found, name check skipped", r.stdout + r.stderr)

    def test_nothing_staged_ok(self):
        self.assertEqual(self.run_staged().returncode, 0)

    def test_denylist_used_and_strict(self):
        (self.repo / "content").mkdir()
        (self.repo / "content" / "a.md").write_text("ExampleStealthCo\n")
        (self.repo / ".denylist").write_text("ExampleStealthCo\n")
        self.git("add", "content/a.md")
        self.assertEqual(self.run_staged().returncode, 1)
        (self.repo / ".denylist").write_text("# nothing\n")
        self.assertNotEqual(self.run_staged().returncode, 0)


if __name__ == "__main__":
    unittest.main()
