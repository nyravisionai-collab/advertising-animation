#!/usr/bin/env python3
"""
ElectricalsKart - Projector Wall Advertising Animation Renderer
----------------------------------------------------------------
Renders a seamless-looping 1920x1080 @ 30fps advertising video for
continuous playback via Lenovo Yoga Tab 3 Pro built-in projector (VLC loop ON).

Output: H.264 MP4 (yuv420p), 44 s seamless loop, subtle royalty-free
synthesised ambient music (generated in this script - no copyrighted audio).

Modes:
  --mode stills   : render sample frames (design check) to output/stills/*.jpg
  --mode audio    : synthesise the ambient music loop -> output/audio_loop.wav
  --mode render   : full render, pipes raw frames to ffmpeg -> output/video_raw.mp4
"""

import argparse
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- constants
W, H = 1920, 1080
FPS = 30
T = 44.0                      # total loop duration (seconds)
N_FRAMES = int(T * FPS)       # 1320
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
OUT_DIR = os.path.join(ROOT, "output")

# palette -------------------------------------------------------------------
BG_TOP = (5, 7, 13)
BG_BOT = (10, 15, 26)
WHITE = (240, 247, 255)
SOFT = (199, 215, 236)
CYAN = (66, 204, 255)          # electric cyan (glow accent)
CYAN_TXT = (168, 233, 255)
AMBER = (255, 196, 84)         # electricity amber (glow accent)
AMBER_TXT = (255, 206, 116)
DARK = (8, 12, 20)

FONT_FILES = {
    "xb": "Montserrat-ExtraBold.ttf",
    "b": "Montserrat-Bold.ttf",
    "sb": "Montserrat-SemiBold.ttf",
    "m": "Montserrat-Medium.ttf",
    "r": "Montserrat-Regular.ttf",
}
_font_cache = {}


def font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            os.path.join(FONT_DIR, FONT_FILES[weight]), size)
    return _font_cache[key]


# ------------------------------------------------------------ easing / math
def clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def smooth(x):
    x = clamp01(x)
    return x * x * (3.0 - 2.0 * x)


def ease_out(x):
    x = clamp01(x)
    return 1.0 - (1.0 - x) ** 3


def env(t, a, b, f=0.7, tail=0.06):
    """Scene envelope: smooth fade-in at a, fade-out ending at b - tail."""
    fin = smooth((t - a) / f)
    fout = 1.0 - smooth((t - (b - tail - f)) / f)
    return fin * fout


