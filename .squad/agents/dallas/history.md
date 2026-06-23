# Dallas — History

## Project Context (seed)

- **Project:** hacktank_esp32 — a street traffic monitor.
- **Requested by:** Paul Sczurek
- **Hardware:** ESP32-S3-DevKitC-1 (PlatformIO, Arduino framework), GC9A01A 240×240 round SPI LCD.
- **Goal:** A PC-side command runs every few minutes, checks for traffic near Paul's location; when traffic is bad it signals the ESP32, which plays an attention-grabbing animation on the LCD. Otherwise the device shows a calm/idle state.
- **Current state:** `src/main.cpp` renders a static "Hi, Paul!" message — the starting point to evolve into the monitor.
- **Open decision:** PC↔ESP32 transport — USB serial vs. Wi-Fi/HTTP. Drives firmware design.

## Learnings

_(none yet)_
2026-06-23T00:20:41-04:00 — v1 implemented & reviewed: firmware, PC monitor, static verification, and RAI review complete; hardware display/serial sign-off remains.
