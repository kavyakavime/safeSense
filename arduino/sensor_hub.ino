#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT.h>

// ---- Pins ----
#define DHTPIN 2
#define DHTTYPE DHT22
#define TRIG_PIN 9
#define ECHO_PIN 10

// ---- LCD ----
// Common I2C addresses: 0x27 or 0x3E (Grove)
#define LCD_ADDR 0x27
#define LCD_COLS 16
#define LCD_ROWS 2

// ---- Thresholds ----
#define TEMP_ALERT_C 40.0
#define PERSON_DISTANCE_CM 50.0

LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);
DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  dht.begin();

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Sensor Hub");
  lcd.setCursor(0, 1);
  lcd.print("Starting...");
  delay(1200);
}

float readDistanceCM() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout
  if (duration == 0) return -1.0;
  float distance = duration * 0.0343 / 2.0;
  return distance;
}

void loop() {
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  float dist = readDistanceCM();

  // LCD display
  lcd.clear();
  lcd.setCursor(0, 0);
  if (isnan(temp) || isnan(hum)) {
    lcd.print("Temp/Hum Err");
  } else {
    lcd.print("T:");
    lcd.print(temp, 1);
    lcd.print("C H:");
    lcd.print(hum, 0);
    lcd.print("%");
  }

  lcd.setCursor(0, 1);
  if (dist < 0) {
    lcd.print("Dist Err");
  } else {
    lcd.print("D:");
    lcd.print(dist, 0);
    lcd.print("cm ");

    if (temp > TEMP_ALERT_C) {
      lcd.print("HOT!");
    } else if (dist < PERSON_DISTANCE_CM) {
      lcd.print("PERSON");
    } else {
      lcd.print("OK");
    }
  }

  // Serial output for host
  if (!isnan(temp) && !isnan(hum) && dist >= 0) {
    Serial.print("TEMP:");
    Serial.print(temp, 1);
    Serial.print(",HUMID:");
    Serial.print(hum, 0);
    Serial.print(",DIST:");
    Serial.println(dist, 0);
  }

  delay(500);
}
