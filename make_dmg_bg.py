"""Generate DMG installer background — drag-to-Applications graphic.

Output: assets/dmg_background.png  (540×333 1x, matches DMG window size exactly)
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).parent
OUT  = ROOT / "assets" / "dmg_background.png"

W, H = 540, 333   # 1x canvas — must match window_rect in dmg_settings.py


# ── colours ────────────────────────────────────────────────────────────────
BG_TOP    = (18,  21,  31)
BG_BOT    = (12,  14,  22)
ARROW_COL = (76, 141, 255)
TEXT_COL  = (180, 190, 210)
HINT_COL  = (90,  100, 120)


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i]-a[i])*t) for i in range(3))


def radial_gradient(img, cx, cy, r_outer, col_inner, col_outer):
    glow = Image.new("RGBA", img.size, (0,0,0,0))
    draw = ImageDraw.Draw(glow)
    steps = 40
    for i in range(steps, 0, -1):
        t = i / steps
        r = r_outer * (1 - t)
        alpha = int(col_inner[3] * t * t)
        c = lerp_color(col_inner[:3], col_outer[:3], 1-t) + (alpha,)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=c)
    img.alpha_composite(glow)


def load_font(size):
    for p in ["/System/Library/Fonts/SFNS.ttf",
              "/System/Library/Fonts/SF Pro.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf",
              "/System/Library/Fonts/LucidaGrande.ttc"]:
        try: return ImageFont.truetype(p, size)
        except Exception: pass
    try: return ImageFont.load_default(size=size)
    except Exception: return ImageFont.load_default()


def draw_arrow(draw, x1, y1, x2, y2, color, width=3, head=14):
    my = (y1+y2)//2
    shaft_end = x2 - head
    draw.line([(x1, my), (shaft_end, my)], fill=color, width=width)
    draw.polygon([(x2, my), (shaft_end, my-head//2), (shaft_end, my+head//2)], fill=color)


def applications_icon(size=90):
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    d = ImageDraw.Draw(img)
    s = size
    d.rounded_rectangle([s*.08, s*.12, s*.4, s*.28], radius=s*.04, fill=(72,140,255))
    d.rounded_rectangle([s*.04, s*.24, s*.96, s*.86], radius=s*.07, fill=(52,120,246))
    d.rounded_rectangle([s*.04, s*.70, s*.96, s*.86], radius=s*.07, fill=(36,90,200))
    d.rounded_rectangle([s*.04, s*.24, s*.96, s*.44], radius=s*.07, fill=(100,170,255,60))
    fnt = load_font(int(s * .34))
    text = "A"
    bbox = d.textbbox((0,0), text, font=fnt)
    tx = (s - (bbox[2]-bbox[0])) // 2 - bbox[0]
    ty = int(s * .38) - bbox[1]
    d.text((tx+1, ty+2), text, font=fnt, fill=(20,70,180,140))
    d.text((tx, ty), text, font=fnt, fill=(255,255,255,230))
    return img


# ── canvas ──────────────────────────────────────────────────────────────────
canvas = Image.new("RGBA", (W, H), BG_TOP)
draw   = ImageDraw.Draw(canvas)

for y in range(H):
    col = lerp_color(BG_TOP, BG_BOT, y/H) + (255,)
    draw.line([(0,y),(W,y)], fill=col)

# dot grid
for x in range(15, W, 30):
    for y in range(15, H, 30):
        draw.ellipse([x-1,y-1,x+1,y+1], fill=(255,255,255,12))

# glows
radial_gradient(canvas, W//4,   H//2, 130, (76,141,255,60), (76,141,255,0))
radial_gradient(canvas, 3*W//4, H//2, 130, (76,141,255,40), (76,141,255,0))
draw = ImageDraw.Draw(canvas)

# ── title ───────────────────────────────────────────────────────────────────
fnt_title = load_font(22)
title = "BetterLanScan"
tb = draw.textbbox((0,0), title, font=fnt_title)
draw.text((W//2 - (tb[2]-tb[0])//2, 18), title, font=fnt_title, fill=(220,228,245))

fnt_sub = load_font(11)
sub = "Network & Wi-Fi scanner for macOS"
sb = draw.textbbox((0,0), sub, font=fnt_sub)
draw.text((W//2 - (sb[2]-sb[0])//2, 46), sub, font=fnt_sub, fill=HINT_COL)

draw.line([(W//2-110, 64), (W//2+110, 64)], fill=(50,62,88), width=1)

# ── app icon (left) ─────────────────────────────────────────────────────────
icon_size = 90
app_icon_src = ROOT / "assets" / "AppIcon.iconset" / "icon_128x128.png"
if app_icon_src.exists():
    app_icon = Image.open(app_icon_src).convert("RGBA").resize(
        (icon_size, icon_size), Image.LANCZOS)
else:
    app_icon = Image.new("RGBA", (icon_size, icon_size), (76,141,255,255))

icon_x = W//4 - icon_size//2   # = 135 - 45 = 90
icon_y = H//2 - icon_size//2 - 10   # ≈ 112

shadow = Image.new("RGBA", (icon_size+20, icon_size+20), (0,0,0,0))
ImageDraw.Draw(shadow).rounded_rectangle([5,7,icon_size+15,icon_size+17],
              radius=14, fill=(0,0,0,100))
shadow = shadow.filter(ImageFilter.GaussianBlur(6))
canvas.alpha_composite(shadow, (icon_x-10, icon_y-10))
canvas.alpha_composite(app_icon, (icon_x, icon_y))

# ── arrow ───────────────────────────────────────────────────────────────────
ax1 = W//4 + icon_size//2 + 20
ax2 = 3*W//4 - icon_size//2 - 20
ay  = H//2 - 10
draw_arrow(draw, ax1, ay, ax2, ay, ARROW_COL, width=3, head=14)

fnt_hint = load_font(10)
hint = "drag to install"
hb = draw.textbbox((0,0), hint, font=fnt_hint)
draw.text(((ax1+ax2)//2 - (hb[2]-hb[0])//2, ay - 20), hint,
          font=fnt_hint, fill=HINT_COL)

# ── Applications folder (right) ─────────────────────────────────────────────
apps_icon = applications_icon(size=icon_size)
apps_x = 3*W//4 - icon_size//2   # = 405 - 45 = 360
apps_y = icon_y

shadow2 = Image.new("RGBA", (icon_size+20, icon_size+20), (0,0,0,0))
ImageDraw.Draw(shadow2).rounded_rectangle([5,7,icon_size+15,icon_size+17],
              radius=12, fill=(0,0,0,90))
shadow2 = shadow2.filter(ImageFilter.GaussianBlur(5))
canvas.alpha_composite(shadow2, (apps_x-10, apps_y-10))
canvas.alpha_composite(apps_icon, (apps_x, apps_y))

# ── version ─────────────────────────────────────────────────────────────────
try:
    import sys; sys.path.insert(0, str(ROOT))
    from betterlanscan import __version__
    ver_text = f"v{__version__}"
except Exception:
    ver_text = ""
if ver_text:
    fnt_ver = load_font(10)
    vb = draw.textbbox((0,0), ver_text, font=fnt_ver)
    draw.text((W//2 - (vb[2]-vb[0])//2, H-18), ver_text, font=fnt_ver, fill=HINT_COL)

out = canvas.convert("RGB")
out.save(OUT, "PNG", optimize=True)
print(f"Saved {OUT}  ({out.size[0]}×{out.size[1]})")
