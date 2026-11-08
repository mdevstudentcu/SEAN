# Wi-Fi FTM responder

Firmware for the spare ESP32-S3 boards placed at surveyed points around the indoor flight area. Each runs a SoftAP with 802.11mc FTM responder enabled, giving the payload metre-level ranges (and indoor reference positions).

Status: not started. Based on ESP-IDF's `wifi/ftm` example. These are deployed beacons, not signals of opportunity; results using them are reported separately.
