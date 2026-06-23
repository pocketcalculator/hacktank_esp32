// display_anim.cpp — Non-blocking animations for the 240×240 GC9A01A round display.
//
// Timing budget per tick call: the ~5 ms guideline is met for IDLE and STALE.
// ALERT draws one car silhouette (~6-10 ms for sz 70-90) but fires only at its
// pulse cadence (every 125–500 ms depending on severity), keeping average load low.
//
// State/animation summary:
//   IDLE  — slow breathing teal car silhouette (sz=65), period 3 s, update every 50 ms.
//   ALERT — bold pulsing: bright → dim colour alternation at [1 Hz / 2 Hz / 4 Hz]
//            for severity [1 / 2 / 3]. Size grows with severity (sz 70/80/90).
//            sev 1: red pulse. sev 2: orange-red pulse. sev 3: red↔yellow strobe.
//   STALE — very dim slow blue-grey pulse (sz=40), period 4 s, update every 200 ms.
//
// Shape: detailed side-view car (draw_car helper). Draw order per frame:
//   body (state color, pulsing) → wheels (fixed dark tyre + mid-grey hub) → windows (fixed glass)
//   Base design at sz=90: 176×88 px, centred on (120,120).
//   Body hull   : cx±88, cy-12 to cy+26  (fillRoundRect, h=38)
//   Cabin rect  : cx±44, cy-44 to cy-12  (fillRect, h=32)
//   Windshield  : fillTriangle front-left slope
//   Rear glass  : fillTriangle rear-right slope
//   Tyre circles: fillCircle r=18 at (cx±56, cy+26), near-black COL_TIRE
//   Hub circles : fillCircle r=9  at (cx±56, cy+26), mid-grey  COL_HUB
//   Windows     : two fillRect panes (front + rear) inset 4 px inside cabin,
//                 split by a 6 px-wide body-coloured centre pillar, COL_GLASS
//   All dimensions scale linearly with sz.

#include "display_anim.h"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static Adafruit_GC9A01A *s_tft = nullptr;

// Pack an RGB triplet into RGB-565. Avoids relying on library colour constants.
static inline uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
    return (uint16_t)(((uint16_t)(r & 0xF8) << 8) |
                      ((uint16_t)(g & 0xFC) << 3) |
                      (b >> 3));
}

// ---------------------------------------------------------------------------
// Fixed detail colors — non-pulsing, drawn on top of the state-color body
// ---------------------------------------------------------------------------

// Glass / windows: light ice-blue — contrasts against all five body colors
// (bright red/orange/yellow in alert bright phases, teal in idle, and dim
// dark-red/blue-grey in dim/stale phases) via luminance contrast.
// RGB (160,200,224) → rgb565 = 0xA65C
static const uint16_t COL_GLASS = 0xA65C;

// Tyre outer: near-black dark grey  RGB (24,24,24) → rgb565 = 0x18C3
static const uint16_t COL_TIRE  = 0x18C3;

// Hub / rim: mid grey  RGB (128,128,128) → rgb565 = 0x8410
static const uint16_t COL_HUB   = 0x8410;

// ---------------------------------------------------------------------------
// Car silhouette helper
// ---------------------------------------------------------------------------

// Draw a detailed side-view car centred at (cx, cy).
// `sz` mirrors the radius used by the former fillCircle call — it scales the car.
// Base design (sz = 90): 176 × 88 px, perfectly centred on (cx, cy).
// Draw order: body (state color) → tyres+hubs (fixed) → windows (fixed glass).
static void draw_car(int16_t cx, int16_t cy, uint8_t sz, uint16_t color) {
    // Integer scale: (v * sz) / 90 — identical to firmware arithmetic everywhere.
#define SC(v)  ((int16_t)((int32_t)(v) * sz / 90))
    int16_t bx  = SC(88);                       // body half-width
    int16_t by_ = SC(12);                       // body top offset:  cy - by_
    int16_t bh  = SC(38);                       // body height
    int16_t br  = SC(8); if (br < 2) br = 2;   // rounded-rect corner radius
    int16_t cdx = SC(44);                       // cabin half-width
    int16_t cdy = SC(44);                       // cabin top offset: cy - cdy
    int16_t ch  = SC(32);                       // cabin height
    int16_t wdx = SC(56);                       // wheel centre x-offset from cx
    int16_t wcy = SC(26);                       // wheel centre y-offset
    int16_t wr  = SC(18); if (wr < 3) wr = 3;  // tyre outer radius
    int16_t whr = SC(9);  if (whr < 2) whr = 2;// hub inner radius (~half of wr)
    // Window insets from cabin rect edges
    int16_t wi_top  = SC(4);                    // inset from cabin top
    int16_t wi_side = SC(4);                    // inset from cabin sides
    int16_t wi_bot  = SC(3);                    // inset from cabin bottom
    int16_t wp      = SC(3);                    // centre-pillar half-width
#undef SC

    // ── Body (state color, pulsing) ──────────────────────────────────────────
    s_tft->fillRoundRect(cx - bx,  cy - by_,  bx * 2, bh, br, color);
    s_tft->fillRect(cx - cdx, cy - cdy, cdx * 2, ch, color);
    s_tft->fillTriangle(cx - bx,  cy - by_,
                        cx - cdx, cy - by_,
                        cx - cdx, cy - cdy, color);
    s_tft->fillTriangle(cx + cdx, cy - by_,
                        cx + bx,  cy - by_,
                        cx + cdx, cy - cdy, color);

    // ── Wheels: dark tyre outer ring + lighter hub (fixed, non-pulsing) ──────
    s_tft->fillCircle(cx - wdx, cy + wcy, wr,  COL_TIRE);
    s_tft->fillCircle(cx + wdx, cy + wcy, wr,  COL_TIRE);
    s_tft->fillCircle(cx - wdx, cy + wcy, whr, COL_HUB);
    s_tft->fillCircle(cx + wdx, cy + wcy, whr, COL_HUB);

    // ── Windows: front + rear panes (fixed glass, non-pulsing) ──────────────
    int16_t wx_l = cx - cdx + wi_side;          // pane left edge
    int16_t wx_r = cx + cdx - wi_side;          // pane right edge
    int16_t wy_t = cy - cdy + wi_top;           // pane top edge
    int16_t wy_b = cy - by_ - wi_bot;           // pane bottom edge
    // Front (left) window pane
    s_tft->fillRect(wx_l,     wy_t,
                    (cx - wp) - wx_l, wy_b - wy_t, COL_GLASS);
    // Rear (right) window pane
    s_tft->fillRect(cx + wp,  wy_t,
                    wx_r - (cx + wp), wy_b - wy_t, COL_GLASS);
}

