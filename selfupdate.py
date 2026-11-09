"""Automatic updates from GitHub Releases, standard library only.

The same file is copied into each desktop program of github.com/jongsu-king;
keep the copies identical (``SELFUPDATE_REVISION`` below says which one you have).

How an update happens
---------------------
1. ``Updater.check()`` sends one anonymous request to
   ``https://api.github.com/repos/<owner>/<repo>/releases/latest``.  The only thing
   it sends about you is the ``User-Agent`` header, ``<program>/<version>``.
2. When the release is newer and this copy was installed from one of the release
   files (installer, disk image, archive or .deb), ``Updater.prepare()`` downloads
   the file for this operating system and processor and compares its SHA-256 with
   the ``SHA256SUMS.txt`` attached to the same release.  A file that does not match
   is deleted.  A release without ``SHA256SUMS.txt`` is never installed
   automatically.
3. The file is unpacked next to the current installation.  When the program
   exits (or the user picks *Restart now*), a small helper script waits for the
   process to end, swaps the old installation for the new one - or runs the
   Windows installer silently - and, if asked, starts the new version.

A copy installed with ``pip`` or run from a source checkout is never modified;
it is told the command that updates it.

Modes (stored in ``update.json`` in the program's settings folder):

* ``auto``   - check once a day, download and verify in the background, install
  on exit or on *Restart now* (default);
* ``notify`` - check once a day and only say that a new version exists;
* ``off``    - never check unless asked (*Help > Check for updates*).

``<PREFIX>_NO_UPDATE=1`` in the environment, or ``CI`` being set, turns the
automatic check off (used by tests and packaging smoke tests).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

SELFUPDATE_REVISION = "2026-11-09.4"

MODES = ("auto", "notify", "off")
DEFAULT_MODE = "auto"
CHECK_INTERVAL_S = 24 * 3600
CHECKSUMS = "SHA256SUMS.txt"
TIMEOUT_S = 10.0

Progress = Callable[[int, int], None]


class UpdateError(RuntimeError):
    """Raised for anything that stops a check, a download or an installation."""


# --------------------------------------------------------------------------- versions
def parse_version(text: str) -> tuple:
    """``"v1.2"`` -> ``(1, 2, 0, 0, 0)``; a pre-release sorts below its release."""
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)(?:[-.]?(a|b|rc|alpha|beta|dev|pre)\.?(\d*))?", str(text or ""), re.I)
    if not m:
        raise ValueError(f"not a version: {text!r}")
    parts = [int(p) for p in m.group(1).split(".")][:4]
    parts += [0] * (4 - len(parts))
    pre = (-1, int(m.group(3) or 0)) if m.group(2) else (0, 0)
    return tuple(parts) + pre


def is_newer(candidate: str, current: str) -> bool:
    try:
        return parse_version(candidate) > parse_version(current)
    except ValueError:
        return False


# --------------------------------------------------------------------------- program
@dataclass(frozen=True)
class App:
    """What the updater needs to know about the program."""

    repo: str                    # "owner/name" on GitHub
    name: str                    # display name, also the settings folder name
    version: str                 # the running version
    env_prefix: str              # "XRD" -> XRD_NO_UPDATE, XRD_UPDATE_API
    pip_name: Optional[str] = None   # distribution name for ``pip install -U``
    settings_dir: Optional[Path] = None

    @property
    def api_url(self) -> str:
        return os.environ.get(f"{self.env_prefix}_UPDATE_API") or (
            f"https://api.github.com/repos/{self.repo}/releases/latest")

    @property
    def releases_page(self) -> str:
        return f"https://github.com/{self.repo}/releases/latest"

    def folder(self) -> Path:
        if self.settings_dir:
            return Path(self.settings_dir)
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        return base / self.name


def disabled_by_environment(app: App, environ=None) -> bool:
    env = os.environ if environ is None else environ
    flag = str(env.get(f"{app.env_prefix}_NO_UPDATE", "")).strip().lower()
    return flag not in ("", "0", "false", "no") or bool(env.get("CI"))


# --------------------------------------------------------------------------- release
@dataclass
class Release:
    version: str
    newer: bool
    page: str
    assets: dict = field(default_factory=dict)      # name -> download URL
    sizes: dict = field(default_factory=dict)       # name -> bytes
    notes: str = ""
    published: str = ""

    @property
    def checksums_url(self) -> Optional[str]:
        return self.assets.get(CHECKSUMS)


# A frozen (PyInstaller) build carries its own OpenSSL, whose built-in certificate
# location usually does not exist on the user's machine (macOS always, some Linux
# distributions), so HTTPS would fail with CERTIFICATE_VERIFY_FAILED. Fall back to
# certifi when it is bundled, else to the system's CA bundle.
CA_FILES = (
    "/etc/ssl/cert.pem",                       # macOS, Alpine, Arch
    "/etc/ssl/certs/ca-certificates.crt",      # Debian, Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",        # Fedora, RHEL
    "/etc/ssl/ca-bundle.pem",                  # openSUSE
    "/etc/pki/tls/cacert.pem",
)
_SSL_CONTEXT: Optional[ssl.SSLContext] = None


def ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        context = ssl.create_default_context()
        if not context.cert_store_stats().get("x509_ca"):
            cafile = None
            try:
                import certifi  # bundled with httpx/requests in several programs
                cafile = certifi.where()
            except Exception:  # noqa: BLE001
                cafile = next((f for f in CA_FILES if os.path.exists(f)), None)
            if cafile and os.path.exists(cafile):
                context = ssl.create_default_context(cafile=cafile)
        _SSL_CONTEXT = context
    return _SSL_CONTEXT


def _request(app: App, url: str, accept: str = "application/octet-stream"):
    req = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": f"{app.name.replace(' ', '-')}/{app.version}"})
    context = ssl_context() if url.startswith("https:") else None
    return urllib.request.urlopen(req, timeout=TIMEOUT_S, context=context)  # noqa: S310


def fetch_release(app: App, opener=None) -> Release:
    """Ask GitHub for the latest release.  ``opener(url) -> dict`` replaces the network in tests."""
    try:
        if opener is not None:
            data = opener(app.api_url)
        else:
            with _request(app, app.api_url, "application/vnd.github+json") as resp:
                data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise UpdateError("GitHub rate limit reached; try again in an hour") from exc
        if exc.code == 404:
            raise UpdateError("no release has been published yet") from exc
        raise UpdateError(f"GitHub answered HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError(f"cannot reach GitHub ({exc})") from exc
    if not isinstance(data, dict):
        raise UpdateError("unexpected answer from GitHub")
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("the latest release has no tag")
    version = tag[1:] if tag[:1] in "vV" else tag
    assets, sizes = {}, {}
    for item in data.get("assets") or []:
        name, url = item.get("name"), item.get("browser_download_url")
        if name and url:
            assets[str(name)] = str(url)
            sizes[str(name)] = int(item.get("size") or 0)
    return Release(version=version, newer=is_newer(version, app.version),
                   page=str(data.get("html_url") or app.releases_page), assets=assets,
                   sizes=sizes, notes=str(data.get("body") or ""),
                   published=str(data.get("published_at") or ""))


# --------------------------------------------------------------------------- installation
@dataclass
class Install:
    """How the running copy was installed, and whether it can replace itself."""

    kind: str                 # win-setup | win-portable | mac-app | linux-deb | unix-dir | pip | source
    target: Optional[Path]    # file, folder or .app bundle that gets replaced
    launch: list              # command that starts the program again
    can_apply: bool
    reason: str = ""
    system: str = sys.platform

    @property
    def frozen(self) -> bool:
        return self.kind not in ("pip", "source")


def _writable(path: Path) -> bool:
    try:
        return os.access(path, os.W_OK)
    except OSError:
        return False


def detect_install(app: App, executable: Optional[str] = None, frozen: Optional[bool] = None,
                   system: str = sys.platform) -> Install:
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = Path(executable or sys.executable).resolve()
    if not frozen:
        kind = "source"
        if app.pip_name:
            try:
                from importlib import metadata
                metadata.distribution(app.pip_name)
                kind = "pip"
            except Exception:  # noqa: BLE001 - any failure means "not a pip install"
                kind = "source"
        return Install(kind, None, [], False, "installed with pip" if kind == "pip" else "run from source", system=system)
    folder = exe.parent
    onedir = (folder / "_internal").is_dir()
    if system == "win32":
        if any(folder.glob("unins*.exe")):
            return Install("win-setup", folder, [str(exe)], True, system=system)
        target = folder if onedir else exe
        ok = _writable(target.parent)
        return Install("win-portable", target, [str(exe)], ok, "" if ok else "folder is read-only", system=system)
    if system == "darwin":
        bundle = next((p for p in exe.parents if p.suffix == ".app"), None)
        if bundle is not None:
            ok = _writable(bundle.parent) and _writable(bundle)
            return Install("mac-app", bundle, ["/usr/bin/open", str(bundle)], ok,
                           "" if ok else f"{bundle.parent} is not writable", system=system)
        target = folder if onedir else exe
        ok = _writable(target.parent)
        return Install("unix-dir", target, [str(exe)], ok, "" if ok else "folder is read-only", system=system)
    # Linux and other Unix
    if str(exe).startswith(("/opt/", "/usr/")) and shutil.which("dpkg"):
        ok = shutil.which("pkexec") is not None
        return Install("linux-deb", None, [str(exe)], ok, "" if ok else "pkexec not found", system=system)
    target = folder if onedir else exe
    ok = _writable(target.parent)
    return Install("unix-dir", target, [str(exe)], ok, "" if ok else "folder is read-only", system=system)


def machine_arch(machine: Optional[str] = None) -> str:
    m = (machine or platform.machine() or "").lower()
    if m in ("arm64", "aarch64", "armv8", "armv8l"):
        return "arm64"
    return "x86_64"


def pick_asset(names, kind: str, system: str = sys.platform, machine: Optional[str] = None) -> Optional[str]:
    """Choose the release file that updates an installation of ``kind`` on this computer."""
    arch = machine_arch(machine)
    lowered = [(n.lower(), n) for n in names if n != CHECKSUMS]
    arch_words = ("arm64", "aarch64") if arch == "arm64" else ("x86_64", "x64", "amd64", "intel")

    def find(ends, words=(), any_of=()):
        for low, real in lowered:
            if low.endswith(ends) and all(w in low for w in words) and (
                    not any_of or any(w in low for w in any_of)):
                return real
        return None

    if kind == "win-setup":
        return find("setup.exe", ("windows",)) or find("setup.exe")
    if kind == "win-portable":
        return find(".zip", ("windows", "portable")) or find(".zip", ("windows",))
    if kind == "mac-app":
        return find(".dmg", any_of=arch_words) or find(".dmg", ("universal",))
    if kind == "linux-deb":
        return find(".deb", any_of=("_amd64",) if arch == "x86_64" else ("_arm64",))
    if kind == "unix-dir":
        word = "macos" if system == "darwin" else "linux"
        return find(".tar.gz", (word,), arch_words) or find(".tgz", (word,), arch_words)
    return None


# --------------------------------------------------------------------------- download
def parse_checksums(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            out[parts[-1].lstrip("*").split("/")[-1]] = parts[0].lower()
    return out


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(app: App, release: Release, name: str, folder: Path,
             progress: Optional[Progress] = None) -> Path:
    """Download ``name`` from ``release`` into ``folder`` and verify it with SHA256SUMS.txt."""
    if not release.checksums_url:
        raise UpdateError(f"the release has no {CHECKSUMS}; not installing it automatically")
    try:
        with _request(app, release.checksums_url) as resp:
            sums = parse_checksums(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(f"cannot download {CHECKSUMS} ({exc})") from exc
    expected = sums.get(name)
    if not expected:
        raise UpdateError(f"{name} is not listed in {CHECKSUMS}")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    partial = folder / (name + ".part")
    digest = hashlib.sha256()
    total = release.sizes.get(name, 0)
    done = 0
    try:
        with _request(app, release.assets[name]) as resp, open(partial, "wb") as out:
            total = int(resp.headers.get("Content-Length") or total or 0)
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except (urllib.error.URLError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"download failed ({exc})") from exc
    if digest.hexdigest() != expected:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"SHA-256 of {name} does not match {CHECKSUMS}; file deleted")
    os.replace(partial, target)
    return target


# --------------------------------------------------------------------------- staging
@dataclass
class Plan:
    mode: str                 # "setup" (run installer), "swap" (replace target), "deb"
    target: Optional[Path]
    new: Path                 # installer, .deb, or the staged replacement
    launch: list
    version: str


def _safe_extract_tar(archive: Path, dest: Path) -> None:
    with tarfile.open(archive) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
            return
        root = dest.resolve()
        for member in tar.getmembers():
            path = (dest / member.name).resolve()
            if root not in path.parents and path != root:
                raise UpdateError(f"unsafe path in archive: {member.name}")
            if member.issym() or member.islnk():
                link = (path.parent / member.linkname).resolve()
                if root not in link.parents:
                    raise UpdateError(f"unsafe link in archive: {member.name}")
        tar.extractall(dest)  # noqa: S202 - members checked above


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            path = (dest / name).resolve()
            if root not in path.parents and path != root:
                raise UpdateError(f"unsafe path in archive: {name}")
        zf.extractall(dest)


def find_replacement(root: Path, target: Path, launcher_name: str) -> Optional[Path]:
    """Find, in an unpacked release, the folder or file that takes ``target``'s place."""
    candidates = []
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts)):
        if len(path.relative_to(root).parts) > 3:
            break
        candidates.append(path)
    if target.is_dir() or target.suffix == ".app":
        for path in candidates:
            if path.is_dir() and path.name == target.name:
                return path
        for path in candidates:
            if path.is_dir() and (path / launcher_name).exists():
                return path
        return None
    for path in candidates:
        if path.is_file() and path.name in (target.name, launcher_name):
            return path
    runnable = [p for p in candidates if p.is_file() and (os.access(p, os.X_OK) or p.suffix.lower() == ".exe")]
    return runnable[0] if len(runnable) == 1 else None


