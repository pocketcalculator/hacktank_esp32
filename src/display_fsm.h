#pragma once
#include <stdint.h>

enum class DisplayState : uint8_t {
    IDLE  = 0,
    ALERT = 1,
    STALE = 2,
};

namespace DisplayFSM {
    void init();

    // Call once per loop(). Handles the 300 s timeout -> STALE transition.
    void tick();

    DisplayState get_state();
    uint8_t      get_severity(); // 1-3 when ALERT, 0 otherwise

    // Called by SerialCmd after line parse.
    void on_bad(uint8_t sev);   // clamps sev to [1,3]
    void on_ok();
    void on_ping();
}