# -------------------------------------------------------------- text layers
def rich_text_layer(segments, tracking=0, pad=140):
    """segments: list of (text, weight, size, color). Drawn on one baseline."""
    fonts = [font(wt, sz) for (_, wt, sz, _) in segments]
    widths = []
    total = 0.0
    for (txt, wt, sz, _), f in zip(segments, fonts):
        wn = [f.getlength(ch) for ch in txt]
        widths.append(wn)
        total += sum(wn) + tracking * max(0, len(txt) - 1)
    total += tracking * 0  # segments are pre-spaced inside text itself
    asc = max(f.getmetrics()[0] for f in fonts)
    desc = max(f.getmetrics()[1] for f in fonts)
    img = Image.new("RGBA", (int(total + 0.5) + 2 * pad, asc + desc + 2 * pad),
                    (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for (txt, wt, sz, col), f, wn in zip(segments, fonts, widths):
        for ch, wch in zip(txt, wn):
            d.text((x, pad), ch, font=f, fill=col)
            x += wch + tracking
    return img


def text_layer(text, weight, size, color, tracking=0, pad=140):
    return rich_text_layer([(text, weight, size, color)], tracking, pad)


def make_glow(rgba, color, radius, intensity=1.0):
    a = rgba.split()[3]
    if intensity < 1.0:
        a = a.point(lambda v: int(v * intensity))
    blurred = a.filter(ImageFilter.GaussianBlur(radius))
    glow = Image.new("RGBA", rgba.size, color + (0,))
    glow.putalpha(blurred)
    return glow


def layer_to_np(img):
    return np.asarray(img, dtype=np.float16) / 255.0


def full_frame(img, cx, cy):
    """Paste tight RGBA layer onto a full-frame transparent canvas centred cx,cy."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = int(cx - img.width / 2)
    py = int(cy - img.height / 2)
    canvas.paste(img, (px, py), img)
    return canvas


# ------------------------------------------------------------------- icons
SS = 3  # supersample factor for icon drawing


def icon_canvas(px=280):
    c = Image.new("RGBA", (px * SS, px * SS), (0, 0, 0, 0))
    return c, ImageDraw.Draw(c), px * SS


def icon_finish(img):
    return img.resize((img.width // SS, img.height // SS), Image.LANCZOS)


def icon_bolt(px=200):
    c, d, s = icon_canvas(px)
    pts_norm = [(0.635, 0.02), (0.17, 0.585), (0.44, 0.585), (0.365, 0.98),
                (0.83, 0.415), (0.56, 0.415)]
    pts = [(x * s, y * s) for x, y in pts_norm]
    d.polygon(pts, fill=WHITE)
    return icon_finish(c)


def icon_bulb(px=200):
    c, d, s = icon_canvas(px)
    cx, r = 0.5 * s, 0.255 * s
    cy = 0.36 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    # rays
    for ang_deg in (-70, -25, 25, 70, 90):
        a = math.radians(ang_deg - 90)
        r0, r1 = r + 0.075 * s, r + 0.16 * s
        x0, y0 = cx + r0 * math.cos(a), cy + r0 * math.sin(a)
        x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
        d.line([x0, y0, x1, y1], fill=WHITE, width=int(0.038 * s))
    # base
    d.rounded_rectangle([cx - 0.155 * s, 0.665 * s, cx + 0.155 * s, 0.765 * s],
                        radius=0.03 * s, fill=WHITE)
    d.rounded_rectangle([cx - 0.115 * s, 0.79 * s, cx + 0.115 * s, 0.865 * s],
                        radius=0.025 * s, fill=WHITE)
    d.rounded_rectangle([cx - 0.06 * s, 0.885 * s, cx + 0.06 * s, 0.94 * s],
                        radius=0.02 * s, fill=WHITE)
    return icon_finish(c)


def icon_socket(px=200):
    c, d, s = icon_canvas(px)
    m = 0.09 * s
    d.rounded_rectangle([m, m, s - m, s - m], radius=0.20 * s, fill=WHITE)
    # slots (dark)
    for sx in (0.36, 0.64):
        d.rounded_rectangle([(sx - 0.045) * s, 0.335 * s, (sx + 0.045) * s,
                             0.545 * s], radius=0.045 * s, fill=DARK)
    d.rounded_rectangle([0.455 * s, 0.655 * s, 0.545 * s, 0.775 * s],
                        radius=0.045 * s, fill=DARK)
    return icon_finish(c)


def icon_fan(px=200):
    c, d, s = icon_canvas(px)
    cx = cy = 0.5 * s
    blade = Image.new("RGBA", c.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(blade)
    bd.rounded_rectangle([cx - 0.085 * s, cy - 0.44 * s, cx + 0.085 * s,
                          cy - 0.04 * s], radius=0.085 * s, fill=WHITE)
    for rot in (0, 120, 240):
        c.alpha_composite(blade.rotate(rot, center=(cx, cy)))
    d = ImageDraw.Draw(c)
    d.ellipse([cx - 0.105 * s, cy - 0.105 * s, cx + 0.105 * s, cy + 0.105 * s],
              fill=WHITE)
    d.ellipse([cx - 0.45 * s, cy - 0.45 * s, cx + 0.45 * s, cy + 0.45 * s],
              outline=WHITE, width=int(0.032 * s))
    return icon_finish(c)


def icon_gear(px=200):
    c, d, s = icon_canvas(px)
    cx = cy = 0.5 * s
    tooth = Image.new("RGBA", c.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(tooth)
    td.rounded_rectangle([cx - 0.075 * s, cy - 0.46 * s, cx + 0.075 * s,
                          cy - 0.26 * s], radius=0.05 * s, fill=WHITE)
    for rot in range(0, 360, 45):
        c.alpha_composite(tooth.rotate(rot, center=(cx, cy)))
    d.ellipse([cx - 0.285 * s, cy - 0.285 * s, cx + 0.285 * s, cy + 0.285 * s],
              outline=WHITE, width=int(0.085 * s))
    return icon_finish(c)


def icon_tools(px=280):
    """Crossed wrench + screwdriver for the services scene."""
    c = Image.new("RGBA", (px * SS, px * SS), (0, 0, 0, 0))
    s = c.width
    # wrench (vertical, jaw up) later rotated
    wr = Image.new("RGBA", c.size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(wr)
    cx = 0.5 * s
    jaw_cy = 0.22 * s
    # jaw: open-end C ring, gap facing 3 o'clock before rotation
    wd.arc([cx - 0.17 * s, jaw_cy - 0.17 * s, cx + 0.17 * s,
            jaw_cy + 0.17 * s], start=40, end=320, fill=WHITE,
           width=int(0.082 * s))
    # neck wedge connecting jaw to handle
    wd.polygon([(cx - 0.075 * s, jaw_cy + 0.10 * s),
                (cx + 0.075 * s, jaw_cy + 0.10 * s),
                (cx + 0.052 * s, jaw_cy + 0.24 * s),
                (cx - 0.052 * s, jaw_cy + 0.24 * s)], fill=WHITE)
    # handle
    wd.rounded_rectangle([cx - 0.052 * s, jaw_cy + 0.16 * s, cx + 0.052 * s,
                          0.84 * s], radius=0.052 * s, fill=WHITE)
    wr = wr.rotate(-38, center=(cx, 0.5 * s))
    # screwdriver
    sd = Image.new("RGBA", c.size, (0, 0, 0, 0))
    sdd = ImageDraw.Draw(sd)
    cx2 = 0.5 * s
    sdd.rounded_rectangle([cx2 - 0.028 * s, 0.16 * s, cx2 + 0.028 * s,
                           0.60 * s], radius=0.02 * s, fill=WHITE)  # shaft
    sdd.polygon([(cx2 - 0.062 * s, 0.085 * s), (cx2 + 0.062 * s, 0.085 * s),
                 (cx2 + 0.028 * s, 0.16 * s), (cx2 - 0.028 * s, 0.16 * s)],
                fill=WHITE)  # tip
    sdd.rounded_rectangle([cx2 - 0.062 * s, 0.60 * s, cx2 + 0.062 * s,
                           0.86 * s], radius=0.055 * s, fill=WHITE)  # handle
    sd = sd.rotate(38, center=(cx2, 0.5 * s))
    c.alpha_composite(wr)
    c.alpha_composite(sd)
    return icon_finish(c)


def badge_layer(px=230):
    """Brand mark: rounded-square ring + lightning bolt."""
    c = Image.new("RGBA", (px * SS, px * SS), (0, 0, 0, 0))
    s = c.width
    d = ImageDraw.Draw(c)
    m = 0.085 * s
    d.rounded_rectangle([m, m, s - m, s - m], radius=0.24 * s, outline=WHITE,
                        width=int(0.035 * s))
    d.polygon([(x * s, y * s) for x, y in
               [(0.62, 0.24), (0.27, 0.60), (0.47, 0.60), (0.38, 0.80),
                (0.73, 0.46), (0.53, 0.46)]], fill=WHITE)
    return icon_finish(c)


# ----------------------------------------------------- ambient background
def build_base():
    """Static gradient + vignette + deterministic micro-noise (anti-banding)."""
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    top = np.array(BG_TOP, dtype=np.float32) / 255
    bot = np.array(BG_BOT, dtype=np.float32) / 255
    col = top[None, None, :] * (1 - y[..., None]) + bot[None, None, :] * y[..., None]
    col = np.repeat(col, W, axis=1)
    # soft central lift
    rr = ((x - 0.5) ** 2 / 0.5 ** 2 + (y - 0.52) ** 2 / 0.36 ** 2)
    lift = np.clip(1 - rr, 0, 1) ** 2 * 0.030
    col = col + lift[..., None]
    # vignette
    rv = ((x - 0.5) ** 2 / 0.62 ** 2 + (y - 0.5) ** 2 / 0.72 ** 2)
    col = col * (1 - 0.42 * np.clip(rv - 0.35, 0, 1) ** 1.4)[..., None]
    # static dither noise (constant over time -> seamless)
    rng = np.random.default_rng(7)
    noise = rng.uniform(-1.1, 1.1, (H, W, 1)).astype(np.float32) / 255
    col = np.clip(col + noise, 0, 1)
    return col.astype(np.float32)  # HxWx3


def build_radial_glow():
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    rr = ((x - 0.5) ** 2 / 0.42 ** 2 + (y - 0.50) ** 2 / 0.44 ** 2)
    g = np.clip(1 - rr, 0, 1) ** 2.6
    col = np.zeros((H, W, 3), dtype=np.float32)
    c = np.array(CYAN, dtype=np.float32) / 255
    col[...] = g[..., None] * c[None, None, :] * 0.16
    return col


def build_beams():
    """Two vertically-periodic soft light bands (seamless when np.roll-ed)."""
    beams = []
    specs = [(3, 2.6, 0.020, (120, 200, 255), 1),   # k, power, alpha, color, periods/T
             (5, 3.2, 0.013, (255, 214, 140), 1)]
    yy = np.arange(H, dtype=np.float32)[:, None]
    for k, pw, amp, rgb, _ in specs:
        prof = (0.5 + 0.5 * np.cos(2 * math.pi * k * yy / H)) ** pw * amp
        c = np.array(rgb, dtype=np.float32) / 255
        tex = np.repeat(prof, W, axis=1)[..., None] * c[None, None, :]
        beams.append(tex.astype(np.float32))  # premultiplied rgb
    return beams


# particle field -------------------------------------------------------------
PART_SPRITE = None


def part_sprite():
    global PART_SPRITE
    if PART_SPRITE is not None:
        return PART_SPRITE
    s = 25
    y, x = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.sqrt((x - s / 2) ** 2 + (y - s / 2) ** 2) / (s / 2)
    a = np.clip(1 - r, 0, 1) ** 2.2
    PART_SPRITE = a
    return a


def gen_particles(n=64):
    rng = np.random.default_rng(42)
    ps = []
    for _ in range(n):
        tint_pick = rng.random()
        if tint_pick < 0.62:
            col = np.array([150, 225, 255], np.float32) / 255
        elif tint_pick < 0.82:
            col = np.array([255, 214, 150], np.float32) / 255
        else:
            col = np.array([235, 244, 255], np.float32) / 255
        q = int(rng.integers(1, 3))          # vertical wraps per loop (1 or 2)
        k = int(rng.integers(2, 6))          # twinkle cycles per loop
        size = float(rng.uniform(0.5, 1.35))
        half = max(4, int(round(12 * size)))
        spr_img = Image.fromarray((part_sprite() * 255).astype(np.uint8))
        spr_img = spr_img.resize((2 * half, 2 * half), Image.BILINEAR)
        ps.append(dict(
            x0=float(rng.uniform(30, W - 30)),
            y0=float(rng.uniform(0, H + 60)),
            q=q, k=k,
            ph=float(rng.uniform(0, 2 * math.pi)),
            sway=float(rng.uniform(6, 26)),
            sway_k=int(rng.integers(1, 4)),
            size=size,
            amp=float(rng.uniform(0.25, 0.85)),
            col=col,
            spr=np.asarray(spr_img, dtype=np.float32) / 255.0,
            half=half,
        ))
    return ps


PARTICLES = gen_particles()


def draw_particles(dst, t):
    Hm = H + 60.0
    for p in PARTICLES:
        y = (p["y0"] - (p["q"] * Hm) * (t / T)) % Hm - 30.0
        x = p["x0"] + p["sway"] * math.sin(2 * math.pi * p["sway_k"] * t / T + p["ph"])
        tw = 0.30 + 0.70 * (0.5 + 0.5 * math.sin(2 * math.pi * p["k"] * t / T + p["ph"] * 2))
        # soft edges near top/bottom for invisible wrap
        edge = min(1.0, (y + 30) / 90.0, (H + 30 - y) / 90.0)
        a = p["amp"] * tw * max(0.0, edge) * 0.75
        if a <= 0.01:
            continue
        half = p["half"]
        xi, yi = int(x), int(y)
        xa0, xa1 = max(0, xi - half), min(W, xi + half)
        ya0, ya1 = max(0, yi - half), min(H, yi + half)
        if xa1 <= xa0 or ya1 <= ya0:
            continue
        spr_c = p["spr"][(ya0 - (yi - half)):(ya1 - (yi - half)),
                         (xa0 - (xi - half)):(xa1 - (xi - half))]
        dst[ya0:ya1, xa0:xa1, :] += spr_c[..., None] * a * p["col"][None, None, :]


def ambient(t, base, radial, beams):
    frame = base.copy()
    pu = 0.72 + 0.28 * math.sin(2 * math.pi * 2 * t / T)      # breathing
    frame += radial * pu
    off1 = int(round((2 * H / 3) * (t / T))) % H              # seamless rolls
    off2 = int(round((3 * H / 5) * (t / T))) % H
    frame += np.roll(beams[0], off1, axis=0)
    frame += np.roll(beams[1], -off2, axis=0)
    draw_particles(frame, t)
    return frame


# ------------------------------------------------------------- compositing
def over(dst, src16, alpha):
    """Composite float16 straight-alpha layer over opaque float32 rgb dst."""
    if alpha <= 0.0:
        return
    src = src16.astype(np.float32)
    a = src[..., 3:4] * alpha
    dst *= (1 - a)
    dst += src[..., :3] * a


def add_glow(dst, glow16, alpha):
    if alpha <= 0.0:
        return
    src = glow16.astype(np.float32)
    dst += src[..., :3] * src[..., 3:4] * alpha


def shifted(layer, dy):
    if dy == 0:
        return layer
    return np.roll(layer, dy, axis=0)


# ------------------------------------------------------ scene construction
def build_scenes():
    scenes = {}

    def card(parts):
        """parts: list of (relative order) already-composited PIL RGBA full frames."""
        base_img = parts
        return layer_to_np(base_img)

    # ---- helpers for combined layer (base + glow pre-merged)
    def merge(glow_pairs_base):
        glows, base = glow_pairs_base
        img = base
        for g in reversed(glows):
            img = Image.alpha_composite(g, img)
        return img

    def text_with_glow(text, wt, sz, col, glow_col, cx, cy, tracking=0,
                       r1=14, r2=40, gi1=0.85, gi2=0.5):
        tl = text_layer(text, wt, sz, col, tracking)
        g1 = make_glow(tl, glow_col, r1, gi1)
        g2 = make_glow(tl, glow_col, r2, gi2)
        combined = Image.alpha_composite(g2, g1)
        combined = Image.alpha_composite(combined, tl)
        return full_frame(combined, cx, cy)

    def seg_text_with_glow(segments, glow_col, cx, cy, tracking=0,
                           r1=14, r2=40, gi1=0.85, gi2=0.5):
        tl = rich_text_layer(segments, tracking)
        g1 = make_glow(tl, glow_col, r1, gi1)
        g2 = make_glow(tl, glow_col, r2, gi2)
        combined = Image.alpha_composite(g2, g1)
        combined = Image.alpha_composite(combined, tl)
        return full_frame(combined, cx, cy)

    def icon_with_glow(icon, glow_col, cx, cy, r1=10, r2=26, gi1=0.8, gi2=0.45,
                       ring=False):
        base = full_frame(icon, cx, cy)
        g1 = make_glow(base, glow_col, r1, gi1)
        g2 = make_glow(base, glow_col, r2, gi2)
        img = Image.alpha_composite(g2, g1)
        img = Image.alpha_composite(img, base)
        return img

    def rule_layer(cx, cy, width, color=(255, 255, 255), hpx=3, glow=CYAN):
        lin = np.linspace(0, 1, width, dtype=np.float32)
        prof = (np.clip(np.sin(lin * math.pi), 0, 1) ** 1.6 * 200).astype(np.uint8)
        strip = np.zeros((hpx, width, 4), dtype=np.uint8)
        strip[..., 0] = color[0]
        strip[..., 1] = color[1]
        strip[..., 2] = color[2]
        strip[..., 3] = prof[None, :]
        img = Image.fromarray(strip, "RGBA")
        g = make_glow(img, glow, 6, 0.8)
        img = Image.alpha_composite(g, img)
        return full_frame(img, cx, cy)

    # ==================================================== SCENE 1 (brand intro)
    s1 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s1.alpha_composite(text_with_glow("HYDRO ELECTRICO", "m", 46, CYAN_TXT,
                                      CYAN, 960, 236, tracking=16, r1=10,
                                      r2=30, gi1=0.7, gi2=0.4))
    badge = badge_layer(210)
    b_glow1 = make_glow(full_frame(badge, 960, 396), CYAN, 14, 0.9)
    b_glow2 = make_glow(full_frame(badge, 960, 396), CYAN, 42, 0.5)
    badge_full = Image.alpha_composite(b_glow2, b_glow1)
    badge_full.alpha_composite(full_frame(badge, 960, 396))
    s1.alpha_composite(badge_full)
    wm = rich_text_layer([("ELECTRICALS", "xb", 148, WHITE),
                          ("KART", "xb", 148, AMBER_TXT)], tracking=7)
    wm_g1 = make_glow(wm, CYAN, 16, 0.8)
    wm_g2 = make_glow(wm, CYAN, 46, 0.45)
    wm_all = Image.alpha_composite(wm_g2, wm_g1)
    wm_all.alpha_composite(wm)
    s1.alpha_composite(full_frame(wm_all, 960, 648))
    s1.alpha_composite(rule_layer(960, 742, 760))
    s1.alpha_composite(text_with_glow("Electrical Solutions at One Place",
                                      "r", 56, SOFT, CYAN, 960, 806,
                                      tracking=2, r1=8, r2=24, gi1=0.5,
                                      gi2=0.3))
    scenes[1] = dict(card=layer_to_np(s1), a=0.0, b=7.0,
                     pulse=layer_to_np(b_glow2))

    # ==================================================== SCENE 2 (categories)
    s2_static = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s2_static.alpha_composite(text_with_glow("PRODUCT CATEGORIES", "m", 42,
                                             AMBER_TXT, AMBER, 960, 146,
                                             tracking=17, r1=10, r2=26))
    s2_static.alpha_composite(rule_layer(960, 196, 420))
    items = [
        ("Electrical Products", icon_bolt(170), CYAN),
        ("LED Lighting", icon_bulb(170), AMBER),
        ("Switches & Sockets", icon_socket(170), CYAN),
        ("Fans", icon_fan(170), CYAN),
        ("Electrical Accessories", icon_gear(170), CYAN),
    ]
    # fixed column geometry (block centred on widest row)
    row_icon_cx = 470
    row_text_x = 620
    rows = []
    y0, dy = 292, 136
    for i, (label, icon, gcol) in enumerate(items):
        row = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        row.alpha_composite(icon_with_glow(icon, gcol, row_icon_cx,
                                           y0 + i * dy))
        tl = text_layer(label, "sb", 86, WHITE, tracking=2)
        g1 = make_glow(tl, gcol, 12, 0.7)
        g2 = make_glow(tl, gcol, 34, 0.4)
        tall = Image.alpha_composite(g2, g1)
        tall.alpha_composite(tl)
        row.alpha_composite(full_frame(tall, row_text_x + tall.width / 2 - 140,
                                       y0 + i * dy))
        rows.append(layer_to_np(row))
    tail = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    tail.alpha_composite(text_with_glow("+ All General Electrical Items", "m",
                                        54, AMBER_TXT, AMBER, 960, 952,
                                        tracking=3, r1=10, r2=26))
    scenes[2] = dict(card=layer_to_np(s2_static), rows=rows,
                     tail=layer_to_np(tail), a=7.0, b=19.0)

    # ==================================================== SCENE 3 (R/W/O)
    s3_rows = []
    labels = [("RETAIL", CYAN), ("WHOLESALE", WHITE), ("ONLINE", AMBER)]
    ys = (330, 560, 790)
    for i, (lab, gcol) in enumerate(labels):
        row = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gc = CYAN if lab != "ONLINE" else AMBER
        row.alpha_composite(seg_text_with_glow([(lab, "xb", 172, WHITE)],
                                               gc, 960, ys[i], tracking=12,
                                               r1=16, r2=48))
        row.alpha_composite(rule_layer(960, ys[i] + 104, 340,
                                       color=tuple(gc), glow=gc))
        s3_rows.append(layer_to_np(row))
    s3_tail = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s3_tail.alpha_composite(text_with_glow(
        "Quality Electrical Products at Competitive Prices", "r", 56, SOFT,
        CYAN, 960, 948, tracking=2, r1=8, r2=22, gi1=0.5, gi2=0.3))
    scenes[3] = dict(rows=s3_rows, tail=layer_to_np(s3_tail), a=19.0, b=25.0)

    # ==================================================== SCENE 4 (services)
    s4 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s4.alpha_composite(text_with_glow("OUR SERVICES", "m", 42, AMBER_TXT,
                                      AMBER, 960, 168, tracking=17, r1=10,
                                      r2=26))
    s4.alpha_composite(rule_layer(960, 216, 420))
    s4.alpha_composite(icon_with_glow(icon_tools(300), AMBER, 960, 398, r1=14,
                                      r2=40))
    s4.alpha_composite(text_with_glow("Electrical Installation", "sb", 122,
                                      WHITE, CYAN, 960, 636, tracking=3,
                                      r1=16, r2=44))
    s4.alpha_composite(seg_text_with_glow([("& ", "sb", 122, AMBER_TXT),
                                           ("Repair Services", "sb", 122,
                                            WHITE)], AMBER, 960, 786,
                                          tracking=3, r1=16, r2=44))
    scenes[4] = dict(card=layer_to_np(s4), a=25.0, b=31.0)

    # ==================================================== SCENE 5 (reminder)
    s5 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    b5 = badge_layer(185)
    bg1 = make_glow(full_frame(b5, 960, 342), CYAN, 13, 0.9)
    bg2 = make_glow(full_frame(b5, 960, 422), CYAN, 38, 0.45)
    b5full = Image.alpha_composite(bg2, bg1)
    b5full.alpha_composite(full_frame(b5, 960, 342))
    s5.alpha_composite(b5full)
    wm5 = rich_text_layer([("ELECTRICALS", "xb", 132, WHITE),
                           ("KART", "xb", 132, AMBER_TXT)], tracking=7)
    w5g1 = make_glow(wm5, CYAN, 15, 0.8)
    w5g2 = make_glow(wm5, CYAN, 42, 0.45)
    w5all = Image.alpha_composite(w5g2, w5g1)
    w5all.alpha_composite(wm5)
    s5.alpha_composite(full_frame(w5all, 960, 606))
    s5.alpha_composite(rule_layer(960, 694, 680))
    s5.alpha_composite(text_with_glow("Your Electrical Store", "r", 60,
                                      CYAN_TXT, CYAN, 960, 762, tracking=3,
                                      r1=10, r2=28, gi1=0.6, gi2=0.35))
    scenes[5] = dict(card=layer_to_np(s5), a=31.0, b=35.0)

    # ==================================================== SCENE 6 (website)
    s6 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s6.alpha_composite(text_with_glow("VISIT US ONLINE", "m", 46, CYAN_TXT,
                                      CYAN, 960, 330, tracking=18, r1=10,
                                      r2=28))
    url = text_layer("electricalskart.com", "xb", 138, WHITE, tracking=3)
    ug1 = make_glow(url, CYAN, 18, 0.95)
    ug2 = make_glow(url, CYAN, 52, 0.6)
    uall = Image.alpha_composite(ug2, ug1)
    uall.alpha_composite(url)
    s6.alpha_composite(full_frame(uall, 960, 566))
    s6.alpha_composite(rule_layer(960, 700, 900, glow=CYAN))
    scenes[6] = dict(card=layer_to_np(s6), pulse=layer_to_np(
        full_frame(make_glow(url, CYAN, 60, 0.9), 960, 566)), a=35.0, b=39.0)

    # sweep sprite for scene 6 underline
    sw_w = 210
    xx = np.linspace(-1, 1, sw_w, dtype=np.float32)
    prof = np.clip(1 - np.abs(xx), 0, 1) ** 2
    sweep = np.zeros((10, sw_w, 3), dtype=np.float32)
    c = np.array([190, 240, 255], np.float32) / 255
    sweep[...] = prof[None, :, None] * c[None, None, :] * 0.9
    scenes[6]["sweep"] = sweep.astype(np.float16)

    # ==================================================== SCENE 7 (final)
    s7 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s7.alpha_composite(text_with_glow("HYDRO ELECTRICO", "m", 42, CYAN_TXT,
                                      CYAN, 960, 214, tracking=16, r1=10,
                                      r2=28))
    wm7 = rich_text_layer([("ELECTRICALS", "xb", 138, WHITE),
                           ("KART", "xb", 138, AMBER_TXT)], tracking=7)
    w7g1 = make_glow(wm7, CYAN, 16, 0.85)
    w7g2 = make_glow(wm7, CYAN, 46, 0.5)
    w7all = Image.alpha_composite(w7g2, w7g1)
    w7all.alpha_composite(wm7)
    s7.alpha_composite(full_frame(w7all, 960, 420))
    s7.alpha_composite(text_with_glow(
        "Electrical Products  •  Retail  •  Wholesale  •  Online", "m", 58,
        SOFT, CYAN, 960, 570, tracking=4, r1=8, r2=24, gi1=0.5, gi2=0.3))
    s7.alpha_composite(rule_layer(960, 646, 760))
    u7 = text_layer("electricalskart.com", "xb", 96, AMBER_TXT, tracking=3)
    u7g1 = make_glow(u7, AMBER, 15, 0.9)
    u7g2 = make_glow(u7, AMBER, 40, 0.5)
    u7all = Image.alpha_composite(u7g2, u7g1)
    u7all.alpha_composite(u7)
    s7.alpha_composite(full_frame(u7all, 960, 748))
    scenes[7] = dict(card=layer_to_np(s7), a=39.0, b=44.0)

    return scenes


# ------------------------------------------------------------ frame render
def render_frame(i, scenes, base, radial, beams):
    t = i / FPS
    frame = ambient(t, base, radial, beams)

    # ---- scene 1
    s = scenes[1]
    a = env(t, s["a"], s["b"])
    if a > 0:
        u = clamp01((t - s["a"]) / 0.9)
        dy = int(round((1 - ease_out(u)) * 44))
        over(frame, shifted(s["card"], dy), a)
        pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 2 * t / T + 1.2)
        add_glow(frame, shifted(s["pulse"], dy), a * 0.16 * pulse)

    # ---- scene 2 (sequential reveals)
    s = scenes[2]
    a = env(t, s["a"], s["b"], f=0.6)
    if a > 0:
        over(frame, s["card"], a * smooth((t - 7.2) / 0.8))
        for idx, row in enumerate(s["rows"]):
            ts = 7.7 + idx * 1.4
            p = (t - ts) / 0.9
            if p <= 0:
                continue
            e = ease_out(p)
            dy = int(round((1 - e) * 34))
            over(frame, shifted(row, dy), a * smooth(p))
        pt = (t - 14.8) / 0.9
        if pt > 0:
            over(frame, s["tail"], a * smooth(pt))

    # ---- scene 3 (R/W/O staggered)
    s = scenes[3]
    a = env(t, s["a"], s["b"], f=0.6)
    if a > 0:
        for idx, row in enumerate(s["rows"]):
            ts = 19.5 + idx * 0.75
            p = (t - ts) / 0.8
            if p <= 0:
                continue
            e = ease_out(p)
            dy = int(round((1 - e) * 40))
            over(frame, shifted(row, dy), a * smooth(p))
        pt = (t - 21.9) / 0.8
        if pt > 0:
            over(frame, s["tail"], a * smooth(pt))

    # ---- scene 4 (services)
    s = scenes[4]
    a = env(t, s["a"], s["b"])
    if a > 0:
        u = clamp01((t - s["a"]) / 0.9)
        dy = int(round((1 - ease_out(u)) * 40))
        over(frame, shifted(s["card"], dy), a)

    # ---- scene 5 (reminder)
    s = scenes[5]
    a = env(t, s["a"], s["b"])
    if a > 0:
        u = clamp01((t - s["a"]) / 0.8)
        dy = int(round((1 - ease_out(u)) * 40))
        over(frame, shifted(s["card"], dy), a)

    # ---- scene 6 (website + underline sweep)
    s = scenes[6]
    a = env(t, s["a"], s["b"])
    if a > 0:
        u = clamp01((t - s["a"]) / 0.8)
        dy = int(round((1 - ease_out(u)) * 40))
        over(frame, shifted(s["card"], dy), a)
        pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 2 * t / T + 0.6)
        add_glow(frame, shifted(s["pulse"], dy), a * 0.10 * pulse)
        # sweep highlight along underline (period 2.2 s -> 20 cycles / loop)
        span0, span1 = 510.0, 1410.0
        frac = (t / 2.2) % 1.0
        sx = span0 + (span1 - span0) * frac
        sy = 700 + dy
        sw = s["sweep"].astype(np.float32)
        x0 = int(sx - sw.shape[1] / 2)
        if 0 <= x0 and x0 + sw.shape[1] < W:
            frame[sy - 5:sy + 5, x0:x0 + sw.shape[1], :] += sw * a

    # ---- scene 7 (final hold)
    s = scenes[7]
    a = env(t, s["a"], s["b"], f=0.75)
    if a > 0:
        over(frame, s["card"], a)

    np.clip(frame, 0, 1, out=frame)
    return (frame * 255).astype(np.uint8)


# ------------------------------------------------------------------- audio
def synth_audio(path):
    sr = 44100
    xf_s = 1.2                       # loop crossfade length
    n = int(T * sr)
    xf = int(xf_s * sr)
    n_gen = n + xf                   # render extra tail used for the crossfade
    t = np.arange(n_gen, dtype=np.float32) / sr
    out = np.zeros(n_gen, dtype=np.float32)
    T_gen = T + xf_s

    chords = [  # Am, F, C, G  (one per 11 s)
        [110.00, 130.81, 164.81, 196.00],
        [87.31, 130.81, 174.61, 220.00],
        [130.81, 164.81, 196.00, 246.94],
        [98.00, 123.47, 146.83, 196.00],
    ]

    def ad_env(tt, a_len, r_len, total):
        e = np.minimum(tt / a_len, 1.0)
        e = np.minimum(e, np.maximum((total - tt) / r_len, 0.0))
        return np.clip(e, 0, 1) ** 1.5

    seg = T / 4
    n_chords = int(T_gen / seg) + 1
    for ci in range(n_chords):
        chord = chords[ci % 4]
        start = ci * seg
        i0, i1 = int(start * sr), min(n_gen, int(((ci + 1) * seg) * sr))
        tt = t[i0:i1] - start
        e = ad_env(tt, 2.2, 2.6, seg) * 0.030
        for fq in chord:
            for det, am in ((0.0, 1.0), (0.0016, 0.55), (-0.0016, 0.55)):
                out[i0:i1] += (np.sin(2 * np.pi * fq * (1 + det) * tt)
                               * am * e).astype(np.float32)
            # soft octave shimmer
            out[i0:i1] += (np.sin(2 * np.pi * fq * 2 * tt) * 0.18 * e
                           ).astype(np.float32)

    # gentle pluck arpeggio
    pluck_notes = [220.0, 261.63, 329.63, 392.0, 329.63, 261.63]
    step = seg / 16.0
    idx = 0
    tt_g = 0.0
    while tt_g < T_gen - 0.3:
        fq = pluck_notes[idx % len(pluck_notes)] * 2
        start = int(tt_g * sr)
        L = int(0.55 * sr)
        if start + L < n:
            tn = np.arange(L, dtype=np.float32) / sr
            envp = np.exp(-tn / 0.17)
            out[start:start + L] += np.sin(2 * np.pi * fq * tn) * envp * 0.020
        idx += 1
        tt_g += step

    # rare soft sparkles
    for k, fq in enumerate([1318.5, 1568.0, 1046.5, 1174.7, 1318.5]):
        start = 2.75 + k * 11.0
        if start < T_gen:
            i0 = int(start * sr)
            L = int(0.9 * sr)
            tn = np.arange(L, dtype=np.float32) / sr
            envp = np.exp(-tn / 0.10)
            if i0 + L > len(out):
                continue
            out[i0:i0 + L] += np.sin(2 * np.pi * fq * tn) * envp * 0.008

    # seamless loop crossfade: extra tail folded into the head
    ramp = np.linspace(0, 1, xf, dtype=np.float32)
    tail = out[n:n + xf].copy()
    head = out[:xf].copy()
    out[:xf] = head * ramp + tail * (1 - ramp)
    out = out[:n]
    t = t[:n]

    out = np.tanh(out * 1.4)
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak * 0.55
    pcm = (out * 32767).astype(np.int16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    print(f"[audio] wrote {path} ({len(out)/sr:.2f}s)")


# ------------------------------------------------------------------- main
def get_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="stills",
                    choices=["stills", "render", "audio"])
    ap.add_argument("--times", default="")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    print("building ambient layers ...", flush=True)
    base = build_base()
    radial = build_radial_glow()
    beams = build_beams()
    print("building scenes ...", flush=True)
    scenes = build_scenes()

    if args.mode == "audio":
        synth_audio(os.path.join(OUT_DIR, "audio_loop.wav"))
        return

    if args.mode == "stills":
        times = [float(x) for x in args.times.split(",") if x] or [
            3.5, 10.5, 16.5, 22.3, 28.0, 33.0, 37.0, 41.5, 43.9, 0.4]
        sdir = os.path.join(OUT_DIR, "stills")
        os.makedirs(sdir, exist_ok=True)
        for tt in times:
            i = int(tt * FPS) % N_FRAMES
            fr = render_frame(i, scenes, base, radial, beams)
            Image.fromarray(fr).save(os.path.join(
                sdir, f"still_t{tt:05.1f}.jpg"), quality=88)
            print(f"still @t={tt}", flush=True)
        return

    # full render
    raw_path = os.path.join(OUT_DIR, "video_raw.mp4")
    ff = get_ffmpeg()
    cmd = [ff, "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "pipe:0",
           "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
           raw_path]
    print("render+encode:", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    import time as _time
    t0 = _time.time()
    for i in range(N_FRAMES):
        fr = render_frame(i, scenes, base, radial, beams)
        proc.stdin.write(fr.tobytes())
        if i % 60 == 0:
            el = _time.time() - t0
            fps_now = (i + 1) / el if el > 0 else 0
            eta = (N_FRAMES - i) / fps_now if fps_now > 0 else 0
            print(f"frame {i}/{N_FRAMES}  {fps_now:.1f} fps  eta {eta:.0f}s",
                  flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"done in {_time.time()-t0:.0f}s -> {raw_path}", flush=True)


if __name__ == "__main__":
    main()