def stage(install: Install, package: Path, version: str) -> Plan:
    """Turn a verified download into a plan the helper script can carry out."""
    if install.kind == "win-setup":
        return Plan("setup", install.target, package, install.launch, version)
    if install.kind == "linux-deb":
        return Plan("deb", None, package, install.launch, version)
    target = install.target
    if target is None:
        raise UpdateError("this installation cannot replace itself")
    staging = target.parent / f".{target.name}.update"
    shutil.rmtree(staging, ignore_errors=True)
    if staging.exists():
        staging.unlink()
    staging.mkdir(parents=True)
    launcher = Path(install.launch[-1]).name if install.launch else target.name
    if install.kind == "mac-app":
        mount = Path(tempfile.mkdtemp(prefix="selfupdate-"))
        try:
            _run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount), str(package)])
        except UpdateError:  # newer macOS: hdiutil attach is deprecated in favour of diskutil
            _run(["diskutil", "image", "attach", "--mountOptions", "nobrowse", "--readOnly",
                  "--mountPoint", str(mount), str(package)])
        try:
            source = next((p for p in mount.iterdir() if p.suffix == ".app"), None)
            if source is None:
                raise UpdateError("the disk image holds no .app")
            new = staging / target.name
            _run(["ditto", str(source), str(new)])
        finally:
            for _ in range(5):
                if subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], capture_output=True).returncode == 0:
                    break
                time.sleep(1.0)
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(new)], capture_output=True)
        return Plan("swap", target, new, install.launch, version)
    if package.name.lower().endswith((".tar.gz", ".tgz")):
        _safe_extract_tar(package, staging)
    elif package.suffix.lower() == ".zip":
        _safe_extract_zip(package, staging)
    else:
        shutil.copy2(package, staging / target.name)
    new = find_replacement(staging, target, launcher)
    if new is None:
        raise UpdateError(f"{package.name} does not contain {target.name}")
    if new.is_file() and sys.platform != "win32":
        new.chmod(new.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return Plan("swap", target, new, install.launch, version)


def _run(command: list) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise UpdateError(f"{Path(command[0]).name}: {detail[-1] if detail else result.returncode}")


# --------------------------------------------------------------------------- applying
POSIX_HELPER = r"""#!/bin/sh
# Written by selfupdate.py: wait for the program to exit, replace it, start it again.
pid="$1"; mode="$2"; target="$3"; new="$4"; shift 4
i=0
while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 600 ]; do sleep 0.2; i=$((i+1)); done
sleep 0.5
case "$mode" in
  swap)
    old="$target.old-update"
    rm -rf "$old"
    mv "$target" "$old" || exit 1
    if mv "$new" "$target"; then rm -rf "$old"; else mv "$old" "$target"; exit 1; fi
    rmdir "$(dirname "$new")" 2>/dev/null
    parent="$(dirname "$target")"; rm -rf "$parent/.$(basename "$target").update"
    ;;
  deb)
    pkexec apt-get install -y "$new" || pkexec dpkg -i "$new" || exit 1
    ;;
esac
echo "updated $(date)"
if [ "$#" -gt 0 ]; then exec "$@"; fi
"""

WINDOWS_HELPER = r"""# Written by selfupdate.py: wait for the program to exit, replace it, start it again.
param([int]$WaitPid, [string]$Mode, [string]$Target, [string]$New, [string]$Launch)
try { Wait-Process -Id $WaitPid -Timeout 120 -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Milliseconds 800
if ($Mode -eq 'setup') {
  $p = Start-Process -FilePath $New -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS','/NORESTARTAPPLICATIONS' -Wait -PassThru
  if ($p.ExitCode -ne 0) { "installer exit code $($p.ExitCode)"; exit $p.ExitCode }
} else {
  $old = "$Target.old-update"
  if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }
  $moved = $false
  for ($i = 0; $i -lt 30 -and -not $moved; $i++) {
    try { Move-Item -LiteralPath $Target -Destination $old -ErrorAction Stop; $moved = $true }
    catch { Start-Sleep -Seconds 1 }
  }
  if (-not $moved) { "could not move $Target"; exit 1 }
  try { Move-Item -LiteralPath $New -Destination $Target -ErrorAction Stop }
  catch { Move-Item -LiteralPath $old -Destination $Target; "could not place the new version"; exit 1 }
  Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
  $staging = Join-Path (Split-Path -Parent $Target) ('.' + (Split-Path -Leaf $Target) + '.update')
  Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
}
"updated $(Get-Date)"
if ($Launch) { Start-Process -FilePath $Launch }
"""


def helper_command(plan: Plan, script: Path, pid: int, relaunch: bool, system: str = sys.platform) -> list:
    launch = list(plan.launch) if relaunch else []
    if system == "win32":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                "-File", str(script), "-WaitPid", str(pid), "-Mode", plan.mode,
                "-Target", str(plan.target or ""), "-New", str(plan.new),
                "-Launch", launch[0] if launch else ""]
    return ["/bin/sh", str(script), str(pid), plan.mode, str(plan.target or ""), str(plan.new), *launch]


