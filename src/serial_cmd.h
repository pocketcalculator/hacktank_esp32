#pragma once
#include <Arduino.h>

namespace SerialCmd {
    // Call once per loop(). Reads available serial bytes, parses complete lines,
    // drives DisplayFSM transitions, and emits ACK/PONG responses.
    void tick();
}
