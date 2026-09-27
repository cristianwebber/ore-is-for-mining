#!/usr/bin/env python3
"""Renders thumbnail.png (144x144) from the game's own graphics, standard library only.

Several designs are available; see DESIGNS at the bottom. Building sprites are
composited the way the game draws them (layers, shifts, shadows), with the layer
numbers taken from the base game's prototype files.

usage: make_thumbnail.py [--design NAME] [--out PATH] [path/to/Factorio/data]

The graphics are read from a local Factorio install, found automatically on the
usual Steam paths when no data folder is given.
"""
import argparse
import math
import random
import struct
import sys
import zlib
from pathlib import Path

SIZE = 144

CANDIDATES = [
    "/mnt/d/SteamLibrary/steamapps/common/Factorio/data",
    "/mnt/c/Program Files (x86)/Steam/steamapps/common/Factorio/data",
    "/mnt/c/Program Files/Factorio/data",
    "~/.steam/steam/steamapps/common/Factorio/data",
    "~/.factorio/data",
]

DATA = None  # Factorio data folder, set in main()


def find_data_dir(arg):
    if arg:
        return Path(arg).expanduser()
    for c in CANDIDATES:
        p = Path(c).expanduser()
        if (p / "base" / "graphics").is_dir():
            return p
    sys.exit("Factorio data folder not found; pass it as an argument")


# --- PNG in/out ---------------------------------------------------------------
class Image:
    """RGBA pixels as premultiplied floats in 0..1, stored row-major."""

    def __init__(self, w, h, px=None):
        self.w, self.h = w, h
        self.px = px if px is not None else [[0.0, 0.0, 0.0, 0.0] for _ in range(w * h)]


_raw_cache = {}


def _decode(path, rows):
    """Unfiltered scanlines of the first `rows` rows, plus the pixel format."""
    key = str(path)
    cached = _raw_cache.get(key)
    if cached and len(cached[0]) >= rows:
        return cached
    data = Path(path).read_bytes()
    pos, idat, palette, trns = 8, b"", None, b""
    while pos < len(data):
        length, tag = struct.unpack(">I4s", data[pos:pos + 8])
        payload = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", payload)
            assert depth == 8 and interlace == 0, f"unsupported PNG: {path}"
        elif tag == b"PLTE":
            palette = payload
        elif tag == b"tRNS":
            trns = payload
        elif tag == b"IDAT":
            idat += payload
        pos += 12 + length
    channels = {0: 1, 3: 1, 4: 2, 2: 3, 6: 4}[ctype]
    rows = min(h, rows)
    stride = w * channels
    raw = zlib.decompressobj().decompress(idat, rows * (stride + 1))
    lines, prev = [], bytearray(stride)
    for y in range(rows):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        lines.append(line)
        prev = line
    result = (lines, w, h, ctype, channels, palette, trns)
    _raw_cache[key] = result
    return result


def read_png(path, box=None):
    """Decodes an 8-bit non-interlaced PNG, or only the box (x, y, w, h) of it."""
    if box is None:
        lines, w, h, *_ = _decode(path, 1 << 30)
        box = (0, 0, w, h)
    bx, by, bw, bh = box
    lines, w, h, ctype, channels, palette, trns = _decode(path, by + bh)
    img = Image(bw, bh, [])
    for line in lines[by:by + bh]:
        for x in range(bx, bx + bw):
            v = line[x * channels:(x + 1) * channels]
            if ctype == 3:
                i = v[0]
                r, g, b = palette[i * 3:i * 3 + 3]
                a = trns[i] if i < len(trns) else 255
            elif ctype == 0:
                r = g = b = v[0]; a = 255
            elif ctype == 4:
                r = g = b = v[0]; a = v[1]
            elif ctype == 2:
                r, g, b = v; a = 255
            else:
                r, g, b, a = v
            al = a / 255
            img.px.append([r / 255 * al, g / 255 * al, b / 255 * al, al])
    return img


