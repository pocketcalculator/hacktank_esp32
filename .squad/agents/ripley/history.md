# Ripley — History

## Project Context (seed)

- **Project:** hacktank_esp32 — a street traffic monitor.
- **Requested by:** Paul Sczurek
- **Goal:** A PC-side command runs every few minutes, checks for traffic near Paul's location, decides if traffic is bad, and signals the ESP32 to animate.
- **Open decisions:**
  - Transport to the device — USB serial vs. Wi-Fi/HTTP (Dallas leads this call).
  - Traffic data source — which maps/traffic provider/API to use, and Paul's location input.
- **Scheduling:** On Windows, the "every few minutes" loop is likely Task Scheduler or a small daemon loop.

## Learnings

_(none yet)_


## 2026-06-23T00:20:41-04:00 — Serial contract summary

Dallas locked v1 transport as USB serial at 115200 baud, LF-terminated ASCII, max 32 bytes per line. PC sends `PING` every 60 seconds plus `TRAFFIC BAD [1-3]` or `TRAFFIC OK` from traffic checks. Device emits `READY`, `PONG`, `ACK BAD <sev>`, `ACK OK`, and optional `LOG ...` lines. On startup, wait up to 5 seconds for `READY`; if absent, send `PING` and proceed on `PONG`. Implement `pc/traffic_monitor.py` with serial connection, heartbeat, configurable traffic polling, CLI/config, and a `--test bad|clear` path for manual signal injection.
2026-06-23T00:20:41-04:00 — v1 implemented & reviewed: firmware, PC monitor, static verification, and RAI review complete; hardware display/serial sign-off remains.
