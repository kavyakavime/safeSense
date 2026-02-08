/*
 * AI CCTV Hazard Detection System - Arduino Nano
 * With LCD 1602A Display + RGB LED
 */

#include <LiquidCrystal.h>
#include <DHT.h>

// ==================== PIN DEFINITIONS ====================
#define TRIG_PIN 2          // Ultrasonic TRIG
#define ECHO_PIN 3          // Ultrasonic ECHO
#define DHT_PIN 6           // DHT11 sensor
#define LED_R 5             // RGB LED Red
#define LED_G 7             // RGB LED Green
#define LED_B 8             // RGB LED Blue
#define LCD_RS 9            // LCD Register Select
#define LCD_E 10            // LCD Enable
#define LCD_D4 11           // LCD Data 4
#define LCD_D5 12           // LCD Data 5
#define LCD_D6 13           // LCD Data 6
#define LCD_D7 A0           // LCD Data 7

// ==================== SENSOR CONFIGURATION ====================
#define DHT_TYPE DHT11

// ==================== HAZARD THRESHOLDS ====================
#define TEMP_FIRE_THRESHOLD 45.0
#define TEMP_WARNING_THRESHOLD 35.0
#define HUMIDITY_HIGH_THRESHOLD 85.0
#define HUMIDITY_LOW_THRESHOLD 20.0
#define MOTION_THRESHOLD 20.0
#define MIN_DISTANCE 2.0
#define MAX_DISTANCE 400.0
#define MOTION_TIMEOUT 3000

// ==================== OBJECT INITIALIZATION ====================
LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);
DHT dht(DHT_PIN, DHT_TYPE);

// ==================== GLOBAL VARIABLES ====================
float temperature = 0.0;
float humidity = 0.0;
float currentDistance = 0.0;
float previousDistance = 0.0;
bool motionDetected = false;
unsigned long lastMotionTime = 0;
int motionCount = 0;

bool alertActive = false;
String alertType = "NONE";
unsigned long alertStartTime = 0;

unsigned long lastUltrasonicRead = 0;
const unsigned long ULTRASONIC_INTERVAL = 50;  // Faster ultrasonic reads
unsigned long lastDHTRead = 0;
const unsigned long DHT_INTERVAL = 2000;  // DHT11 hardware limit
unsigned long lastDisplayUpdate = 0;
const unsigned long DISPLAY_INTERVAL = 500;  // Faster LCD updates
unsigned long lastSerialSend = 0;
const unsigned long SERIAL_INTERVAL = 300;  // Send data every 300ms for real-time feel

bool ledState = false;
unsigned long lastLedToggle = 0;
unsigned long LED_BLINK_INTERVAL = 250;

unsigned long systemUptime = 0;
int totalAlerts = 0;
int totalMotionEvents = 0;

// ==================== SETUP ====================
void setup() {
  Serial.begin(115200);
  
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  setRGBColor(0, 0, 0);
  digitalWrite(TRIG_PIN, LOW);
  
  dht.begin();
  
  lcd.begin(16, 2);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("AI CCTV SYSTEM");
  lcd.setCursor(0, 1);
  lcd.print("Starting...");
  delay(2000);
  
  currentDistance = readUltrasonicDistance();
  previousDistance = currentDistance;
  
  Serial.println(F("{\"status\":\"READY\",\"device\":\"ARDUINO_NANO\",\"version\":\"2.0\",\"system\":\"AI_CCTV\",\"display\":\"LCD_1602A\"}"));
}

// ==================== MAIN LOOP ====================
void loop() {
  unsigned long currentMillis = millis();
  systemUptime = currentMillis / 1000;
  
  if (currentMillis - lastUltrasonicRead >= ULTRASONIC_INTERVAL) {
    readUltrasonicSensor();
    lastUltrasonicRead = currentMillis;
  }
  
  if (currentMillis - lastDHTRead >= DHT_INTERVAL) {
    readDHTSensor();
    lastDHTRead = currentMillis;
  }
  
  if (currentMillis - lastDisplayUpdate >= DISPLAY_INTERVAL) {
    updateDisplay();
    lastDisplayUpdate = currentMillis;
  }
  
  if (currentMillis - lastSerialSend >= SERIAL_INTERVAL) {
    sendSensorData();
    lastSerialSend = currentMillis;
  }
  
  handleLEDAlert(currentMillis);
  processSerialCommands();
  
  if (motionDetected && (currentMillis - lastMotionTime > MOTION_TIMEOUT)) {
    motionDetected = false;
    motionCount = max(0, motionCount - 1);
  }
}

