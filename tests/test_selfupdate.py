"""Tests for selfupdate.py (standard library unittest; pytest also collects them)."""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent


def _find_selfupdate() -> None:
    """Put the folder holding this repository's copy of selfupdate.py on sys.path
    (it sits at the top level, or inside the package, e.g. src/<pkg>/)."""
    skip = {".git", "build", "dist", "dist-app", ".venv", "venv", "site-packages", "node_modules"}
    for depth in range(4):
        for path in sorted(HERE.parent.glob("/".join(["*"] * depth + ["selfupdate.py"]))):
            if not skip.intersection(path.parts):
                if str(path.parent) not in sys.path:
                    sys.path.insert(0, str(path.parent))
                return


_find_selfupdate()

import selfupdate as su  # noqa: E402


def make_app(tmp: Path, version: str = "1.0.0", api: str | None = None) -> su.App:
    app = su.App(repo="owner/demo", name="Demo App", version=version, env_prefix="DEMO",
                 settings_dir=tmp / "settings")
    if api:
        os.environ["DEMO_UPDATE_API"] = api
    return app


class VersionTests(unittest.TestCase):
    def test_order(self):
        self.assertTrue(su.is_newer("1.0.1", "1.0.0"))
        self.assertTrue(su.is_newer("v2.0", "1.9.9"))
        self.assertTrue(su.is_newer("1.1", "1.0"))
        self.assertFalse(su.is_newer("1.0", "1.0.0"))
        self.assertFalse(su.is_newer("1.0.0rc1", "1.0.0"))
        self.assertTrue(su.is_newer("1.0.0", "1.0.0rc1"))
        self.assertFalse(su.is_newer("garbage", "1.0"))


class AssetTests(unittest.TestCase):
    names = [
        "Demo-1.1.0-windows-x64-setup.exe", "Demo-1.1.0-windows-x64-portable.zip",
        "Demo-1.1.0-macos-arm64.dmg", "Demo-1.1.0-macos-x86_64.dmg",
        "Demo-1.1.0-linux-x86_64.tar.gz", "demo_1.1.0_amd64.deb", "SHA256SUMS.txt",
        "demo-1.1.0-py3-none-any.whl",
    ]

    def test_each_kind(self):
        self.assertEqual(su.pick_asset(self.names, "win-setup", "win32"), self.names[0])
        self.assertEqual(su.pick_asset(self.names, "win-portable", "win32"), self.names[1])
        self.assertEqual(su.pick_asset(self.names, "mac-app", "darwin", "arm64"), self.names[2])
        self.assertEqual(su.pick_asset(self.names, "mac-app", "darwin", "x86_64"), self.names[3])
        self.assertEqual(su.pick_asset(self.names, "unix-dir", "linux", "x86_64"), self.names[4])
        self.assertEqual(su.pick_asset(self.names, "linux-deb", "linux", "x86_64"), self.names[5])
        self.assertIsNone(su.pick_asset(self.names, "unix-dir", "linux", "aarch64"))
        self.assertIsNone(su.pick_asset(self.names, "pip", "linux"))

    def test_older_spelling(self):
        names = ["XPS-AutoFit-Studio-0.5.0-Windows-x64-Setup.exe", "XPS-AutoFit-Studio-0.5.0-macOS-arm64.dmg",
                 "XPS-AutoFit-Studio-0.5.0-Linux-x86_64.tar.gz", "XPS-AutoFit-Studio-0.5.0-Windows-x64.zip"]
        self.assertEqual(su.pick_asset(names, "win-setup", "win32"), names[0])
        self.assertEqual(su.pick_asset(names, "win-portable", "win32"), names[3])
        self.assertEqual(su.pick_asset(names, "mac-app", "darwin", "arm64"), names[1])
        self.assertIsNone(su.pick_asset(names, "mac-app", "darwin", "x86_64"))
        self.assertEqual(su.pick_asset(names, "unix-dir", "linux", "x86_64"), names[2])


