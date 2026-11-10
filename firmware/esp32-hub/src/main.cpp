// ESP32-S3 sensor hub: timestamps PPS, IMU, baro and Wi-Fi, sends them to the Pi as MAVLink
// (systems/icd/pnt.xml, ADR-0005) over USB CDC.
//
// Status: skeleton. PPS capture and hub status work; sensors are TODOs until the parts arrive.
// Pins are placeholders: set them to the real wiring (see the payload spec doc).

#include <Arduino.h>
#include <esp_timer.h>

#include "pnt/mavlink.h"

namespace {

constexpr int PIN_PPS = 4;          // TODO: real pin. PPS wire tapped from the GPS HAT (Pi GPIO4)
constexpr uint8_t SYS_ID = 42;      // payload hub
constexpr uint8_t COMP_ID = 191;    // MAV_COMP_ID_ONBOARD_COMPUTER

volatile int64_t g_pps_time_us = 0;
volatile uint32_t g_pps_count = 0;
volatile bool g_pps_pending = false;

void IRAM_ATTR onPps() {
  // Interrupt latency is a few us. TODO (RSK-05): measure jitter; move to MCPWM capture if needed.
  g_pps_time_us = esp_timer_get_time();
  g_pps_count = g_pps_count + 1;
  g_pps_pending = true;
}

void send(const mavlink_message_t& msg) {
  uint8_t buf[MAVLINK_MAX_PACKET_LEN];
  const uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
  Serial.write(buf, len);
}

}  // namespace

void setup() {
  Serial.begin(921600);
  pinMode(PIN_PPS, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_PPS), onPps, RISING);
  // GPS NMEA goes to the Pi (GPS HAT, ADR-0014): the hub only timestamps PPS edges, and the Pi
  // labels each edge with GPS week/TOW.
  // TODO: MPU6050 on I2C (400 kHz) at up to 1 kHz -> PNT_IMU_RAW
  // TODO: BMP280 on I2C -> PNT_BARO
  // TODO: Wi-Fi scan loop -> PNT_WIFI_AP, BSSID = first 8 bytes of SHA-256(salt || bssid) (ADR-0011)
  // TODO: FTM sessions to responders -> PNT_FTM_RANGE (esp_wifi_ftm_initiate_session)
}

void loop() {
  static int64_t last_status_us = 0;
  mavlink_message_t msg;

  if (g_pps_pending) {
    noInterrupts();
    const int64_t t = g_pps_time_us;
    g_pps_pending = false;
    interrupts();
    // gps_week / gps_tow_ms are filled once the GPS UART parser exists; 0 means "unknown".
    mavlink_msg_pnt_pps_pack(SYS_ID, COMP_ID, &msg, static_cast<uint64_t>(t), 0, 0);
    send(msg);
  }

  const int64_t now = esp_timer_get_time();
  if (now - last_status_us >= 1000000) {
    last_status_us = now;
    mavlink_msg_pnt_hub_status_pack(SYS_ID, COMP_ID, &msg, static_cast<uint64_t>(now),
                                    g_pps_count, 0, 0);
    send(msg);
  }
}
