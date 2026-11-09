// Drives rc_bridge.h from stdin so Python can check that the two sides agree
// (tests/test_rc_bridge_cpp.py). One command per line:
//   bridge <key hex> <nonce> <timeout ms>   start a bridge
//   pkt <now ms> <packet hex>               -> "rx <0..4>" (rcb::Rx)
//   frame <now ms>                          -> "frame <hex>" or "frame none"
//   status <now ms>                         -> "status <hex>"
#include <stdio.h>

#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "rc_bridge.h"

static std::string hex(const uint8_t* p, size_t n) {
  static const char* d = "0123456789abcdef";
  std::string s;
  for (size_t i = 0; i < n; ++i) {
    s += d[p[i] >> 4];
    s += d[p[i] & 15];
  }
  return s;
}

int main() {
  std::unique_ptr<rcb::Bridge> bridge;
  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream in(line);
    std::string cmd;
    in >> cmd;
    if (cmd == "bridge") {
      std::string key_hex;
      unsigned long nonce = 0, timeout = 0;
      in >> key_hex >> nonce >> timeout;
      uint8_t key[rcb::kKeyLen];
      if (!rcb::parse_hex(key_hex.c_str(), key, sizeof key)) return 2;
      bridge.reset(new rcb::Bridge(key, uint32_t(nonce), uint32_t(timeout)));
    } else if (cmd == "pkt") {
      unsigned long now = 0;
      std::string pkt_hex;
      in >> now >> pkt_hex;
      std::vector<uint8_t> buf(pkt_hex.size() / 2);
      if (!rcb::parse_hex(pkt_hex.c_str(), buf.data(), buf.size())) return 2;
      printf("rx %d\n", int(bridge->on_packet(buf.data(), buf.size(), uint32_t(now))));
    } else if (cmd == "frame") {
      unsigned long now = 0;
      in >> now;
      uint8_t f[rcb::kCrsfFrameLen];
      if (bridge->next_frame(uint32_t(now), f)) {
        printf("frame %s\n", hex(f, sizeof f).c_str());
      } else {
        printf("frame none\n");
      }
    } else if (cmd == "status") {
      unsigned long now = 0;
      in >> now;
      uint8_t s[rcb::kStatusLen];
      bridge->build_status(uint32_t(now), s);
      printf("status %s\n", hex(s, sizeof s).c_str());
    } else if (!cmd.empty()) {
      return 2;
    }
  }
  return 0;
}
