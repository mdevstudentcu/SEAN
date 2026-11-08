# AGENTS.md

Guidance for coding agents (and people) working in this repo. Read this before changing anything.

## What this repo is

Our entry for **Hack the Horizons (Honeywell Aerospace × Carleton), Challenge 2: resilient navigation in GPS-denied environments.** A removable, receive-only payload records signals of opportunity (cellular, ADS-B, VOR, Wi-Fi, broadcast time) plus IMU, barometer and GPS. A ground laptop fuses them into position and time with numerical confidence, and shows it live. Judging is Thu 2026-11-12.

| Path | What | Runs on |
| --- | --- | --- |
| `systems/` | **Source of truth**: requirements (REQ), assumptions (ASM), decisions (ADR), interfaces (ICD), risks (RSK), safety, verification. Read `systems/README.md` first | — |
| `src/pnt/core/` | `Measurement` record, time (GPS ns), frames (WGS84/ECEF/ENU) | everywhere |
| `src/pnt/sources/` | The three interchangeable sources: `sim`, `replay`, `live` (ADR-0004) | laptop |
| `src/pnt/sim/` | Trajectories, per-source error models, fault injection, `scenarios/*.yaml` | laptop |
| `src/pnt/frontends/` | Raw signal → observables (LTE, ADS-B, VOR, Wi-Fi, CHU, GNSS, IMU) | laptop |
| `src/pnt/nav/` | Estimators. `baseline.py` is the deliberately simple reference filter | laptop |
| `src/pnt/integrity/` | Protection levels, fault detection, per-source trust | laptop |
| `src/pnt/payload/` | Recorder and streamer | **Raspberry Pi 4B** |
| `src/pnt/dashboard/` | Operator panel (FastAPI + static page) | laptop |
| `firmware/esp32-hub/` | ESP32-S3 sensor hub (PlatformIO): IMU, baro, PPS, Wi-Fi → MAVLink over USB | ESP32-S3 |
| `flight/` | ArduPilot params, scripted missions (pymavlink), SITL | FC / laptop |
| `deploy/pi/` | Pi setup, systemd units, chrony + PPS config | Pi |
| `analysis/` | Monte Carlo and figure scripts; figures go in `analysis/results/` | laptop |
| `data/reference/` | Small committed reference data (towers, navaids, TLEs), each with source + date | — |

## Commands

Python ≥ 3.11 with [uv](https://docs.astral.sh/uv/); commands live in the `justfile` ([just](https://just.systems)).

```bash
just setup                 # uv sync --extra ground --extra dev
just sim gps-outage        # scenario -> data/sessions/sim-*.mcap + metrics
just eval gps-outage 50    # Monte Carlo
just replay <file.mcap>    # re-run nav over a log
just test && just lint
just gen                   # regenerate MAVLink code from systems/icd/pnt.xml
```

Without uv/just: `python -m venv .venv && .venv/bin/pip install -e '.[ground,dev]'`, then `.venv/bin/pnt sim gps-outage`.

## Rules

- **`systems/` wins.** If code or a README disagrees with a requirement, ADR or ICD, the `systems/` file is right. Flag the conflict; don't silently pick one.
- **Unknown values are `TBD` (no value yet) or `TBC` (proposed, not confirmed)**, never "about".
- **Don't make engineering decisions in passing.** A new choice of approach, part or target value gets an ADR (`systems/adr/0000-template.md`) or an open question, not a silent edit.
- **The ICDs are contracts between the two software owners.** A PR that changes `systems/icd/*` (the `Measurement` record, `pnt.xml`, the session layout) carries the `icd` label and needs the other owner's approval before merging.
- **Generated code is never edited by hand.** Change `systems/icd/pnt.xml`, run `just gen`, commit both.
- **Time is int64 GPS nanoseconds everywhere** (`pnt.core.time`). Positions are ENU metres about the session origin; lat/lon only for display (ADR-0008).
- **Never add a transmit path.** The payload is receive-only (ADR-0001, REQ-07). No code may key an SDR transmitter, generate GNSS signals, or jam anything. Jamming and spoofing exist only as software fault injection in `sim/` and `sources/`.
- **Decode only what is meant for everyone**: sync signals, pilots, beacons, navaid and broadcast fields. Never decode or store communication content. Wi-Fi BSSIDs are hashed at capture (ADR-0011, Radiocommunication Act s.9(2)).
- **Raw data never goes in git.** Sessions live in `data/sessions/` (ignored). Only small reference CSVs and test fixtures are committed.
- **Every reported number must be reproducible** from a committed scenario, or a named session plus a commit hash (REQ-10).
- Don't commit the kickoff deck or anything marked confidential.

## Git

- **Never commit to `main` directly.** All work happens on a branch and lands through a pull request, including docs and one-line fixes.
- Branch from an up-to-date `main`: `name/<type>/<issue>-<short-name>` (e.g. `shrikar/feat/3-plots`). One issue per branch where possible.
- [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`, imperative, ≤ 72 chars. Scopes: `systems`, `core`, `sim`, `nav`, `integrity`, `frontends`, `payload`, `dashboard`, `firmware`, `flight`, `deploy`, `analysis`, `ci`. One logical change per commit.
- **No AI attribution:** no `Co-Authored-By: Claude`, `Claude-Session:` or "Generated with" lines in commits or PR descriptions.
- PRs: title in Conventional Commit form, body follows `.github/pull_request_template.md` and links the issue (`Closes #n`). CI must be green. `CODEOWNERS` requests a review from the other owner; `icd` PRs need their approval. New issues use the Task or Bug template.
- Merge with "Rebase and merge" (or "Squash and merge" for messy branches); delete the branch after.
- Keep branches current by rebasing on `origin/main`; never merge `main` into a branch, and don't use GitHub's "Update branch" button (it makes a merge commit).
- Check `git status` before committing so stray files (sessions, PDFs) don't get swept in.
