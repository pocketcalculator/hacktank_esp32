#pragma once
#include <Adafruit_GC9A01A.h>
#include "display_fsm.h"

namespace DisplayAnim {
    // Pass the already-initialized TFT instance from main.
    void init(Adafruit_GC9A01A &tft);

    // Call once per loop(). Non-blocking; drives animation from millis().
    void tick();
}