// ==================== ULTRASONIC SENSOR ====================
float readUltrasonicDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  float distance = duration * 0.01715;
  
  if (distance < MIN_DISTANCE || distance > MAX_DISTANCE) {
    return 0;
  }
  
  return distance;
}

void readUltrasonicSensor() {
  float newDistance = readUltrasonicDistance();
  
  if (newDistance > 0) {
    currentDistance = newDistance;
    
    if (previousDistance > 0) {
      float distanceChange = abs(currentDistance - previousDistance);
      
      if (distanceChange > MOTION_THRESHOLD) {
        if (!motionDetected) {
          motionDetected = true;
          motionCount++;
          totalMotionEvents++;
          lastMotionTime = millis();
          
          Serial.print(F("{\"event\":\"MOTION_DETECTED\",\"distance\":"));
          Serial.print(currentDistance, 1);
          Serial.print(F(",\"change\":"));
          Serial.print(distanceChange, 1);
          Serial.println(F("}"));
        }
        lastMotionTime = millis();
      }
    }
    
    previousDistance = currentDistance;
  }
}

// ==================== DHT SENSOR ====================
void readDHTSensor() {
  float newTemp = dht.readTemperature();
  float newHum = dht.readHumidity();
  
  if (!isnan(newTemp) && !isnan(newHum)) {
    temperature = newTemp;
    humidity = newHum;
    
    if (temperature >= TEMP_FIRE_THRESHOLD) {
      triggerAlert("FIRE");
      Serial.print(F("{\"event\":\"FIRE_HAZARD\",\"temp\":"));
      Serial.print(temperature, 1);
      Serial.println(F("}"));
    }
    
    if (humidity >= HUMIDITY_HIGH_THRESHOLD) {
      Serial.print(F("{\"event\":\"HIGH_HUMIDITY\",\"humidity\":"));
      Serial.print(humidity, 1);
      Serial.println(F("}"));
    }
    if (humidity <= HUMIDITY_LOW_THRESHOLD) {
      Serial.print(F("{\"event\":\"LOW_HUMIDITY_FIRE_RISK\",\"humidity\":"));
      Serial.print(humidity, 1);
      Serial.println(F("}"));
    }
  }
}

// ==================== DISPLAY ====================
void updateDisplay() {
  lcd.clear();
  
  if (alertActive) {
    lcd.setCursor(0, 0);
    lcd.print("ALERT:");
    lcd.print(alertType);
    lcd.setCursor(0, 1);
    lcd.print("CHECK SYSTEM!");
  } else {
    lcd.setCursor(0, 0);
    lcd.print("NORMAL-AllClear");
    lcd.setCursor(0, 1);
    lcd.print("T:");
    lcd.print(temperature, 1);
    lcd.print(" H:");
    lcd.print((int)humidity);
    lcd.print(" D:");
    lcd.print((int)currentDistance);
  }
}

// ==================== RGB LED ====================
void setRGBColor(int r, int g, int b) {
  analogWrite(LED_R, r);
  analogWrite(LED_G, g);
  analogWrite(LED_B, b);
}

