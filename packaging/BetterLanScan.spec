# PyInstaller spec — builds a self-contained BetterLanScan.app.
# Run from the project root:  pyinstaller packaging/BetterLanScan.spec --noconfirm
import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.getcwd())

# pyobjc submodules PyInstaller can't always see by static analysis.
hidden = []
for mod in ("CoreWLAN", "CoreLocation", "objc", "Foundation"):
    hidden += collect_submodules(mod)

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, "betterlanscan"), "betterlanscan")],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BetterLanScan",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,           # native arch; set "universal2" for fat binary
    codesign_identity=None,     # signing handled by sign_and_notarize.sh
    entitlements_file=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="BetterLanScan",
)
app = BUNDLE(
    coll,
    name="BetterLanScan.app",
    icon=os.path.join(ROOT, "assets", "AppIcon.icns"),
    bundle_identifier="com.betterlanscan.app",
    version="1.0.0",
    info_plist={
        "CFBundleName": "BetterLanScan",
        "CFBundleDisplayName": "BetterLanScan",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSLocationUsageDescription":
            "Location access lets BetterLanScan read nearby Wi-Fi network "
            "names (SSIDs) and signal details.",
        "NSLocationWhenInUseUsageDescription":
            "Location access lets BetterLanScan read nearby Wi-Fi network "
            "names (SSIDs) and signal details.",
    },
)
