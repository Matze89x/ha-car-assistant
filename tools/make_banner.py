"""Banner (1280x400) and add-on logo (500x200) in the site's design: Space Grotesk, site colour tokens, glass chips.

Usage: python make_banner.py <assets_dir> <out_dir>   (needs master.png and SpaceGrotesk.ttf in assets_dir)
"""

import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

A, OUT = sys.argv[1], sys.argv[2]
master = Image.open(f"{A}/master.png").convert("RGBA")

BG = (13, 16, 22)  # --bg
ACCENT = (226, 0, 26)  # --accent
OK = (74, 222, 128)  # --ok
TEXT = (242, 243, 245)  # --text
MUTED = (155, 161, 172)  # --muted
SS = 2  # supersampling


def font(size, weight):
    f = ImageFont.truetype(f"{A}/SpaceGrotesk.ttf", int(size * SS))
    f.set_variation_by_axes([weight])
    return f


def backdrop(w, h, radius=0, glow=0.30):
    """Site background: --bg with the red glow top-left (like the page) and a faint green one bottom-right."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    img = np.zeros((h, w, 3)) + np.array(BG, dtype=np.float64)
    r1 = np.clip(1 - np.hypot(xx - 0.02 * w, yy - 0.0) / (0.78 * w), 0, 1) ** 2.2
    img += r1[..., None] * glow * (np.array(ACCENT) - np.array(BG))
    r2 = np.clip(1 - np.hypot(xx - w, yy - h) / (0.55 * w), 0, 1) ** 2.4
    img += r2[..., None] * 0.10 * (np.array(OK) - np.array(BG))
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    if radius:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
        base.putalpha(mask)
    return base


def paste_icon(canvas, size, x, y):
    ic = master.resize((int(size * SS), int(size * SS)), Image.LANCZOS)
    canvas.alpha_composite(ic, (int(x * SS), int(y * SS)))


def pill(canvas, x, y, w, h, text, f):
    """Glass chip like the site's chips (--glass fill, --glass-b border)."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = (int(x * SS), int(y * SS), int((x + w) * SS), int((y + h) * SS))
    d.rounded_rectangle(box, radius=int(h * SS / 2), fill=(255, 255, 255, 14), outline=(255, 255, 255, 38), width=SS)
    canvas.alpha_composite(layer)
    d = ImageDraw.Draw(canvas)
    tw = d.textlength(text, font=f)
    asc, desc = f.getmetrics()
    d.text((box[0] + (box[2] - box[0] - tw) / 2, box[1] + (box[3] - box[1] - (asc + desc)) / 2 - SS * 1), text, font=f, fill=TEXT)


def ink(d, text, f):
    """Left and right ink edge of a text (in supersampled pixels, relative to its origin)."""
    left, _, right, _ = d.textbbox((0, 0), text, font=f)
    return left, right


def slogan(canvas, x_left, x_right, y, size, color=OK, weight=600):
    """DRIVE · LOG · GO spread so its ink runs exactly from x_left to x_right (the C to the t of the name above)."""
    d = ImageDraw.Draw(canvas)
    f = font(size, weight)
    text = "DRIVE · LOG · GO"
    adv = [d.textlength(c, font=f) for c in text]
    first_l = d.textbbox((0, 0), text[0], font=f)[0]
    last = d.textbbox((0, 0), text[-1], font=f)
    last_r = last[2]
    natural = sum(adv[:-1]) + last_r - first_l
    gap = (x_right * SS - x_left * SS - natural) / (len(text) - 1)
    x = x_left * SS - first_l
    for c, a in zip(text, adv, strict=True):
        d.text((x, y * SS), c, font=f, fill=color)
        x += a + gap
    return gap / SS


def gradient_bar(canvas, y, h):
    w = canvas.width
    t = np.linspace(0, 1, w)[None, :, None]
    bar = np.array(ACCENT)[None, None] + t * (np.array(OK) - np.array(ACCENT))[None, None]
    bar = np.repeat(bar, h * SS, axis=0)
    img = Image.fromarray(bar.astype(np.uint8), "RGB").convert("RGBA")
    canvas.alpha_composite(img, (0, int(y * SS)))


# ------------------------------------------------------------------ banner 1280 x 400
W, H = 1280, 400
bn = backdrop(W * SS, H * SS)
gradient_bar(bn, H - 8, 8)
icon_size = 264
paste_icon(bn, icon_size, 64, (H - 8 - icon_size) / 2)
d = ImageDraw.Draw(bn)
x0 = 64 + icon_size + 52
f_big = font(112, 700)
d.text((x0 * SS, 74 * SS), "Car ", font=f_big, fill=TEXT)
d.text((x0 * SS + d.textlength("Car ", font=f_big), 74 * SS), "Assistant", font=f_big, fill=ACCENT)
l_ink = ink(d, "Car Assistant", f_big)
x_c = x0 + l_ink[0] / SS
x_t = x0 + l_ink[1] / SS
b_gap = slogan(bn, x_c, x_t, 206, 52, weight=700)
f_chip = font(27, 600)
x = x0 + 4
for label in ("Fuel", "Service", "Parts", "Documents", "Trips"):
    w = d.textlength(label, font=f_chip) / SS + 46
    pill(bn, x, 296, w, 54, label, f_chip)
    x += w + 14
bn = bn.resize((W, H), Image.LANCZOS).convert("RGB")
bn.save(f"{OUT}/banner.png", optimize=True)

# ------------------------------------------------------------------ add-on logo 500 x 200 (rounded plate, transparent corners)
W2, H2 = 500, 200
lg = backdrop(W2 * SS, H2 * SS, radius=30 * SS, glow=0.34)
icon2 = 140
paste_icon(lg, icon2, 20, (H2 - icon2) / 2)
d = ImageDraw.Draw(lg)
x_text, x_end = 20 + icon2 + 22, W2 - 22
fs = 60
f_l = font(fs, 700)
while ink(d, "Car Assistant", f_l)[1] / SS - ink(d, "Car Assistant", f_l)[0] / SS > x_end - x_text:
    fs -= 1
    f_l = font(fs, 700)
# the name in ONE line like the banner, the slogan below it from the C to the t; the block sits vertically centred on the icon
n_l, n_r = ink(d, "Car Assistant", f_l)
x0 = x_text - n_l / SS
n_top, _, _, n_bot = d.textbbox((0, 0), "Car Assistant", font=f_l)
s_size = 24
s_top, s_bot = d.textbbox((0, 0), "D", font=font(s_size, 700))[1::2]
gap = fs * 0.30
block = (n_bot - n_top) / SS + gap + (s_bot - s_top) / SS
y_top = H2 / 2 - block / 2
d.text((x0 * SS, y_top * SS - n_top), "Car ", font=f_l, fill=TEXT)
d.text((x0 * SS + d.textlength("Car ", font=f_l), y_top * SS - n_top), "Assistant", font=f_l, fill=ACCENT)
slogan(lg, x_text, x_text + (n_r - n_l) / SS, y_top + (n_bot - n_top) / SS + gap - s_top / SS, s_size, weight=700)
lg = lg.resize((W2, H2), Image.LANCZOS)
lg.save(f"{OUT}/logo_wide.png", optimize=True)
print("banner.png", bn.size, "| logo_wide.png", lg.size, "| Schriftgroesse Logo", fs)
