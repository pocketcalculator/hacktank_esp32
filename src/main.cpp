#include <Arduino.h>
#include <Adafruit_GC9A01A.h>

namespace {
constexpr int LCD_BL_VENDOR = 40;
constexpr int LCD_BL_ALT = 2;
constexpr int LCD_DC = 8;
constexpr int LCD_CS = 9;
constexpr int LCD_SCK = 10;
constexpr int LCD_MOSI = 11;
constexpr int LCD_RST = 12;

Adafruit_GC9A01A tft(LCD_CS, LCD_DC, LCD_MOSI, LCD_SCK, LCD_RST);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(LCD_BL_VENDOR, OUTPUT);
  pinMode(LCD_BL_ALT, OUTPUT);
  digitalWrite(LCD_BL_VENDOR, HIGH);
  digitalWrite(LCD_BL_ALT, HIGH);

  tft.begin(40000000);
  tft.setRotation(0);
  tft.fillScreen(GC9A01A_BLACK);
  tft.setTextColor(GC9A01A_WHITE);
  tft.setTextSize(2);

  const char *msg = "Hi, Paul!";
  int16_t x1, y1;
  uint16_t w, h;
  tft.getTextBounds(msg, 0, 0, &x1, &y1, &w, &h);
  int16_t x = (240 - static_cast<int16_t>(w)) / 2;
  int16_t y = (240 + static_cast<int16_t>(h)) / 2;
  tft.setCursor(x, y);
  tft.print(msg);

  Serial.println("Rendered Hi, Paul! on LCD");
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last >= 2000) {
    last = millis();
    Serial.printf("hello-screen alive ms=%lu\n", static_cast<unsigned long>(last));
  }
}