def write_png(img, path):
    rows = []
    for y in range(img.h):
        row = bytearray([0])
        for x in range(img.w):
            r, g, b, a = img.px[y * img.w + x]
            row += bytes(int(round(max(0.0, min(1.0, c)) * 255)) for c in (r, g, b))
        rows.append(bytes(row))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", img.w, img.h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
    png += chunk(b"IEND", b"")
    Path(path).write_bytes(png)


# --- Image operations -----------------------------------------------------------
def resample(src, w, h, kx, ky, fx=0.0, fy=0.0):
    """Area-averaging resample: src scaled by (kx, ky), shifted right/down by (fx, fy)
    canvas pixels, into a w x h image."""
    out = Image(w, h)
    area = 1 / (kx * ky)
    for y in range(h):
        y0, y1 = (y - fy) / ky, (y + 1 - fy) / ky
        for x in range(w):
            x0, x1 = (x - fx) / kx, (x + 1 - fx) / kx
            acc = [0.0, 0.0, 0.0, 0.0]
            for j in range(max(0, math.floor(y0)), min(src.h, math.ceil(y1))):
                wy = min(y1, j + 1) - max(y0, j)
                row = j * src.w
                for i in range(max(0, math.floor(x0)), min(src.w, math.ceil(x1))):
                    wgt = wy * (min(x1, i + 1) - max(x0, i))
                    p = src.px[row + i]
                    acc[0] += p[0] * wgt; acc[1] += p[1] * wgt
                    acc[2] += p[2] * wgt; acc[3] += p[3] * wgt
            out.px[y * w + x] = [c / area for c in acc]
    return out


def resize(src, w, h):
    return resample(src, w, h, w / src.w, h / src.h)


def paste(dst, src, ox, oy, opacity=1.0):
    for y in range(src.h):
        dy = oy + y
        if not 0 <= dy < dst.h:
            continue
        for x in range(src.w):
            dx = ox + x
            if not 0 <= dx < dst.w:
                continue
            s = src.px[y * src.w + x]
            if s[3] <= 0:
                continue
            d = dst.px[dy * dst.w + dx]
            k = 1 - s[3] * opacity
            dst.px[dy * dst.w + dx] = [s[i] * opacity + d[i] * k for i in range(4)]


def blurred_alpha(img, blur, strength, color=(0.0, 0.0, 0.0)):
    """Soft silhouette of img in a flat color, padded by blur on every side."""
    w, h = img.w + 2 * blur, img.h + 2 * blur
    alpha = [0.0] * (w * h)
    for y in range(img.h):
        for x in range(img.w):
            alpha[(y + blur) * w + x + blur] = img.px[y * img.w + x][3]
    for _ in range(2):  # two box blurs ~ gaussian
        tmp = [0.0] * (w * h)
        for y in range(h):
            for x in range(w):
                xs = range(max(0, x - blur), min(w, x + blur + 1))
                tmp[y * w + x] = sum(alpha[y * w + i] for i in xs) / (2 * blur + 1)
        alpha = [0.0] * (w * h)
        for y in range(h):
            for x in range(w):
                ys = range(max(0, y - blur), min(h, y + blur + 1))
                alpha[y * w + x] = sum(tmp[j * w + x] for j in ys) / (2 * blur + 1)
    out = []
    for a in alpha:
        a = min(1.0, a * strength)
        out.append([color[0] * a, color[1] * a, color[2] * a, a])
    return Image(w, h, out)


def blur(img, r):
    """Two box blurs of radius r over all channels (edges clamp)."""
    w, h = img.w, img.h
    px = img.px
    for _ in range(2):
        tmp = [None] * (w * h)
        for y in range(h):
            for x in range(w):
                acc = [0.0, 0.0, 0.0, 0.0]
                for i in range(x - r, x + r + 1):
                    p = px[y * w + min(w - 1, max(0, i))]
                    for c in range(4):
                        acc[c] += p[c]
                tmp[y * w + x] = [c / (2 * r + 1) for c in acc]
        out = [None] * (w * h)
        for y in range(h):
            for x in range(w):
                acc = [0.0, 0.0, 0.0, 0.0]
                for j in range(y - r, y + r + 1):
                    p = tmp[min(h - 1, max(0, j)) * w + x]
                    for c in range(4):
                        acc[c] += p[c]
                out[y * w + x] = [c / (2 * r + 1) for c in acc]
        px = out
    return Image(w, h, px)


