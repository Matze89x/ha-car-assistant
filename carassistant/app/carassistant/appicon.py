"""App and per-vehicle icons: upload your own, automatic sizes for favicon, home screen and web-app manifest.

The icon of the app itself cannot be changed - only the colours of its frame follow the design. A car has an icon of its own (``<files>/icons/v<id>.png``,
your logo or photo), put into the same frame. Sizes are generated on demand and cached.
"""

from __future__ import annotations

import functools
import io
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps, UnidentifiedImageError

from . import config

SIZES = (32, 48, 64, 96, 128, 180, 192, 256, 512)
MAX_BYTES = 5 * 1024 * 1024
STATIC = Path(__file__).parent / "static"
DEFAULT = STATIC / "appicon-default.png"  # the tile with rounded corners (transparent outside)
DEFAULT_FULL = STATIC / "appicon-full.png"  # a full square: iOS rounds the home-screen icon itself and paints anything transparent black
DEFAULT_MASKABLE = STATIC / "appicon-maskable.png"  # the whole tile inside the safe zone: Android may cut a circle or a squircle out of it
BACKGROUND = (13, 16, 22, 255)
FRAME_FROM = (226, 0, 26)  # the coloured frame of the real icon: red at the top left, green at the bottom right (the classic design)
FRAME_TO = (74, 222, 128)
CLASSIC = (FRAME_FROM, FRAME_TO)
FRAME_VERSION = "f2"  # part of the cache name: a new look of the frame makes new files


class IconError(ValueError):
    """Raised for files that are not a usable image."""


def _folder() -> Path:
    folder = config.files_dir() / "icons"
    (folder / "cache").mkdir(parents=True, exist_ok=True)
    return folder


def custom_path(vid: int) -> Path:
    return _folder() / f"v{int(vid)}.png"


def source(vid: int | None) -> Path:
    """The car's own icon, or the built-in one (the app itself has no icon of your own)."""
    if vid is not None and custom_path(vid).is_file():
        return custom_path(vid)
    return DEFAULT


def has_custom(vid: int | None) -> bool:
    return vid is not None and custom_path(vid).is_file()


def frame_colours(vid: int | None) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """The colours of the frame: red to green in the classic design, otherwise the colour of the design and its partner (a car with a design of its
    own wears that one)."""
    from . import db, themes

    with db.tx() as conn:
        own = None
        if vid is not None:
            row = conn.execute("SELECT theme FROM vehicles WHERE id = ?", (vid,)).fetchone()
            own = row["theme"] if row else None
        theme = own if own in themes.available() else themes.current(conn)
        accent = db.get_setting(conn, themes.ACCENT_SETTING, "")
    return themes.frame_colours(accent) if themes.is_custom(theme) else CLASSIC


def themed(vid: int | None) -> bool:
    """The frame has colours other than the classic ones."""
    return frame_colours(vid) != CLASSIC


def _colour_key(colours) -> str:
    return "".join(f"{r:02x}{g:02x}{b:02x}" for r, g, b in colours)


def revision(vid: int | None) -> int:
    """Changes whenever the icon changes (used as cache buster). The built-in icon changes with the app version: a phone and every cache in
    between must fetch it again after an update, whatever the date of the file in the image says."""
    import zlib

    from . import __version__

    path = source(vid)
    colours = frame_colours(vid)
    if path == DEFAULT:
        return zlib.crc32((__version__ + _colour_key(colours)).encode())
    try:
        return (
            int(path.stat().st_mtime) + zlib.crc32((FRAME_VERSION + _colour_key(colours)).encode()) % 1000
        )  # a new frame look or colour is fetched again
    except OSError:
        return 0


def save_custom(data: bytes, vid: int | None) -> None:
    if len(data) > MAX_BYTES:
        raise IconError("err.file_big")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ("PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF"):
                raise IconError("err.file_type")
            probe.load()
            image = ImageOps.exif_transpose(probe).convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise IconError("err.file_type") from exc
    # centred and cut to a full square (the picture fills the whole icon)
    side = min(image.size)
    image = ImageOps.fit(image, (side, side), Image.LANCZOS)
    if side > 1024:
        image = image.resize((1024, 1024), Image.LANCZOS)
    path = custom_path(vid)
    image.save(path, "PNG", optimize=True)  # re-encoded: no metadata, no foreign payload
    clear_cache()


def reset(vid: int | None) -> None:
    custom_path(vid).unlink(missing_ok=True)
    clear_cache()


def clear_cache() -> None:
    for old in (_folder() / "cache").glob("*.png"):
        old.unlink(missing_ok=True)


