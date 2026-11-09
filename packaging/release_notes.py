#!/usr/bin/env python3
"""Write the release notes: hand-written text + a generated table of every download.

    python packaging/release_notes.py --dir artifacts --repo owner/name --tag v1.2.0 \
        --name "Program" [--notes docs/release-notes/1.2.0.md] > notes.md

It also writes SHA256SUMS.txt into --dir (the file the in-app updater checks).
Standard library only; the same script is used by several repositories.
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

PLATFORMS = [  # (test on the lower-case file name, platform, what it is, how to install)
    (r"windows.*setup\.exe$", "Windows 10/11 (64-bit)", "Installer",
     "Run it; no administrator rights needed (installs for the current user)."),
    (r"windows.*(portable)?\.zip$|windows\.exe$", "Windows 10/11 (64-bit)", "Portable",
     "Unzip anywhere and run the program inside; nothing is installed."),
    (r"macos.*(arm64|aarch64).*\.dmg$", "macOS 11+ · Apple silicon (M1–M4)", "Disk image",
     "Open, drag the app to Applications."),
    (r"macos.*(x86_64|intel|x64).*\.dmg$", "macOS 11+ · Intel", "Disk image",
     "Open, drag the app to Applications."),
    (r"macos.*\.dmg$", "macOS", "Disk image", "Open, drag the app to Applications."),
    (r"macos.*(arm64|aarch64).*\.tar\.gz$", "macOS 11+ · Apple silicon (M1–M4)", "Archive",
     "Unpack, then `./install.sh` (current user) or run in place."),
    (r"macos.*(x86_64|intel|x64).*\.tar\.gz$", "macOS 11+ · Intel", "Archive",
     "Unpack, then `./install.sh` (current user) or run in place."),
    (r"_amd64\.deb$", "Ubuntu/Debian (x86-64)", "Package",
     "`sudo apt install ./<file>`"),
    (r"linux.*\.tar\.gz$", "Linux (x86-64, glibc 2.35+)", "Archive",
     "Unpack, then `./install.sh` (current user) or run in place."),
    (r"\.whl$", "Any (Python)", "Wheel", "`pip install <file>`"),
    (r"\.tar\.gz$", "Any (Python)", "Source", "`pip install <file>`"),
    (r"\.ipa$", "iPhone/iPad (sideload)", "Unsigned app", "Sign and install with AltStore/Sideloadly/Xcode."),
    (r"\.zip$", "Any", "Archive", "Unpack."),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return str(size)


def classify(name: str) -> tuple[int, str, str, str]:
    low = name.lower()
    for i, (pattern, platform, kind, how) in enumerate(PLATFORMS):
        if re.search(pattern, low):
            return i, platform, kind, how.replace("<file>", name)
    return len(PLATFORMS), "Other", "File", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--notes", type=Path)
    ap.add_argument("--no-update-section", action="store_true")
    ap.add_argument("--menu", default="Help → Automatic updates",
                    help="where the update setting is in the program")
    args = ap.parse_args()

    files = sorted(p for p in args.dir.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    sums = {p.name: sha256(p) for p in files}
    (args.dir / "SHA256SUMS.txt").write_text("".join(f"{sums[n]}  {n}\n" for n in sorted(sums)))

    base = f"https://github.com/{args.repo}/releases/download/{args.tag}"
    rows = sorted(files, key=lambda p: (classify(p.name)[0], p.name))
    out: list[str] = []
    if args.notes and args.notes.exists():
        out.append(args.notes.read_text(encoding="utf-8").rstrip() + "\n")
    out.append("## Downloads\n")
    out.append("| Platform | Type | File | Size | How to install |")
    out.append("|---|---|---|---:|---|")
    for p in rows:
        _, platform, kind, how = classify(p.name)
        out.append(f"| {platform} | {kind} | [`{p.name}`]({base}/{p.name}) | {human(p.stat().st_size)} | {how} |")
    out.append("")
    out.append("<details><summary>SHA-256 checksums</summary>\n")
    out.append("```")
    out.extend(f"{sums[p.name]}  {p.name}" for p in rows)
    out.append("```")
    out.append("")
    out.append("Check a download: `shasum -a 256 <file>` (macOS), `sha256sum <file>` (Linux), "
               "`Get-FileHash <file>` (Windows PowerShell). The same list is attached as "
               "`SHA256SUMS.txt`.\n</details>\n")
    out.append("### First start on an unsigned build\n")
    out.append("These builds are not code-signed, so the operating system asks once:\n")
    out.append("- **Windows** - SmartScreen *Windows protected your PC*: **More info → Run anyway**.")
    out.append("- **macOS** - *cannot be opened because Apple cannot check it*: open **System Settings → "
               "Privacy & Security** and click **Open Anyway** (or run "
               "`xattr -dr com.apple.quarantine \"/Applications/<App>.app\"`).")
    out.append("- **Linux** - no prompt; the `.deb` adds a menu entry, `install.sh` adds one for the current user.\n")
    if not args.no_update_section:
        out.append("### Automatic updates\n")
        out.append("The installed program checks this page at most once a day (one anonymous request to "
                   "the GitHub API; nothing but the program name and version is sent). When a newer "
                   "release appears it downloads the file for your system, verifies it against "
                   "`SHA256SUMS.txt`, and installs it when you close the program (or at once if you "
                   f"choose *Restart now*). **{args.menu}** switches between *download and "
                   "install*, *only tell me*, and *off*. Copies installed with pip or run from source "
                   "are never changed; they show the command to update instead.\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