class ChecksumTests(unittest.TestCase):
    def test_parse(self):
        text = ("a" * 64 + "  Demo.dmg\n" + "B" * 64 + " *dist/Demo.zip\nnot a line\n")
        self.assertEqual(su.parse_checksums(text), {"Demo.dmg": "a" * 64, "Demo.zip": "b" * 64})


class DetectTests(unittest.TestCase):
    def test_not_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(Path(tmp))
            inst = su.detect_install(app, frozen=False)
            self.assertEqual(inst.kind, "source")
            self.assertFalse(inst.can_apply)

    def test_windows_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Demo"
            (root / "_internal").mkdir(parents=True)
            exe = root / "Demo.exe"
            exe.write_bytes(b"MZ")
            app = make_app(Path(tmp))
            inst = su.detect_install(app, str(exe), True, "win32")
            self.assertEqual((inst.kind, inst.target), ("win-portable", root.resolve()))
            (root / "unins000.exe").write_bytes(b"MZ")
            self.assertEqual(su.detect_install(app, str(exe), True, "win32").kind, "win-setup")

    def test_mac_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Demo.app" / "Contents" / "MacOS" / "Demo"
            exe.parent.mkdir(parents=True)
            exe.write_text("#!/bin/sh\n")
            inst = su.detect_install(make_app(Path(tmp)), str(exe), True, "darwin")
            self.assertEqual(inst.kind, "mac-app")
            self.assertEqual(inst.target.name, "Demo.app")
            self.assertTrue(inst.can_apply)

    def test_linux_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Demo"
            (root / "_internal").mkdir(parents=True)
            exe = root / "demo"
            exe.write_text("#!/bin/sh\n")
            inst = su.detect_install(make_app(Path(tmp)), str(exe), True, "linux")
            self.assertEqual((inst.kind, inst.target), ("unix-dir", root.resolve()))


class SettingsTests(unittest.TestCase):
    def test_mode_and_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(Path(tmp))
            up = su.Updater(app, su.Install("source", None, [], False))
            self.assertEqual(up.mode, "auto")
            with mock.patch.dict(os.environ, {"CI": "", "DEMO_NO_UPDATE": ""}):
                os.environ.pop("CI")
                self.assertTrue(up.due())
                up.mode = "off"
                self.assertFalse(up.due())
                up.mode = "notify"
                self.assertEqual(su.Updater(app).mode, "notify")
                up._settings["last_check"] = time.time()
                self.assertFalse(up.due())
            with mock.patch.dict(os.environ, {"DEMO_NO_UPDATE": "1"}):
                up._settings["last_check"] = 0
                self.assertFalse(up.due())
            with self.assertRaises(ValueError):
                up.mode = "sometimes"


class FakeGitHub:
    """Serve a release JSON and its files from a temporary folder."""

    def __init__(self, files: dict, version: str, corrupt: str | None = None):
        self.files = dict(files)
        sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items())
        self.files["SHA256SUMS.txt"] = sums.encode()
        if corrupt:
            self.files[corrupt] = self.files[corrupt] + b"tampered"
        self.version = version
        handler = self._handler()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _handler(self):
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/api":
                    body = json.dumps({
                        "tag_name": f"v{fake.version}", "html_url": fake.base + "/page",
                        "assets": [{"name": n, "browser_download_url": f"{fake.base}/f/{n}", "size": len(d)}
                                   for n, d in fake.files.items()]}).encode()
                elif self.path.startswith("/f/") and self.path[3:] in fake.files:
                    body = fake.files[self.path[3:]]
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def close(self):
        self.server.shutdown()


