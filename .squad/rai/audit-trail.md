# RAI Audit Trail

> Append-only evidence log. Entries are redacted — never contains raw secrets or harmful content.

<!-- Rai appends findings below -->

---

## Review: ESP32 Traffic Monitor feature — 2026-06-23T00:41 EDT

**Reviewer:** Rai  
**Requested by:** Paul Sczurek  
**Verdict:** 🟡 Yellow — ship with noted recommendations (no blockers)

### Files reviewed
- `pc/traffic_monitor.py`, `pc/requirements.txt`, `pc/README.md`
- `src/serial_cmd.h`, `src/serial_cmd.cpp`, `src/display_fsm.h`, `src/display_fsm.cpp`, `src/main.cpp`
- `.gitignore`

### Category results

#### 1. CREDENTIALS / SECRETS — ✅ PASS
- No API key hardcoded anywhere in source or config templates.
- Key loaded exclusively from `TOMTOM_API_KEY` env var or `pc/.traffic_config` (load_api_key(), line 80–95).
- `_masked_key()` redacts all but first 4 chars before any log emission (line 98–103). Auth-failure log uses `_masked_key()`. ✅
- `.gitignore` line 62 explicitly excludes `pc/.traffic_config`. ✅
- README prominently says "Never hardcode the key." ✅

#### 2. PII / PRIVACY — 🟡 Advisory
- **Finding PII-1:** `monitor_loop()` logs `lat=%.5f lon=%.5f` at INFO level on startup (line 369–373). Five decimal places = ~1 m precision. If the user captures logs to a file (e.g., Task Scheduler redirect or syslog), their home coordinates are written in plaintext at high resolution. Low risk for a hobby project but inconsistent with "minimal exposure" principle.
  - *Recommendation (Ripley):* Reduce log precision to 2 decimal places (≈1 km), e.g., `lat=%.2f lon=%.2f`.
- Location is sent only to TomTom Traffic API (expected, by design). Not forwarded anywhere else. ✅

#### 3. INJECTION / INPUT HANDLING — ✅ PASS
- **Firmware serial buffer (serial_cmd.cpp):** Fixed 33-byte buffer with `s_len < 32` guard; overflow flag discards over-long lines cleanly — no overrun possible. `atoi()` result clamped to [1,3] immediately. `snprintf` is size-bounded. ✅
- **PC JSON parsing:** `resp.json()` in try/except ValueError; `.get()` with None checks; `free_flow <= 0` division guard. All paths to "unknown" on malformed/missing data. ✅
- **No shell execution on either side.** ✅

#### 4. CODE-LEVEL SAFETY / ROBUSTNESS — 🟡 Advisory
- **Finding ROB-1:** `send_cmd()` uses `assert len(encoded) <= 32` (line 226) as a runtime length guard. Python assertions are disabled when the interpreter runs with `-O` or `-OO`. Since all callers pass hardcoded string literals this can never trigger in practice, but it's the wrong idiom for a runtime safety check.
  - *Recommendation (Ripley):* Replace with `if len(encoded) > 32: raise ValueError(...)`.
- **millis() rollover (display_fsm.cpp):** `uint32_t` subtraction `millis() - s_last_msg_ms` correctly wraps at 2³² ≈ 49.7 days. ✅

#### 5. HARMFUL CONTENT — N/A (hobby embedded project)
#### 6. BIAS / FAIRNESS — N/A
#### 7. INCLUSIVE LANGUAGE — ✅ No flagged terminology found

### Summary
Two 🟡 advisory items (PII-1, ROB-1). Neither blocks shipping. Original authors (Parker / Ripley) are free to address at discretion. No 🔴 blocking issues detected.