def sharpen(img, amount):
    """Unsharp mask; brings back the detail lost when shrinking icons."""
    soft = blur(img, 1)
    for p, q in zip(img.px, soft.px):
        a = p[3]
        for c in range(3):
            p[c] = max(0.0, min(a, p[c] + amount * (p[c] - q[c])))
    return img


def darken(img, amount):
    for p in img.px:
        for i in range(3):
            p[i] *= 1 - amount


def vignette(img, amount):
    cx, cy = img.w / 2, img.h / 2
    rmax = math.hypot(cx, cy)
    for y in range(img.h):
        for x in range(img.w):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / rmax
            k = 1 - amount * max(0.0, d - 0.45) / 0.55
            p = img.px[y * img.w + x]
            for i in range(3):
                p[i] *= k


def tint_invalid(img):
    """The game's red 'cannot build here' preview: a red, see-through version."""
    for p in img.px:
        a = p[3]
        if a <= 0:
            continue
        lum = 0.3 * p[0] + 0.59 * p[1] + 0.11 * p[2]
        k = 0.85
        p[0], p[1], p[2], p[3] = min(a, 0.18 * a + lum * 1.5) * k, lum * 0.5 * k, lum * 0.42 * k, a * k


def draw_shape(img, inside, bbox, color, ss=4):
    """Anti-aliased fill of every point where inside(x, y) holds (thumbnail coords)."""
    x0, y0, x1, y1 = bbox
    for py in range(max(0, int(y0)), min(img.h, math.ceil(y1))):
        for px in range(max(0, int(x0)), min(img.w, math.ceil(x1))):
            hits = sum(inside(px + (i + 0.5) / ss, py + (j + 0.5) / ss)
                       for i in range(ss) for j in range(ss))
            if hits:
                a = hits / (ss * ss)
                d = img.px[py * img.w + px]
                img.px[py * img.w + px] = [color[i] * a + d[i] * (1 - a) for i in range(3)] + [1.0]


def no_sign(img, cx, cy, r, t=None, outline=1.2):
    """Red prohibition sign with a thin white outline."""
    t = t or r * 0.2
    red, white = (0.86, 0.15, 0.15), (1.0, 1.0, 1.0)
    bbox = (cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2)
    c = s = math.sqrt(0.5)

    def ring(width):
        return lambda x, y: r - t - width <= math.hypot(x - cx, y - cy) <= r + width

    def bar(width):
        def inside(x, y):
            dx, dy = x - cx, y - cy
            along, across = dx * c + dy * s, -dx * s + dy * c
            return abs(across) <= t / 2 + width and abs(along) <= r - t / 2
        return inside

    draw_shape(img, ring(outline), bbox, white)
    draw_shape(img, bar(outline), bbox, white)
    draw_shape(img, ring(0), bbox, red)
    draw_shape(img, bar(0), bbox, red)


def badge(img, cx, cy, r, color, mark):
    """Round badge with a white check or cross, like a status marker."""
    bbox = (cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2)
    draw_shape(img, lambda x, y: math.hypot(x - cx, y - cy) <= r + 1.2, bbox, (1.0, 1.0, 1.0))
    draw_shape(img, lambda x, y: math.hypot(x - cx, y - cy) <= r, bbox, color)
    t = r * 0.28

    def seg(ax, ay, bx, by):
        vx, vy = bx - ax, by - ay
        l2 = vx * vx + vy * vy

        def inside(x, y):
            u = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / l2))
            return math.hypot(x - ax - u * vx, y - ay - u * vy) <= t / 2
        return inside

    if mark == "check":
        parts = [seg(cx - r * 0.45, cy + r * 0.02, cx - r * 0.12, cy + r * 0.38),
                 seg(cx - r * 0.12, cy + r * 0.38, cx + r * 0.48, cy - r * 0.34)]
    else:
        d = r * 0.4
        parts = [seg(cx - d, cy - d, cx + d, cy + d), seg(cx - d, cy + d, cx + d, cy - d)]
    draw_shape(img, lambda x, y: any(p(x, y) for p in parts), bbox, (1.0, 1.0, 1.0))


