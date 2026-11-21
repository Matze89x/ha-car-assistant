"""Cut the provided icon free (transparent outside, glow kept) and grade it to the site's design tokens.

Usage: python make_icon.py <input.jpg> <output_dir>
Writes master.png (1024 px, transparent) and a few previews.
"""

import sys

import numpy as np
from PIL import Image
from scipy import ndimage

src, out = sys.argv[1], sys.argv[2]
rgb = np.asarray(Image.open(src).convert("RGB")).astype(np.float64)
H, W, _ = rgb.shape
minc = rgb.min(axis=2)
maxc = rgb.max(axis=2)

# ---- site tokens (app.css)
BG = np.array([13, 16, 22.0])  # --bg
CARD2 = np.array([30, 34, 43.0])  # --card2
ACCENT = np.array([226, 0, 26.0])  # --accent
OK = np.array([74, 222, 128.0])  # --ok
TEXT = np.array([242, 243, 245.0])  # --text

# ---- 1) core = the icon itself (dark interior + coloured border); holes (the white car) are filled
core = ndimage.binary_fill_holes(minc < 90)
core = ndimage.binary_opening(core, iterations=2)

# ---- 2) the border's gradient position along x, measured on the top stroke (smooth, noise free)
OLD_RED, OLD_GREEN = np.array([222, 27, 33.0]), np.array([19, 174, 108.0])
dist = ndimage.distance_transform_edt(core)
ys_c, xs_c = np.where(core)
x_l, x_r, y_t = xs_c.min(), xs_c.max(), ys_c.min()
band = rgb[y_t + 22 : y_t + 52, :, :].mean(axis=0)  # mean colour of the top stroke per x
t_lut = np.linspace(0, 1, 2001)
old_line = OLD_RED[None] + t_lut[:, None] * (OLD_GREEN - OLD_RED)[None]
# project each stroke colour onto the red->green line (least squares): robust against JPEG noise
d = OLD_GREEN - OLD_RED
s_raw = np.clip(((band - OLD_RED) @ d) / (d @ d), 0, 1)
x0s, x1s = x_l + 240, x_r - 240  # straight part of the top stroke (the corners curve away from the sampled rows)
seg = ndimage.gaussian_filter1d(s_raw[x0s:x1s], 20)
seg = np.maximum.accumulate(seg)
seg = np.clip((seg - seg[0]) / max(seg[-1] - seg[0], 1e-6), 0, 1)
s_x = np.zeros(W)
s_x[x0s:x1s] = seg
s_x[x1s:] = 1.0
print(
    "Verlauf s(x) bei 20/35/45/50/55/65/80 %:",
    [round(float(s_x[int(x_l + (x_r - x_l) * f)]), 2) for f in (0.2, 0.35, 0.45, 0.5, 0.55, 0.65, 0.8)],
)
S = np.broadcast_to(s_x[None, :], (H, W))
grad = ACCENT[None, None] + S[..., None] * (OK - ACCENT)[None, None]  # new border colour per pixel

# ---- 3) interior: tone to the site's blue-black (keeps the graphic's shading) and add the soft red/green vignette from the new gradient
luma = rgb.mean(axis=2)
chroma = maxc - minc
base_t = np.clip((luma - 30.0) / (58.0 - 30.0), 0, 1.4)
interior = BG[None, None] + base_t[..., None] * (CARD2 - BG)[None, None]
interior = interior + (np.clip(chroma, 0, 60) / 255.0 * 0.9)[..., None] * grad * 0.9
w_dark = np.clip((130 - maxc) / 40.0, 0, 1)  # 1 = dark interior pixel, 0 = border / car
graded = rgb * (1 - w_dark[..., None]) + interior * w_dark[..., None]
neutral = ((maxc - minc) < 14) & (minc > 140)  # car body: scale the graphic's white to the site's text colour
graded[neutral] = np.clip(graded[neutral] * (TEXT / np.array([238, 239, 241.0])), 0, 255)
ring_w = np.clip((maxc - 60) / 50.0, 0, 1) * (dist <= 95)  # the coloured stroke (not the car, not the dark interior)
graded = graded * (1 - ring_w[..., None]) + grad * ring_w[..., None]
graded = np.where(core[..., None], graded, rgb)

# ---- 4) cut out: outside the core the white background becomes transparency, the glow stays as a soft tint (in the new gradient colours)
alpha = np.where(core, 1.0, np.clip((255 - minc) / 195.0, 0, 1))
alpha[alpha < 0.03] = 0
fg = np.where(core[..., None], graded, grad)

# ---- 5) crop to the glow's bounding box (square, small margin), premultiplied downscale to 1024
ys, xs = np.where(alpha > 0.02)
pad = int(0.02 * max(xs.max() - xs.min(), ys.max() - ys.min()))
x0, x1, y0, y1 = xs.min() - pad, xs.max() + pad, ys.min() - pad, ys.max() + pad
side = max(x1 - x0, y1 - y0)
cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
x1, y1 = min(W, x0 + side), min(H, y0 + side)
fg_c, a_c = fg[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
pm = fg_c * a_c[..., None]
size = 1024
chans = [np.asarray(Image.fromarray(pm[..., i].astype(np.float32), "F").resize((size, size), Image.LANCZOS)) for i in range(3)]
al = np.asarray(Image.fromarray(a_c.astype(np.float32), "F").resize((size, size), Image.LANCZOS))
al = np.clip(al, 0, 1)
rgb_out = np.stack(chans, axis=-1) / np.maximum(al, 1e-4)[..., None]
rgba = np.dstack([np.clip(rgb_out, 0, 255), np.clip(al, 0, 1) * 255]).round().astype(np.uint8)
master = Image.fromarray(rgba, "RGBA")
master.save(f"{out}/master.png", optimize=True)
print("master.png", master.size, "Rahmen aus Original:", (x0, y0, x1, y1))


# ---- previews: on the site's dark background, on white and on a checkerboard
def over(bg_rgb):
    bg = Image.new("RGBA", master.size, (*tuple(bg_rgb), 255))
    bg.alpha_composite(master)
    return bg.convert("RGB")


check = Image.new("RGBA", master.size, (255, 255, 255, 255))
px = check.load()
for yy in range(0, size, 32):
    for xx in range(0, size, 32):
        if (xx // 32 + yy // 32) % 2:
            for dy in range(32):
                for dx in range(32):
                    px[xx + dx, yy + dy] = (205, 205, 205, 255)
check.alpha_composite(master)
sheet = Image.new("RGB", (size * 3 // 2, size // 2), (255, 255, 255))
for i, im in enumerate((over(BG.astype(int)), over((255, 255, 255)), check.convert("RGB"))):
    sheet.paste(im.resize((size // 2, size // 2), Image.LANCZOS), (i * size // 2, 0))
sheet.save(f"{out}/preview.png")
print("preview.png (dunkel | weiss | Schachbrett)")
