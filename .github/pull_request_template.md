<!-- Dead to the point: single lines or short bullets. No background, no restating the issue or diff. Rules: systems/quality.md -->

## What and why

<!-- One or two lines. Link the issue: "Closes #12". -->

## Traces to

<!-- REQ-nn, UC-nn, ADR-nnnn, ICD-<name>, RSK-nn this implements or changes, or "none". -->

## Evidence

<!-- Images first: plots, screenshots, photos, before/after against main. Caption each with scenario/session, commit and kind (sim, replay, real session, hardware). If no image can show it: "No image: <reason>". -->

## How it was tested

<!-- Commit and clean/dirty state. One line per command, with its result. -->

## Not checked

<!-- One line each, including known limits. "Nothing" only if that is true. -->

## Verdict

<!-- Keep one. A draft PR has no verdict yet.
**Ready for the agreed scope.**
**Implemented, named check blocked:** which check, why, what is needed to finish it.
**Not ready:** which criterion failed, where the evidence is.
-->

## Checklist

- [ ] `just qa` passes on the final commit
- [ ] Each claim has the evidence `systems/quality.md` asks for
- [ ] Description is dead to the point; evidence is images, or it says `No image: <reason>`
- [ ] `systems/` updated if behaviour, a requirement or an interface changed (new decision → ADR)
- [ ] Changes `systems/icd/*`: has the `icd` label and the other owner approved
- [ ] Any reported number or figure names its scenario/session and commit
- [ ] No raw data, confidential files or AI attribution lines
