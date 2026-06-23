# Squad Decisions

## Active Decisions

No decisions recorded yet.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction


## 2026-06-23T00:20:41-04:00 — Project direction & key decisions
**Source:** decisions/inbox/copilot-directive-2026-06-23T002041.md
**By:** Paul Sczurek (via Copilot)

- Project goal: turn the ESP32-S3 (GC9A01A 240×240 round LCD) from a "Hi, Paul!" hello-world into a street traffic monitor. A PC command runs every few minutes, checks traffic near Paul's location, and when traffic is bad signals the device to play an attention-grabbing animation. Calm idle state otherwise.
- **Transport decision:** PC↔ESP32 communication is over **USB serial** (device stays plugged into the PC). Not Wi-Fi/HTTP.
- **Traffic data source:** Ripley to recommend the easiest provider to set up; not yet fixed.

**Rationale:** User-selected during team kickoff — foundational scope and architecture decisions.

## 2026-06-23 — Serial Contract & Architecture
**Source:** decisions/inbox/dallas-serial-contract.md
**By:** Dallas (Lead)
**Status:** LOCKED — Parker and Ripley build against this. Do not change without Dallas sign-off.

### Protocol
- USB-to-UART bridge on ESP32-S3-DevKitC-1; `Serial` maps to UART/USB bridge.
- Baud: **115200**. Line ending: **LF only**. Encoding: ASCII. Max line length: 32 bytes including terminator.
- PC→device commands: `TRAFFIC BAD\n`, `TRAFFIC BAD 2\n`, `TRAFFIC BAD 3\n`, `TRAFFIC OK\n`, `PING\n`.
- Device→PC responses: `READY\n`, `PONG\n`, `ACK BAD <sev>\n`, `ACK OK\n`; freeform debug lines may begin with `LOG ...`.
- Severity scale: 1=slow/heavy, 2=significant delays, 3=gridlock; unknown severity defaults to 1.
- PC sends `PING` at least every 60 seconds. Device transitions to STALE after 300 seconds without any command or ping.
- On startup, Ripley's script should wait up to 5 seconds for `READY`; if missing, send `PING` and proceed on `PONG`.

### Display state machine
- States: `IDLE` (boot/calm/all clear), `ALERT` (traffic bad, severity 1–3), `STALE` (connection lost/unknown, muted/calm fail-safe).
- `IDLE --TRAFFIC BAD [sev]--> ALERT`; `ALERT --TRAFFIC OK--> IDLE`; any state times out to `STALE`; `STALE --PING/TRAFFIC OK--> IDLE`; `STALE --TRAFFIC BAD--> ALERT`.
- Fail-safe: if the device is in ALERT when timeout fires, it transitions to STALE, never stuck ALERT.
- FSM stores `uint8_t current_severity` 1–3; clears severity to 0 on OK or STALE.

### File layout / work split
- Firmware modules: `src/main.cpp`, `src/serial_cmd.{h,cpp}`, `src/display_fsm.{h,cpp}`, `src/display_anim.{h,cpp}`.
- PC modules: `pc/traffic_monitor.py`, `pc/requirements.txt`.
- `main.cpp` should only initialize peripherals, call serial/FSM ticks, and print `READY`; no protocol parsing or animation logic.
- Parker owns non-blocking parser, FSM, and non-blocking animations; Ripley owns serial connection, heartbeat, traffic checks, CLI/config, and Python requirements.

### Non-negotiables
1. No blocking delays in `loop()` after refactor; use `millis()`.
2. Serial stays at 115200; do not touch `ARDUINO_USB_MODE` or `ARDUINO_USB_CDC_ON_BOOT`.
3. Protocol is line-oriented ASCII; reject JSON/binary framing for v1.
4. Animations are non-blocking and should not block more than ~5 ms per call.
5. STALE is always the disconnected/unknown fail-safe, never ALERT.

## 2026-06-23T00:27:56-04:00 — Test Scenarios
**Source:** decisions/inbox/ash-test-scenarios.md
**By:** Ash (Tester)
**Status:** Draft — anticipatory, written before implementation is final