def apply(plan: Plan, log_folder: Path, relaunch: bool = True, pid: Optional[int] = None,
          system: str = sys.platform) -> list:
    """Start the helper that installs ``plan`` once process ``pid`` has exited.

    The caller must exit soon afterwards; the helper waits up to two minutes.
    Returns the helper command (for logging and tests).
    """
    log_folder.mkdir(parents=True, exist_ok=True)
    if system == "win32":
        script = log_folder / "apply-update.ps1"
        script.write_text(WINDOWS_HELPER, encoding="utf-8-sig")
    else:
        script = log_folder / "apply-update.sh"
        script.write_text(POSIX_HELPER, encoding="utf-8")
        script.chmod(0o700)
    command = helper_command(plan, script, pid or os.getpid(), relaunch, system)
    log = open(log_folder / "update.log", "a", encoding="utf-8")  # noqa: SIM115 - handed to the child
    log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] applying {plan.version} ({plan.mode})\n")
    log.flush()
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT, "close_fds": True}
    if system == "win32":
        kwargs["creationflags"] = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                                   | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)  # noqa: S603 - fixed helper script
    log.close()
    return command


# --------------------------------------------------------------------------- settings + controller
class Updater:
    """Holds the mode, remembers when it last checked and carries out updates."""

    def __init__(self, app: App, install: Optional[Install] = None) -> None:
        self.app = app
        self.install = install or detect_install(app)
        self.pending: Optional[Plan] = None
        self._at_exit_registered = False
        self._settings = self._load()

    # settings
    @property
    def settings_file(self) -> Path:
        return self.app.folder() / "update.json"

    def _load(self) -> dict:
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")
        except OSError:
            pass

    @property
    def mode(self) -> str:
        mode = self._settings.get("mode", DEFAULT_MODE)
        return mode if mode in MODES else DEFAULT_MODE

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in MODES:
            raise ValueError(value)
        self._settings["mode"] = value
        self._save()

    def due(self, now: Optional[float] = None) -> bool:
        """True when the automatic check should run now."""
        if self.mode == "off" or disabled_by_environment(self.app):
            return False
        last = float(self._settings.get("last_check") or 0)
        return (now or time.time()) - last >= CHECK_INTERVAL_S

    # actions
    def check(self, opener=None) -> Release:
        release = fetch_release(self.app, opener)
        self._settings["last_check"] = time.time()
        self._settings["last_seen"] = release.version
        self._save()
        return release

    def asset_for(self, release: Release) -> Optional[str]:
        return pick_asset(release.assets, self.install.kind, self.install.system)

    def can_install(self, release: Release) -> bool:
        return bool(release.newer and self.install.can_apply and self.asset_for(release)
                    and release.checksums_url)

    def prepare(self, release: Release, progress: Optional[Progress] = None) -> Plan:
        """Download, verify and unpack ``release``; afterwards ``pending`` holds the plan."""
        name = self.asset_for(release)
        if not name:
            raise UpdateError("the release has no file for this computer")
        if not self.install.can_apply:
            raise UpdateError(f"this copy cannot update itself ({self.install.reason})")
        folder = self.app.folder() / "updates"
        if folder.exists():
            for leftover in folder.iterdir():
                if leftover.is_file():
                    leftover.unlink(missing_ok=True)
        package = download(self.app, release, name, folder, progress)
        self.pending = stage(self.install, package, release.version)
        if not self._at_exit_registered:
            atexit.register(self._apply_at_exit)
            self._at_exit_registered = True
        return self.pending

    def apply_now(self, relaunch: bool = True) -> bool:
        """Start the helper; the caller must then quit the program."""
        if self.pending is None:
            return False
        plan, self.pending = self.pending, None
        apply(plan, self.app.folder(), relaunch=relaunch)
        return True

    def _apply_at_exit(self) -> None:
        if self.pending is not None:
            try:
                self.apply_now(relaunch=False)
            except Exception:  # noqa: BLE001 - never fail interpreter shutdown
                pass

    def manual_instructions(self, release: Release) -> str:
        if self.install.kind == "pip" and self.app.pip_name:
            return f'python -m pip install -U "{self.app.pip_name}"'
        if self.install.kind == "source":
            return "git pull"
        if self.install.kind == "linux-deb":
            name = self.asset_for(release) or "<package>.deb"
            return f"sudo apt install ./{name}"
        return release.page

    def cleanup(self) -> None:
        """Remove what a finished update left behind.  Call once at start-up."""
        shutil.rmtree(self.app.folder() / "updates", ignore_errors=True)
        target = self.install.target
        if target is not None:
            shutil.rmtree(target.parent / f".{target.name}.update", ignore_errors=True)
            old = target.with_name(target.name + ".old-update")
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)
            elif old.exists():
                old.unlink(missing_ok=True)


