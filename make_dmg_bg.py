"""Generate DMG installer background — drag-to-Applications graphic.

Output: assets/dmg_background.png  (1080×660 @2x, displayed at 540×330)
"""
from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).parent
OUT  = ROOT / "assets" / "dmg_background.png"

W, H = 1080, 660   # @2x canvas (DMG window will be 540×330)


# ── colours ────────────────────────────────────────────────────────────────
BG_TOP    = (18,  21,  31)
BG_BOT    = (12,  14,  22)
GLOW_COL  = (76, 141, 255, 28)    # subtle blue glow
ARROW_COL = (76, 141, 255)
TEXT_COL  = (180, 190, 210)
HINT_COL  = (90,  100, 120)
RING_COL  = (40,  50,  70)


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i]-a[i])*t) for i in range(3))


def radial_gradient(img: Image.Image, cx, cy, r_inner, r_outer, col_inner, col_outer):
    """Paint a soft radial glow over img (RGBA)."""
    glow = Image.new("RGBA", img.size, (0,0,0,0))
    draw = ImageDraw.Draw(glow)
    steps = 40
    for i in range(steps, 0, -1):
        t = i / steps
        r = r_inner + (r_outer - r_inner) * (1 - t)
        alpha = int(col_inner[3] * t * t)
        c = lerp_color(col_inner[:3], col_outer[:3], 1-t) + (alpha,)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=c)
    img.alpha_composite(glow)


def draw_rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    x0,y0,x1,y1 = box
    r = radius
    if fill:
        draw.rectangle([x0+r, y0, x1-r, y1], fill=fill)
        draw.rectangle([x0, y0+r, x1, y1-r], fill=fill)
        draw.ellipse([x0, y0, x0+2*r, y0+2*r], fill=fill)
        draw.ellipse([x1-2*r, y0, x1, y0+2*r], fill=fill)
        draw.ellipse([x0, y1-2*r, x0+2*r, y1], fill=fill)
        draw.ellipse([x1-2*r, y1-2*r, x1, y1], fill=fill)
    if outline:
        draw.rounded_rectangle(box, radius=radius, outline=outline, width=width)


def load_font(size, bold=False):
    """Try SF Pro / Helvetica Neue, fall back to default."""
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SF Pro.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/LucidaGrande.ttc",
    ]
    for p in candidates:
        try: return ImageFont.truetype(p, size)
        except Exception: pass
    try: return ImageFont.load_default(size=size)
    except Exception: return ImageFont.load_default()