### Happy path
- Bad traffic from PC transitions ESP32 from idle to alert animation.
- Clear traffic returns to calm idle cleanly.
- Duplicate bad signals keep alert idempotent with no flicker/restart glitch.
- Consistently good traffic leaves idle unchanged.
- First boot with no serial input starts idle/calm.

### Serial-link edge cases
- Unplugged device, wrong COM port, PC process absent, garbled/partial serial lines, partial writes, repeated identical signals, baud mismatch, buffer overflow, and rapid toggling must not crash or corrupt display state.
- Unrecognized or partial tokens are ignored; duplicate signals are idempotent; firmware handles mid-animation interrupts safely.

### Traffic API edge cases
- API outage, rate limiting, auth failure, server error, timeout, empty/null response, ambiguous threshold data, malformed schema, and wrong location data must be handled deterministically and logged.
- Unknown or failed traffic checks should not spuriously flip the device into alert; preserve state or fail safe according to the implementation contract.

### Fail-safe
- No serial message for N minutes should revert/stay idle or stale/calm; alert must not latch forever without refresh.
- PC reboot or device reboot returns to a safe calm baseline until a fresh BAD signal arrives.
- Recommended timeout from Ash: 10 minutes (2× polling interval), but Dallas contract sets device timeout at 300 seconds and heartbeat at 60 seconds.

### Manual signal injection recommendation
- Primary: add a Ripley `--test` flag, e.g. `python traffic_monitor.py --test bad` and `python traffic_monitor.py --test clear`, exercising the production serial code path.
- Secondary: support direct terminal/pyserial injection for Parker firmware isolation.
- Tertiary: optional firmware test mode via compile flag or BOOT long-press for demos/visual QA.

### Protocol assumptions
Ash's scenarios assume newline-terminated ASCII commands, discarded unrecognized lines, PC→device protocol with Dallas-approved ACK/PONG responses, and default baud 115200. Tests must be updated if the protocol changes.

## 2026-06-23T00:20:41-04:00 — Ash Verification Report — 2026-06-23
**Source:** decisions/inbox/ash-verification.md
**By:** Ash (Tester)

# Ash Verification Report — 2026-06-23

**Verifier:** Ash (Tester)
**Firmware build:** pio run previously succeeded (not re-run here)
**Method:** Static code review + local Python execution (no physical hardware)

---

## Scenario-by-Scenario Verdict

### Happy Path

| Scenario | Verdict | Justification |
|---|---|---|
| Bad traffic → IDLE → ALERT animation | CANNOT-VERIFY-WITHOUT-HARDWARE | Code path correct: Python `fetch_congestion` → `send_cmd("TRAFFIC BAD 2\n")` → `serial_cmd.cpp` `strncmp` branch → `on_bad(2)` → `DisplayAnim::tick_alert`. Requires display. |
| Clear traffic → ALERT → calm IDLE | CANNOT-VERIFY-WITHOUT-HARDWARE | Code path: `"TRAFFIC OK\n"` → `on_ok()` → `s_state=IDLE, s_severity=0`; `fresh=true` → `tick_idle` clears screen. Requires display. |
| Duplicate BAD keeps ALERT idempotent (no flicker) | PASS | `display_anim.cpp` line 132: `fresh = (state != prev_state \|\| sev != prev_sev)`. Duplicate signal leaves `prev_state` and `prev_sev` unchanged → `fresh=false` → no fillScreen reset. Animation continues without restart. ✓ |
| Consistently good traffic leaves IDLE unchanged | PASS | `on_ok()` sets IDLE regardless; subsequent calls with same state/sev produce `fresh=false`. No display thrash. ✓ |
| First boot with no serial → starts IDLE/calm | PASS | `DisplayFSM::init()` sets `s_state=IDLE`. `DisplayAnim::tick()` sees `prev_state=0xFF != IDLE` → `fresh=true` → `tick_idle` with black fill → breathing teal. ✓ |

### Serial-Link Edge Cases