# --------------------------------------------------------------------------- texts
TEXTS = {
    "en": {
        "menu_check": "Check for updates…",
        "menu_mode": "Automatic updates",
        "mode_auto": "Download and install automatically",
        "mode_notify": "Only tell me about new versions",
        "mode_off": "Off",
        "title": "Update",
        "latest": "{name} {current} is the latest version.",
        "ready": "{name} {version} has been downloaded and verified (SHA-256).\n\n"
                 "Restart now to finish updating?\nIf you choose No, it is installed when you close the program.",
        "offer": "{name} {version} is available (you have {current}).\n\nDownload, verify and install it now?",
        "available": "{name} {version} is available (you have {current}).\n\n{how}\n\nOpen the download page?",
        "how_auto": "This copy cannot update itself ({reason}).",
        "how_cmd": "Update with:\n{cmd}",
        "failed": "Could not check for updates:\n{error}",
        "install_failed": "The update could not be prepared:\n{error}",
        "status_downloading": "Downloading {name} {version}…",
        "status_ready": "{name} {version} will be installed when you close the program",
    },
    "ko": {
        "menu_check": "업데이트 확인…",
        "menu_mode": "자동 업데이트",
        "mode_auto": "자동으로 내려받아 설치",
        "mode_notify": "새 버전이 있으면 알리기만",
        "mode_off": "끄기",
        "title": "업데이트",
        "latest": "{name} {current}이(가) 최신 버전입니다.",
        "ready": "{name} {version}을(를) 내려받아 SHA-256 검증을 마쳤습니다.\n\n"
                 "지금 다시 시작해 업데이트를 끝낼까요?\n'아니요'를 고르면 프로그램을 닫을 때 설치합니다.",
        "offer": "{name} {version}이(가) 나왔습니다(현재 {current}).\n\n지금 내려받아 검증한 뒤 설치할까요?",
        "available": "{name} {version}이(가) 나왔습니다(현재 {current}).\n\n{how}\n\n내려받기 페이지를 열까요?",
        "how_auto": "이 설치본은 스스로 업데이트할 수 없습니다({reason}).",
        "how_cmd": "업데이트 명령:\n{cmd}",
        "failed": "업데이트를 확인하지 못했습니다:\n{error}",
        "install_failed": "업데이트를 준비하지 못했습니다:\n{error}",
        "status_downloading": "{name} {version} 내려받는 중…",
        "status_ready": "프로그램을 닫으면 {name} {version}이(가) 설치됩니다",
    },
}


