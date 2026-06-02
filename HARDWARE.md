HARDWARE.md — Waveshare ESP32-S3-LCD-1.28
Drop this file into a project so an AI assistant (Copilot, Cursor, Claude Code, etc.) has all the board-specific context it needs to wire up code correctly without re-researching the datasheet.

Product: Waveshare ESP32-S3-LCD-1.28 MCU dev board with 1.28″ round IPS LCD Amazon ASIN: B0CSYVVV2N Vendor wiki: https://www.waveshare.com/wiki/ESP32-S3-LCD-1.28 Schematic (PDF): https://files.waveshare.com/wiki/ESP32-S3-LCD-1.28/Esp32-s3-lcd-.128-sch.pdf

1. System-on-Chip
Item	Value
MCU	ESP32-S3R2 (Xtensa LX7 dual-core, 32-bit)
Clock	up to 240 MHz
SRAM	512 KB internal
ROM	384 KB
PSRAM	2 MB in-package, QSPI (NOT octal — important!)
Flash	16 MB external (W25Q128JVSIQ, QIO)
Wi-Fi	802.11 b/g/n, 2.4 GHz, on-board ceramic antenna
Bluetooth	BLE 5.0
Crypto	AES-128/256, RSA, HMAC, digital signature, secure boot
⚠️ R2 vs R8: This board is the R2 variant. Do not pick a board definition that assumes 8 MB octal PSRAM (opi_opi) — it will crash at boot. Use memory_type = qio_qspi.

2. On-board peripherals & pin map
Peripheral	ESP32-S3 GPIO	Notes
LCD GC9A01 (SPI)		1.28″ round IPS, 240×240, up to 80 MHz SPI
  BL (backlight)	GPIO2	PWM dimmable
  DC	GPIO8	data/command
  CS	GPIO9	
  SCK	GPIO10	
  MOSI (SDA)	GPIO11	
  RST	GPIO14	
I²C bus (shared)		QMI8658 IMU lives here
  SDA	GPIO6	
  SCL	GPIO7	