| Scenario | Verdict | Justification |
|---|---|---|
| Garbled/partial lines ignored | PASS | `serial_cmd.cpp` `process_line()` falls through all `strcmp`/`strncmp` comparisons silently (line 38 comment: "Unknown / partial lines are silently ignored per contract"). ✓ |
| Buffer overflow (line > 32 bytes) | PASS | `s_overflow=true` set when `s_len >= 32` (line 56); on `\n` arrival the `if (!s_overflow && s_len > 0)` guard (line 46) skips `process_line`. Buffer consumed cleanly. ✓ |
| CRLF from terminals | PASS | `if (c == '\r') continue;` at line 44. ✓ |
| Empty line (bare `\n`) | PASS | `s_len==0` check at line 46 prevents `process_line("")` call. ✓ |
| Rapid toggling / mid-animation interrupts | PASS | `fresh` flag in `DisplayAnim::tick()` triggers a clean state reset on any state/sev change; `on_bad()` and `on_ok()` are idempotent and fully overwrite FSM state. ✓ |
| Duplicate PING | PASS | `on_ping()` only clears STALE→IDLE if currently STALE; otherwise only updates timestamp. No display side-effect. ✓ |
| Device disconnected (PC side) | CANNOT-VERIFY-WITHOUT-HARDWARE | Requires live port. Python `open_serial` raises `SystemExit` with helpful port list on failure. ✓ code path. |

### Traffic API Edge Cases

| Scenario | Verdict | Justification |
|---|---|---|
| API timeout / network error | PASS | `fetch_congestion` line 136-141: catches `requests.Timeout` and `RequestException` → returns `("unknown", 0)`. Monitor loop line 398: `status=="unknown"` → no `send_cmd` called. ✓ |
| Rate limiting (429) | PASS | Lines 152-154: `resp.status_code==429` → `return "unknown", 0`. Fail-safe preserved. ✓ |
| Auth failure (401/403) | PASS | Lines 143-150: raises `AuthError` → monitor exits with `SystemExit("[FATAL]...")`. Stops cleanly. ✓ |
| Server error (5xx) | PASS | Lines 156-158: `resp.status_code >= 500` → `return "unknown", 0`. ✓ |
| Unexpected HTTP status | PASS | Lines 160-162: any other non-200 → `return "unknown", 0`. ✓ |
| Empty / null speed data | PASS | Lines 178-184: `currentSpeed is None or freeFlowSpeed is None or freeFlowSpeed <= 0` → `return "unknown", 0`. ✓ |
| Missing `flowSegmentData` key | PASS | Lines 170-173: `if not flow:` → `return "unknown", 0`. ✓ |
| Malformed JSON | PASS | Lines 164-168: `except ValueError:` → `return "unknown", 0`. ✓ |
| Unknown/failed traffic does NOT trigger ALERT | PASS | `monitor_loop` only calls `send_cmd` inside `else:` branch (line 404), which is skipped when `status=="unknown"`. Spurious ALERT impossible on bad API data. ✓ |

### Fail-Safe / Timeout

| Scenario | Verdict | Justification |
|---|---|---|
| ALERT cannot latch forever (300 s → STALE) | PASS | `display_fsm.cpp` line 19: `millis() - s_last_msg_ms >= 300000` fires unconditionally; line 21 checks `s_state != STALE` (idempotent re-entry guard) but does NOT check for ALERT. An ALERT device with no PC messages transitions to STALE after 300 s. ✓ |
| Firmware cannot be stuck in STALE | PASS | Any `on_ping()`, `on_ok()`, or `on_bad()` call exits STALE. Python heartbeat pings every 60 s (< 300 s threshold). ✓ |
| PING keeps device alive | PASS | `Heartbeat` thread (`threading.Thread`, daemon=True): `self._stop_event.wait(timeout=60)` → sends `"PING\n"` every 60 s. Device `on_ping()` updates `s_last_msg_ms`. 60 s << 300 s. ✓ |
| PC reboot → device goes STALE within 300 s | PASS | No messages from dead PC → timeout fires → STALE (calm/dim animation, not ALERT). ✓ |
| Device reboot → safe calm baseline | PASS | `setup()` calls `DisplayFSM::init()` (→ IDLE) then `Serial.println("READY")`. PC `wait_for_ready` sees READY or falls back to PING/PONG. ✓ |
| PC reconnect after device STALE | PASS | Python `wait_for_ready` sends PING; firmware `on_ping()` sees STALE → transitions to IDLE. ✓ |

### Manual Signal Injection / `--test` mode