def draw_arrow(draw, x1, y1, x2, y2, color, width=5, head=28):
    """Draw a chunky right-pointing arrow."""
    # shaft
    my = (y1+y2)//2
    tip_x = x2
    shaft_end = tip_x - head
    draw.line([(x1, my), (shaft_end, my)], fill=color, width=width)
    # arrowhead (filled triangle)
    pts = [
        (tip_x, my),
        (shaft_end, my - head//2),
        (shaft_end, my + head//2),
    ]
    draw.polygon(pts, fill=color)


def applications_icon(size=180):
    """Draw a simple macOS-style Applications folder icon."""
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    d = ImageDraw.Draw(img)
    s = size

    # folder body
    body_col = (52, 120, 246)
    dark_col = (36,  90, 200)
    tab_col  = (72, 140, 255)

    # tab
    d.rounded_rectangle([s*.08, s*.12, s*.4, s*.28], radius=s*.04, fill=tab_col)
    # body
    d.rounded_rectangle([s*.04, s*.24, s*.96, s*.86], radius=s*.07, fill=body_col)
    # bottom shadow
    d.rounded_rectangle([s*.04, s*.70, s*.96, s*.86], radius=s*.07, fill=dark_col)
    # shine
    d.rounded_rectangle([s*.04, s*.24, s*.96, s*.44], radius=s*.07,
                         fill=(100, 170, 255, 60))

    # "A" glyph
    fnt = load_font(int(s * .34))
    text = "A"
    bbox = d.textbbox((0,0), text, font=fnt)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    tx = (s - tw) // 2 - bbox[0]
    ty = int(s * .38) - bbox[1]
    d.text((tx+2, ty+3), text, font=fnt, fill=(20, 70, 180, 140))
    d.text((tx, ty), text, font=fnt, fill=(255,255,255,230))

    return img


# ── build canvas ────────────────────────────────────────────────────────────
canvas = Image.new("RGBA", (W, H), BG_TOP)
draw   = ImageDraw.Draw(canvas)

# gradient background
for y in range(H):
    t = y / H
    col = lerp_color(BG_TOP, BG_BOT, t) + (255,)
    draw.line([(0,y),(W,y)], fill=col)

# very subtle dot grid
for x in range(30, W, 60):
    for y in range(30, H, 60):
        draw.ellipse([x-1, y-1, x+1, y+1], fill=(255,255,255,12))

# glow behind left icon
radial_gradient(canvas, W//4, H//2, 0, 260, (76,141,255,60), (76,141,255,0))
# glow behind right icon
radial_gradient(canvas, 3*W//4, H//2, 0, 260, (76,141,255,40), (76,141,255,0))

draw = ImageDraw.Draw(canvas)

# ── app icon (left) ─────────────────────────────────────────────────────────
icon_size = 200
app_icon_src = ROOT / "assets" / "AppIcon.iconset" / "icon_256x256.png"
if app_icon_src.exists():
    app_icon = Image.open(app_icon_src).convert("RGBA").resize(
        (icon_size, icon_size), Image.LANCZOS)
else:
    app_icon = Image.new("RGBA", (icon_size, icon_size), (76, 141, 255, 255))

icon_x = W//4 - icon_size//2
icon_y = H//2 - icon_size//2 - 20

# drop shadow
shadow = Image.new("RGBA", (icon_size+40, icon_size+40), (0,0,0,0))
sd = ImageDraw.Draw(shadow)
sd.rounded_rectangle([10,14,icon_size+30,icon_size+34], radius=30,
                     fill=(0,0,0,120))
shadow = shadow.filter(ImageFilter.GaussianBlur(12))
canvas.alpha_composite(shadow, (icon_x-20, icon_y-20))
canvas.alpha_composite(app_icon, (icon_x, icon_y))

# label ring
ring_cx, ring_cy = W//4, icon_y + icon_size + 38
r = 90
draw.ellipse([ring_cx-r, ring_cy-8, ring_cx+r, ring_cy+8],
             fill=(30,36,52), outline=(50,62,88), width=1)
fnt_label = load_font(24)
draw.text((ring_cx, ring_cy), "BetterLanScan.app",
          font=fnt_label, fill=TEXT_COL, anchor="mm")

# ── arrow (centre) ──────────────────────────────────────────────────────────
ax1 = W//4 + icon_size//2 + 50
ax2 = 3*W//4 - icon_size//2 - 50
ay  = H//2 - 20
draw_arrow(draw, ax1, ay-1, ax2, ay+1, ARROW_COL, width=6, head=30)

# small "drag to install" hint above arrow
fnt_hint = load_font(20)
hint_text = "drag to install"
bbox = draw.textbbox((0,0), hint_text, font=fnt_hint)
hw = bbox[2]-bbox[0]
draw.text(((ax1+ax2)//2 - hw//2, ay - 46), hint_text,
          font=fnt_hint, fill=HINT_COL)

# ── Applications folder (right) ─────────────────────────────────────────────
apps_icon = applications_icon(size=icon_size)
apps_x = 3*W//4 - icon_size//2
apps_y = icon_y  # same vertical as app icon

# drop shadow
shadow2 = Image.new("RGBA", (icon_size+40, icon_size+40), (0,0,0,0))
sd2 = ImageDraw.Draw(shadow2)
sd2.rounded_rectangle([10,14,icon_size+30,icon_size+34], radius=24,
                      fill=(0,0,0,100))
shadow2 = shadow2.filter(ImageFilter.GaussianBlur(10))
canvas.alpha_composite(shadow2, (apps_x-20, apps_y-20))
canvas.alpha_composite(apps_icon, (apps_x, apps_y))

# label ring
ring2_cx = 3*W//4
draw.ellipse([ring2_cx-r, ring_cy-8, ring2_cx+r, ring_cy+8],
             fill=(30,36,52), outline=(50,62,88), width=1)
draw.text((ring2_cx, ring_cy), "Applications",
          font=fnt_label, fill=TEXT_COL, anchor="mm")

# ── top title ───────────────────────────────────────────────────────────────
fnt_title = load_font(42)
title = "BetterLanScan"
tb = draw.textbbox((0,0), title, font=fnt_title)
tw = tb[2]-tb[0]
draw.text((W//2 - tw//2, 52), title, font=fnt_title, fill=(220,228,245))

fnt_sub = load_font(22)
sub = "Network & Wi-Fi scanner for macOS"
sb = draw.textbbox((0,0), sub, font=fnt_sub)
sw = sb[2]-sb[0]
draw.text((W//2 - sw//2, 106), sub, font=fnt_sub, fill=HINT_COL)

# thin separator under title
draw.line([(W//2-220, 148), (W//2+220, 148)], fill=(50,62,88), width=1)

# ── bottom version ──────────────────────────────────────────────────────────
try:
    import sys; sys.path.insert(0, str(ROOT))
    from betterlanscan import __version__
    ver_text = f"v{__version__}"
except Exception:
    ver_text = ""
if ver_text:
    fnt_ver = load_font(20)
    vb = draw.textbbox((0,0), ver_text, font=fnt_ver)
    vw = vb[2]-vb[0]
    draw.text((W//2 - vw//2, H-46), ver_text, font=fnt_ver, fill=HINT_COL)

# ── final composite ─────────────────────────────────────────────────────────
out = canvas.convert("RGB")
out.save(OUT, "PNG", optimize=True)
print(f"Saved {OUT}  ({out.size[0]}×{out.size[1]})")
