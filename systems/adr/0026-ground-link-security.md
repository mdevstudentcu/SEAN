# ADR-0026: Ground links are authenticated and session logs are tamper-evident

- **Status:** Accepted for CurveZMQ on the ZeroMQ links (2026-11-09, #89). MAVLink 2 signing is `TBC`. Hash-chained logs come after judging.
- **Date:** 2026-11-09
- **Deciders:** Shrikar Vempati, M. Elshoubky
- **Traces to:** REQ-04, REQ-05, REQ-07, REQ-08, REQ-10, ADR-0005, ADR-0007, ADR-0009, ADR-0018, ADR-0020

## Context

Every radio defence we build checks signals in the air. An attacker on a ground link skips all of them by injecting well-formed records that already look right. Our links today:

- **Payload → laptop:** ZeroMQ PUB/SUB over Wi-Fi, carrying msgpack `Measurement` records (ADR-0009). `src/pnt/sources/live.py` subscribes with no authentication.
- **Base → laptop:** the ground reference station streams over Ethernet (ADR-0020). A forged base corrupts every differential correction.
- **MAVLink:** flight-controller telemetry and, if the Pi Zero hub returns, hub to recorder (ADR-0018 keeps ADR-0005's dialect). The flight controller runs INAV (ADR-0028), and the recorder only listens to it.
- **Logs:** MCAP chunks carry CRC32s, which catch corruption but not deliberate edits ([MCAP spec](https://mcap.dev/spec)). REQ-10 needs results we can trust later.

Tools we can use:

- **MAVLink 2 signing** appends a 48-bit truncated SHA-256 signature over the packet, a 32-byte shared key and a timestamp that must keep increasing, which rejects replays ([MAVLink message signing](https://mavlink.io/en/guide/message_signing.html)).
- **CurveZMQ** is built into ZeroMQ. It authenticates and encrypts with Curve25519 keys, and the server can allow-list client keys ([26/CURVEZMQ](https://rfc.zeromq.org/spec/26/), [25/ZMTP-CURVE](https://rfc.zeromq.org/spec/25/), [27/ZAP](https://rfc.zeromq.org/spec/27/)).
- **A hash chain** makes a log tamper-evident: each entry commits to the one before it ([Schneier & Kelsey, ACM TISSEC 1999](https://doi.org/10.1145/317087.317089)).

## Options

| Link | Option | Pros | Cons |
| --- | --- | --- | --- |
| ZeroMQ | A. CurveZMQ with an allow-list of client keys | Already in libzmq, and pyzmq is already in both extras; authenticates and encrypts | Needs libzmq built with CURVE: true on the laptop venv (`zmq.has("curve")`, libzmq 4.3.5), `TBC` on the Pi; key distribution |
| ZeroMQ | B. WireGuard tunnel between hosts | Covers all traffic, not only ZeroMQ | OS-level install and config on three hosts; a new system dependency needing sign-off |
| ZeroMQ | C. Our own per-message HMAC (stdlib) with a counter | No new library | Home-made protocol; replay handling is ours; no confidentiality |
| ZeroMQ | D. Rely on an isolated network | Nothing to build | Campus and venue Wi-Fi are shared |
| MAVLink | MAVLink 2 signing | Standard, and pymavlink supports it | Key on each end; an unsigned-message policy to choose |
| Logs | Hash chain whose head is also held off the recorder | An edit or truncation is detectable | Changes the session layout (ICD) |
| Logs | MCAP CRC only (today) | Nothing to build | Detects accidents, not tampering |

## Decision

Authenticate and encrypt every ZeroMQ link with CurveZMQ (option A). Built in #89:
- Each host has its own key pair, made with `pnt keys gen --role payload|reference|laptop`. The secret key stays on that host in `~/.config/pnt/keys/<role>.key_secret` (mode 600). Peers' public keys are copied by hand into `trusted/` (`pnt keys trust`), and people compare key ids (`deploy/pi/RUNBOOK.md`, Keys).
- The payload and the base are CurveZMQ servers. A ZAP handler admits only trusted laptop keys.
- The laptop pins each endpoint's server key, so a host without the Pi's secret key cannot complete the handshake.
- `pnt record` and `pnt live` refuse to stream without keys, and refuse when libzmq lacks CURVE. Plaintext needs an explicit `--insecure` and prints a warning. Each session's `meta.yaml` `notes` say whether its stream was authenticated (no ICD change).

MAVLink 2 signing is `TBC`. The flight controller runs INAV (ADR-0028), the recorder only listens to it, and whether INAV signs MAVLink is unconfirmed. Hash-chaining the session logs is the design, but it waits until after judging.

We chose CurveZMQ over WireGuard (decided 2026-11-09):
- pyzmq is already a dependency, and the laptop's libzmq has CURVE.
- WireGuard would add a system dependency and set-up on three hosts.
- Whether the Pi's libzmq has CURVE is checked on day 1 (#88).

## Consequences

- **Keys are never in git.** They are generated per host and live in `~/.config/pnt/keys` (`*.key_secret` is also git-ignored). The owner signed off on the key-handling code on 2026-11-09 (`AGENTS.md`).
- **A stolen secret key defeats it.** Whoever copies a Pi's `*.key_secret` (or its SD card) can impersonate that Pi. The key is then replaced (`pnt keys gen --force`, then re-trusted on the peers). Nothing detects the theft.
- **Unauthenticated input is dropped, not fused.**
  - CurveZMQ drops it at the handshake or at the message, before `LiveSource` decodes anything. A message that fails authentication ends that connection, and libzmq does not reopen it, so `pnt live` must be restarted (fails closed).
  - The Pi counts refused laptop keys in its session notes. The panel showing per-link counts of rejected, unsigned and replayed messages is `TBD`.
  - Which unsigned MAVLink messages, if any, are still accepted is `TBD`; the default is none.
- **Session logs (roadmap, not before judging).** The hash chain needs an `icd` PR. For the demo, #89 covers MAVLink signing, CurveZMQ, and a test that a forged message is rejected.
  - Each recorded record (or chunk, `TBD`) carries a hash over the previous hash and its own content.
  - The head is streamed to the laptop every `TBD` s, so an edit, a deletion or a truncation on the payload is detectable.
  - This changes `systems/icd/session.md`, so it needs an `icd` PR with the other owner's approval. Old sessions still load and are marked unverified.
- **Base station (ADR-0020):** an authenticated link is a precondition for trusting the base. The base is still its own fault hypothesis.
- **Limits:** this does not defend a payload or base that has been physically compromised. The logs then help forensics, not prevention.
- **Cost:** the CPU and latency cost on the Pi is `TBD`. The day-1 test (#88) streams with CurveZMQ, and the cost is checked against REQ-05.
- **Radio:** no new radio. The Wi-Fi and telemetry links are the existing licence-exempt ones (REQ-07).
- **Evidence (#89):** loopback tests (`tests/test_link_security.py`) show these attacks fail, each against a control that succeeds without the protection: an impersonating server, an untrusted client, and a stream tampered with in flight. They also show the stream is encrypted on the wire. Log-edit detection waits for the hash chain.
- **Reopen if:**
  - libzmq on the Pi lacks CURVE (then B or C; until then the Pi records with `--no-stream`, or `--insecure` on a private link)
  - signing or encryption breaks the REQ-05 latency target