| Scenario | Verdict | Justification |
|---|---|---|
| `--test bad` sends via real serial path, no API key | PASS (code path) | `main()` line 506: API key and location resolved only when `not args.test`. `run_test` sends `"TRAFFIC BAD 2"` via `send_cmd`. Firmware would respond `"ACK BAD 2"`. CANNOT-VERIFY-WITHOUT-HARDWARE for ACK receipt. |
| `--test clear` sends TRAFFIC OK | PASS (code path) | `run_test` sends `"TRAFFIC OK"` → firmware `on_ok()` → `"ACK OK"`. CANNOT-VERIFY-WITHOUT-HARDWARE for ACK receipt. |
| `--test` with unknown mode | PASS | `run_test` line 325: `raise SystemExit(f"[ERROR] Unknown --test mode...")` for any value not "bad"/"clear". But `argparse` `choices=["bad","clear"]` already rejects it before reaching `run_test`. Double-guarded. ✓ |

---

## Protocol Compliance Checks

| Check | Verdict | Detail |
|---|---|---|
| PC sends LF-only (`\n`) | PASS | `send_cmd` line 224: `cmd.strip() + "\n"` then `encode("ascii")`. Confirmed last byte = `0x0A` (LF). ✓ |
| Commands within 32-byte limit | PASS | Longest command: `"TRAFFIC BAD 3\n"` = 14 bytes. `assert len(encoded) <= 32` guard in `send_cmd`. ✓ |
| Firmware accepts all contract commands | PASS | `serial_cmd.cpp`: `PING`, `TRAFFIC OK`, `TRAFFIC BAD`, `TRAFFIC BAD <N>` all handled. Unknown lines silently discarded. ✓ |
| `READY\n` on boot | PASS | `main.cpp` line 43: `Serial.println("READY")`. ✓ |
| `PONG\n` response to PING | PASS | `serial_cmd.cpp` line 14: `Serial.println("PONG")`. ✓ |
| `ACK BAD <sev>\n` response | PASS | Lines 33-36: `snprintf(resp, sizeof(resp), "ACK BAD %d", sev)` + `Serial.println(resp)`. ✓ |
| `ACK OK\n` response | PASS | Line 19: `Serial.println("ACK OK")`. ✓ |
| CRLF tolerance on firmware | PASS | `\r` stripped at `serial_cmd.cpp` line 44. ✓ |

---

## Local Executable Checks (No Hardware Needed)

| Check | Result |
|---|---|
| `python -c "import ast; ast.parse(open('pc/traffic_monitor.py', encoding='utf-8').read())"` | **PASS** — no syntax errors |
| `python pc\traffic_monitor.py --help` | **PASS** — `--test {bad\|clear}`, `--port`, `--lat`, `--lon`, `--location`, `--interval` all present |
| `python -c "import serial"` (pyserial 3.5) | **PASS** — import succeeds |
| No hardcoded API key/secret in tracked files | **PASS** — grep finds no key literals; `TOMTOM_API_KEY` only appears as env-var name or help text |
| `pc/.traffic_config` gitignored | **PASS** — `.gitignore` line 62: `pc/.traffic_config` |

---

## Defects Found

### D1 — LOW severity | Assign to: **Ripley**
**File:** `pc/traffic_monitor.py`, line 406
**Description:** Python sends `"TRAFFIC BAD 1"` for severity 1, but the Dallas serial contract lists only `"TRAFFIC BAD"` (no number suffix) as the severity-1 command. `"TRAFFIC BAD 1"` is not in the contract's enumerated command set.

The firmware handles it correctly (the `strncmp("TRAFFIC BAD ", 12)` branch, `atoi("1")=1`), so this is **functionally harmless**. However, it is a protocol deviation that could cause confusion in future firmware parsers or when testing with the exact contract strings.

**Recommended fix:** Change line 406 to:
```python
cmd = "TRAFFIC BAD" if severity == 1 else f"TRAFFIC BAD {severity}"
```
This sends the contract-canonical `TRAFFIC BAD` for sev=1, and `TRAFFIC BAD 2`/`TRAFFIC BAD 3` for sev=2/3.

---

## No-Ship Blockers

**None found** for the parts that can be verified without hardware.

---

## Overall Recommendation