def favicon_ico(vid: int | None = None) -> bytes:
    """A multi-size favicon.ico (16/32/48) for browsers that ask for /favicon.ico."""
    big = Image.open(variant(vid, 64)).convert("RGBA")
    buf = io.BytesIO()
    big.save(buf, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    return buf.getvalue()


def framed(picture: Image.Image, side: int = 1024, colours=CLASSIC) -> Image.Image:
    """Your picture inside the coloured frame of the real icon: a dark tile with rounded corners, a red-to-green edge and the picture inside it.

    Drawn at twice the size and scaled down, so the edges are smooth. Transparent outside the tile (the corners).
    """
    big = side * 2
    margin, edge, radius = 0, round(big * 0.047), round(big * 0.22)  # like the real icon: the tile goes to the edge
    box = (margin, margin, big - margin, big - margin)
    inner = (box[0] + edge, box[1] + edge, box[2] - edge, box[3] - edge)
    across = Image.linear_gradient("L").resize((big, big)).rotate(90)  # 0 at the left .. 255 at the right
    down = Image.linear_gradient("L").resize((big, big))  # 0 at the top .. 255 at the bottom
    ramp = ImageChops.add(across, down, scale=2)  # diagonal: red at the top left, green at the bottom right, as in the real icon
    gradient = Image.composite(Image.new("RGB", (big, big), colours[1]), Image.new("RGB", (big, big), colours[0]), ramp)
    mask_outer = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask_outer).rounded_rectangle(box, radius=radius, fill=255)
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    tile.paste(gradient, (0, 0), mask_outer)
    inner_side = inner[2] - inner[0]
    cover = ImageOps.fit(picture.convert("RGBA"), (inner_side, inner_side), Image.LANCZOS)
    dark = Image.new("RGBA", (inner_side, inner_side), BACKGROUND)
    dark.alpha_composite(cover)  # a transparent picture sits on the dark of the app
    mask_inner = Image.new("L", (inner_side, inner_side), 0)
    ImageDraw.Draw(mask_inner).rounded_rectangle((0, 0, inner_side - 1, inner_side - 1), radius=max(radius - edge, 1), fill=255)
    tile.paste(dark, (inner[0], inner[1]), mask_inner)
    return tile.resize((side, side), Image.LANCZOS)


@functools.lru_cache(maxsize=8)
def _framed_master(path: str, stamp: int, colours) -> Image.Image:
    """The framed picture at full size, made once per picture and colours (the sizes are cut from it). The built-in icon is the car on its dark
    tile: only its inside is taken, the frame is drawn new in the colours of the design."""
    with Image.open(path) as image:
        picture = image.convert("RGBA")
    if path == str(DEFAULT):
        edge = round(picture.width * 0.047)
        picture = picture.crop((edge, edge, picture.width - edge, picture.height - edge))
    return framed(picture, colours=colours)


def variant(vid: int | None, size: int, kind: str = "any") -> Path:
    """Path of the icon scaled to ``size`` px (cached). ``kind``: "any" (the tile; 180 px for the iPhone is a full square) or "maskable" (Android)."""
    if size not in SIZES or kind not in ("any", "maskable"):
        raise KeyError(size)
    src = source(vid)
    colours = frame_colours(vid)
    original = src == DEFAULT and colours == CLASSIC  # the classic design: the icon exactly as drawn
    if original:
        art = DEFAULT_MASKABLE if kind == "maskable" else DEFAULT_FULL if size == 180 else DEFAULT
        tag = "d" + art.stem.removeprefix("appicon")
        stamp = int(art.stat().st_mtime)
    else:
        art, tag, stamp = src, f"{src.stem}-{FRAME_VERSION}-{_colour_key(colours)}", int(src.stat().st_mtime)
    target = _folder() / "cache" / f"{tag}-{kind}-{size}-{stamp}.png"
    if not target.is_file():
        with Image.open(art) as image:
            icon = image.convert("RGBA")
            if not original:
                icon = _framed_master(str(art), stamp, colours).copy()  # the frame in the colours of the design
            if not original and kind == "maskable":  # in the safe zone, on the page colour
                inner = icon.resize((round(size * 0.78),) * 2, Image.LANCZOS)
                canvas = Image.new("RGBA", (size, size), BACKGROUND)
                canvas.alpha_composite(inner, ((size - inner.width) // 2,) * 2)
                icon = canvas
            icon = icon.resize((size, size), Image.LANCZOS)
        if size == 180 and kind == "any":
            flat = Image.new("RGBA", icon.size, BACKGROUND)
            flat.alpha_composite(icon)
            icon = flat.convert("RGB")  # iOS paints transparency black: the home-screen icon has no alpha channel at all
        icon.save(target, "PNG", optimize=True)
    return target
