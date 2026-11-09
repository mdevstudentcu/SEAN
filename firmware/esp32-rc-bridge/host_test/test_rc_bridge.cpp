// Host unit tests for rc_bridge.h. Built and run by tests/test_rc_bridge_cpp.py:
//   g++ -std=c++17 -Wall -Wextra -Werror -I lib/rc_bridge host_test/test_rc_bridge.cpp
// Exit status 0 means every check passed.
#include <stdio.h>
#include <string>

#include "rc_bridge.h"

using namespace rcb;

static int failures = 0;
#define CHECK(cond)                                                  \
  do {                                                               \
    if (!(cond)) {                                                   \
      ++failures;                                                    \
      fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
    }                                                                \
  } while (0)

static std::string hex(const uint8_t* p, size_t n) {
  static const char* d = "0123456789abcdef";
  std::string s;
  for (size_t i = 0; i < n; ++i) {
    s += d[p[i] >> 4];
    s += d[p[i] & 15];
  }
  return s;
}

static const uint8_t kKey[kKeyLen] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
                                      17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32};
constexpr uint32_t kNonce = 0xA5A5F00D;
constexpr uint32_t kTimeout = 200;

// Builds a control packet the way the laptop does (rc_link.py).
static void control(uint8_t out[kControlLen], uint64_t seq, const uint16_t us[kChannels],
                    uint8_t flags, uint32_t nonce = kNonce, const uint8_t* key = kKey) {
  out[0] = kMagic0;
  out[1] = kMagic1;
  out[2] = kVersion;
  out[3] = kTypeControl;
  wr32(out + 4, nonce);
  wr64(out + 8, seq);
  for (size_t i = 0; i < kChannels; ++i) wr16(out + 16 + 2 * i, us[i]);
  out[48] = flags;
  out[49] = 0;
  uint8_t tag[32];
  hmac_sha256(key, kKeyLen, out, kControlBody, tag);
  memcpy(out + kControlBody, tag, kTagLen);
}

static void neutral(uint16_t us[kChannels]) {
  for (size_t i = 0; i < kChannels; ++i) us[i] = kUsMid;
  us[kChThrottle] = kUsLow;
  us[kChArm] = kUsLow;
}

// One channel of a packed frame, in CRSF ticks.
static uint16_t unpack(const uint8_t* frame, size_t ch) {
  uint16_t v = 0;
  for (int b = 0; b < 11; ++b) {
    const size_t bit = ch * 11 + b;
    if (frame[3 + bit / 8] & (1 << (bit % 8))) v |= uint16_t(1 << b);
  }
  return v;
}

