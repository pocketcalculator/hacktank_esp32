# Parker — History

## Project Context (seed)

- **Project:** hacktank_esp32 — a street traffic monitor.
- **Requested by:** Paul Sczurek
- **Hardware:** ESP32-S3-DevKitC-1 (PlatformIO, Arduino framework), GC9A01A 240×240 round SPI LCD.
- **Pins (from src/main.cpp):** BL=40/2, DC=8, CS=9, SCK=10, MOSI=11, RST=12. Driver `Adafruit_GC9A01A`, SPI at 40 MHz, rotation 0, screen 240×240.
- **Goal:** Device shows a calm idle state; on a "traffic bad" signal it plays an attention-grabbing animation.
- **Current state:** `src/main.cpp` renders a static "Hi, Paul!" message via Adafruit_GC9A01A — the base to extend.

## Learnings

_(none yet)_


## 2026-06-23T00:20:41-04:00 — Serial contract summary

Dallas locked v1 transport as USB serial at 115200 baud, LF-terminated ASCII, max 32 bytes per line. PC sends `PING`, `TRAFFIC BAD [1-3]`, or `TRAFFIC OK`; firmware replies `READY`, `PONG`, `ACK BAD <sev>`, or `ACK OK`, with optional `LOG ...` lines. Firmware must implement non-blocking `serial_cmd`, `display_fsm`, and `display_anim` modules. Display states are IDLE, ALERT(severity 1–3), and STALE; no message for 300 seconds forces STALE as the calm fail-safe. `loop()` must avoid blocking delays and animation work must be non-blocking.
2026-06-23T00:20:41-04:00 — v1 implemented & reviewed: firmware, PC monitor, static verification, and RAI review complete; hardware display/serial sign-off remains.
