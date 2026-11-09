# ADR-0026: Ground links are authenticated and session logs are tamper-evident

- **Status:** Proposed
- **Date:** 2026-11-09
- **Deciders:** team
- **Traces to:** REQ-04, REQ-05, REQ-07, REQ-08, REQ-10, ADR-0005, ADR-0007, ADR-0009, ADR-0018, ADR-0020

## Context

Every radio defence we build checks signals in the air. An attacker on a ground link skips all of them by injecting well-formed records that already look right. Our links today:

- **Payload → laptop:** ZeroMQ PUB/SUB over Wi-Fi, carrying msgpack `Measurement` records (ADR-0009). `src/pnt/sources/live.py` subscribes with no authentication.
- **Base → laptop:** the ground reference station streams over Ethernet (ADR-0020). A forged base corrupts every differential correction.
- **MAVLink:** flight-controller telemetry and, if the Pi Zero hub returns, hub to recorder (ADR-0018 keeps ADR-0005's dialect).
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

Sign MAVLink 2 traffic and authenticate every ZeroMQ link with CurveZMQ (option A). Hash-chaining the session logs is the design, but it waits until after judging.

We chose CurveZMQ over WireGuard (decided 2026-11-09):
- pyzmq is already a dependency, and the laptop's libzmq has CURVE.
- WireGuard would add a system dependency and set-up on three hosts.
- Whether the Pi's libzmq has CURVE is checked on day 1 (#88).

## Consequences

- **Keys are never in git.** They are generated per deployment on each host, and where they live is `TBD`. Code that handles keys or credentials needs an owner's sign-off before it is written (`AGENTS.md`).
- **Unauthenticated input is dropped, not fused.**
  - The panel shows per-link counts of rejected, unsigned and replayed messages.
  - Which unsigned MAVLink messages, if any, are still accepted is `TBD`; the default is none.
- **Session logs (roadmap, not before judging).** The hash chain needs an `icd` PR. For the demo, #89 covers MAVLink signing, CurveZMQ, and a test that a forged message is rejected.
  - Each recorded record (or chunk, `TBD`) carries a hash over the previous hash and its own content.
  - The head is streamed to the laptop every `TBD` s, so an edit, a deletion or a truncation on the payload is detectable.
  - This changes `systems/icd/session.md`, so it needs an `icd` PR with the other owner's approval. Old sessions still load and are marked unverified.
- **Base station (ADR-0020):** an authenticated link is a precondition for trusting the base. The base is still its own fault hypothesis.
- **Limits:** this does not defend a payload or base that has been physically compromised. The logs then help forensics, not prevention.
- **Cost:** the CPU and latency cost on the Pi is `TBD` and is checked against REQ-05.
- **Radio:** no new radio. The Wi-Fi and telemetry links are the existing licence-exempt ones (REQ-07).
- **Evidence (#89):** a test shows that a forged or modified message is rejected and that a log edit is detected.
- **Reopen if:**
  - libzmq on the Pi lacks CURVE (then B or C)
  - signing or encryption breaks the REQ-05 latency target