void handleLEDAlert(unsigned long currentMillis) {
  if (alertActive) {
    if (alertType == "FIRE") {
      LED_BLINK_INTERVAL = 100;
    } else if (alertType == "VIOLENCE" || alertType == "WEAPON") {
      LED_BLINK_INTERVAL = 150;
    } else {
      LED_BLINK_INTERVAL = 250;
    }
    
    if (currentMillis - lastLedToggle >= LED_BLINK_INTERVAL) {
      ledState = !ledState;
      
      if (ledState) {
        if (alertType == "FIRE") {
          setRGBColor(255, 0, 0);  // RED
        } else if (alertType == "VIOLENCE" || alertType == "WEAPON") {
          setRGBColor(255, 0, 0);  // RED
        } else if (alertType == "INTRUSION") {
          setRGBColor(0, 0, 255);  // BLUE
        } else {
          setRGBColor(255, 100, 0);  // ORANGE
        }
      } else {
        setRGBColor(0, 0, 0);
      }
      
      lastLedToggle = currentMillis;
    }
  } else {
    setRGBColor(0, 150, 0);  // GREEN = All good (medium brightness)
    ledState = false;
  }
}

void triggerAlert(String type) {
  alertActive = true;
  alertType = type;
  alertStartTime = millis();
  totalAlerts++;
}

void clearAlert() {
  alertActive = false;
  alertType = "NONE";
  setRGBColor(0, 150, 0);  // Medium brightness green
  ledState = false;
}

// ==================== SERIAL ====================
void sendSensorData() {
  Serial.print(F("{"));
  Serial.print(F("\"type\":\"SENSOR_DATA\","));
  Serial.print(F("\"temp\":"));
  Serial.print(temperature, 2);
  Serial.print(F(",\"humidity\":"));
  Serial.print(humidity, 2);
  Serial.print(F(",\"distance\":"));
  Serial.print(currentDistance, 1);
  Serial.print(F(",\"motion\":"));
  Serial.print(motionDetected ? F("true") : F("false"));
  Serial.print(F(",\"motion_count\":"));
  Serial.print(motionCount);
  Serial.print(F(",\"alert\":"));
  Serial.print(alertActive ? F("true") : F("false"));
  Serial.print(F(",\"alert_type\":\""));
  Serial.print(alertType);
  Serial.print(F("\",\"uptime\":"));
  Serial.print(systemUptime);
  Serial.print(F(",\"total_alerts\":"));
  Serial.print(totalAlerts);
  Serial.print(F(",\"total_motion\":"));
  Serial.print(totalMotionEvents);
  Serial.println(F("}"));
}

void processSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command == "FIRE") {
      triggerAlert("FIRE");
      Serial.println(F("{\"response\":\"FIRE_ALERT_ACTIVATED\"}"));
    }
    else if (command == "INTRUSION") {
      triggerAlert("INTRUSION");
      Serial.println(F("{\"response\":\"INTRUSION_ALERT_ACTIVATED\"}"));
    }
    else if (command == "VIOLENCE") {
      triggerAlert("VIOLENCE");
      Serial.println(F("{\"response\":\"VIOLENCE_ALERT_ACTIVATED\"}"));
    }
    else if (command == "WEAPON") {
      triggerAlert("WEAPON");
      Serial.println(F("{\"response\":\"WEAPON_ALERT_ACTIVATED\"}"));
    }
    else if (command == "ALERT_OFF" || command == "CLEAR") {
      clearAlert();
      Serial.println(F("{\"response\":\"ALERT_CLEARED\"}"));
    }
    else if (command == "STATUS") {
      sendSensorData();
    }
    else if (command == "RESET") {
      clearAlert();
      motionCount = 0;
      totalMotionEvents = 0;
      totalAlerts = 0;
      Serial.println(F("{\"response\":\"SYSTEM_RESET\"}"));
    }
    else if (command == "PING") {
      Serial.println(F("{\"response\":\"PONG\",\"status\":\"ONLINE\"}"));
    }
    else if (command.startsWith("LED_")) {
      if (command == "LED_ON") {
        setRGBColor(255, 255, 255);
        Serial.println(F("{\"response\":\"LED_ON\"}"));
      } else if (command == "LED_OFF") {
        setRGBColor(0, 0, 0);
        Serial.println(F("{\"response\":\"LED_OFF\"}"));
      }
    }
    else {
      Serial.print(F("{\"error\":\"UNKNOWN_COMMAND\",\"received\":\""));
      Serial.print(command);
      Serial.println(F("\"}"));
    }
  }
}