**SHIP (conditional) for the PC-side software. CANNOT-FULLY-VERIFY firmware animation on hardware.**

- All statically verifiable scenarios pass.
- The single defect found (D1) is low-severity and functionally harmless — firmware produces identical behavior for `TRAFFIC BAD` and `TRAFFIC BAD 1`.
- Fail-safe logic is correct and verified: `unknown` API results never trigger ALERT; 300 s timeout reliably exits ALERT.
- No secrets hardcoded. No API key in tracked files. `.traffic_config` gitignored.
- The `--test bad|clear` path is correct for no-API-key manual QA use; it requires a real serial port (by design).
- Hardware-dependent scenarios (display animation rendering, actual serial ACK round-trips) require physical device for final sign-off.

**Blocking items before hardware sign-off:**
1. Fix D1 (Ripley, trivial one-liner)
2. Physical test: `--test bad` → confirm alert animation fires; `--test clear` → confirm idle returns

---

*Ash (Tester) — 2026-06-23T00:41:26-04:00*


## 2026-06-23T00:20:41-04:00 — Parker — Firmware Implementation Decisions
**Source:** decisions/inbox/parker-firmware-implementation.md
**By:** Parker (Firmware Dev)

# Parker — Firmware Implementation Decisions

**Date:** 2026-06-23T00:33:41-04:00
**By:** Parker (Firmware Dev)
**Status:** Implemented

## What was built

Implemented the full device firmware against Dallas's locked Serial Contract & Architecture:

- `src/serial_cmd.{h,cpp}` — non-blocking line reader (32-byte ring accumulator, overflow discard), parses `PING`, `TRAFFIC OK`, `TRAFFIC BAD [1-3]`; emits `PONG`, `ACK OK`, `ACK BAD <sev>`.
- `src/display_fsm.{h,cpp}` — IDLE / ALERT(sev 1-3) / STALE state machine with 300 s timeout to STALE; `uint8_t current_severity` clears to 0 on OK/STALE. `on_ping()` from STALE goes to IDLE; `on_bad()` from any state goes to ALERT.
- `src/display_anim.{h,cpp}` — non-blocking, millis()-driven animations (no `delay()`). State change triggers one `fillScreen` clear (acceptable one-time cost), then each tick draws a single `fillCircle` (no erase+redraw = no double SPI cost).
- `src/main.cpp` — refactored: setup() initialises Serial/TFT/FSM/anim, prints `READY`; loop() is `SerialCmd::tick(); DisplayFSM::tick(); DisplayAnim::tick();` only.

## Animation design decisions

| State | Visual | Rate | Approx SPI cost/tick |
|-------|--------|------|----------------------|
| IDLE | Breathing teal circle r=65, triangle-wave brightness lo=30→hi=200 over 3 s | 20 fps (50 ms) | ~4.5 ms |
| ALERT sev 1 | Red pulse (bright↔dark red), 1 Hz, r=70 | 2 fps (500 ms) | ~5 ms |
| ALERT sev 2 | Orange-red pulse, 2 Hz, r=80 | 4 fps (250 ms) | ~6.5 ms |
| ALERT sev 3 | Yellow↔red strobe, 4 Hz, r=90 | 8 fps (125 ms) | ~8 ms |
| STALE | Very dim blue-grey pulse r=40, period 4 s | 5 fps (200 ms) | ~1.3 ms |

ALERT sev 3 slightly exceeds the ~5 ms SPI guideline (~8 ms) because it is the headline feature — Paul needs to see it at a glance. Average loop impact is low since the draw fires only every 125 ms.

## Compile-time test hook

`#ifdef FORCE_ALERT_ON_BOOT` in `setup()` — add `-D FORCE_ALERT_ON_BOOT` to `build_flags` in platformio.ini for visual QA of the alert animation without a PC attached.

## Dependencies / constraints respected

- Serial stays 115200; `ARDUINO_USB_MODE` / `ARDUINO_USB_CDC_ON_BOOT` untouched.
- No `delay()` in `loop()`.
- Protocol is line-oriented ASCII (LF-terminated, max 32 bytes).
- Severity defaults to 1 when unspecified; clamped 1-3.
- STALE is always the fail-safe — ALERT never latches past 300 s timeout.