def texts(lang: Optional[str] = None) -> dict:
    if lang is None:
        try:
            import locale
            lang = (locale.getlocale()[0] or os.environ.get("LANG") or "en")[:2].lower()
        except Exception:  # noqa: BLE001
            lang = "en"
    return TEXTS.get(lang, TEXTS["en"])


def _how(updater: Updater, release: Release, t: dict) -> str:
    if updater.install.kind in ("pip", "source", "linux-deb"):
        return t["how_cmd"].format(cmd=updater.manual_instructions(release))
    if not updater.install.can_apply:
        return t["how_auto"].format(reason=updater.install.reason)
    return ""


class _Worker:
    """Run check/prepare off the GUI thread; the GUI polls ``results``."""

    def __init__(self, updater: Updater) -> None:
        self.updater = updater
        self.results: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False

    def check(self, manual: bool) -> None:
        if self.busy:
            return
        self.busy = True

        def run() -> None:
            try:
                release = self.updater.check()
                if (not manual and self.updater.mode == "auto"
                        and self.updater.can_install(release)):
                    self.results.put(("downloading", release, manual))
                    self.updater.prepare(release)
                    self.results.put(("ready", release, manual))
                else:
                    self.results.put(("checked", release, manual))
            except Exception as exc:  # noqa: BLE001 - reported to the GUI
                self.results.put(("error", exc, manual))
            finally:
                self.busy = False

        threading.Thread(target=run, name="selfupdate", daemon=True).start()

    def prepare(self, release: Release) -> None:
        self.busy = True

        def run() -> None:
            try:
                self.updater.prepare(release)
                self.results.put(("ready", release, True))
            except Exception as exc:  # noqa: BLE001
                self.results.put(("prepare-error", exc, True))
            finally:
                self.busy = False

        threading.Thread(target=run, name="selfupdate", daemon=True).start()


