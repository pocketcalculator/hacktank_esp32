#!/usr/bin/env python3
"""
traffic_monitor.py — PC-side traffic monitor for the ESP32-S3 street traffic display.

Traffic provider: TomTom Traffic Flow API
  Why TomTom:
    - Generous free tier: 2,500 requests/day — covers 3-minute polling (480 calls/day)
      with plenty of headroom. No billing / credit-card required.
    - Simple REST endpoint: returns currentSpeed + freeFlowSpeed per road segment.
      One deterministic ratio threshold; no fiddly incident parsing needed.
    - HERE is a solid alternative but TomTom's free tier sign-up is faster.
    - Google Maps Platform requires a billing account even for free-tier use — skipped.

  Get a free API key:
    1. Go to https://developer.tomtom.com/
    2. Click "Sign up free" → create account
    3. Dashboard → My Apps → + New App → check "Traffic" → Save
    4. Copy the API key shown
    5. Set env var TOMTOM_API_KEY=<key>  (or put it in pc/.traffic_config — gitignored)

Serial contract: Dallas v1 (LOCKED — do not change without Dallas sign-off)
  Baud:       115200
  Line ending: LF only (\\n), ASCII, max 32 bytes/line
  PC→device:  PING, TRAFFIC BAD, TRAFFIC BAD 2, TRAFFIC BAD 3, TRAFFIC OK
  Device→PC:  READY, PONG, ACK BAD <sev>, ACK OK, LOG ...
"""

import argparse
import logging
import logging.handlers
import os
import re
import sys
import threading
import time
from pathlib import Path

import requests
import serial
import serial.tools.list_ports

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "traffic_monitor.log"


class RedactingFilter(logging.Filter):
    """Redact TomTom API keys from fully-rendered log messages."""

    KEY_QUERY_RE = re.compile(r"(?i)(key=)[^&\s]+")

    def __init__(self) -> None:
        super().__init__()
        self._api_key: str | None = None

    def set_api_key(self, api_key: str | None) -> None:
        self._api_key = api_key or None

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if self._api_key:
            message = message.replace(self._api_key, "***REDACTED***")
        message = self.KEY_QUERY_RE.sub(r"\1***REDACTED***", message)
        record.msg = message
        record.args = ()
        return True


_redacting_filter = RedactingFilter()


