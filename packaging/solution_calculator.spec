# PyInstaller spec: one-folder build (+ .app bundle on macOS).
#   pyinstaller --noconfirm packaging/solution_calculator.spec
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "solution_calculator.py").read_text()).group(1)
ICONS = ROOT / "packaging" / "icons"
icon = str(ICONS / ("app.ico" if sys.platform == "win32" else "app.icns")) if ICONS.exists() else None

a = Analysis(
    [str(ROOT / "solution_calculator.py")],
    pathex=[str(ROOT)],
    hiddenimports=["selfupdate"],
    excludes=["numpy", "matplotlib", "PIL", "pytest", "setuptools"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SolutionCalculator",
          console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="SolutionCalculator")
if sys.platform == "darwin":
    app = BUNDLE(
        coll, name="Solution Calculator.app", icon=icon,
        bundle_identifier="io.github.jongsu-king.solution-calculator", version=VERSION,
        info_plist={"CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                    "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0",
                    "NSHumanReadableCopyright": "© 2026 Jongsu Lim, MIT License"},
    )
