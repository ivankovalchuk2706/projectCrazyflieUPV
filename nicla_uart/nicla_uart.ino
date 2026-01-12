#include <Arduino.h>
#include <Arduino_BHY2.h>

// Sensors
Sensor temp(SENSOR_ID_TEMP);
Sensor hum(SENSOR_ID_HUM);
SensorBSEC bsec(SENSOR_ID_BSEC);

#define PKT_SIZE 14
#define PKT_HEADER 0xAA

void setup() {
  Serial.begin(115200);   // Для відладочного USB
  Serial1.begin(115200);  // UART → Crazyflie

  Serial.println("=== Nicla → Crazyflie UART ===");

  if (!BHY2.begin()) {
    Serial.println("BHY2 initialization FAILED!");
    return;
  }

  temp.begin();
  hum.begin();
  bsec.begin();

  Serial.println("BHY2 initialized OK");

  delay(1500);  // даємо сенсорам стабілізуватися
}

void loop() {
  // Must be called every loop
  BHY2.update();

  float T = temp.value();
  float H = hum.value();
  float A = bsec.iaq();

  // Вивід у USB (відладка)
  Serial.print("T=");
  Serial.print(T);
  Serial.print("C, H=");
  Serial.print(H);
  Serial.print("%, P=");
  Serial.print(A);
  Serial.println(" ");

  // Не посилаємо, якщо дані не дійсні
  if (isnan(T) || isnan(H) || isnan(A)) {
    Serial.println("Sensor data invalid, skipping");
    delay(200);
    return;
  }

  // Створюємо пакет
  uint8_t buf[PKT_SIZE];

  buf[0] = PKT_HEADER;

  memcpy(&buf[1],  &T, 4);
  memcpy(&buf[5],  &H, 4);
  memcpy(&buf[9],  &A, 4);

  // CRC (XOR всіх байтів окрім CRC)
  uint8_t crc = 0;
  for (int i = 0; i < PKT_SIZE - 1; i++)
    crc ^= buf[i];

  buf[PKT_SIZE - 1] = crc;

  // Відправка у Crazyflie
  Serial1.write(buf, PKT_SIZE);

  Serial.println("Packet sent");

  delay(100);   // 10 Гц
}