# --- Game graphics -------------------------------------------------------------------
def gfx(rel):
    return DATA / "base" / "graphics" / rel


def icon(name, size, sharp=0.0):
    """The full-resolution 64x64 level of a mipmapped item icon, scaled to size."""
    img = resize(read_png(gfx(f"icons/{name}.png"), (0, 0, 64, 64)), size, size)
    return sharpen(img, sharp) if sharp else img


def place_icon(canvas, img, x, y, blur=3, strength=1.6):
    paste(canvas, blurred_alpha(img, blur, strength), x - blur + 2, y - blur + 3, 0.85)
    paste(canvas, img, x, y)


def px(v):
    """util.by_pixel: sprite pixels at scale 1 to tiles."""
    return v / 32


class Layer:
    def __init__(self, file, w, h, x=0, y=0, shift=(0, 0), scale=0.5, shadow=False):
        self.file, self.w, self.h, self.x, self.y = file, w, h, x, y
        self.shift, self.scale, self.shadow = shift, scale, shadow


# Layer data from base/prototypes/entity/*.lua (frame 0, high resolution sprites).
def drill(direction):
    d = "electric-mining-drill/electric-mining-drill"
    head = Layer(d + ".png", 162, 156, shift=(px(1), px(-11)))
    head_shadow = Layer(d + "-shadow.png", 218, 56, shift=(px(33), px(-5)), shadow=True)
    if direction == "north":
        return [Layer(d + "-N.png", 190, 208, shift=(0, px(-4))),
                Layer(d + "-N-output.png", 60, 66, shift=(px(-3), px(-44))),
                head,
                Layer(d + "-N-shadow.png", 212, 204, shift=(px(6), px(-3)), shadow=True), head_shadow]
    return [Layer(d + "-S.png", 184, 192, shift=(0, px(-1))),
            head,
            Layer(d + "-S-output.png", 84, 56, shift=(px(-1), px(34))),
            Layer(d + "-S-front.png", 190, 104, shift=(0, px(27))),
            Layer(d + "-S-shadow.png", 212, 204, shift=(px(6), px(2)), shadow=True), head_shadow]


def small_pole():
    return [Layer("small-electric-pole/small-electric-pole.png", 72, 220, shift=(px(1.5), px(-42.5))),
            Layer("small-electric-pole/small-electric-pole-shadow.png", 256, 52,
                  shift=(px(51), px(3)), shadow=True)]


def assembler():
    d = "assembling-machine-1/assembling-machine-1"
    return [Layer(d + "-base.png", 198, 184, shift=(0, px(4))),
            Layer(d + "-anim.png", 140, 158, shift=(0, px(-13.5))),
            Layer(d + "-shadow.png", 50, 166, shift=(px(44.5), px(0.5)), shadow=True)]


def stone_furnace():
    return [Layer("stone-furnace/stone-furnace.png", 151, 146, shift=(px(-0.25), px(6))),
            Layer("stone-furnace/stone-furnace-shadow.png", 164, 74, shift=(px(14.5), px(13)), shadow=True)]