def set_log_api_key(api_key: str | None) -> None:
    _redacting_filter.set_api_key(api_key)


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("traffic_monitor")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    console_handler.addFilter(_redacting_filter)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    file_handler.addFilter(_redacting_filter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


log = setup_logging()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BAUD = 115200
STARTUP_READY_TIMEOUT = 5       # seconds to wait for READY on connect
PING_INTERVAL = 60              # heartbeat interval in seconds (Dallas: device STALE at 300s)
DEFAULT_POLL_INTERVAL = 180     # traffic poll interval in seconds (3 minutes)
SERIAL_READ_TIMEOUT = 2.0       # seconds per readline call
SERIAL_RECONNECT_INITIAL_DELAY = 1.0
SERIAL_RECONNECT_MAX_DELAY = 5.0
SERIAL_RECONNECT_TOTAL_TIMEOUT = 300.0
API_TIMEOUT = 10                # HTTP request timeout in seconds

SERIAL_RECONNECT_LOCK = threading.Lock()

# TomTom Traffic Flow Segment endpoint (zoom=10 gives ~1 km road segment)
TOMTOM_FLOW_URL = (
    "https://api.tomtom.com/traffic/services/4/flowSegmentData/relative0/10/json"
)

# Congestion thresholds (ratio = currentSpeed / freeFlowSpeed)
#   >= 0.85          : clear
#   0.60 – <0.85     : bad, severity 1 (slow/heavy traffic)
#   0.35 – <0.60     : bad, severity 2 (significant delays)
#   < 0.35           : bad, severity 3 (gridlock)
THRESH_CLEAR = 0.85
THRESH_SEV1  = 0.60
THRESH_SEV2  = 0.35

# ---------------------------------------------------------------------------
# Config / secrets loading
# ---------------------------------------------------------------------------
CONFIG_FILE = Path(__file__).parent / ".traffic_config"


def load_api_key() -> str | None:
    """
    Load the TomTom API key from:
      1. TOMTOM_API_KEY environment variable  (preferred)
      2. pc/.traffic_config file (gitignored), format: TOMTOM_API_KEY=yourkey
    Returns None if not found anywhere.
    """
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    if key:
        return key
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TOMTOM_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def _masked_key(key: str) -> str:
    """Return only the first 4 chars of the key for safe logging."""
    if len(key) > 4:
        return key[:4] + "..."
    return "****"


# ---------------------------------------------------------------------------
# Traffic API
# ---------------------------------------------------------------------------
class AuthError(Exception):
    """Raised when TomTom returns 401/403 — caller should stop the monitor."""


def fetch_congestion(lat: float, lon: float, api_key: str) -> tuple[str, int]:
    """
    Query TomTom Traffic Flow for the road segment nearest (lat, lon).

    Returns (status, severity):
      status   "bad" | "clear" | "unknown"
      severity 1–3 when status=="bad", 0 otherwise

    Edge-case handling (per Ash's test scenarios):
      Timeout / network error → "unknown" (skip cycle, log warning)
      5xx server error        → "unknown" (skip cycle, log warning)
      429 Too Many Requests   → "unknown" (back off, skip cycle)
      401/403 Auth failure    → raises AuthError (fatal — caller must stop)
      Empty / null speed data → "unknown" (fail safe to calm)
      Malformed JSON          → "unknown" (log warning, skip cycle)
    """
    params = {
        "key": api_key,
        "point": f"{lat},{lon}",
        "unit": "KMPH",
    }

    try:
        resp = requests.get(TOMTOM_FLOW_URL, params=params, timeout=API_TIMEOUT)
    except requests.Timeout:
        log.warning("TomTom API request timed out — skipping this cycle")
        return "unknown", 0
    except requests.RequestException as exc:
        log.warning("TomTom API network error: %s — skipping this cycle", exc)
        return "unknown", 0

    if resp.status_code in (401, 403):
        log.error(
            "TomTom API auth failure (HTTP %d) — key prefix: %s. "
            "Check TOMTOM_API_KEY. Stopping monitor.",
            resp.status_code,
            _masked_key(api_key),
        )
        raise AuthError(f"HTTP {resp.status_code}")

    if resp.status_code == 429:
        log.warning("TomTom API rate-limited (429) — backing off, skipping this cycle")
        return "unknown", 0

    if resp.status_code >= 500:
        log.warning("TomTom API server error (HTTP %d) — skipping this cycle", resp.status_code)
        return "unknown", 0

    if resp.status_code != 200:
        log.warning("TomTom API unexpected status %d — skipping this cycle", resp.status_code)
        return "unknown", 0

    try:
        data = resp.json()
    except ValueError:
        log.warning("TomTom API returned non-JSON body — skipping this cycle")
        return "unknown", 0

    flow = data.get("flowSegmentData")
    if not flow:
        log.warning("TomTom response missing flowSegmentData — skipping this cycle")
        return "unknown", 0

    current = flow.get("currentSpeed")
    free_flow = flow.get("freeFlowSpeed")

    if current is None or free_flow is None or free_flow <= 0:
        log.warning(
            "TomTom returned null/zero speed values (currentSpeed=%s, freeFlowSpeed=%s) "
            "— skipping this cycle",
            current, free_flow,
        )
        return "unknown", 0

    ratio = current / free_flow
    log.info(
        "Traffic: currentSpeed=%.1f km/h  freeFlow=%.1f km/h  ratio=%.2f",
        current, free_flow, ratio,
    )

    if ratio >= THRESH_CLEAR:
        return "clear", 0
    elif ratio >= THRESH_SEV1:
        return "bad", 1
    elif ratio >= THRESH_SEV2:
        return "bad", 2
    else:
        return "bad", 3


# ---------------------------------------------------------------------------
# Serial helpers
# ---------------------------------------------------------------------------
def open_serial(port: str) -> serial.Serial:
    """Open the serial port; raise SystemExit with a helpful message on failure."""
    try:
        ser = serial.Serial(port, BAUD, timeout=SERIAL_READ_TIMEOUT)
        log.info("Opened serial port %s at %d baud", port, BAUD)
        return ser
    except serial.SerialException as exc:
        available = [p.device for p in serial.tools.list_ports.comports()]
        raise SystemExit(
            f"\n[ERROR] Cannot open serial port '{port}': {exc}\n"
            f"Available ports: {available or ['(none found)']}\n"
            f"Tip (Windows): Device Manager → Ports (COM & LPT) → look for\n"
            f"  'Silicon Labs CP210x USB to UART Bridge' or 'USB-SERIAL CH340'\n"
            f"  and use that COM port (e.g. COM3, COM7).\n"
        ) from None


def send_cmd(ser: serial.Serial, cmd: str, lock: threading.Lock) -> None:
    """Send one LF-terminated ASCII command. Thread-safe via lock."""
    line = cmd.strip() + "\n"
    encoded = line.encode("ascii")
    if len(encoded) > 32:
        raise ValueError(f"Command exceeds 32-byte limit: {line!r}")
    with lock:
        ser.write(encoded)
        ser.flush()
    log.debug("→ %s", cmd.strip())


def reopen_serial(
    old_ser: serial.Serial | None,
    port: str,
    lock: threading.Lock,
    stop_event: threading.Event | None = None,
) -> serial.Serial | None:
    """Close a bad handle and retry opening the port with bounded backoff."""
    with lock:
        if old_ser is not None:
            try:
                if old_ser.is_open:
                    old_ser.close()
            except Exception:
                pass

    deadline = time.monotonic() + SERIAL_RECONNECT_TOTAL_TIMEOUT
    delay = SERIAL_RECONNECT_INITIAL_DELAY
    while True:
        try:
            ser = serial.Serial(port, BAUD, timeout=SERIAL_READ_TIMEOUT)
            log.info("Reconnected to %s.", port)
            return ser
        except (serial.SerialException, OSError, PermissionError) as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                log.error(
                    "Unable to reconnect to %s after %.0fs: %s",
                    port,
                    SERIAL_RECONNECT_TOTAL_TIMEOUT,
                    exc,
                )
                return None
            sleep_for = min(delay, SERIAL_RECONNECT_MAX_DELAY, remaining)
            log.warning(
                "Reconnect to %s failed: %s; retrying in %.1fs",
                port,
                exc,
                sleep_for,
            )
            if stop_event is not None:
                if stop_event.wait(timeout=sleep_for):
                    return None
            else:
                time.sleep(sleep_for)
            delay = min(delay * 2, SERIAL_RECONNECT_MAX_DELAY)


def _replace_serial(
    serial_ref: dict[str, serial.Serial],
    old_ser: serial.Serial,
    new_ser: serial.Serial,
    lock: threading.Lock,
) -> serial.Serial:
    with lock:
        if serial_ref["ser"] is old_ser:
            serial_ref["ser"] = new_ser
            return new_ser
        current = serial_ref["ser"]
    try:
        new_ser.close()
    except Exception:
        pass
    return current


def _reconnect_serial(
    serial_ref: dict[str, serial.Serial],
    port: str,
    lock: threading.Lock,
    stop_event: threading.Event | None = None,
    failed_ser: serial.Serial | None = None,
) -> bool:
    with SERIAL_RECONNECT_LOCK:
        with lock:
            old_ser = serial_ref["ser"]
            if failed_ser is not None and old_ser is not failed_ser:
                return True
        log.warning("Serial connection lost — attempting to reconnect to %s...", port)
        new_ser = reopen_serial(old_ser, port, lock, stop_event)
        if new_ser is None:
            return False
        _replace_serial(serial_ref, old_ser, new_ser, lock)
        return True


def send_cmd_resilient(
    serial_ref: dict[str, serial.Serial],
    port: str,
    cmd: str,
    lock: threading.Lock,
    stop_event: threading.Event | None = None,
) -> bool:
    """Send a command, reconnecting and retrying once on transient serial failure."""
    for attempt in (1, 2):
        with lock:
            ser = serial_ref["ser"]
        try:
            send_cmd(ser, cmd, lock)
            return True
        except (serial.SerialException, OSError, PermissionError) as exc:
            if attempt == 1:
                log.warning(
                    "Serial write failed — attempting to reconnect to %s: %s",
                    port,
                    exc,
                )
                if _reconnect_serial(serial_ref, port, lock, stop_event, ser):
                    continue
                log.warning("Skipping %r because serial reconnect did not complete", cmd)
                return False
            log.warning("Serial write failed after reconnect; skipping %r: %s", cmd, exc)
            return False
    return False


def read_line(ser: serial.Serial) -> str | None:
    """
    Non-blocking read of one line from serial.
    Returns stripped ASCII string, or None on timeout/empty/error.
    """
    try:
        raw = ser.readline()
        if raw:
            return raw.decode("ascii", errors="replace").strip()
    except (serial.SerialException, OSError, PermissionError):
        pass
    return None


def read_line_resilient(
    serial_ref: dict[str, serial.Serial],
    port: str,
    lock: threading.Lock,
    stop_event: threading.Event | None = None,
) -> str | None:
    """Read one line, reconnecting on transient serial read failure."""
    with lock:
        ser = serial_ref["ser"]
        try:
            raw = ser.readline()
        except (serial.SerialException, OSError, PermissionError) as exc:
            log.warning(
                "Serial read failed — attempting to reconnect to %s: %s",
                port,
                exc,
            )
            raw = None

    if raw:
        return raw.decode("ascii", errors="replace").strip()
    if raw is None:
        _reconnect_serial(serial_ref, port, lock, stop_event, ser)
    return None


def wait_for_ready(ser: serial.Serial, lock: threading.Lock) -> bool:
    """
    Wait up to STARTUP_READY_TIMEOUT seconds for a READY line.
    If not seen, send PING and wait for PONG.
    Returns True if device is responsive, False if no response
    (proceeding is still attempted — caller can warn but continue).
    """
    deadline = time.monotonic() + STARTUP_READY_TIMEOUT
    log.info("Waiting up to %ds for READY from device...", STARTUP_READY_TIMEOUT)
    while time.monotonic() < deadline:
        line = read_line(ser)
        if line == "READY":
            log.info("Device sent READY — connected")
            return True
        if line:
            log.debug("← %s (startup, ignored)", line)

    log.info("No READY received; sending PING...")
    send_cmd(ser, "PING", lock)
    pong_deadline = time.monotonic() + STARTUP_READY_TIMEOUT
    while time.monotonic() < pong_deadline:
        line = read_line(ser)
        if line == "PONG":
            log.info("Device responded PONG — connected")
            return True
        if line:
            log.debug("← %s (ping wait, ignored)", line)

    log.warning(
        "No READY/PONG within %ds. Proceeding anyway — "
        "check --port is correct and firmware is running.",
        STARTUP_READY_TIMEOUT * 2,
    )
    return False


# ---------------------------------------------------------------------------
# Heartbeat thread
# ---------------------------------------------------------------------------
class Heartbeat(threading.Thread):
    """
    Sends PING every PING_INTERVAL (60s) to keep the device out of STALE state.
    Dallas contract: device transitions STALE after 300s without any command.
    """

    def __init__(
        self,
        serial_ref: dict[str, serial.Serial],
        port: str,
        lock: threading.Lock,
    ) -> None:
        super().__init__(daemon=True, name="heartbeat")
        self._serial_ref = serial_ref
        self._port = port
        self._lock = lock
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(timeout=PING_INTERVAL):
            if send_cmd_resilient(
                self._serial_ref,
                self._port,
                "PING",
                self._lock,
                self._stop_event,
            ):
                log.debug("Heartbeat PING sent")
            else:
                log.warning("Heartbeat PING skipped; serial is not currently available")

    def stop(self) -> None:
        self._stop_event.set()


# ---------------------------------------------------------------------------
# --test mode
# ---------------------------------------------------------------------------
def run_test(ser: serial.Serial, lock: threading.Lock, mode: str) -> None:
    """
    Manual QA mode: send ONE signal through the real serial path and exit.
    No API key required — exercises the serial code path directly.
      mode "bad"   → TRAFFIC BAD 2  (mid-severity; easy visual confirmation)
      mode "clear" → TRAFFIC OK
    """
    if mode == "bad":
        cmd = "TRAFFIC BAD 2"
    elif mode == "clear":
        cmd = "TRAFFIC OK"
    else:
        raise SystemExit(f"[ERROR] Unknown --test mode '{mode}'. Use 'bad' or 'clear'.")

    wait_for_ready(ser, lock)

    log.info("TEST MODE: sending %r", cmd)
    send_cmd(ser, cmd, lock)

    # Wait up to 3 s for ACK
    ack_deadline = time.monotonic() + 3.0
    while time.monotonic() < ack_deadline:
        line = read_line(ser)
        if line:
            log.info("← %s", line)
            if line.startswith("ACK"):
                log.info("TEST PASS: received ACK for '%s'", cmd)
                return
    log.warning(
        "TEST: No ACK received within 3 s — "
        "command was sent, but device may not be running firmware yet."
    )


# ---------------------------------------------------------------------------
# Main monitor loop
# ---------------------------------------------------------------------------
def monitor_loop(
    ser: serial.Serial,
    port: str,
    lock: threading.Lock,
    lat: float,
    lon: float,
    api_key: str,
    interval: int,
) -> None:
    """
    Main polling loop.
    - Polls TomTom every `interval` seconds.
    - Sends TRAFFIC BAD <sev> or TRAFFIC OK on state change AND as periodic refresh.
    - Reads + logs any lines from device (ACKs, LOGs).
    - Never crashes the loop on a single bad API call (unknown → preserve state).
    - Heartbeat PING sent by background thread every 60s.
    """
    last_state: str | None = None   # "bad_1"|"bad_2"|"bad_3"|"clear"|None
    next_poll = time.monotonic()    # poll immediately on first iteration
    serial_ref = {"ser": ser}

    log.info(
        "Monitor running — lat=%.2f lon=%.2f interval=%ds  (Ctrl+C to stop)",
        lat, lon, interval,
    )

    heartbeat = Heartbeat(serial_ref, port, lock)
    heartbeat.start()

    try:
        while True:
            now = time.monotonic()

            # Drain incoming serial lines (non-blocking window = SERIAL_READ_TIMEOUT)
            line = read_line_resilient(serial_ref, port, lock)
            if line:
                log.info("← %s", line)

            # Time to poll traffic?
            if now >= next_poll:
                next_poll = now + interval
                try:
                    status, severity = fetch_congestion(lat, lon, api_key)
                except AuthError:
                    heartbeat.stop()
                    raise SystemExit(
                        "[FATAL] TomTom API authentication failed. "
                        "Check TOMTOM_API_KEY and restart."
                    )

                if status == "unknown":
                    # Fail safe: do NOT flip device into alert; preserve current state
                    log.info(
                        "Traffic status unknown this cycle — "
                        "device state preserved (fail-safe to calm)"
                    )
                else:
                    new_state = f"bad_{severity}" if status == "bad" else "clear"
                    cmd = ("TRAFFIC BAD" if severity == 1 else f"TRAFFIC BAD {severity}") if status == "bad" else "TRAFFIC OK"

                    if new_state != last_state:
                        log.info(
                            "State: %s → %s  sending '%s'",
                            last_state or "none", new_state, cmd,
                        )
                    else:
                        log.info("State unchanged (%s) — periodic refresh '%s'", new_state, cmd)

                    if send_cmd_resilient(serial_ref, port, cmd, lock):
                        last_state = new_state
                    else:
                        log.warning("Traffic command not sent; will retry on next poll")

            time.sleep(0.5)

    except KeyboardInterrupt:
        log.info("Interrupted by user — shutting down")
    finally:
        heartbeat.stop()
        heartbeat.join(timeout=SERIAL_RECONNECT_MAX_DELAY + 1.0)
        try:
            with lock:
                serial_ref["ser"].close()
        except Exception:
            pass
        log.info("Serial port closed. Bye.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="traffic_monitor.py",
        description=(
            "ESP32-S3 traffic monitor — polls TomTom Traffic API and signals\n"
            "the device over USB serial (115200 baud, LF-terminated ASCII)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
API key (required for normal mode, not --test):
  Set environment variable:  set TOMTOM_API_KEY=yourkey      (Windows CMD)
                             $env:TOMTOM_API_KEY="yourkey"   (PowerShell)
  Or create pc\\.traffic_config (gitignored) with:
      TOMTOM_API_KEY=yourkey

Examples:
  # Normal monitor:
  python traffic_monitor.py --port COM3 --lat 40.7128 --lon -74.0060

  # Using --location shorthand:
  python traffic_monitor.py --port COM3 --location 40.7128,-74.0060

  # Fast poll for testing (60 s):
  python traffic_monitor.py --port COM3 --lat 40.7128 --lon -74.0060 --interval 60

  # Manual QA — no API key needed:
  python traffic_monitor.py --port COM3 --test bad
  python traffic_monitor.py --port COM3 --test clear
""",
    )

    parser.add_argument(
        "--port", required=True,
        help="Serial COM port (e.g. COM3 on Windows, /dev/ttyUSB0 on Linux)",
    )

    loc_group = parser.add_argument_group("location (not required for --test mode)")
    loc_mutex = loc_group.add_mutually_exclusive_group()
    loc_mutex.add_argument(
        "--location", metavar="LAT,LON",
        help='Location as "lat,lon" (e.g. 40.7128,-74.0060)',
    )
    loc_mutex.add_argument(
        "--lat", type=float, metavar="LAT",
        help="Latitude (use with --lon)",
    )
    loc_group.add_argument(
        "--lon", type=float, metavar="LON",
        help="Longitude (use with --lat)",
    )

    parser.add_argument(
        "--interval", type=int, default=DEFAULT_POLL_INTERVAL, metavar="SECONDS",
        help=f"Traffic API poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--test", choices=["bad", "clear"], metavar="{bad|clear}",
        help=(
            "Test mode: send ONE signal through the real serial path and exit. "
            "No API key required. Use 'bad' or 'clear'."
        ),
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)

    lat = lon = None
    api_key = None

    if not args.test:
        # Resolve location
        if args.location:
            try:
                lat_s, lon_s = args.location.split(",", 1)
                lat, lon = float(lat_s.strip()), float(lon_s.strip())
            except ValueError:
                raise SystemExit(
                    f"[ERROR] --location must be 'lat,lon', got: {args.location!r}"
                )
        elif args.lat is not None and args.lon is not None:
            lat, lon = args.lat, args.lon
        else:
            raise SystemExit(
                "[ERROR] Location required for normal mode.\n"
                "Provide --location LAT,LON  or  --lat LAT --lon LON.\n"
                "(Location not required for --test mode.)"
            )

        # Load API key
        api_key = load_api_key()
        if not api_key:
            raise SystemExit(
                "\n[ERROR] TomTom API key not found.\n"
                "Set TOMTOM_API_KEY in your environment:\n"
                "  Windows CMD:   set TOMTOM_API_KEY=yourkey\n"
                "  PowerShell:    $env:TOMTOM_API_KEY=\"yourkey\"\n"
                "Or create pc\\.traffic_config (gitignored):\n"
                "  TOMTOM_API_KEY=yourkey\n"
                "Get a free key at https://developer.tomtom.com/\n"
            )
        set_log_api_key(api_key)

    # Open serial port
    ser = open_serial(args.port)
    lock = threading.Lock()

    if args.test:
        run_test(ser, lock, args.test)
        ser.close()
        return

    wait_for_ready(ser, lock)
    monitor_loop(ser, args.port, lock, lat, lon, api_key, args.interval)


if __name__ == "__main__":
    main()
