# Quality standard

What every change must show before it is called ready, whoever made it. Decision: [ADR-0017](adr/0017-quality-standard.md).

**The rule:** a claim is only as good as the evidence for it. Run what you claim, on the commit you are submitting, and say what you did not check.

Our worst failure is not a crash. It is a wrong or overconfident number in front of the judges, so most of this file is about numbers and honesty.

## Before coding

Use the issue's *Done when* as the acceptance note. It should say what will be true afterwards, how you will observe it, what would count as failing, and which module owns the rule (see the table in `AGENTS.md`). Ordinary implementation choices need no approval; new engineering decisions still get an ADR.

## Evidence must match the claim

| Claim | Evidence required |
| --- | --- |
| A function or model behaves | Focused test through its public function |
| Sim, replay and live are interchangeable (ADR-0004) | The same assertions run against each source; replay equals what was recorded |
| An estimator or sim change is better, or no worse | `just eval <scenario>` on the branch and on `main`, same scenario and run count, both numbers in the PR |
| Position or time confidence is honest (REQ-02, REQ-03) | Stanford plot, HPL bound rate and misleading epochs across fault scenarios, not only `nominal` |
| A fault or spoof is detected (REQ-04) | Detection time and rate on the attack scenarios, and false alarms on `nominal` |
| The sim reflects reality (ADR-0015) | The *Sim validity* row in `verification.md` moved, with the session that moved it |
| An interface is unchanged or correctly changed | The ICD and generated-code rules in `AGENTS.md` met, and the CI `generated-code` job green |
| The dashboard or a viewer works | Opened and looked at in the real app, screenshot attached, viewer and version named |
| Code works on the Pi, the hub or the drone | Run on that board, session named. A compile or a simulation does not show this |
| Still receive-only and private (REQ-07, REQ-08) | Changed code inspected against `safety.md`; a session audit when capture changes |
| A result shown to the judges | `just results`, or `pnt eval` / `pnt plot`, from a clean commit that the figure names |
| Documentation is correct | Links and commands in it checked. Docs work makes no runtime claim |

Stop when the evidence is sufficient. Do not invent extra tests to look thorough.

## Reporting numbers

- **While a REQ target is `TBD`, compare against `main`** and report both values. A worse number needs a stated reason in the PR, or the PR is not ready.
- **Compare paired runs.** `pnt eval` uses seeds `0` to `N-1`, so the same scenario and run count gives both sides the same draws, and a difference in an estimator change is a real effect on those runs, not noise. A change to the sim alters the draws and breaks the pairing: say so, and do not read a small difference as better or worse.
- **One seed shows that it runs.** It does not show that it is better. Use at least the `just eval` default of 50 runs for any claim of improvement.
- **Every number is reproducible** as REQ-10 and `AGENTS.md` require.
- **Say what kind of evidence it is:** sim, replay of a real session, real session with injected faults, or hardware.
- **Describe a sim result by its model's status** in the *Sim validity* table of `verification.md` (ADR-0015): a `placeholder` result is never called validated or real-world.
- **Report the bad cases too:** worst run, misleading epochs and false alarms, not only the average.
- **Do not pick a target inside a test.** A threshold that is not a requirement is a regression guard and says so in a comment.

## Tests

- Test behaviour through public functions, not internals. Do not chase a coverage figure.
- Tests are deterministic: seeded, with no network, no hardware and no raw data. Small fixtures only.
- For a bug fix, write the failing test first where practical.
- Never skip, xfail, loosen or delete a test to get a green run. If the contract really changed, say so in the PR and give the replacement evidence.
- A test that backs a requirement names it, for example `test_no_transmit_calls_req07`.

## Design review questions

These come from [SOLID](https://www.digitalocean.com/community/conceptual-articles/s-o-l-i-d-the-first-five-principles-of-object-oriented-design), applied to a codebase of functions, dataclasses and one `Source` protocol. They are questions for review, not a checklist to tick.

- **One reason to change:** does this rule live in the module that owns it, or is it now copied somewhere else?
- **Extend without editing:** can a new attack, source or scenario be added without changing `nav/`?
- **Substitutable:** can any `Source` stand in for another, with no source-type branch in the estimator (ADR-0004)?
- **Small dependencies:** does Pi code still need only the `payload` extra?
- **Depend on the contract:** do `nav/` and `integrity/` use `Measurement` and `Source`, never MCAP or ZeroMQ directly?

Do not add an abstraction before a second implementation exists.

## Checks

| Check | What it covers | When |
| --- | --- | --- |
| `just qa` | Lint, format, tests, sim and plot smoke. Prints the commit and whether the tree is clean | On the final commit, before asking for review |
| CI | The same checks, plus generated code and the firmware build | Every PR. Must be green |
| Author and reviewer | Everything else in the evidence table | Every PR |

Without uv or just, run the same commands through `.venv` and say so in the PR. If you edit anything after `just qa`, run it again.

Not automated yet: the requirement-named tests, the `Source` contract test and checks for the hard rules in `AGENTS.md`. A ticked checklist does not prove that anything ran.

## PR descriptions

**Dead to the point.** State what changed, the result and any blocker, in single lines or short bullets. No background, no restating the issue or diff, no story of how you got there.

**Images are the default evidence.** Show the result instead of describing it:

- Plots: error, Stanford, trust, clock. For a change to numbers, before and after against `main`.
- Screens: the dashboard or viewer in its settled state.
- Hardware: a photo of the setup, or the board's real output.

Rules for images:

- Each caption names the scenario or session, the commit, and the kind of evidence (sim, replay, real session, hardware).
- If no image can show the change (docs, a pure refactor), write `No image: <reason>`.
- A change with visible output and no image cannot carry the *Ready* verdict.
- Drag images into the description. Where that is not possible (`gh` cannot upload), commit the image under `analysis/pr-evidence/<n>/`, kept apart from `analysis/results/`, which holds the figures we present, and link it pinned to the commit: `![caption](https://github.com/<owner>/<repo>/blob/<sha>/analysis/pr-evidence/<n>/<file>.png?raw=true)`.
- Images follow the data rules: no raw data, unhashed BSSIDs, tokens, personal details or confidential slides.

The reviewer checks these rules; no CI job does yet.

## Verdict

Every PR ends with one verdict, scoped to what the issue agreed:

| Verdict | Means | PR state |
| --- | --- | --- |
| **Ready for the agreed scope** | Evidence from the final commit supports every criterion and nothing observed contradicts it | Ready for review |
| **Implemented, named check blocked** | Name the unverified criterion, why it could not run, and what is needed to finish it | Draft, unless only the reviewer can run that check |
| **Not ready** | Name the failed criterion and where the evidence is | Draft |

A draft PR has no verdict yet.

Alongside the verdict, the PR gives the commit and whether the tree was clean, the commands run, the results, what was **not** checked, and known limits. PR #45 shows why: looking at the real output caught a bug the tests missed, and it says plainly what was not checked.

An unrun check is unverified, never a pass. A green test run cannot override something you saw go wrong.

Instructions for coding agents live in `AGENTS.md` only (*Before you call work ready*), so they keep its sign-off rule.