def _handle(updater: Updater, worker: _Worker, kind: str, payload, manual: bool, t: dict, ui) -> None:
    """Shared reaction to worker results; ``ui`` supplies ask/info/warn/open/status/quit."""
    name, current = updater.app.name, updater.app.version
    if kind == "downloading":
        ui.status(t["status_downloading"].format(name=name, version=payload.version))
    elif kind == "ready":
        ui.status(t["status_ready"].format(name=name, version=payload.version))
        if ui.ask(t["title"], t["ready"].format(name=name, version=payload.version)):
            if updater.apply_now(relaunch=True):
                ui.quit()
    elif kind == "checked":
        release = payload
        if not release.newer:
            if manual:
                ui.info(t["title"], t["latest"].format(name=name, current=current))
            return
        if updater.can_install(release):
            if ui.ask(t["title"], t["offer"].format(name=name, version=release.version, current=current)):
                ui.status(t["status_downloading"].format(name=name, version=release.version))
                worker.prepare(release)
            return
        how = _how(updater, release, t)
        text = t["available"].format(name=name, version=release.version, current=current, how=how)
        if ui.ask(t["title"], re.sub(r"\n{3,}", "\n\n", text)):
            ui.open(release.page)
    elif kind == "error":
        ui.status("")
        if manual:
            ui.warn(t["title"], t["failed"].format(error=payload))
    elif kind == "prepare-error":
        ui.status("")
        ui.warn(t["title"], t["install_failed"].format(error=payload))