def tar_of(folder_name: str, files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, (data, mode) in files.items():
            info = tarfile.TarInfo(f"{folder_name}/{rel}")
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: os.environ.pop("DEMO_UPDATE_API", None))

    def _installed(self) -> Path:
        root = self.tmp / "apps" / "Demo"
        (root / "_internal").mkdir(parents=True)
        (root / "_internal" / "version.txt").write_text("1.0.0")
        exe = root / "demo"
        exe.write_text("#!/bin/sh\necho 1.0.0\n")
        exe.chmod(0o755)
        return exe

    def test_checksum_mismatch_is_refused(self):
        exe = self._installed()
        archive = tar_of("Demo", {"demo": (b"#!/bin/sh\necho 1.1.0\n", 0o755)})
        gh = FakeGitHub({"Demo-1.1.0-linux-x86_64.tar.gz": archive}, "1.1.0",
                        corrupt="Demo-1.1.0-linux-x86_64.tar.gz")
        self.addCleanup(gh.close)
        app = make_app(self.tmp, api=gh.base + "/api")
        up = su.Updater(app, su.detect_install(app, str(exe), True, "linux"))
        release = up.check()
        with mock.patch.object(su, "machine_arch", return_value="x86_64"):
            self.assertTrue(up.can_install(release))
            with self.assertRaises(su.UpdateError):
                up.prepare(release)
        self.assertIsNone(up.pending)
        self.assertFalse(any((app.folder() / "updates").glob("*.part")))

    @unittest.skipIf(sys.platform == "win32", "POSIX helper")
    def test_swap_after_exit(self):
        exe = self._installed()
        archive = tar_of("Demo", {"demo": (b"#!/bin/sh\necho 1.1.0\n", 0o755),
                                  "_internal/version.txt": (b"1.1.0", 0o644)})
        gh = FakeGitHub({"Demo-1.1.0-linux-x86_64.tar.gz": archive}, "1.1.0")
        self.addCleanup(gh.close)
        app = make_app(self.tmp, api=gh.base + "/api")
        up = su.Updater(app, su.detect_install(app, str(exe), True, "linux"))
        release = up.check()
        self.assertTrue(release.newer)
        with mock.patch.object(su, "machine_arch", return_value="x86_64"):
            plan = up.prepare(release)
        self.assertEqual(plan.mode, "swap")
        self.assertEqual((plan.new / "_internal" / "version.txt").read_text(), "1.1.0")
        # The helper waits for this stand-in "program" to exit before swapping.
        program = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
        su.apply(up.pending, app.folder(), relaunch=False, pid=program.pid, system="linux")
        up.pending = None
        time.sleep(0.6)
        self.assertEqual((exe.parent / "_internal" / "version.txt").read_text(), "1.0.0")
        program.wait()

        def installed() -> str | None:
            # between the helper's two renames the folder briefly does not exist
            try:
                return (exe.parent / "_internal" / "version.txt").read_text()
            except OSError:
                return None

        for _ in range(100):
            if installed() == "1.1.0":
                break
            time.sleep(0.2)
        self.assertEqual(installed(), "1.1.0")
        self.assertEqual(subprocess.run([str(exe)], capture_output=True, text=True).stdout.strip(), "1.1.0")
        self.assertFalse((exe.parent.parent / "Demo.old-update").exists())
        self.assertFalse((exe.parent.parent / ".Demo.update").exists())
        self.assertIn("updated", (app.folder() / "update.log").read_text())

    @unittest.skipUnless(sys.platform == "darwin", "needs hdiutil")
    def test_mac_dmg_swap(self):
        def bundle(where: Path, version: str) -> Path:
            app = where / "Demo.app"
            (app / "Contents" / "MacOS").mkdir(parents=True)
            exe = app / "Contents" / "MacOS" / "Demo"
            exe.write_text(f"#!/bin/sh\necho {version}\n")
            exe.chmod(0o755)
            (app / "Contents" / "Info.plist").write_text(version)
            return exe
        exe = bundle(self.tmp / "Applications", "1.0.0")
        src = self.tmp / "dmgsrc"
        bundle(src, "1.1.0")
        dmg = self.tmp / "Demo-1.1.0-macos-arm64.dmg"
        subprocess.run(["hdiutil", "create", "-quiet", "-volname", "Demo", "-srcfolder", str(src),
                        "-format", "UDZO", str(dmg)], check=True)
        gh = FakeGitHub({dmg.name: dmg.read_bytes()}, "1.1.0")
        self.addCleanup(gh.close)
        app = make_app(self.tmp, api=gh.base + "/api")
        up = su.Updater(app, su.detect_install(app, str(exe), True, "darwin"))
        with mock.patch.object(su, "machine_arch", return_value="arm64"):
            plan = up.prepare(up.check())
        self.assertEqual(plan.target.name, "Demo.app")
        program = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"])
        su.apply(up.pending, app.folder(), relaunch=False, pid=program.pid, system="darwin")
        up.pending = None
        program.wait()
        plist = self.tmp / "Applications" / "Demo.app" / "Contents" / "Info.plist"

        def installed() -> str | None:
            try:
                return plist.read_text()
            except OSError:
                return None

        for _ in range(100):
            if installed() == "1.1.0":
                break
            time.sleep(0.2)
        self.assertEqual(installed(), "1.1.0")
        self.assertEqual(sorted(p.name for p in (self.tmp / "Applications").iterdir()), ["Demo.app"])

    def test_zip_portable_stage(self):
        root = self.tmp / "apps" / "Demo"
        (root / "_internal").mkdir(parents=True)
        exe = root / "Demo.exe"
        exe.write_bytes(b"MZ old")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Demo/Demo.exe", b"MZ new")
            zf.writestr("Demo/_internal/x.dll", b"dll")
        gh = FakeGitHub({"Demo-1.1.0-windows-x64-portable.zip": buf.getvalue()}, "1.1.0")
        self.addCleanup(gh.close)
        app = make_app(self.tmp, api=gh.base + "/api")
        up = su.Updater(app, su.detect_install(app, str(exe), True, "win32"))
        plan = up.prepare(up.check())
        self.assertEqual(plan.target, root.resolve())
        self.assertEqual((plan.new / "Demo.exe").read_bytes(), b"MZ new")
        cmd = su.helper_command(plan, Path("x.ps1"), 42, True, "win32")
        self.assertIn("-WaitPid", cmd)
        self.assertEqual(cmd[cmd.index("-Mode") + 1], "swap")

    def test_no_checksums_no_install(self):
        release = su.Release("2.0", True, "p", {"Demo-2.0-linux-x86_64.tar.gz": "u"})
        app = make_app(self.tmp)
        up = su.Updater(app, su.Install("unix-dir", self.tmp, ["x"], True))
        with mock.patch.object(su, "machine_arch", return_value="x86_64"):
            self.assertFalse(up.can_install(release))

    def test_unsafe_tar_is_refused(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo("../evil")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        path = self.tmp / "evil.tar.gz"
        path.write_bytes(buf.getvalue())
        with self.assertRaises(Exception):
            su._safe_extract_tar(path, self.tmp / "out")
        self.assertFalse((self.tmp / "evil").exists())


class CliTests(unittest.TestCase):
    def test_up_to_date_and_pip_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = su.App("owner/demo", "Demo", "1.0.0", "DEMO", pip_name="demo", settings_dir=Path(tmp))
            up = su.Updater(app, su.Install("pip", None, [], False))
            lines = []
            with mock.patch.object(su, "fetch_release", return_value=su.Release("1.0.0", False, "p")):
                self.assertEqual(su.cli(up, out=lines.append), 0)
            self.assertIn("up to date", lines[-1])
            lines.clear()
            with mock.patch.object(su, "fetch_release", return_value=su.Release("1.2.0", True, "p")):
                su.cli(up, out=lines.append)
            self.assertIn('pip install -U "demo"', lines[-1])


if __name__ == "__main__":
    unittest.main()
