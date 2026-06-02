---
title: initial_esp32_project
description: PlatformIO Arduino project for the Waveshare ESP32-S3-LCD-1.28 board with working LCD bring-up and upload workflow
author: Paul Sczurek and Copilot
ms.date: 2026-06-02
ms.topic: how-to
keywords:
    - esp32-s3
    - platformio
    - waveshare
    - gc9a01
    - arduino
estimated_reading_time: 10
---

## Overview

This project targets the Waveshare ESP32-S3-LCD-1.28 board using PlatformIO + Arduino.

Current known-good state:

* Build and upload work over USB-UART (CH343 bridge)
* LCD initializes and renders text on the onboard GC9A01 display
* Serial heartbeat confirms the app is running continuously

## Hardware Target

* Board: Waveshare ESP32-S3-LCD-1.28
* SoC variant: ESP32-S3R2 (QSPI PSRAM)
* USB interface: CH343 USB-to-UART bridge (not native USB CDC for this workflow)

See [HARDWARE.md](HARDWARE.md) for full pin mapping and board notes.

## Key Files and Why They Matter

### [platformio.ini](platformio.ini)

This file defines the entire PlatformIO build/upload environment.

Important settings in this project:

* `board = esp32-s3-devkitc-1`
* `framework = arduino`
* `monitor_speed = 115200`
* `upload_speed = 921600`
* `board_build.flash_mode = qio`
* `board_build.flash_size = 16MB`
* `board_build.arduino.memory_type = qio_qspi`
* `build_flags` disable USB CDC-on-boot and enable PSRAM macros
* `lib_deps` includes `adafruit/Adafruit GC9A01A`

Why this matters:

* The board/memory settings must match the R2 hardware, or boot/runtime can fail.
* Upload/monitor speed and USB mode choices are tuned for CH343 UART workflow.

### [src/main.cpp](src/main.cpp)

This is the firmware entry point.

Current behavior:

* Initializes Serial at 115200
* Drives two candidate backlight pins high (`GPIO40` and `GPIO2`) for robustness
* Initializes GC9A01 over SPI with these values:
    * DC = GPIO8
    * CS = GPIO9
    * SCK = GPIO10
    * MOSI = GPIO11
    * RST = GPIO12
* Draws centered text `Hi, Paul!`
* Prints an alive heartbeat every 2 seconds

Why this matters:

* It is a minimal, readable baseline proving upload + LCD draw + runtime loop.

### [HARDWARE.md](HARDWARE.md)

This is the board knowledge file used during bring-up. It contains:

* Pin maps
* flash/PSRAM guidance
* USB/UART notes
* boot/upload troubleshooting

Why this matters:

* Board variants differ. This document avoids incorrect assumptions.

## What We Changed to Make It Work

High-level history of the key edits:

1. Corrected PlatformIO environment and memory settings to match ESP32-S3R2 board requirements.
2. Standardized upload/monitor speeds and USB mode flags for CH343 serial flashing.
3. Tested multiple display bring-up paths and kept the stable one in this project:
     * Adafruit GC9A01A driver
     * explicit SPI and control pin mapping
4. Added and used serial heartbeat logs to separate display visibility issues from firmware crashes.
5. Validated hardware by flashing Waveshare factory image, then restored project firmware.

## Build and Upload Commands (Windows PowerShell)

Run these from the project folder.

### Option A: Full executable path

```powershell
Set-Location "C:\Users\paulsczurek\OneDrive - Microsoft\Documents\PlatformIO\Projects\initial_esp32_project"
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -t upload --upload-port COM3
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -b 115200 -p COM3
```

### Option B: Short `pio` command (after profile helper)

```powershell
pio run
pio run -t upload --upload-port COM3
pio device monitor -b 115200 -p COM3
```

### Important typo to avoid

Wrong:

```powershell
"$env:USERPROFILE.platformio\penv\Scripts\platformio.exe"
```

Right:

```powershell
"$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
```

The missing backslash before `.platformio` causes the command-not-found error.

## Troubleshooting

### COM port busy or access denied

Symptom:

* Upload or monitor fails on `COM3` with access denied

Fix:

1. Close all monitor sessions using COM3.
2. Re-run upload command.
3. Re-open monitor.

### `pio` not recognized

Use the full executable path, or define this helper in your PowerShell profile:

```powershell
function pio { & "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" @args }
```

Then open a new terminal tab.

### Display dark

1. Verify serial heartbeat still prints.
2. If firmware is alive but display is dark, test with a simple color-fill diagnostic.
3. If needed, flash factory image to confirm hardware path:
    * Download from the Waveshare wiki firmware section for ESP32-S3-LCD-1.28

## Publish to a New GitHub Repo

Use these commands to publish your existing local `main` branch:

```powershell
Set-Location "C:\Users\paulsczurek\OneDrive - Microsoft\Documents\PlatformIO\Projects\initial_esp32_project"
git remote add origin https://github.com/<your-username>/<new-repo>.git
git push -u origin main
```

Replace `<your-username>` and `<new-repo>` with your repository values.

## Notes About Large Files

This repository intentionally excludes large vendor demo bundles.

If you need the full vendor examples later, download them from Waveshare and keep them outside this repository.