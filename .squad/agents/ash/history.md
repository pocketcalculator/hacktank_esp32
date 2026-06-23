# Ash — History

## Project Context (seed)

- **Project:** hacktank_esp32 — a street traffic monitor.
- **Requested by:** Paul Sczurek
- **Goal:** Validate that a "traffic bad" signal from the PC reliably triggers the ESP32 animation, and that the idle state holds otherwise.
- **Key edge cases to cover:** traffic API down or rate-limited, no/ambiguous traffic data, device unplugged, malformed or repeated signals, transport reconnect.
- **Testability note:** push for a way to inject a fake signal so the device path is verifiable without live traffic.

## Learnings

_(none yet)_
2026-06-23T00:20:41-04:00 — v1 implemented & reviewed: firmware, PC monitor, static verification, and RAI review complete; hardware display/serial sign-off remains.