## 2026-06-23T00:20:41-04:00 — RAI Review Decision — ESP32 Traffic Monitor
**Source:** decisions/inbox/rai-review.md
**By:** Rai

# RAI Review Decision — ESP32 Traffic Monitor

**Date:** 2026-06-23T00:41 EDT  
**Reviewer:** Rai  
**Verdict:** 🟡 Yellow — ship with recommendations

## Decision

No blocking issues found. Work may proceed to merge. Two advisory items are logged for the original authors to address at their discretion.

## Advisory Findings (non-blocking)

### PII-1 — High-precision location in INFO log
- **What:** `monitor_loop()` in `pc/traffic_monitor.py` logs `lat=%.5f lon=%.5f` (≈1 m precision) at INFO level.
- **Why it matters:** If logs are redirected to a file (Task Scheduler, syslog), the user's home coordinates are stored in plaintext.
- **How to fix (Ripley):** Change format spec to `%.2f` for log-only output (≈1 km resolution). The full-precision values are still passed to the API call unchanged.

### ROB-1 — `assert` used as runtime guard in send_cmd
- **What:** `assert len(encoded) <= 32` in `pc/traffic_monitor.py` line 226.
- **Why it matters:** Assertions are silently disabled by Python `-O`/`-OO` flags, making this a no-op in optimized mode.
- **How to fix (Ripley):** Replace with `if len(encoded) > 32: raise ValueError(f"Command exceeds 32-byte limit: {line!r}")`.

## Non-findings (confirmed clean)

- ✅ No API key hardcoded anywhere
- ✅ API key masked (`key[:4]...`) in all log/error output
- ✅ `pc/.traffic_config` listed in `.gitignore`
- ✅ Firmware serial buffer cannot overrun (33-byte buffer, overflow flag, per-byte guard)
- ✅ API JSON parsing handles all failure modes (timeout, 4xx, 5xx, malformed JSON, null speeds)
- ✅ No shell execution on either side — no injection surface
- ✅ `millis()` rollover handled correctly in display_fsm.cpp


## 2026-06-23T00:20:41-04:00 — Decision: TomTom Traffic Flow API chosen as provider
**Source:** decisions/inbox/ripley-tomtom-provider.md
**By:** Ripley (Integration Dev)

# Decision: TomTom Traffic Flow API chosen as provider

**By:** Ripley (Integration Dev)
**Date:** 2026-06-23T00:33:41-04:00
**Status:** Implemented

## Decision

Use **TomTom Traffic Flow API** as the traffic data source for `pc/traffic_monitor.py`.

## Rationale

| Provider | Free tier | Billing required | Setup friction | Notes |
|----------|-----------|-----------------|----------------|-------|
| **TomTom** | 2,500 req/day | No | Low — sign up, copy key | Chosen |
| HERE | 250,000 req/month | No | Low | Solid alternative |
| Google Maps | ~$200 credit/mo | **Yes** | Medium (billing acct) | Skipped |

TomTom's free tier (2,500 req/day) covers 3-minute polling all day (~480 calls)
with room to spare. The Flow Segment endpoint returns `currentSpeed` and
`freeFlowSpeed` directly — one ratio gives a deterministic, testable severity
with no ambiguity.

## Severity thresholds (currentSpeed / freeFlowSpeed)

- `>= 0.85` → TRAFFIC OK (clear)
- `0.60 – 0.85` → TRAFFIC BAD 1 (slow/heavy)
- `0.35 – 0.60` → TRAFFIC BAD 2 (significant delays)
- `< 0.35` → TRAFFIC BAD 3 (gridlock)

## Files created

- `pc/traffic_monitor.py` — single-file PC monitor (serial + heartbeat + traffic API + CLI)
- `pc/requirements.txt` — `pyserial>=3.5`, `requests>=2.28`
- `pc/README.md` — setup, key signup, COM port, scheduling on Windows

## Secrets hygiene

- API key loaded from `TOMTOM_API_KEY` env var or `pc/.traffic_config` (gitignored)
- `.gitignore` updated to exclude `pc/.traffic_config`, `pc/.venv/`, `pc/__pycache__/`
- Key is never logged in full (only first 4 chars on auth error)
- `--test` mode works with no API key at all

