// RC bridge protocol logic (ADR-0029): authenticated UDP control packets in,
// CRSF RC_CHANNELS_PACKED frames out, and the link watchdog.
//
// Pure C++17 with no Arduino or ESP-IDF calls, so the same code runs on the
// ESP32 and in the host tests (host_test/). The Python side of the protocol
// is src/pnt/flight/rc_link.py; the two must agree byte for byte, which
// tests/test_rc_bridge_cpp.py checks.
//
// Safety model (ADR-0029):
//   - Silence means failsafe: with no valid packet for hb_timeout_ms, next_frame()
//     returns false and the firmware sends nothing, so INAV sees RX loss. Stale
//     values are never re-sent and no substitute "failsafe" values are invented.
//   - KILL always wins: it forces the arm channel and the throttle low.
//   - The arm gate is closed at boot and after every link loss. It opens only on a
//     valid packet with ARM clear, so a link that comes back cannot arm by itself.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace rcb {

// ---------------------------------------------------------------------------
// Wire format (little-endian). Keep in step with src/pnt/flight/rc_link.py.
//
// Control, laptop -> bridge (66 bytes):
//   0  2  magic 'R' 'C'
//   2  1  version (1)
//   3  1  type (1 = control)
//   4  4  boot nonce (uint32), learnt from the bridge's status packet
//   8  8  sequence number (uint64), strictly increasing
//  16 32  16 channels, uint16 microseconds (1000..2000)
//  48  1  flags: bit0 ARM requested, bit1 KILL
//  49  1  reserved, 0
//  50 16  tag: HMAC-SHA256(key, bytes 0..49), first 16 bytes
//
// Status, bridge -> laptop (56 bytes):
//   0  2  magic 'R' 'C'
//   2  1  version (1)
//   3  1  type (2 = status)
//   4  4  boot nonce
//   8  8  last accepted sequence number (0 if none)
//  16 20  counters, uint32 each: accepted, bad_format, bad_tag, bad_nonce, replay
//  36  1  link state: 0 none yet, 1 live, 2 lost
//  37  1  arm gate open (1) or closed (0)
//  38  1  armed channel being sent (1) or not (0)
//  39  1  reserved, 0
//  40 16  tag: HMAC-SHA256(key, bytes 0..39), first 16 bytes
// ---------------------------------------------------------------------------

constexpr uint8_t kMagic0 = 'R';
constexpr uint8_t kMagic1 = 'C';
constexpr uint8_t kVersion = 1;
constexpr uint8_t kTypeControl = 1;
constexpr uint8_t kTypeStatus = 2;

constexpr size_t kKeyLen = 32;
constexpr size_t kTagLen = 16;
constexpr size_t kChannels = 16;
constexpr size_t kControlBody = 50;
constexpr size_t kControlLen = kControlBody + kTagLen;  // 66
constexpr size_t kStatusBody = 40;
constexpr size_t kStatusLen = kStatusBody + kTagLen;  // 56

constexpr uint8_t kFlagArm = 0x01;
constexpr uint8_t kFlagKill = 0x02;

// Channel order is INAV's default `map AETR`, then AUX1 = arm, AUX2 = mode.
constexpr size_t kChRoll = 0;
constexpr size_t kChPitch = 1;
constexpr size_t kChThrottle = 2;
constexpr size_t kChYaw = 3;
constexpr size_t kChArm = 4;   // AUX1, owned by the bridge (from the flags)
constexpr size_t kChMode = 5;  // AUX2

constexpr uint16_t kUsLow = 1000;
constexpr uint16_t kUsMid = 1500;
constexpr uint16_t kUsHigh = 2000;

constexpr uint8_t kLinkNone = 0;
constexpr uint8_t kLinkLive = 1;
constexpr uint8_t kLinkLost = 2;

// CRSF RC_CHANNELS_PACKED: sync, length, type, 22 payload bytes, CRC8.
constexpr uint8_t kCrsfSync = 0xC8;  // address of the flight controller
constexpr uint8_t kCrsfTypeRcChannels = 0x16;
constexpr size_t kCrsfPayloadLen = 22;                       // 16 x 11 bits
constexpr size_t kCrsfFrameLen = 3 + kCrsfPayloadLen + 1;  // 26

// ---------------------------------------------------------------------------
// Little-endian helpers
// ---------------------------------------------------------------------------

