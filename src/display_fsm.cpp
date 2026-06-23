#include "display_fsm.h"
#include <Arduino.h>

namespace DisplayFSM {

static DisplayState s_state    = DisplayState::IDLE;
static uint8_t      s_severity = 0;
static uint32_t     s_last_msg_ms = 0;

static constexpr uint32_t STALE_TIMEOUT_MS = 300000UL; // 300 s per contract

void init() {
    s_state       = DisplayState::IDLE;
    s_severity    = 0;
    s_last_msg_ms = millis();
}

void tick() {
    if (millis() - s_last_msg_ms >= STALE_TIMEOUT_MS) {
        if (s_state != DisplayState::STALE) {
            Serial.println("LOG FSM timeout -> STALE");
            s_state    = DisplayState::STALE;
            s_severity = 0;
        }
    }
}

DisplayState get_state()    { return s_state; }
uint8_t      get_severity() { return s_severity; }

void on_bad(uint8_t sev) {
    if (sev < 1) sev = 1;
    if (sev > 3) sev = 3;
    s_state       = DisplayState::ALERT;
    s_severity    = sev;
    s_last_msg_ms = millis();
}

void on_ok() {
    s_state       = DisplayState::IDLE;
    s_severity    = 0;
    s_last_msg_ms = millis();
}

void on_ping() {
    if (s_state == DisplayState::STALE) {
        s_state    = DisplayState::IDLE;
        s_severity = 0;
    }
    s_last_msg_ms = millis();
}

} // namespace DisplayFSM