// ---------------------------------------------------------------------------
// Triangle-wave brightness
// ---------------------------------------------------------------------------

// Triangle-wave brightness: returns 0–255 over `period_ms`, low→high→low.
static uint8_t breathe(uint32_t now, uint32_t period_ms, uint8_t lo, uint8_t hi) {
    uint32_t phase = now % period_ms;
    uint32_t half  = period_ms >> 1;
    uint32_t range = hi - lo;
    if (phase < half) {
        return (uint8_t)(lo + phase * range / half);
    } else {
        return (uint8_t)(hi - (phase - half) * range / half);
    }
}

// ---------------------------------------------------------------------------
// Per-state tick helpers (static, module-private)
// ---------------------------------------------------------------------------

static void tick_idle(uint32_t now, bool fresh) {
    static uint32_t last_ms = 0;

    if (fresh) {
        s_tft->fillScreen(0x0000);  // black
        last_ms = 0;
    }
    if (now - last_ms < 50) return;  // ~20 fps for IDLE
    last_ms = now;

    // Breathing teal (R=0, G=0..160, B=0..200) — overwrite same-size car silhouette.
    uint8_t b = breathe(now, 3000, 30, 200);
    uint16_t color = rgb565(0, (uint8_t)(b * 4 / 5), b);
    draw_car(120, 120, 65, color);
}

static void tick_alert(uint32_t now, uint8_t sev, bool fresh) {
    // Per-severity pulse half-periods (ms) and radii.
    static const uint16_t HALF_MS[4] = {0, 500, 250, 125}; // [sev 1/2/3]
    static const uint8_t  RADII[4]   = {0,  70,  80,  90};

    static uint32_t last_ms = 0;
    static bool     bright  = true;

    if (sev < 1) sev = 1;
    if (sev > 3) sev = 3;

    if (fresh) {
        s_tft->fillScreen(0x0000);
        last_ms = 0;
        bright  = true; // always start with the bright phase for maximum impact
    }

    if (now - last_ms < HALF_MS[sev]) return;
    last_ms = now;

    uint16_t color;
    if (bright) {
        if      (sev == 1) color = rgb565(220,  30,   0);  // vivid red
        else if (sev == 2) color = rgb565(255,  90,   0);  // hot orange-red
        else               color = rgb565(255, 220,   0);  // alarm yellow
    } else {
        if      (sev == 1) color = rgb565( 55,   0,   0);  // dark red
        else if (sev == 2) color = rgb565( 70,  15,   0);  // dark orange
        else               color = rgb565(180,   0,   0);  // medium red (yellow↔red strobe)
    }

    draw_car(120, 120, RADII[sev], color);
    bright = !bright;
}

static void tick_stale(uint32_t now, bool fresh) {
    static uint32_t last_ms = 0;

    if (fresh) {
        s_tft->fillScreen(0x0000);
        last_ms = 0;
    }
    if (now - last_ms < 200) return;  // ~5 fps for STALE
    last_ms = now;

    // Very dim blue-grey: R=b/4, G=b/4, B=b — max brightness ~55.
    uint8_t b = breathe(now, 4000, 12, 55);
    uint16_t color = rgb565((uint8_t)(b / 4), (uint8_t)(b / 4), b);
    draw_car(120, 120, 40, color);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

namespace DisplayAnim {

void init(Adafruit_GC9A01A &tft) {
    s_tft = &tft;
}

void tick() {
    if (!s_tft) return;

    static DisplayState prev_state = (DisplayState)0xFF;
    static uint8_t      prev_sev   = 0xFF;

    uint32_t     now   = millis();
    DisplayState state = DisplayFSM::get_state();
    uint8_t      sev   = DisplayFSM::get_severity();

    bool fresh = (state != prev_state || sev != prev_sev);
    if (fresh) {
        prev_state = state;
        prev_sev   = sev;
    }

    switch (state) {
        case DisplayState::IDLE:  tick_idle(now, fresh);        break;
        case DisplayState::ALERT: tick_alert(now, sev, fresh);  break;
        case DisplayState::STALE: tick_stale(now, fresh);       break;
    }
}

} // namespace DisplayAnim
