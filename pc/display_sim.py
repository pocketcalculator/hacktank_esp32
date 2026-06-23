#!/usr/bin/env python3
"""
display_sim.py — PC-side simulator for the HackTank ESP32 round display (240×240 GC9A01A).

Faithfully reproduces all five static visual states from display_anim.cpp using
the EXACT firmware constants for colors and radii. A single render_frame()
function drives both interactive (pygame) and headless (Pillow export) modes.

Usage
-----
Live preview  (requires pygame — `pip install pygame`):
    python pc\\display_sim.py
    python pc\\display_sim.py --state alert2
    Keys: 0=IDLE  1/2/3=ALERT severity  s=STALE  Esc/q=quit

Headless export  (Pillow only, works anywhere — no display required):
    python pc\\display_sim.py --export pc\\preview
    Writes animated GIFs + filmstrip montage PNGs + overview.png to the given directory.
"""

import sys
import os
import argparse

# ---------------------------------------------------------------------------
# Pillow (required)
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print(
        "ERROR: Pillow is required.\n"
        "  pip install pillow\n"
        "For the optional live window also install:  pip install pygame",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# *** Firmware constants — mirrored verbatim from display_anim.cpp ***
# ---------------------------------------------------------------------------

DISPLAY_W = 240
DISPLAY_H = 240
CX, CY = 120, 120                       # display center (pixels)

# IDLE — static teal car
IDLE_RADIUS      = 115                  # draw_car size: 224 px wide (x=8..232)
IDLE_COLOR       = (0, 160, 200)

# ALERT — static fixed colors; indexed by severity [0 unused / 1 / 2 / 3]
ALERT_RADII   = [0, 109, 112, 115]      # draw_car size per severity: ~212/218/224 px wide
ALERT_COLORS  = [None,
                 (220,  30,   0),       # sev 1 — vivid red
                 (255,  90,   0),       # sev 2 — hot orange-red
                 (255, 180,   0)]       # sev 3 — steady amber

# STALE — static dim blue-grey
STALE_RADIUS     = 115
STALE_COLOR      = (13, 13, 55)

# ---------------------------------------------------------------------------
# Fixed detail colors — non-pulsing, identical to firmware COL_* constants
# ---------------------------------------------------------------------------
# Glass / windows: light ice-blue — contrasts vs all five body palettes.
# RGB (160,200,224) → rgb565 quantized stays (160,200,224).
GLASS_COLOR = (160, 200, 224)   # pre-quantized; rgb565_quantize(160,200,224) is identity

# Tyre outer: near-black dark grey  RGB (24,24,24)
TIRE_COLOR  = (24, 24, 24)      # pre-quantized; rgb565_quantize(24,24,24) is identity

# Hub / rim: mid grey  RGB (128,128,128)
HUB_COLOR   = (128, 128, 128)   # pre-quantized; rgb565_quantize(128,128,128) is identity

# ---------------------------------------------------------------------------
# Helpers — exact Python translations of firmware functions
# ---------------------------------------------------------------------------

def rgb565_quantize(r: int, g: int, b: int) -> tuple:
    """
    Reproduce the bit-depth loss from the firmware's rgb565() helper.
    R → 5 bits (mask 0xF8), G → 6 bits (mask 0xFC), B → 5 bits (mask 0xF8).
    """
    return (r & 0xF8, g & 0xFC, b & 0xF8)


def _draw_car(draw: "ImageDraw.Draw", cx: int, cy: int, sz: int, color: tuple) -> None:
    """
    Draw a detailed side-view car centred at (cx, cy).
    `sz` mirrors the radius used by the former fillCircle call — scales the car.
    Geometry matches firmware draw_car() exactly (integer scale: v * sz // 90).
    Base design (sz=90): 176 × 88 px, centred on (cx, cy).

    Draw order per frame:
      1. Body shape (state color)
      2. Wheels: dark tyre outer ellipse + lighter hub ellipse (fixed TIRE/HUB_COLOR)
      3. Windows: front + rear panes inset inside cabin (fixed GLASS_COLOR)
    """
    def sc(v: int) -> int:
        return int(v) * sz // 90     # integer arithmetic — pixel-faithful to firmware

    bx  = sc(88);  by_ = sc(12); bh = sc(38)
    cdx = sc(44);  cdy = sc(44); ch = sc(32)
    wdx = sc(56);  wcy = sc(26); wr = max(3, sc(18))
    whr = max(2, sc(9))              # hub radius (~half of wr)

    # Window insets (mirroring firmware SC() values)
    wi_top  = sc(4)
    wi_side = sc(4)
    wi_bot  = sc(3)
    wp      = sc(3)                  # centre-pillar half-width

    # ── Body (state color) ───────────────────────────────────────────────────
    # Lower body hull
    draw.rectangle([cx - bx, cy - by_, cx + bx, cy - by_ + bh], fill=color)
    # Upper cabin rect
    draw.rectangle([cx - cdx, cy - cdy, cx + cdx, cy - cdy + ch], fill=color)
    # Front (left) windshield slope
    draw.polygon([(cx - bx, cy - by_), (cx - cdx, cy - by_), (cx - cdx, cy - cdy)], fill=color)
    # Rear (right) window slope
    draw.polygon([(cx + cdx, cy - by_), (cx + bx, cy - by_), (cx + cdx, cy - cdy)], fill=color)

    # ── Wheels: dark tyre outer + lighter hub (fixed, non-pulsing) ───────────
    for wx in (cx - wdx, cx + wdx):
        wy = cy + wcy
        draw.ellipse([wx - wr,  wy - wr,  wx + wr,  wy + wr],  fill=TIRE_COLOR)
        draw.ellipse([wx - whr, wy - whr, wx + whr, wy + whr], fill=HUB_COLOR)

    # ── Windows: front + rear panes (fixed glass, non-pulsing) ──────────────
    wx_l = cx - cdx + wi_side       # pane left edge
    wx_r = cx + cdx - wi_side       # pane right edge
    wy_t = cy - cdy + wi_top        # pane top edge
    wy_b = cy - by_ - wi_bot        # pane bottom edge
    # Front (left) window pane
    draw.rectangle([wx_l,     wy_t, cx - wp, wy_b], fill=GLASS_COLOR)
    # Rear (right) window pane
    draw.rectangle([cx + wp,  wy_t, wx_r,    wy_b], fill=GLASS_COLOR)


# ---------------------------------------------------------------------------
# Round-display mask — constructed once, reused by every render call
# ---------------------------------------------------------------------------

_ROUND_MASK = Image.new("L", (DISPLAY_W, DISPLAY_H), 0)
ImageDraw.Draw(_ROUND_MASK).ellipse(
    (0, 0, DISPLAY_W - 1, DISPLAY_H - 1), fill=255
)
_BLACK_BG = Image.new("RGB", (DISPLAY_W, DISPLAY_H), (0, 0, 0))


def _apply_round_mask(img: Image.Image) -> Image.Image:
    """Clip img to the 240 px display circle; corners outside the circle are black."""
    out = _BLACK_BG.copy()
    out.paste(img, (0, 0), mask=_ROUND_MASK)
    return out


# ---------------------------------------------------------------------------
# *** Core render function — shared by live preview AND export modes ***
# ---------------------------------------------------------------------------

def render_frame(state: str, sev: int, t_ms: float) -> Image.Image:
    """
    Render one 240×240 RGB PIL Image for the given state at simulation time t_ms.

    Parameters
    ----------
    state : 'idle' | 'alert' | 'stale'
    sev   : alert severity 1-3 (unused for idle / stale)
    t_ms  : simulation time in milliseconds

    Returns
    -------
    PIL Image (RGB, 240×240), round-masked (corners are black).
    """
    img = Image.new("RGB", (DISPLAY_W, DISPLAY_H), (0, 0, 0))
    d   = ImageDraw.Draw(img)

    if state == "idle":
        color = rgb565_quantize(*IDLE_COLOR)
        r     = IDLE_RADIUS
        _draw_car(d, CX, CY, r, color)

    elif state == "alert":
        sev     = max(1, min(3, int(sev)))
        color   = rgb565_quantize(*ALERT_COLORS[sev])
        r       = ALERT_RADII[sev]
        _draw_car(d, CX, CY, r, color)

    elif state == "stale":
        color = rgb565_quantize(*STALE_COLOR)
        r     = STALE_RADIUS
        _draw_car(d, CX, CY, r, color)

    return _apply_round_mask(img)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def _cycle_and_tick(state: str, sev: int) -> tuple:
    """Return a single static-frame cadence for export compatibility."""
    if state in ("idle", "alert", "stale"):
        return 1000, 1000
    raise ValueError(f"Unknown state: {state!r}")


def _get_font():
    """Return a PIL font, trying a modest size first, falling back to bitmap default."""
    try:
        return ImageFont.load_default(size=12)
    except TypeError:
        return ImageFont.load_default()


def _draw_centered_text(draw, font, text: str, cx: int, y: int, color):
    """Draw text horizontally centred at (cx, y), compatible with bitmap & truetype fonts."""
    try:
        w = int(font.getlength(text))
    except AttributeError:
        w = len(text) * 6   # fallback estimate for the default bitmap font
    draw.text((cx - w // 2, y), text, fill=color, font=font)


# ── Static GIF ───────────────────────────────────────────────────────────────

def _merge_duplicate_frames(frames, tick_ms: int):
    """
    Merge consecutive identical frames, summing their durations.

    Static exports intentionally produce duplicate frames for compatibility with
    the existing GIF path. Merge them so the output remains a single still image.

    Returns (unique_frames_rgb, duration_list_ms).
    """
    unique: list = [frames[0]]
    durs:   list = [tick_ms]
    for f in frames[1:]:
        if f.tobytes() == unique[-1].tobytes():
            durs[-1] += tick_ms          # extend the last frame's display time
        else:
            unique.append(f)
            durs.append(tick_ms)
    return unique, durs


def export_gif(state: str, sev: int, path: str):
    """Export a static GIF preview."""
    cycle_ms, tick_ms = _cycle_and_tick(state, sev)
    n_frames = max(2, cycle_ms // tick_ms)
    frames   = [render_frame(state, sev, i * tick_ms) for i in range(n_frames)]

    unique, durs = _merge_duplicate_frames(frames, tick_ms)

    # Convert to palette mode for GIF; no dithering keeps the solid circles crisp
    p_frames = [f.quantize(colors=256, dither=0) for f in unique]
    p_frames[0].save(
        path,
        save_all=True,
        append_images=p_frames[1:],
        duration=durs,
        loop=0,
        optimize=False,
    )


# ── Filmstrip montage PNG ─────────────────────────────────────────────────────

_STATE_LABELS = {
    ("idle",  0): "IDLE",
    ("alert", 1): "ALERT sev 1",
    ("alert", 2): "ALERT sev 2",
    ("alert", 3): "ALERT sev 3",
    ("stale", 0): "STALE",
}


def export_filmstrip(state: str, sev: int, path: str, n_strip: int = 6):
    """
    Export a filmstrip PNG: n_strip frames evenly distributed across one full cycle,
    laid side by side on a dark background with millisecond timestamps.
    """
    cycle_ms, _ = _cycle_and_tick(state, sev)
    timestamps  = [int(cycle_ms * i / n_strip) for i in range(n_strip)]
    frames      = [render_frame(state, sev, t) for t in timestamps]

    pad      = 8
    label_h  = 18
    cell_w   = DISPLAY_W + pad * 2
    cell_h   = DISPLAY_H + pad * 2 + label_h
    strip_w  = cell_w * n_strip
    strip_h  = cell_h + pad * 3 + label_h   # extra row for the state name

    strip = Image.new("RGB", (strip_w, strip_h), (20, 20, 26))
    d     = ImageDraw.Draw(strip)
    font  = _get_font()

    for i, (frame, ts) in enumerate(zip(frames, timestamps)):
        x = i * cell_w + pad
        y = pad
        # Subtle border that outlines the round display shape
        d.ellipse((x - 1, y - 1, x + DISPLAY_W, y + DISPLAY_H),
                  outline=(55, 55, 68), width=1)
        strip.paste(frame, (x, y))
        ts_label = f"{ts} ms"
        _draw_centered_text(d, font, ts_label,
                            cx=x + DISPLAY_W // 2,
                            y=y + DISPLAY_H + 4,
                            color=(120, 120, 145))

    # State name centred at the bottom
    key        = (state, sev if state == "alert" else 0)
    name_label = _STATE_LABELS.get(key, state.upper())
    _draw_centered_text(d, font, name_label,
                        cx=strip_w // 2,
                        y=strip_h - label_h - 2,
                        color=(200, 200, 220))

    strip.save(path)


# ── Overview PNG ──────────────────────────────────────────────────────────────

def export_overview(path: str):
    """
    Export overview.png — one representative peak-brightness frame per state,
    all five states in a single row with labels.
    """
    # (state, sev, t_ms_ignored_for_static_frame, label)
    representative = [
        ("idle",  0,    0, "IDLE"),
        ("alert", 1,    0, "ALERT sev1"),
        ("alert", 2,    0, "ALERT sev2"),
        ("alert", 3,    0, "ALERT sev3"),
        ("stale", 0,    0, "STALE"),
    ]

    n        = len(representative)
    pad      = 12
    label_h  = 20
    cell_w   = DISPLAY_W + pad * 2
    cell_h   = DISPLAY_H + pad * 2 + label_h
    img_w    = cell_w * n
    img_h    = cell_h + pad * 2

    overview = Image.new("RGB", (img_w, img_h), (15, 15, 20))
    d        = ImageDraw.Draw(overview)
    font     = _get_font()

    for i, (state, sev, t_ms, label) in enumerate(representative):
        x     = i * cell_w + pad
        y     = pad
        frame = render_frame(state, sev, t_ms)
        d.ellipse((x - 1, y - 1, x + DISPLAY_W, y + DISPLAY_H),
                  outline=(60, 60, 75), width=1)
        overview.paste(frame, (x, y))
        _draw_centered_text(d, font, label,
                            cx=x + DISPLAY_W // 2,
                            y=y + DISPLAY_H + 6,
                            color=(200, 200, 220))

    overview.save(path)


# ── Run all exports ───────────────────────────────────────────────────────────

def run_export(out_dir: str):
    """Headless export of all GIFs, filmstrip PNGs, and the overview PNG."""
    os.makedirs(out_dir, exist_ok=True)

    tasks = [
        ("idle",  0, "idle"),
        ("alert", 1, "alert1"),
        ("alert", 2, "alert2"),
        ("alert", 3, "alert3"),
        ("stale", 0, "stale"),
    ]

    print(f"Exporting display previews to: {os.path.abspath(out_dir)}")
    for state, sev, name in tasks:
        gif_path = os.path.join(out_dir, f"{name}.gif")
        png_path = os.path.join(out_dir, f"{name}.png")
        export_gif(state, sev, gif_path)
        export_filmstrip(state, sev, png_path)
        print(f"  {gif_path}")
        print(f"  {png_path}")

    overview_path = os.path.join(out_dir, "overview.png")
    export_overview(overview_path)
    print(f"  {overview_path}")

    print("\nAll files written:")
    for fname in sorted(os.listdir(out_dir)):
        fsize = os.path.getsize(os.path.join(out_dir, fname))
        print(f"  {fname:20s}  {fsize:>7,} bytes")


# ---------------------------------------------------------------------------
# Interactive live preview (pygame — optional)
# ---------------------------------------------------------------------------

def run_live(initial_state: str = "idle", initial_sev: int = 1):
    try:
        import pygame
    except ImportError:
        print(
            "\npygame is not installed — the live window is unavailable.\n"
            "Install it with:  pip install pygame\n"
            "\nFor headless export (no display required) use:\n"
            "  python pc\\display_sim.py --export pc\\preview\n",
            file=sys.stderr,
        )
        sys.exit(1)

    SCALE = 2
    WIN_W = DISPLAY_W * SCALE
    WIN_H = DISPLAY_H * SCALE

    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))

    state: str = initial_state
    sev:   int = initial_sev

    def update_title():
        key   = (state, sev if state == "alert" else 0)
        label = _STATE_LABELS.get(key, state.upper())
        pygame.display.set_caption(
            f"HackTank Display Sim — {label}"
            "    [0=IDLE  1/2/3=ALERT  s=STALE  q=quit]"
        )

    update_title()
    clock = pygame.time.Clock()
    redraw_needed = True

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_0:
                    state, sev = "idle", 0;   update_title(); redraw_needed = True
                elif event.key == pygame.K_1:
                    state, sev = "alert", 1;  update_title(); redraw_needed = True
                elif event.key == pygame.K_2:
                    state, sev = "alert", 2;  update_title(); redraw_needed = True
                elif event.key == pygame.K_3:
                    state, sev = "alert", 3;  update_title(); redraw_needed = True
                elif event.key in (pygame.K_s, pygame.K_S):
                    state, sev = "stale", 0;  update_title(); redraw_needed = True

        if redraw_needed:
            frame     = render_frame(state, sev, 0)
            frame_big = frame.resize((WIN_W, WIN_H), Image.NEAREST)
            surf      = pygame.image.fromstring(frame_big.tobytes(), (WIN_W, WIN_H), "RGB")
            screen.blit(surf, (0, 0))
            pygame.display.flip()
            redraw_needed = False

        clock.tick(30)

    pygame.quit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="HackTank ESP32 display simulator — live preview or headless export"
    )
    parser.add_argument(
        "--export", metavar="DIR",
        help="Headless mode: write GIFs + PNGs to DIR (no display required)"
    )
    parser.add_argument(
        "--state",
        choices=["idle", "alert1", "alert2", "alert3", "stale"],
        default="idle",
        help="Initial state for live preview (default: idle)"
    )
    args = parser.parse_args()

    if args.export:
        run_export(args.export)
    else:
        state_map = {
            "idle":   ("idle",  0),
            "alert1": ("alert", 1),
            "alert2": ("alert", 2),
            "alert3": ("alert", 3),
            "stale":  ("stale", 0),
        }
        s, v = state_map[args.state]
        run_live(s, v)


if __name__ == "__main__":
    main()