# --------------------------------------------------------------------------- tkinter
def attach_tk(root, updater: Updater, menu=None, lang: Optional[str] = None,
              status: Optional[Callable[[str], None]] = None):
    """Add the update entries to ``menu`` (a ``tk.Menu``) and start the daily check."""
    import tkinter as tk
    import webbrowser
    from tkinter import messagebox

    t = texts(lang)
    worker = _Worker(updater)
    updater.cleanup()

    class UI:
        def ask(self, title, text):
            return messagebox.askyesno(title, text, parent=root)

        def info(self, title, text):
            messagebox.showinfo(title, text, parent=root)

        def warn(self, title, text):
            messagebox.showwarning(title, text, parent=root)

        def open(self, url):
            webbrowser.open(url)

        def status(self, text):
            if status:
                status(text)

        def quit(self):
            root.after(50, root.destroy)

    ui = UI()

    def poll() -> None:
        try:
            while True:
                kind, payload, manual = worker.results.get_nowait()
                _handle(updater, worker, kind, payload, manual, t, ui)
        except queue.Empty:
            pass
        try:
            root.after(300, poll)
        except tk.TclError:
            pass

    if menu is not None:
        menu.add_command(label=t["menu_check"], command=lambda: worker.check(manual=True))
        mode_var = tk.StringVar(master=root, value=updater.mode)
        sub = tk.Menu(menu, tearoff=False)
        for mode in MODES:
            sub.add_radiobutton(label=t[f"mode_{mode}"], value=mode, variable=mode_var,
                                command=lambda m=mode: setattr(updater, "mode", m))
        menu.add_cascade(label=t["menu_mode"], menu=sub)
        root._selfupdate_mode_var = mode_var  # keep a reference
    root.after(300, poll)
    if updater.due():
        root.after(3000, lambda: worker.check(manual=False))
    return worker


