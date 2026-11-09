# Installing Solution Preparation Calculator

Every release on the [Releases page](https://github.com/jongsu-king/perovskite-opv-solution-calculator/releases/latest) carries ready-to-run builds for Windows, macOS and Linux - Python is **not** needed for them - plus a `SHA256SUMS.txt` with the checksum of every file. The newest release is always at <https://github.com/jongsu-king/perovskite-opv-solution-calculator/releases/latest>.

## Which file do I need?

| Your computer | File | Notes |
|---|---|---|
| Windows 10 or 11, 64-bit | `Solution-Calculator-<version>-windows-x64-setup.exe` | Installer (recommended). No administrator rights needed. |
| Windows, no installation | `Solution-Calculator-<version>-windows-x64-portable.zip` | Unzip and run `SolutionCalculator.exe`. Updates itself when the folder is writable. |
| Mac with Apple silicon (M1, M2, M3, M4) | `Solution-Calculator-<version>-macos-arm64.dmg` | macOS 11 Big Sur or newer. |
| Mac with an Intel processor | `Solution-Calculator-<version>-macos-x86_64.dmg` | macOS 11 or newer. |
| Ubuntu 22.04+, Debian 12+, Mint 21+ (x86-64) | `solution-calculator_<version>_amd64.deb` | System-wide package with a menu entry. |
| Other Linux (x86-64, glibc 2.35+) | `Solution-Calculator-<version>-linux-x86_64.tar.gz` | Per-user install with `install.sh`, or run in place. |

Not sure which Mac you have? Apple menu → **About This Mac**: *Chip Apple M…* means Apple silicon, *Processor Intel…* means Intel.

## Windows

**Installer**

1. Download `Solution-Calculator-<version>-windows-x64-setup.exe` and run it.
2. If SmartScreen says *Windows protected your PC*, click **More info → Run anyway**
   (the build is not code-signed; compare the SHA-256 below if you want to be sure).
3. Choose *Install for me only* (default, no administrator rights) or *Install for all
   users*. The program appears in the Start menu as **Solution Preparation Calculator**.

Uninstall from **Settings → Apps → Installed apps → Solution Preparation Calculator → Uninstall**. Your
settings in `%APPDATA%\Solution Preparation Calculator` are left in place; delete that folder to remove
them too.

Unattended installation (for IT departments):
`Solution-Calculator-<version>-windows-x64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER`
(or `/ALLUSERS` from an elevated prompt; `/DIR="D:\Apps\Solution-Calculator"` picks the folder).

**Portable zip**

Unzip `Solution-Calculator-<version>-windows-x64-portable.zip` anywhere (for example a USB stick) and
run `SolutionCalculator.exe` inside the folder. Nothing is written to the registry.

## macOS

1. Download the `.dmg` for your processor (see the table above) and open it.
2. Drag **Solution Calculator.app** onto the **Applications** folder shown next to it.
3. Eject the disk image and start the program from Applications or Launchpad.
4. The first start of an unsigned build shows *"Solution Calculator" cannot be
   opened because Apple cannot check it for malicious software*. Click **Done**, open
   **System Settings → Privacy & Security**, scroll down and click **Open Anyway**,
   then confirm. On macOS 14 and older, right-click the app → **Open** also works.
   From a terminal: `xattr -dr com.apple.quarantine "/Applications/Solution Calculator.app"`.

Keep the app in **Applications** (or another folder you can write to) - an app started
directly from the disk image or from Downloads runs from a read-only location
("App Translocation") and can only tell you about updates, not install them.

Uninstall: drag **Solution Calculator.app** to the Trash. Settings live in
`~/Library/Application Support/Solution Preparation Calculator`.

## Linux

**Debian, Ubuntu, Linux Mint (.deb)**

```bash
sudo apt install ./solution-calculator_<version>_amd64.deb
```

The program is installed in `/opt/solution-calculator`, the command `solution-calculator` is put on the PATH and a
menu entry is added. Remove it with `sudo apt remove solution-calculator`.

**Any distribution (.tar.gz)**

```bash
tar -xzf Solution-Calculator-<version>-linux-x86_64.tar.gz
Solution-Calculator/install.sh          # installs for the current user, no root
```

`install.sh` copies the program to `~/.local/share/solution-calculator`, links
`~/.local/bin/solution-calculator` and adds a menu entry. `uninstall.sh` (in the same folder)
removes all three. You can also run `Solution-Calculator/SolutionCalculator` without installing.
Settings live in `~/.config/Solution Preparation Calculator`.

## From source (Python)

Python 3.10+ with tkinter; no other packages.

```bash
git clone https://github.com/jongsu-king/perovskite-opv-solution-calculator.git
cd perovskite-opv-solution-calculator
python3 solution_calculator.py
```

Update a source checkout with `git pull`. When run from source, your material library is
`library.json` next to `solution_calculator.py`; an installed copy keeps it in the settings
folder named below instead.

## Automatic updates

The installed program keeps itself up to date. **Help → Automatic updates** has three
settings:

| Setting | What happens |
|---|---|
| **Download and install automatically** (default) | Once a day, a few seconds after start-up, the program asks GitHub for the latest release. If it is newer, the file for your system is downloaded in the background and checked against the release's `SHA256SUMS.txt`. You are then asked whether to restart now; otherwise the update is installed when you close the program. |
| **Only tell me about new versions** | The same daily check, but nothing is downloaded until you agree. |
| **Off** | No automatic check. **Help → Check for updates…** still works. |

**What is installed, per platform**

| Installed from | How the update is applied |
|---|---|
| Windows installer | the new `-setup.exe` runs silently (`/VERYSILENT`) into the same folder, then the program starts again |
| Windows portable zip | the program folder is replaced by the new one after the program exits |
| macOS disk image | the new `.dmg` is mounted, the app is copied next to the old one and swapped in after the program exits |
| Linux `install.sh` | `~/.local/share/solution-calculator` is replaced after the program exits |
| Linux `.deb` | `pkexec apt-get install` asks for your password once and upgrades the package |
| pip / source checkout | nothing is changed; the program shows the command (`pip install -U …` or `git pull`) |

**Privacy and safety**

- One HTTPS request to `api.github.com/repos/jongsu-king/perovskite-opv-solution-calculator/releases/latest` per day; the only
  information sent is the `User-Agent` `<program>/<version>`. No account, no tracking.
- A downloaded file is used only if its SHA-256 equals the value in the release's
  `SHA256SUMS.txt`; otherwise it is deleted. A release without that file is never
  installed automatically.
- The previous version is kept until the new one is in place and restored if the
  swap fails. A log of each update is written to `update.log` in the settings folder
  (`%APPDATA%\Solution Preparation Calculator`, `~/Library/Application Support/Solution Preparation Calculator`,
  `~/.config/Solution Preparation Calculator`).

**Turning it off for a whole machine**: set the environment variable
`SOLCALC_NO_UPDATE=1`. Continuous-integration runners (`CI` set) never check
automatically.

Command line: `SolutionCalculator --update` checks and, for an installed copy, installs the
latest release.

## Checking a download

Each release has `SHA256SUMS.txt`; the same values are printed in the release notes.

```bash
shasum -a 256 Solution-Calculator-<version>-macos-arm64.dmg            # macOS
sha256sum -c SHA256SUMS.txt --ignore-missing        # Linux
```

```powershell
Get-FileHash .\Solution-Calculator-<version>-windows-x64-setup.exe     # Windows
```

## Building the installers yourself

The workflow [`.github/workflows/release.yml`](../.github/workflows/release.yml) builds
everything on GitHub's runners (Windows, macOS arm64, macOS Intel, Ubuntu 22.04),
runs each build's self-test, test-installs the Windows installer, the `.deb` and the
`.tar.gz`, and attaches the files to the release when a `v*` tag is pushed. *Run
workflow* on the Actions tab builds without publishing. Locally:

```bash
python -m pip install pyinstaller pillow
python packaging/make_icons.py --text SC --color "#2f6f9f" --out packaging/icons
pyinstaller --noconfirm packaging/solution_calculator.spec
packaging/macos/build_dmg.sh "Solution Calculator.app" Solution-Calculator <version>     # macOS
packaging/linux/build_linux.sh <version>                     # Linux
```

On Windows install [Inno Setup 6](https://jrsoftware.org/isinfo.php) and run
`ISCC.exe /DAppVersion=<version> packaging\windows\installer.iss`.