class Scene:
    """A camera over the game world: tile (ox, oy) at the canvas' top-left corner."""

    def __init__(self, canvas, tile_px, ox=0.0, oy=0.0):
        self.canvas, self.tile, self.ox, self.oy = canvas, tile_px, ox, oy
        self.shadows = Image(canvas.w, canvas.h)
        self.bodies = []  # (sort y, image, x, y)

    def to_px(self, tx, ty):
        return (tx - self.ox) * self.tile, (ty - self.oy) * self.tile

    def sprite(self, layer, tx, ty):
        """The layer resampled to the canvas, and its integer top-left corner."""
        src = read_png(gfx("entity/" + layer.file), (layer.x, layer.y, layer.w, layer.h))
        size = layer.scale / 32 * self.tile
        w, h = layer.w * size, layer.h * size
        cx, cy = self.to_px(tx + layer.shift[0], ty + layer.shift[1])
        left, top = cx - w / 2, cy - h / 2
        fx, fy = left - math.floor(left), top - math.floor(top)
        img = resample(src, math.ceil(w + fx), math.ceil(h + fy), size, size, fx, fy)
        return img, math.floor(left), math.floor(top)

    def entity(self, layers, tx, ty, invalid=False):
        for layer in layers:
            img, x, y = self.sprite(layer, tx, ty)
            if layer.shadow:
                if not invalid:
                    paste(self.shadows, img, x, y)
            else:
                if invalid:
                    tint_invalid(img)
                self.bodies.append((ty + (100 if invalid else 0), len(self.bodies), img, x, y))

    def belt_east(self, tx0, tx1, ty, frame=0, items=None):
        for tx in range(tx0, tx1):
            layer = Layer("transport-belt/transport-belt.png", 128, 128, x=128 * frame, y=0)
            img, x, y = self.sprite(layer, tx + 0.5, ty + 0.5)
            paste(self.canvas, img, x, y)
        for (ix, lane, name) in items or []:
            size = round(self.tile * 0.42)
            cx, cy = self.to_px(ix, ty + (0.28 if lane == 0 else 0.72))
            place_icon(self.canvas, icon(name, size), round(cx - size / 2), round(cy - size / 2),
                       blur=1, strength=1.0)

    def finish(self, shadow_opacity=0.55):
        for p in self.shadows.px:
            p[3] = min(1.0, p[3])
        black = Image(self.shadows.w, self.shadows.h, [[0.0, 0.0, 0.0, p[3]] for p in self.shadows.px])
        paste(self.canvas, black, 0, 0, shadow_opacity)
        for _, _, img, x, y in sorted(self.bodies, key=lambda b: (b[0], b[1])):
            paste(self.canvas, img, x, y)


