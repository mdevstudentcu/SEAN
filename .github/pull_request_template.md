## What and why

<!-- What this changes and why. Link the issue: "Closes #12". -->

## Traces to

<!-- REQ-nn, UC-nn, ADR-nnnn, ICD-<name>, RSK-nn this implements or changes, or "none". -->

## How it was tested

<!-- Commit and clean/dirty state. Commands you ran (`just qa`, `pnt sim …`, `pnt eval …`), before/after numbers against main, plots or screenshots. Say whether evidence is sim, replay, real session or hardware. See systems/quality.md for what each claim needs. -->

## Not checked

<!-- What you did not or could not check, and known limits. "Nothing" only if that is true. -->

## Verdict

<!-- Keep one. A draft PR has no verdict yet.
**Ready for the agreed scope.**
**Implemented, named check blocked:** which check, why, what is needed to finish it.
**Not ready:** which criterion failed, where the evidence is.
-->

## Checklist

- [ ] `just qa` passes on the final commit
- [ ] Each claim has the evidence `systems/quality.md` asks for
- [ ] `systems/` updated if behaviour, a requirement or an interface changed (new decision → ADR)
- [ ] Changes `systems/icd/*`: has the `icd` label and the other owner approved
- [ ] Any reported number or figure names its scenario/session and commit
- [ ] No raw data, confidential files or AI attribution lines