inline uint16_t rd16(const uint8_t* p) { return uint16_t(p[0] | (p[1] << 8)); }
inline uint32_t rd32(const uint8_t* p) {
  return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}
inline uint64_t rd64(const uint8_t* p) { return uint64_t(rd32(p)) | (uint64_t(rd32(p + 4)) << 32); }
inline void wr16(uint8_t* p, uint16_t v) {
  p[0] = uint8_t(v);
  p[1] = uint8_t(v >> 8);
}
inline void wr32(uint8_t* p, uint32_t v) {
  for (int i = 0; i < 4; ++i) p[i] = uint8_t(v >> (8 * i));
}
inline void wr64(uint8_t* p, uint64_t v) {
  for (int i = 0; i < 8; ++i) p[i] = uint8_t(v >> (8 * i));
}

// ---------------------------------------------------------------------------
// SHA-256 (FIPS 180-4) and HMAC-SHA256 (RFC 2104)
// ---------------------------------------------------------------------------

class Sha256 {
 public:
  Sha256() { reset(); }

  void reset() {
    static const uint32_t kInit[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    memcpy(h_, kInit, sizeof h_);
    len_ = 0;
    fill_ = 0;
  }

  void update(const uint8_t* data, size_t n) {
    len_ += n;
    while (n > 0) {
      size_t take = 64 - fill_;
      if (take > n) take = n;
      memcpy(buf_ + fill_, data, take);
      fill_ += take;
      data += take;
      n -= take;
      if (fill_ == 64) {
        block(buf_);
        fill_ = 0;
      }
    }
  }

  void finish(uint8_t out[32]) {
    const uint64_t bits = len_ * 8;
    const uint8_t one = 0x80, zero = 0x00;
    update(&one, 1);
    while (fill_ != 56) update(&zero, 1);
    uint8_t len_be[8];
    for (int i = 0; i < 8; ++i) len_be[i] = uint8_t(bits >> (56 - 8 * i));
    update(len_be, 8);
    for (int i = 0; i < 8; ++i) {
      out[4 * i + 0] = uint8_t(h_[i] >> 24);
      out[4 * i + 1] = uint8_t(h_[i] >> 16);
      out[4 * i + 2] = uint8_t(h_[i] >> 8);
      out[4 * i + 3] = uint8_t(h_[i]);
    }
  }

 private:
  static uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

  void block(const uint8_t* p) {
    static const uint32_t K[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i) {
      w[i] = (uint32_t(p[4 * i]) << 24) | (uint32_t(p[4 * i + 1]) << 16) |
             (uint32_t(p[4 * i + 2]) << 8) | uint32_t(p[4 * i + 3]);
    }
    for (int i = 16; i < 64; ++i) {
      const uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      const uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h_[0], b = h_[1], c = h_[2], d = h_[3];
    uint32_t e = h_[4], f = h_[5], g = h_[6], h = h_[7];
    for (int i = 0; i < 64; ++i) {
      const uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const uint32_t ch = (e & f) ^ (~e & g);
      const uint32_t t1 = h + S1 + ch + K[i] + w[i];
      const uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      const uint32_t t2 = S0 + maj;
      h = g;
      g = f;
      f = e;
      e = d + t1;
      d = c;
      c = b;
      b = a;
      a = t1 + t2;
    }
    h_[0] += a;
    h_[1] += b;
    h_[2] += c;
    h_[3] += d;
    h_[4] += e;
    h_[5] += f;
    h_[6] += g;
    h_[7] += h;
  }

  uint32_t h_[8];
  uint64_t len_;
  uint8_t buf_[64];
  size_t fill_;
};

inline void sha256(const uint8_t* data, size_t n, uint8_t out[32]) {
  Sha256 s;
  s.update(data, n);
  s.finish(out);
}

inline void hmac_sha256(const uint8_t* key, size_t key_len, const uint8_t* msg, size_t n,
                        uint8_t out[32]) {
  uint8_t k[64] = {0};
  if (key_len > 64) {
    sha256(key, key_len, k);
  } else {
    memcpy(k, key, key_len);
  }
  uint8_t pad[64];
  uint8_t inner[32];
  for (int i = 0; i < 64; ++i) pad[i] = k[i] ^ 0x36;
  Sha256 s;
  s.update(pad, 64);
  s.update(msg, n);
  s.finish(inner);
  for (int i = 0; i < 64; ++i) pad[i] = k[i] ^ 0x5c;
  s.reset();
  s.update(pad, 64);
  s.update(inner, 32);
  s.finish(out);
}

// Compares without an early exit, so timing does not leak how many bytes matched.
inline bool equal_ct(const uint8_t* a, const uint8_t* b, size_t n) {
  uint8_t diff = 0;
  for (size_t i = 0; i < n; ++i) diff |= uint8_t(a[i] ^ b[i]);
  return diff == 0;
}

// Parses exactly 2*n hex digits into out. Returns false on any other input.
inline bool parse_hex(const char* s, uint8_t* out, size_t n) {
  if (s == nullptr || strlen(s) != 2 * n) return false;
  for (size_t i = 0; i < 2 * n; ++i) {
    const char c = s[i];
    uint8_t v;
    if (c >= '0' && c <= '9') {
      v = uint8_t(c - '0');
    } else if (c >= 'a' && c <= 'f') {
      v = uint8_t(c - 'a' + 10);
    } else if (c >= 'A' && c <= 'F') {
      v = uint8_t(c - 'A' + 10);
    } else {
      return false;
    }
    if (i % 2 == 0) {
      out[i / 2] = uint8_t(v << 4);
    } else {
      out[i / 2] |= v;
    }
  }
  return true;
}

// ---------------------------------------------------------------------------
// CRSF
// ---------------------------------------------------------------------------

// CRC-8/DVB-S2: polynomial 0xD5, initial value 0, no reflection.
inline uint8_t crc8_dvb_s2(const uint8_t* p, size_t n) {
  uint8_t crc = 0;
  for (size_t i = 0; i < n; ++i) {
    crc ^= p[i];
    for (int b = 0; b < 8; ++b) crc = (crc & 0x80) ? uint8_t((crc << 1) ^ 0xD5) : uint8_t(crc << 1);
  }
  return crc;
}

// Microseconds to CRSF ticks: 1000 us -> 192, 1500 -> 992, 2000 -> 1792 (the
// ELRS/TBS convention). Clamped to 1000..2000 us first. Integer maths only, and
// non-negative throughout, so Python's // gives the same result.
inline uint16_t us_to_crsf(uint16_t us) {
  if (us < kUsLow) us = kUsLow;
  if (us > kUsHigh) us = kUsHigh;
  return uint16_t((uint32_t(us - kUsLow) * 8 + 2) / 5 + 192);
}

// Packs 16 channels of 11-bit CRSF ticks, least significant bit first.
inline void pack_crsf_channels(const uint16_t ticks[kChannels], uint8_t out[kCrsfFrameLen]) {
  out[0] = kCrsfSync;
  out[1] = uint8_t(kCrsfPayloadLen + 2);  // type + payload + crc = 24
  out[2] = kCrsfTypeRcChannels;
  memset(out + 3, 0, kCrsfPayloadLen);
  size_t bit = 0;
  for (size_t ch = 0; ch < kChannels; ++ch) {
    const uint16_t v = ticks[ch] & 0x7FF;
    for (int b = 0; b < 11; ++b, ++bit) {
      if ((v >> b) & 1) out[3 + bit / 8] |= uint8_t(1 << (bit % 8));
    }
  }
  out[kCrsfFrameLen - 1] = crc8_dvb_s2(out + 2, kCrsfPayloadLen + 1);
}

// ---------------------------------------------------------------------------
// Bridge: packet check, channel state and the watchdog
// ---------------------------------------------------------------------------

enum class Rx : uint8_t { Accepted = 0, BadFormat, BadTag, BadNonce, Replay };

struct Counters {
  uint32_t accepted = 0;
  uint32_t bad_format = 0;
  uint32_t bad_tag = 0;
  uint32_t bad_nonce = 0;
  uint32_t replay = 0;
};

class Bridge {
 public:
  // key: kKeyLen bytes. nonce: random per boot, never 0. hb_timeout_ms: watchdog.
  Bridge(const uint8_t key[kKeyLen], uint32_t nonce, uint32_t hb_timeout_ms)
      : nonce_(nonce), hb_timeout_ms_(hb_timeout_ms) {
    memcpy(key_, key, kKeyLen);
    for (size_t i = 0; i < kChannels; ++i) ticks_[i] = us_to_crsf(kUsMid);
    ticks_[kChThrottle] = us_to_crsf(kUsLow);
    ticks_[kChArm] = us_to_crsf(kUsLow);
  }

  // Checks one datagram. Only an accepted packet changes the channels or feeds the
  // watchdog; anything else just bumps a counter.
  Rx on_packet(const uint8_t* p, size_t n, uint32_t now_ms) {
    expire(now_ms);
    if (n != kControlLen || p[0] != kMagic0 || p[1] != kMagic1 || p[2] != kVersion ||
        p[3] != kTypeControl || p[49] != 0) {
      ++counters_.bad_format;
      return Rx::BadFormat;
    }
    uint8_t tag[32];
    hmac_sha256(key_, kKeyLen, p, kControlBody, tag);
    if (!equal_ct(tag, p + kControlBody, kTagLen)) {
      ++counters_.bad_tag;
      return Rx::BadTag;
    }
    if (rd32(p + 4) != nonce_) {
      ++counters_.bad_nonce;
      return Rx::BadNonce;
    }
    const uint64_t seq = rd64(p + 8);
    if (have_seq_ && seq <= last_seq_) {
      ++counters_.replay;
      return Rx::Replay;
    }
    have_seq_ = true;
    last_seq_ = seq;

    const uint8_t flags = p[48];
    const bool kill = (flags & kFlagKill) != 0;
    const bool arm_req = (flags & kFlagArm) != 0 && !kill;
    if (!arm_req) gate_open_ = true;  // a disarmed packet opens the arm gate
    for (size_t i = 0; i < kChannels; ++i) ticks_[i] = us_to_crsf(rd16(p + 16 + 2 * i));
    armed_out_ = arm_req && gate_open_;
    ticks_[kChArm] = us_to_crsf(armed_out_ ? kUsHigh : kUsLow);
    if (kill) ticks_[kChThrottle] = us_to_crsf(kUsLow);

    last_valid_ms_ = now_ms;
    link_ = kLinkLive;
    ++counters_.accepted;
    return Rx::Accepted;
  }

  // Fills out with the CRSF frame to send now, or returns false: send nothing.
  bool next_frame(uint32_t now_ms, uint8_t out[kCrsfFrameLen]) {
    expire(now_ms);
    if (link_ != kLinkLive) return false;
    pack_crsf_channels(ticks_, out);
    return true;
  }

  // Authenticated status for the laptop. Returns its length (kStatusLen).
  size_t build_status(uint32_t now_ms, uint8_t out[kStatusLen]) {
    expire(now_ms);
    out[0] = kMagic0;
    out[1] = kMagic1;
    out[2] = kVersion;
    out[3] = kTypeStatus;
    wr32(out + 4, nonce_);
    wr64(out + 8, have_seq_ ? last_seq_ : 0);
    wr32(out + 16, counters_.accepted);
    wr32(out + 20, counters_.bad_format);
    wr32(out + 24, counters_.bad_tag);
    wr32(out + 28, counters_.bad_nonce);
    wr32(out + 32, counters_.replay);
    out[36] = link_;
    out[37] = gate_open_ ? 1 : 0;
    out[38] = (link_ == kLinkLive && armed_out_) ? 1 : 0;
    out[39] = 0;
    uint8_t tag[32];
    hmac_sha256(key_, kKeyLen, out, kStatusBody, tag);
    memcpy(out + kStatusBody, tag, kTagLen);
    return kStatusLen;
  }

  uint8_t link(uint32_t now_ms) {
    expire(now_ms);
    return link_;
  }
  bool gate_open() const { return gate_open_; }
  const Counters& counters() const { return counters_; }
  uint32_t nonce() const { return nonce_; }

 private:
  // The watchdog. Latches the loss, so millis() wrapping round cannot revive old values.
  void expire(uint32_t now_ms) {
    if (link_ == kLinkLive && uint32_t(now_ms - last_valid_ms_) >= hb_timeout_ms_) {
      link_ = kLinkLost;
      gate_open_ = false;
      armed_out_ = false;
    }
  }

  uint8_t key_[kKeyLen];
  uint32_t nonce_;
  uint32_t hb_timeout_ms_;
  uint16_t ticks_[kChannels];
  bool have_seq_ = false;
  uint64_t last_seq_ = 0;
  uint32_t last_valid_ms_ = 0;
  uint8_t link_ = kLinkNone;
  bool gate_open_ = false;
  bool armed_out_ = false;
  Counters counters_;
};

}  // namespace rcb