# --------------------------------------------------------------------------- Qt (PySide6)
def attach_qt(window, updater: Updater, menu=None, lang=None,
              status: Optional[Callable[[str], None]] = None):
    """Same as :func:`attach_tk` for a PySide6 ``QMainWindow``; ``menu`` is a ``QMenu``.

    ``lang`` may be a language code or a function returning one (for programs that
    switch language at run time); call ``window._selfupdate["retranslate"]()``
    after switching to relabel the menu entries.
    """
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QAction, QActionGroup, QDesktopServices
    from PySide6.QtWidgets import QApplication, QMessageBox

    def t() -> dict:
        return texts(lang() if callable(lang) else lang)

    worker = _Worker(updater)
    updater.cleanup()

    class UI:
        def ask(self, title, text):
            return QMessageBox.question(window, title, text) == QMessageBox.StandardButton.Yes

        def info(self, title, text):
            QMessageBox.information(window, title, text)

        def warn(self, title, text):
            QMessageBox.warning(window, title, text)

        def open(self, url):
            QDesktopServices.openUrl(QUrl(url))

        def status(self, text):
            if status:
                status(text)
            elif hasattr(window, "statusBar"):
                window.statusBar().showMessage(text, 15000 if text else 1)

        def quit(self):
            QTimer.singleShot(50, QApplication.instance().quit)

    ui = UI()

    def poll() -> None:
        try:
            while True:
                kind, payload, manual = worker.results.get_nowait()
                _handle(updater, worker, kind, payload, manual, t(), ui)
        except queue.Empty:
            pass

    timer = QTimer(window)
    timer.timeout.connect(poll)
    timer.start(300)
    labels = []   # (object, key, setter)
    if menu is not None:
        check = QAction(t()["menu_check"], window)
        check.triggered.connect(lambda: worker.check(manual=True))
        menu.addAction(check)
        sub = menu.addMenu(t()["menu_mode"])
        group = QActionGroup(window)
        labels += [(check, "menu_check", check.setText), (sub, "menu_mode", sub.setTitle)]
        for mode in MODES:
            act = QAction(t()[f"mode_{mode}"], window, checkable=True)
            act.setChecked(updater.mode == mode)
            act.triggered.connect(lambda _=False, m=mode: setattr(updater, "mode", m))
            group.addAction(act)
            sub.addAction(act)
            labels.append((act, f"mode_{mode}", act.setText))

    def retranslate() -> None:
        current = t()
        for _obj, key, setter in labels:
            setter(current[key])

    window._selfupdate = {"worker": worker, "timer": timer, "labels": labels, "retranslate": retranslate,
                          "check": lambda: worker.check(manual=True)}
    if updater.due():
        QTimer.singleShot(3000, lambda: worker.check(manual=False))
    return worker


# --------------------------------------------------------------------------- command line
def cli(updater: Updater, install: bool = True, out=print) -> int:
    """``<program> update``: check, and for an installed copy download and install."""
    try:
        release = updater.check()
    except UpdateError as exc:
        out(f"update check failed: {exc}")
        return 2
    name = updater.app.name
    if not release.newer:
        out(f"{name} {updater.app.version} is up to date (latest release {release.version})")
        return 0
    out(f"{name} {release.version} is available (you have {updater.app.version})")
    out(release.page)
    if not install or not updater.can_install(release):
        out(f"update with: {updater.manual_instructions(release)}")
        return 0
    try:
        shown = [-1]

        def bar(done: int, total: int) -> None:
            pct = done * 100 // total if total else 0
            if total and pct // 5 != shown[0]:
                shown[0] = pct // 5
                sys.stderr.write(f"\r  {pct:3d}%  {done / 1e6:.1f} of {total / 1e6:.1f} MB")
                sys.stderr.flush()
        updater.prepare(release, bar)
        sys.stderr.write("\n")
        updater.apply_now(relaunch=False)
    except UpdateError as exc:
        out(f"update failed: {exc}")
        return 1
    out(f"{name} {release.version} verified; it is installed as soon as this command exits")
    return 0