QMI8658 IMU INT1 / INT2	GPIO4 / GPIO3	Optional motion-wake interrupts
Battery voltage sense	GPIO1	200 kΩ / 100 kΩ divider → multiply ADC by 3
Aux MOSFET switch #1	GPIO4	Pad near battery — vibration motor, etc.
Aux MOSFET switch #2	GPIO5	Pad near battery
UART0 (CH343P bridge)	TXD GPIO43, RXD GPIO44	USB ⇄ serial, NOT native USB
BOOT button	GPIO0	Hold to enter download mode
RESET button	EN	Active-low reset
Lithium battery connector	MX1.25 2-pin	3.7 V Li-ion, on-board charger (ETA6096)
Pins to avoid / handle with care
GPIO0 — BOOT strapping; don't drive low at reset.
GPIO3, GPIO45, GPIO46 — strapping pins (default OK, but don't pull during reset).
GPIO19 / GPIO20 — connected internally to the USB peripheral pads; unused here because of CH343P bridge, but still avoid for general I/O unless you've checked the schematic.
GPIO26–GPIO32 — wired to the internal SPI flash; never repurpose.
GPIO33–GPIO37 — reserved for PSRAM on R2 (do not use).
Free / safe GPIO for headers
GPIO15, GPIO16, GPIO17, GPIO18, GPIO21, GPIO38, GPIO39, GPIO40, GPIO41, GPIO42, GPIO47, GPIO48 are typically broken out and safe for general use. Always confirm against the schematic because Waveshare's silkscreen swaps a couple of labels.

3. Programming & flashing
USB: Type-C → CH343P USB-to-UART bridge.
Windows: install CH343 driver from WCH if the COM port doesn't appear: https://www.wch-ic.com/downloads/CH343SER_ZIP.html
macOS/Linux: built-in CDC-ACM driver works.
No native USB-CDC — set ARDUINO_USB_MODE=0 and ARDUINO_USB_CDC_ON_BOOT=0.
Auto-download circuit is present; esptool's default DTR/RTS sequence works.
Manual bootloader (if auto fails): hold BOOT, tap RESET, release BOOT, then re-run upload.
Recommended baud: upload 921600, monitor 115200.
4. PlatformIO configuration cheat-sheet
[env:esp32-s3-devkitc-1]
platform              = espressif32
board                 = esp32-s3-devkitc-1
framework             = arduino

monitor_speed         = 115200
upload_speed          = 921600

board_build.mcu        = esp32s3
board_build.f_cpu      = 240000000L
board_build.flash_mode = qio
board_build.flash_size = 16MB
board_upload.flash_size = 16MB
board_upload.maximum_size = 16777216
board_build.partitions = default_16MB.csv
board_build.arduino.memory_type = qio_qspi   ; R2: QSPI PSRAM, not OPI

build_flags =
    -D BOARD_HAS_PSRAM
    -D ARDUINO_USB_MODE=0
    -D ARDUINO_USB_CDC_ON_BOOT=0
Arduino IDE equivalent
Board: ESP32S3 Dev Module
USB CDC On Boot: Disabled
Flash Size: 16 MB (128 Mb)
Partition Scheme: 16M Flash (3MB APP/9.9MB FATFS) or similar 16 MB scheme
PSRAM: QSPI PSRAM (do not pick OPI)
Upload Mode: UART0 / Hardware CDC
Upload Speed: 921600
5. Recommended libraries
Purpose	Library
Display (GC9A01)	moononournation/GFX Library for Arduino
UI framework	lvgl/lvgl (≥ 9.x), or bodmer/TFT_eSPI + LVGL
IMU (QMI8658)	bolderflight/QMI8658 or hand-rolled I²C driver
Wi-Fi provisioning	tzapu/WiFiManager
OTA / web config	Built-in ArduinoOTA, ESPAsyncWebServer
Minimal Arduino_GFX init for the on-board LCD
#include <Arduino_GFX_Library.h>

Arduino_DataBus *bus = new Arduino_ESP32SPI(
    /*DC*/ 8, /*CS*/ 9, /*SCK*/ 10, /*MOSI*/ 11, /*MISO*/ -1, FSPI);

Arduino_GFX *gfx = new Arduino_GC9A01(
    bus, /*RST*/ 14, /*rotation*/ 0, /*IPS*/ true,
    /*width*/ 240, /*height*/ 240,
    /*col_offset1*/ 0, /*row_offset1*/ 0,
    /*col_offset2*/ 0, /*row_offset2*/ 0);

void setup() {
  pinMode(2, OUTPUT); digitalWrite(2, HIGH);   // backlight on
  gfx->begin(80000000);                        // 80 MHz SPI
  gfx->fillScreen(BLACK);
}
Minimal QMI8658 read (I²C addr 0x6B)
#include <Wire.h>
constexpr uint8_t QMI_ADDR = 0x6B;             // 0x6A if SA0 tied low
void setup() {
  Wire.begin(/*SDA*/ 6, /*SCL*/ 7, 400000);
  Wire.beginTransmission(QMI_ADDR);
  Wire.write(0x00);                            // WHO_AM_I
  Wire.endTransmission(false);
  Wire.requestFrom(QMI_ADDR, (uint8_t)1);
  Serial.printf("QMI8658 WHO_AM_I = 0x%02X (expect 0x05)\n", Wire.read());
}
6. Power notes
USB-C provides 5 V → ME6217C33M5G LDO → 3.3 V rail (800 mA).
A Li-ion battery on the MX1.25 jack is charged through ETA6096 while USB is connected and powers the board when USB is removed.
Read the battery voltage on GPIO1; convert with: v_batt = (analogReadMilliVolts(1) * 3) / 1000.0f; // volts
Deep-sleep current is in the low-µA range if the LCD backlight (GPIO2) is driven low and the IMU is put to sleep over I²C.
7. Quick "is it alive?" checklist for an AI assistant
When helping a new user with this board, verify in this order:

platformio.ini has board = esp32-s3-devkitc-1, memory_type = qio_qspi, flash 16 MB.
ARDUINO_USB_CDC_ON_BOOT=0 (board uses CH343P, not native USB-CDC).
CH343 driver is installed on Windows; COM port shows up.
Backlight on GPIO2 driven HIGH before talking to the display.
Display init uses GC9A01, 240×240, IPS=true, SPI pins DC=8, CS=9, SCK=10, MOSI=11, RST=14.
I²C uses SDA=6, SCL=7. QMI8658 WHO_AM_I returns 0x05.
Battery ADC on GPIO1 needs to be multiplied by 3.