static void test_sha256_and_hmac() {
  uint8_t out[32];
  sha256(reinterpret_cast<const uint8_t*>("abc"), 3, out);
  CHECK(hex(out, 32) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  sha256(nullptr, 0, out);
  CHECK(hex(out, 32) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  // Two blocks of padding (56-byte message).
  const char* m56 = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
  sha256(reinterpret_cast<const uint8_t*>(m56), strlen(m56), out);
  CHECK(hex(out, 32) == "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");

  // RFC 4231 test cases 1, 2 and 6.
  uint8_t k1[20];
  memset(k1, 0x0b, sizeof k1);
  hmac_sha256(k1, sizeof k1, reinterpret_cast<const uint8_t*>("Hi There"), 8, out);
  CHECK(hex(out, 32) == "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7");
  const char* m2 = "what do ya want for nothing?";
  hmac_sha256(reinterpret_cast<const uint8_t*>("Jefe"), 4, reinterpret_cast<const uint8_t*>(m2),
              strlen(m2), out);
  CHECK(hex(out, 32) == "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
  uint8_t k6[131];
  memset(k6, 0xaa, sizeof k6);
  const char* m6 = "Test Using Larger Than Block-Size Key - Hash Key First";
  hmac_sha256(k6, sizeof k6, reinterpret_cast<const uint8_t*>(m6), strlen(m6), out);
  CHECK(hex(out, 32) == "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
}

static void test_parse_hex() {
  uint8_t out[2];
  CHECK(parse_hex("0aFf", out, 2) && out[0] == 0x0a && out[1] == 0xff);
  CHECK(!parse_hex("0aF", out, 2));
  CHECK(!parse_hex("0aFg", out, 2));
  CHECK(!parse_hex(nullptr, out, 2));
}

static void test_crsf() {
  // CRC-8/DVB-S2 check value.
  CHECK(crc8_dvb_s2(reinterpret_cast<const uint8_t*>("123456789"), 9) == 0xBC);

  CHECK(us_to_crsf(1000) == 192);
  CHECK(us_to_crsf(1500) == 992);
  CHECK(us_to_crsf(2000) == 1792);
  CHECK(us_to_crsf(900) == 192);    // clamped
  CHECK(us_to_crsf(2500) == 1792);  // clamped
  CHECK(us_to_crsf(1001) == 194);   // 193.6 rounds to 194

  uint16_t ticks[kChannels] = {0};
  uint8_t f[kCrsfFrameLen];
  ticks[0] = 0x7FF;
  ticks[1] = 1;
  pack_crsf_channels(ticks, f);
  CHECK(f[0] == 0xC8 && f[1] == 24 && f[2] == 0x16);
  CHECK(f[3] == 0xFF && f[4] == 0x0F && f[5] == 0x00);  // ch0 = 11 ones, ch1 bit 0 at bit 11
  CHECK(f[25] == crc8_dvb_s2(f + 2, 23));

  // All channels centred: the well-known 11-byte pattern, twice.
  for (size_t i = 0; i < kChannels; ++i) ticks[i] = 992;
  pack_crsf_channels(ticks, f);
  CHECK(hex(f + 3, 22) == "e0031ff8c0073ef0810f7ce0031ff8c0073ef0810f7c");
  for (size_t i = 0; i < kChannels; ++i) CHECK(unpack(f, i) == 992);
}

static void test_watchdog_silence_after_timeout() {
  Bridge b(kKey, kNonce, kTimeout);
  uint8_t frame[kCrsfFrameLen];
  CHECK(!b.next_frame(0, frame));  // boot: nothing until a valid packet
  CHECK(b.link(0) == kLinkNone);

  uint16_t us[kChannels];
  neutral(us);
  uint8_t p[kControlLen];
  control(p, 1, us, 0);
  CHECK(b.on_packet(p, sizeof p, 1000) == Rx::Accepted);
  CHECK(b.next_frame(1000, frame));
  CHECK(b.next_frame(1199, frame));   // 199 ms after the last packet: still live
  CHECK(!b.next_frame(1200, frame));  // 200 ms: silence
  CHECK(b.link(1200) == kLinkLost);
  // The loss is latched: millis() wrapping round 2^32 does not revive old values.
  CHECK(!b.next_frame(1000 + 50, frame));
  CHECK(!b.next_frame(1000u + 0xFFFFFFFFu, frame));
  // A new valid packet brings frames back.
  control(p, 2, us, 0);
  CHECK(b.on_packet(p, sizeof p, 5000) == Rx::Accepted);
  CHECK(b.next_frame(5000, frame));
}

static void test_rejections_do_not_feed_watchdog() {
  Bridge b(kKey, kNonce, kTimeout);
  uint16_t us[kChannels];
  neutral(us);
  uint8_t p[kControlLen];
  uint8_t frame[kCrsfFrameLen];
  control(p, 10, us, 0);
  CHECK(b.on_packet(p, sizeof p, 0) == Rx::Accepted);

  // Stale sequence: the same packet again, and an older one.
  CHECK(b.on_packet(p, sizeof p, 100) == Rx::Replay);
  uint8_t old[kControlLen];
  control(old, 9, us, 0);
  CHECK(b.on_packet(old, sizeof old, 100) == Rx::Replay);

  // Forged tag: one payload bit flipped, tag left alone.
  uint8_t forged[kControlLen];
  control(forged, 11, us, 0);
  forged[16] ^= 1;
  CHECK(b.on_packet(forged, sizeof forged, 100) == Rx::BadTag);

  // Signed with the wrong key.
  uint8_t other_key[kKeyLen];
  memset(other_key, 0x55, sizeof other_key);
  uint8_t wrong[kControlLen];
  control(wrong, 12, us, 0, kNonce, other_key);
  CHECK(b.on_packet(wrong, sizeof wrong, 100) == Rx::BadTag);

  // Valid tag but another boot's nonce (recorded before a reboot).
  uint8_t stale_boot[kControlLen];
  control(stale_boot, 13, us, 0, kNonce ^ 1);
  CHECK(b.on_packet(stale_boot, sizeof stale_boot, 100) == Rx::BadNonce);

  // Wrong length, magic, type.
  CHECK(b.on_packet(p, sizeof p - 1, 100) == Rx::BadFormat);
  uint8_t bad[kControlLen];
  memcpy(bad, p, sizeof bad);
  bad[0] = 'X';
  CHECK(b.on_packet(bad, sizeof bad, 100) == Rx::BadFormat);

  const Counters& c = b.counters();
  CHECK(c.accepted == 1 && c.replay == 2 && c.bad_tag == 2 && c.bad_nonce == 1 && c.bad_format == 2);

  // None of the rejected packets moved the watchdog: silence 200 ms after the valid one.
  CHECK(b.next_frame(199, frame));
  CHECK(!b.next_frame(200, frame));
  // The replay counter rejected seq 10, so the sequence high-water mark is still 10.
  control(p, 11, us, 0);
  CHECK(b.on_packet(p, sizeof p, 300) == Rx::Accepted);
}

static void test_kill_and_arm_gate() {
  Bridge b(kKey, kNonce, kTimeout);
  uint16_t us[kChannels];
  neutral(us);
  uint8_t p[kControlLen];
  uint8_t frame[kCrsfFrameLen];
  uint64_t seq = 100;

  // Boot is disarmed: an ARM request in the very first packet is not forwarded.
  us[kChArm] = kUsHigh;
  control(p, ++seq, us, kFlagArm);
  CHECK(b.on_packet(p, sizeof p, 0) == Rx::Accepted);
  CHECK(!b.gate_open());
  CHECK(b.next_frame(0, frame) && unpack(frame, kChArm) == 192);

  // A disarmed packet opens the gate; then ARM goes out.
  us[kChArm] = kUsLow;
  control(p, ++seq, us, 0);
  b.on_packet(p, sizeof p, 10);
  CHECK(b.gate_open());
  us[kChArm] = kUsHigh;
  us[kChThrottle] = 1300;
  control(p, ++seq, us, kFlagArm);
  b.on_packet(p, sizeof p, 20);
  CHECK(b.next_frame(20, frame) && unpack(frame, kChArm) == 1792);
  CHECK(unpack(frame, kChThrottle) == us_to_crsf(1300));

  // KILL wins over ARM, and over whatever the laptop put in the channels.
  control(p, ++seq, us, kFlagArm | kFlagKill);
  b.on_packet(p, sizeof p, 30);
  CHECK(b.next_frame(30, frame));
  CHECK(unpack(frame, kChArm) == 192 && unpack(frame, kChThrottle) == 192);

  // The bridge owns the arm channel: a high AUX1 without the ARM flag is sent low.
  control(p, ++seq, us, 0);
  b.on_packet(p, sizeof p, 40);
  CHECK(b.next_frame(40, frame) && unpack(frame, kChArm) == 192);

  // After a link loss the gate is closed again: ARM is held low until a disarmed packet.
  control(p, ++seq, us, kFlagArm);
  b.on_packet(p, sizeof p, 50);
  CHECK(b.next_frame(50, frame) && unpack(frame, kChArm) == 1792);
  CHECK(!b.next_frame(250, frame));
  control(p, ++seq, us, kFlagArm);
  b.on_packet(p, sizeof p, 400);
  CHECK(!b.gate_open());
  CHECK(b.next_frame(400, frame) && unpack(frame, kChArm) == 192);
}

static void test_status() {
  Bridge b(kKey, kNonce, kTimeout);
  uint8_t s[kStatusLen];
  CHECK(b.build_status(0, s) == kStatusLen);
  CHECK(s[0] == 'R' && s[1] == 'C' && s[3] == kTypeStatus && rd32(s + 4) == kNonce);
  CHECK(s[36] == kLinkNone && s[37] == 0 && s[38] == 0);
  uint8_t tag[32];
  hmac_sha256(kKey, kKeyLen, s, kStatusBody, tag);
  CHECK(equal_ct(tag, s + kStatusBody, kTagLen));
}

int main() {
  test_sha256_and_hmac();
  test_parse_hex();
  test_crsf();
  test_watchdog_silence_after_timeout();
  test_rejections_do_not_feed_watchdog();
  test_kill_and_arm_gate();
  test_status();
  if (failures == 0) printf("rc_bridge host tests: all passed\n");
  return failures == 0 ? 0 : 1;
}
