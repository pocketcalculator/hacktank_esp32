#include <Arduino.h>
#include <Adafruit_GC9A01A.h>
#include "serial_cmd.h"
#include "display_fsm.h"
#include "display_anim.h"

// Define FORCE_ALERT_ON_BOOT (e.g., add -D FORCE_ALERT_ON_BOOT to build_flags)
// to boot straight into severity-3 ALERT for visual QA without a PC attached.

namespace {
constexpr int LCD_BL_VENDOR = 40;
constexpr int LCD_BL_ALT    = 2;
constexpr int LCD_DC        = 8;
constexpr int LCD_CS        = 9;
constexpr int LCD_SCK       = 10;
constexpr int LCD_MOSI      = 11;
constexpr int LCD_RST       = 12;

Adafruit_GC9A01A tft(LCD_CS, LCD_DC, LCD_MOSI, LCD_SCK, LCD_RST);
}

void setup() {
    Serial.begin(115200);
    delay(200); // allow USB-CDC to enumerate (setup only, not loop)

    pinMode(LCD_BL_VENDOR, OUTPUT);
    pinMode(LCD_BL_ALT, OUTPUT);
    digitalWrite(LCD_BL_VENDOR, HIGH);
    digitalWrite(LCD_BL_ALT, HIGH);

    tft.begin(40000000);
    tft.setRotation(0);
    tft.fillScreen(0x0000); // black

    DisplayFSM::init();
    DisplayAnim::init(tft);

#ifdef FORCE_ALERT_ON_BOOT
    DisplayFSM::on_bad(3);
    Serial.println("LOG FORCE_ALERT_ON_BOOT sev=3");
#endif

    Serial.println("READY");
}

void loop() {
    SerialCmd::tick();
    DisplayFSM::tick();
    DisplayAnim::tick();
}