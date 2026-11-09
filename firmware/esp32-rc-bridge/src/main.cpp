// ESP32 RC bridge (ADR-0029). Tethered indoor hover only.
//
// The laptop sends authenticated control packets over UDP to this board's own
// 2.4 GHz WPA2 access point. Valid packets become CRSF RC frames on UART2, which
// the flight controller (INAV, `serialrx_provider = CRSF`) reads as an RC receiver.
// With no valid packet for kHbTimeoutMs the board sends nothing at all, so INAV
// sees RX loss and runs its own failsafe. All protocol logic is in rc_bridge.h.
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "rc_bridge.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Copy include/secrets.h.example to include/secrets.h and fill it in (README.md)"
#endif

static_assert(sizeof(RCB_AP_PASSWORD) >= 9, "WPA2 needs a password of at least 8 characters");
static_assert(sizeof(RCB_PSK_HEX) == 2 * rcb::kKeyLen + 1, "RCB_PSK_HEX must be 64 hex digits");

namespace {

// Values marked TBC are proposed, not confirmed (ADR-0029); change them only with the ADR.
constexpr uint32_t kHbTimeoutMs = 200;     // TBC: silence longer than this -> stop sending
constexpr uint32_t kFramePeriodMs = 20;    // TBC: 50 Hz CRSF frames
constexpr uint32_t kCrsfBaud = 420000;     // TBC: INAV's CRSF rate
constexpr int kUartRxPin = 16;             // UART2 RX2 on an esp32dev board (FC TX)
constexpr int kUartTxPin = 17;             // UART2 TX2 on an esp32dev board (FC RX)
constexpr uint16_t kUdpPort = 14650;       // control packets in, status out
constexpr uint8_t kApChannel = 1;          // TBC: 2.4 GHz channel, pick the quietest
constexpr uint32_t kStatusPeriodMs = 100;  // status replies, at most 10 Hz
constexpr uint32_t kLogPeriodMs = 1000;    // counters to the USB serial console

WiFiUDP udp;
rcb::Bridge* bridge = nullptr;
uint32_t next_frame_ms = 0;
uint32_t last_status_ms = 0;
uint32_t last_log_ms = 0;
uint32_t frames_sent = 0;

[[noreturn]] void halt(const char* why) {
  // Never start the access point or the UART with a bad configuration.
  for (;;) {
    Serial.println(why);
    delay(1000);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Serial2.begin(kCrsfBaud, SERIAL_8N1, kUartRxPin, kUartTxPin);

  uint8_t key[rcb::kKeyLen];
  if (!rcb::parse_hex(RCB_PSK_HEX, key, sizeof key)) halt("rc-bridge: RCB_PSK_HEX is not 64 hex digits");

  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  // One client only: the laptop. softAP with a password uses WPA2-PSK.
  if (!WiFi.softAP(RCB_AP_SSID, RCB_AP_PASSWORD, kApChannel, /*ssid_hidden=*/0,
                   /*max_connection=*/1)) {
    halt("rc-bridge: softAP failed");
  }
  udp.begin(kUdpPort);

  // A new nonce every boot, so packets recorded before a reboot are useless.
  // esp_random() is a true RNG once the radio is on.
  uint32_t nonce = 0;
  while (nonce == 0) nonce = esp_random();
  static rcb::Bridge b(key, nonce, kHbTimeoutMs);
  bridge = &b;
  memset(key, 0, sizeof key);

  Serial.printf("rc-bridge: AP %s on %s ch %u, udp %u, nonce %08lx\n", RCB_AP_SSID,
                WiFi.softAPIP().toString().c_str(), kApChannel, kUdpPort,
                static_cast<unsigned long>(nonce));
  next_frame_ms = millis();
}

void loop() {
  uint8_t buf[128];
  for (int n = udp.parsePacket(); n > 0; n = udp.parsePacket()) {
    const int got = udp.read(buf, sizeof buf);
    // An oversized datagram is passed as length 0, so it fails the length check.
    const size_t len = (n > int(sizeof buf) || got < 0) ? 0 : size_t(got);
    const uint32_t now = millis();
    bridge->on_packet(buf, len, now);
    if (now - last_status_ms >= kStatusPeriodMs) {
      last_status_ms = now;
      uint8_t status[rcb::kStatusLen];
      bridge->build_status(now, status);
      udp.beginPacket(udp.remoteIP(), udp.remotePort());
      udp.write(status, sizeof status);
      udp.endPacket();
    }
  }

  // INAV may send CRSF telemetry back; it is not used.
  while (Serial2.available() > 0) Serial2.read();

  const uint32_t now = millis();
  if (int32_t(now - next_frame_ms) >= 0) {
    next_frame_ms += kFramePeriodMs;
    if (int32_t(now - next_frame_ms) > int32_t(5 * kFramePeriodMs)) next_frame_ms = now;
    uint8_t frame[rcb::kCrsfFrameLen];
    if (bridge->next_frame(now, frame)) {  // false: link stale, send nothing
      Serial2.write(frame, sizeof frame);
      ++frames_sent;
    }
  }

  if (now - last_log_ms >= kLogPeriodMs) {
    last_log_ms = now;
    const rcb::Counters& c = bridge->counters();
    static const char* const kLink[] = {"none", "LIVE", "LOST"};
    Serial.printf(
        "link %s gate %s frames %lu | ok %lu bad_format %lu bad_tag %lu bad_nonce %lu replay %lu\n",
        kLink[bridge->link(now)], bridge->gate_open() ? "open" : "closed",
        static_cast<unsigned long>(frames_sent), static_cast<unsigned long>(c.accepted),
        static_cast<unsigned long>(c.bad_format), static_cast<unsigned long>(c.bad_tag),
        static_cast<unsigned long>(c.bad_nonce), static_cast<unsigned long>(c.replay));
  }
}
