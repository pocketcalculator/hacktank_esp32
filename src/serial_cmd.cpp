#include "serial_cmd.h"
#include "display_fsm.h"

namespace SerialCmd {

// 32-byte max per Dallas contract (plus null terminator)
static char s_buf[33];
static uint8_t s_len = 0;
static bool s_overflow = false;

static void process_line(const char *line) {
    if (strcmp(line, "PING") == 0) {
        DisplayFSM::on_ping();
        Serial.println("PONG");
        return;
    }
    if (strcmp(line, "TRAFFIC OK") == 0) {
        DisplayFSM::on_ok();
        Serial.println("ACK OK");
        return;
    }
    if (strcmp(line, "TRAFFIC BAD") == 0) {
        DisplayFSM::on_bad(1);
        Serial.println("ACK BAD 1");
        return;
    }
    // "TRAFFIC BAD <N>" — N is one digit after the space
    if (strncmp(line, "TRAFFIC BAD ", 12) == 0) {
        int sev = atoi(line + 12);
        if (sev < 1) sev = 1;
        if (sev > 3) sev = 3;
        DisplayFSM::on_bad((uint8_t)sev);
        char resp[16];
        snprintf(resp, sizeof(resp), "ACK BAD %d", sev);
        Serial.println(resp);
        return;
    }
    // Unknown / partial lines are silently ignored per contract.
}

void tick() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\r') continue;   // tolerate CRLF from some terminals
        if (c == '\n') {
            if (!s_overflow && s_len > 0) {
                s_buf[s_len] = '\0';
                process_line(s_buf);
            }
            s_len = 0;
            s_overflow = false;
        } else {
            if (s_len < 32) {
                s_buf[s_len++] = c;
            } else {
                s_overflow = true; // keep consuming until newline
            }
        }
    }
}

} // namespace SerialCmd
