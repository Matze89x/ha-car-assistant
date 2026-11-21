"""Cut the car photo free (pink background -> transparent), keep a soft contact shadow, add a ground glow in the logo's colours.

Usage: python make_car.py <input.jpg> <output.png> [preview.png]
"""

import sys

import numpy as np
from PIL import Image
from scipy import ndimage

src, out = sys.argv[1], sys.argv[2]
prev = sys.argv[3] if len(sys.argv) > 3 else None
ACCENT = np.array([226, 0, 26.0])  # --accent
OK = np.array([74, 222, 128.0])  # --ok
BGPAGE = np.array([13, 16, 22.0])  # --bg

img = Image.open(src).convert("RGB")
rgb = np.asarray(img.crop((0, 0, img.width, 1560))).astype(np.float64)  # below y=1560: dark artefact band of the picture
H, W, _ = rgb.shape
PINK = np.median(rgb[:300].reshape(-1, 3), axis=0)  # uniform background colour
print("Hintergrund-Rosa:", PINK.round(0))

# ---- 1) classify: background (pink), shadow (pink scaled towards black), car (everything else)
dist = np.linalg.norm(rgb - PINK, axis=2)
norm = np.linalg.norm(rgb, axis=2)
cos = (rgb @ PINK) / np.maximum(norm * np.linalg.norm(PINK), 1e-6)
bg_like = dist < 55
shadow_like = (cos > 0.962) & (norm < 0.93 * np.linalg.norm(PINK)) & ~bg_like
car = ~(bg_like | shadow_like)
car = ndimage.binary_opening(car, iterations=2)
lab, n = ndimage.label(car)
sizes = ndimage.sum(car, lab, range(1, n + 1))
car = lab == (1 + int(np.argmax(sizes)))
car = ndimage.binary_fill_holes(ndimage.binary_closing(car, iterations=3))

# ---- 2) soft edge: unmix each edge pixel from its local background (pink or shadow) and the nearest car interior colour
inner = ndimage.binary_erosion(car, iterations=4)
outer = ~ndimage.binary_dilation(car, iterations=4)
_, (iy, ix) = ndimage.distance_transform_edt(~inner, return_indices=True)
_, (oy, ox) = ndimage.distance_transform_edt(~outer, return_indices=True)
c_in = rgb[iy, ix]  # nearest interior colour
c_out = rgb[oy, ox]  # nearest background colour
v = c_in - c_out
alpha_edge = np.clip(((rgb - c_out) * v).sum(axis=2) / np.maximum((v * v).sum(axis=2), 1.0), 0, 1)
band = ndimage.binary_dilation(car, iterations=4) & ~inner
alpha = np.where(inner, 1.0, np.where(band, alpha_edge, 0.0))
alpha = np.where(car & ~band, 1.0, alpha)
fg = np.where((inner)[..., None], rgb, c_in)  # edge pixels take the interior colour (no pink fringe)

# ---- 3) edge clean-up: no pink may remain at the soft edge
pinkish = (np.linalg.norm(fg - PINK, axis=2) < 95) & ~inner
alpha = np.where(pinkish, 0.0, alpha)
alpha = np.where(~inner & (alpha < 0.30), 0.0, alpha)  # faint leftovers of the old shadow at the soft edge
alpha = ndimage.gaussian_filter(alpha, 0.7)

# ---- 4) under the car: a soft contact shadow and a ground glow in the logo's colours (accent red at the front -> status green at the rear)
ys, xs = np.where(alpha > 0.5)
x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
height, width = (y1 - y0), (x1 - x0)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)


def blob(cx, cy, rx, ry, power, sigma):
    g = np.clip(1 - np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2), 0, 1) ** power
    return ndimage.gaussian_filter(g, sigma)


glow = blob((x0 + x1) / 2, y1 - 0.004 * height, 0.54 * width, 0.105 * height, 1.15, 24)  # fades out completely inside the picture
glow_a = np.clip(glow * 1.35, 0, 0.85)
t = np.clip((xx - x0) / width, 0, 1)[..., None]  # front (left) -> rear (right)
glow_rgb = ACCENT[None, None] + t * (OK - ACCENT)[None, None]
shadow = np.clip(blob((x0 + x1) / 2 + 0.02 * width, y1 - 0.012 * height, 0.52 * width, 0.045 * height, 0.9, 10) * 1.6, 0, 0.78)


# ---- 5) compose layers: glow, shadow, car (premultiplied "over")
def over(base_rgb, base_a, top_rgb, top_a):
    a = top_a + base_a * (1 - top_a)
    c = (top_rgb * top_a[..., None] + base_rgb * (base_a * (1 - top_a))[..., None]) / np.maximum(a, 1e-6)[..., None]
    return c, a


# pure cut-out: shadow and glow are drawn by the page (CSS), not baked into the picture
layer_c, layer_a = fg, alpha
rgba = np.dstack([np.clip(layer_c, 0, 255), np.clip(layer_a, 0, 1) * 255]).round().astype(np.uint8)
res = Image.fromarray(rgba, "RGBA")

# ---- 6) crop to content (+ small margin) and scale to 1100 px wide
bb = res.getchannel("A").point(lambda p: 255 if p > 6 else 0).getbbox()
pad = 6
res = res.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(W, bb[2] + pad), min(H, bb[3] + pad)))
res = res.resize((1100, round(res.height * 1100 / res.width)), Image.LANCZOS)
res.save(out, "PNG", optimize=True)
print("Auto:", res.size, "| Datei:", out)

if prev:  # preview on the site background and on white / checkerboard

    def on(bgc):
        b = Image.new("RGBA", res.size, (*tuple(int(v) for v in bgc), 255))
        b.alpha_composite(res)
        return b.convert("RGB")

    sheet = Image.new("RGB", (res.width, res.height * 2), (0, 0, 0))
    sheet.paste(on(BGPAGE), (0, 0))
    sheet.paste(on((255, 255, 255)), (0, res.height))
    sheet.save(prev)