def ore_ground(canvas, tile_px, ore="iron-ore", seed=7, richness=(0, 4), dim=0.3):
    """Dirt tiles covered in ore sprites, like a rich patch seen in game."""
    dirt_px = math.ceil(canvas.w * 64 / tile_px)
    dirt = read_png(gfx("terrain/dirt-1.png"), (0, 0, dirt_px, dirt_px))
    paste(canvas, resize(dirt, canvas.w, canvas.h), 0, 0)
    rng = random.Random(seed)
    frames = {}
    n = math.ceil(canvas.w / tile_px) + 1
    for ty in range(-1, n):
        for tx in range(-1, n):
            key = (rng.randrange(8), rng.randrange(*richness))
            if key not in frames:
                col, row = key
                frames[key] = resize(read_png(gfx(f"entity/{ore}/{ore}.png"),
                                              (col * 128, row * 128, 128, 128)),
                                     2 * tile_px, 2 * tile_px)
            paste(canvas, frames[key], tx * tile_px - tile_px // 2, ty * tile_px - tile_px // 2)
    darken(canvas, dim)


# --- Designs -------------------------------------------------------------------------
def design_outpost():
    """In-game mining outpost; a red 'cannot build' assembler preview on the ore."""
    canvas = Image(SIZE, SIZE)
    tile = 20
    ore_ground(canvas, tile, dim=0.2)
    scene = Scene(canvas, tile, ox=-0.1, oy=-0.05)
    iron = "iron-ore"
    scene.belt_east(-1, 9, 3, items=[(0.2, 0, iron), (1.7, 1, iron), (3.3, 0, iron),
                                     (4.4, 1, iron), (5.8, 0, iron), (6.6, 1, iron)])
    scene.entity(drill("south"), 1.5, 1.5)
    scene.entity(drill("south"), 4.5, 1.5)
    scene.entity(small_pole(), 6.5, 0.5)
    scene.entity(small_pole(), 3.5, 4.5)
    scene.entity(drill("north"), 5.5, 5.5)
    scene.entity(assembler(), 1.5, 5.5, invalid=True)
    scene.finish()
    vignette(canvas, 0.35)
    return canvas


def design_icons():
    """Item icons on an ore patch; the assembler crossed out."""
    canvas = Image(SIZE, SIZE)
    ore_ground(canvas, 24, dim=0.35)
    place_icon(canvas, icon("electric-mining-drill", 64), 6, 6)
    place_icon(canvas, icon("inserter", 44), 90, 8)
    place_icon(canvas, icon("transport-belt", 44), 8, 90)
    place_icon(canvas, icon("small-electric-pole", 48), 52, 44)
    place_icon(canvas, icon("assembling-machine-1", 50), 84, 84)
    no_sign(canvas, 109, 109, 27, 5.5)
    return canvas


def design_split():
    """Allowed (green check) against not allowed (red cross), in two panels."""
    canvas = Image(SIZE, SIZE)
    ore_ground(canvas, 24, dim=0.5)
    half = SIZE // 2
    for y in range(SIZE):
        top = y < half
        for x in range(SIZE):
            p = canvas.px[y * SIZE + x]
            if top:
                p[0], p[1], p[2] = p[0] * 0.8, p[1] * 0.9 + 0.035, p[2] * 0.8
            else:
                p[0], p[1], p[2] = p[0] * 0.9 + 0.06, p[1] * 0.6, p[2] * 0.6
    draw_shape(canvas, lambda x, y: half - 1 <= y <= half + 1, (0, half - 2, SIZE, half + 2),
               (0.06, 0.06, 0.06))
    size, gap = 44, 3
    left = (SIZE - 3 * size - 2 * gap) // 2
    rows = [
        (["electric-mining-drill", "transport-belt", "inserter"], 16, (0.22, 0.66, 0.22), "check"),
        (["assembling-machine-1", "stone-furnace", "solar-panel"], half + 16, (0.84, 0.16, 0.16), "cross"),
    ]
    for names, top, color, mark in rows:
        for i, name in enumerate(names):
            place_icon(canvas, icon(name, size, sharp=0.6), left + i * (size + gap), top,
                       blur=2, strength=1.8)
        badge(canvas, SIZE - 12, top - 5, 9, color, mark)
    return canvas


def design_furnace():
    """One big 'cannot build' furnace on the ore: no more smelters on your iron."""
    canvas = Image(SIZE, SIZE)
    tile = 48
    ore_ground(canvas, tile, dim=0.3, seed=3)
    scene = Scene(canvas, tile, ox=-0.5, oy=-0.55)
    scene.entity(stone_furnace(), 1, 1, invalid=True)
    scene.finish()
    vignette(canvas, 0.4)
    no_sign(canvas, 72, 72, 54, 8, outline=1.6)
    return canvas


def design_drill():
    """Close-up of a mining drill on the ore, with a green check mark."""
    canvas = Image(SIZE, SIZE)
    tile = 36
    ore_ground(canvas, tile, dim=0.25, seed=11)
    scene = Scene(canvas, tile, ox=0, oy=-0.2)
    scene.belt_east(-1, 5, 3, items=[(0.3, 0, "iron-ore"), (1.4, 1, "iron-ore"), (2.6, 0, "iron-ore")])
    scene.entity(drill("south"), 1.5, 1.5)
    scene.entity(small_pole(), 3.5, 1.5)
    scene.finish()
    vignette(canvas, 0.35)
    badge(canvas, 124, 124, 13, (0.2, 0.62, 0.2), "check")
    return canvas


DESIGNS = {
    "outpost": design_outpost,
    "icons": design_icons,
    "split": design_split,
    "furnace": design_furnace,
    "drill": design_drill,
}
DEFAULT = "split"


def main():
    global DATA
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("data", nargs="?", help="Factorio data folder")
    parser.add_argument("--design", choices=DESIGNS, default=DEFAULT)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "thumbnail.png"))
    args = parser.parse_args()
    DATA = find_data_dir(args.data)
    write_png(DESIGNS[args.design](), args.out)
    print(f"wrote {args.out} ({args.design}) using graphics from {DATA}")


if __name__ == "__main__":
    main()
