"""dmgbuild settings for BetterLanScan installer DMG."""
import os, sys

# Called as: dmgbuild -s packaging/dmg_settings.py "BetterLanScan X.Y.Z" output.dmg
# VERSION and ROOT are injected via dmgbuild -D flags or derived from environment.

ROOT = os.path.realpath(os.environ["BLS_ROOT"])

# ── Volume appearance ────────────────────────────────────────────────────────
background  = os.path.join(ROOT, "assets", "dmg_background.png")
icon_size   = 100
# DMG window: 540 × 333 (matches @2x background 1080 × 666)
window_rect = ((200, 120), (540, 333))
icon_locations = {
    "BetterLanScan.app": (135, 175),
    "Applications":      (405, 175),
}
default_view   = "icon-view"
show_icon_preview = False
show_status_bar   = False
show_toolbar      = False
show_pathbar      = False
show_sidebar      = False
sidebar_width     = 0
grid_offset       = (0, 0)
grid_spacing      = 100

# ── Contents ─────────────────────────────────────────────────────────────────
app_path = os.path.join(ROOT, "dist_standalone", "BetterLanScan.app")
files = [app_path]
symlinks = {"Applications": "/Applications"}

# ── Format / compression ─────────────────────────────────────────────────────
format   = "UDZO"
size     = None     # auto-size
