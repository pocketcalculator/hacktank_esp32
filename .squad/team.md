# Squad Team

> hacktank_esp32

## Coordinator

| Name | Role | Notes |
|------|------|-------|
| Squad | Coordinator | Routes work, enforces handoffs and reviewer gates. |

## Members

| Name | Role | Charter | Status |
|------|------|---------|--------|
| Dallas | Lead | .squad/agents/dallas/charter.md | active |
| Parker | Firmware Dev | .squad/agents/parker/charter.md | active |
| Ripley | Integration Dev | .squad/agents/ripley/charter.md | active |
| Ash | Tester | .squad/agents/ash/charter.md | active |
| Scribe | Session Logger | .squad/agents/scribe/charter.md | active |
| Ralph | Work Monitor | .squad/agents/ralph/charter.md | active |
| Rai | RAI Reviewer | .squad/agents/Rai/charter.md | active |

## Project Context

- **Project:** hacktank_esp32 — ESP32-S3 street traffic monitor
- **Lead contact:** Paul Sczurek
- **Created:** 2026-06-23
- **Hardware:** ESP32-S3-DevKitC-1 (PlatformIO, Arduino framework), GC9A01A 240×240 round SPI LCD
- **Goal:** PC command checks traffic near Paul's location every few minutes; when traffic is bad, the ESP32 displays an attention-grabbing animation. Otherwise it shows a calm idle state.
- **Open decision:** PC↔ESP32 transport — USB serial vs. Wi-Fi/HTTP.
