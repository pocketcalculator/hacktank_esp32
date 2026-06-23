// display_anim.cpp — Static state renderer for the 240×240 GC9A01A round display.
//
// DisplayAnim::tick() may be called every loop(), but it only renders when the
// displayed state or alert severity changes. Otherwise it leaves existing pixels
// untouched to avoid visible redraw flicker.
//
// State summary:
//   IDLE  — static teal car silhouette (sz=115).
//   ALERT — static high-visibility car; size grows with severity (sz 109/112/115).
//   STALE — static dim blue-grey car silhouette (sz=115).
//
// Shape: detailed side-view car (draw_car helper). Draw order per frame:
//   body (state color) → wheels (fixed dark tyre + mid-grey hub) → windows (fixed glass)
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

// Glass / windows: light ice-blue — contrasts against the alert colors, teal
// idle body, and dim stale body via luminance contrast.
// RGB (160,200,224) → rgb565 = 0xA65C
static const uint16_t COL_GLASS = 0xA65C;

// Tyre outer: near-black dark grey  RGB (24,24,24) → rgb565 = 0x18C3
static const uint16_t COL_TIRE  = 0x18C3;

// Hub / rim: mid grey  RGB (128,128,128) → rgb565 = 0x8410
static const uint16_t COL_HUB   = 0x8410;

static const int16_t DISPLAY_CX = 120;
static const int16_t DISPLAY_CY = 120;
static const uint8_t CAR_SZ_FULL_WIDTH = 115;  // 224 px wide: x=8..232 on a 240 px panel

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

    // ── Body (state color) ───────────────────────────────────────────────────
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
// Per-state render helpers (static, module-private)
// ---------------------------------------------------------------------------

static void render_idle() {
    uint16_t color = rgb565(0, 160, 200);
    draw_car(DISPLAY_CX, DISPLAY_CY, CAR_SZ_FULL_WIDTH, color);
}

static void render_alert(uint8_t sev) {
    static const uint8_t RADII[4] = {0, 109, 112, 115};

    if (sev < 1) sev = 1;
    if (sev > 3) sev = 3;

    uint16_t color;
    if      (sev == 1) color = rgb565(220,  30,   0);  // vivid red
    else if (sev == 2) color = rgb565(255,  90,   0);  // hot orange-red
    else               color = rgb565(255, 180,   0);  // steady amber

    draw_car(DISPLAY_CX, DISPLAY_CY, RADII[sev], color);
}

static void render_stale() {
    uint16_t color = rgb565(13, 13, 55);
    draw_car(DISPLAY_CX, DISPLAY_CY, CAR_SZ_FULL_WIDTH, color);
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

    DisplayState state = DisplayFSM::get_state();
    uint8_t      sev   = DisplayFSM::get_severity();

    if (state == prev_state && sev == prev_sev) return;

    prev_state = state;
    prev_sev   = sev;

    s_tft->fillScreen(0x0000);

    switch (state) {
        case DisplayState::IDLE:  render_idle();        break;
        case DisplayState::ALERT: render_alert(sev);    break;
        case DisplayState::STALE: render_stale();       break;
    }
}

} // namespace DisplayAnim
