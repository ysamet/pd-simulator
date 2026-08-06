# M11a — Phase B follow-up 2: layout-file validation at config time

You are Claude Code working in the pdsim repository. This is a **small-fix
prompt**, not a phase. It repairs one defect found in the owner's manual
validation of the previous follow-up (DECISIONS #121–#125, now committed).
Where this prompt and the frozen spec ever appear to disagree, the spec
wins — stop and report rather than improvising.

## 0. Session start

1. **`docs/WIP.md` exists and is Phase C's baton. Read it for context but DO
   NOT delete it.** Update it only if this session changes Phase C's entry
   point (unlikely); say in the handback whether you touched it.
2. Read: the spec's Design 8 (its validator sentences and the two
   consequences, including "an error at spec validation, not a silent
   override mid-campaign"); `docs/DECISIONS.md` #119 (especially (d)),
   #121–#125; `CLAUDE.md`.
3. Standing rules: frozen spec — deviations and extensions become DECISIONS
   entries (numbering from the current tail), never spec-body edits;
   **never run `git commit`**; validation is app-first; all hard rules
   apply.

## 1. The defect, exactly as observed

Run lab, evolution mode, `structure.rows = 12`, `structure.cols = 12`,
`initial_layout = from_file`, `layout_file = example_island.txt` (a 4×6
template). The owner declined the populate offer and pressed Run. Result: a
raw `ValueError` with a full traceback rendered in the app window —
"Layout file is 4x6 but this run's grid is 12x12…" — raised from
`layouts.py:validate_layout_file`, called by `found_population`, called by
`PopulationDynamics.__init__`.

What the trace proves:

- The layout-file checks run at **founding time, inside the engine**, not at
  config-validation time. The user sees a stack trace where every other
  configuration error in the app produces a friendly validation message.
- The Run path is **not blocked** while a from-file mismatch is unresolved.
  The dimension check happened to fire here; the deeper consequence is that
  any mismatch the engine happens to tolerate would let `config.yaml`
  record a composition that is not what ran — a hard-rule-8 lie in the
  recorded config.
- Spec Design 8 names these checks as *validators* and its sweep-axis rule
  explicitly demands rejection "at spec validation" — so config-time
  placement is the spec's intent, not a deviation.

## 2. Required behaviour

1. **All layout-file checks run at config-validation time** (the same
   `before`-path where the app's other validators live), when
   `initial_layout = from_file`:
   - the `layout_file` value is non-blank and resolves (per the #122
     resolution rule) to a readable file;
   - the file parses (header well-formed, body consistent — the existing
     #123 comma/whitespace rules and blank-field errors);
   - header dimensions match the resolved `structure.rows` /
     `structure.cols`;
   - every non-`.` token is a registered strategy machine name (message
     names token, line, cell, and the valid names — reuse the #122 error
     content);
   - at least 2 agents are placed;
   - **composition equality**: the resolved widget composition (size and
     mixture) equals the file's implied composition. The error message
     states both and points the user at the "Populate the Population
     section from the file" button, which makes compliance one click. This
     is the guard that keeps `config.yaml` honest: with it, a from-file run
     can never record a composition other than the one that runs.
   - the existing sweep-axis rejection (a layout file combined with a swept
     composition axis): verify where it currently runs; if it is not at
     sweep-spec validation, move it there.
2. **Surface through the app's standard validation channel** — the same
   display path other config errors use (the K ≥ N message's channel), with
   the real message text. A user must never see a traceback for a
   configuration mistake. Where the panel's idiom supports it, show the
   failure pre-Run beside the widgets (the #124 mismatch warning already
   does part of this for composition; dimensions should get the same
   pre-Run visibility).
3. **Engine-side checks stay as defence in depth** but become unreachable
   through the app (config validation runs first). Do not delete them —
   they protect headless callers constructing configs programmatically —
   but the CLI (`python -m pdsim.run`) should also fail with the validation
   message, not a traceback, if its config path allows the same mistake.
4. Keep #124's flow intact: the populate offer, the token-check-before-
   offer, the sub-2-agent refusal, and the user's freedom to switch the
   layout away and keep their numbers. This fix adds the missing "…but you
   cannot Run while unresolved" backstop; it does not change the offer.

## 3. The #119(d) distinction — reason it, do not stumble into it

#119(d) rejected deriving N from the file inside a before-validator, partly
because that puts a filesystem read inside validation. This fix necessarily
reads the file at validation time. These are compatible, and the DECISIONS
entry must say why: **reading to derive** is still rejected — derived
defaults (auto rows/cols, K's default) remain pure functions of widget
values and never of file contents — while **reading to validate** is the
entire job of a cross-check validator: it consults the file precisely to
confirm the widgets agree with it, deriving nothing. State this distinction
explicitly in the entry so a later reader does not conclude #119(d) was
quietly overturned. Handle the read's failure modes (missing file,
unreadable, unparseable) as validation errors with their own messages, never
as exceptions escaping the validator.

## 4. Tests

- Config validation rejects each failure mode from §2.1 with the intended
  message: unresolvable path, parse failure, dimension mismatch,
  unregistered token, sub-2 agents, composition mismatch (size-only,
  mixture-only, and both).
- The exact defect state is pinned: 12×12 pinned dims + a 4×6 file fails at
  config validation, and the app path raises nothing.
- Populate-then-Run succeeds end to end (widgets filled from the file, dims
  matching, run completes, run folder carries the layout copy).
- Existing suites stay green; engine behaviour unchanged; the well-mixed
  byte-identity suite green (run and report).

## 5. Validation (app-first) — what the owner will do

Venv active (`.venv\Scripts\Activate.ps1`), restart
`streamlit run pdsim/ui/app.py`, Run lab, evolution mode:

1. **Reproduce the defect scenario:** pin rows and cols to 12, set
   `initial_layout = from_file`, `layout_file = example_island.txt`,
   decline the populate offer, press Run. Expected: a friendly validation
   message (dimension mismatch, with the fix paths), **no traceback**, no
   run started.
2. Clear rows/cols mismatch (set 4 and 6, or follow the message), still
   decline populate, press Run. Expected: blocked again — this time the
   composition-mismatch message naming both compositions and pointing at
   the populate button.
3. Click populate, press Run. Expected: the run proceeds, the island
   renders, `layout.txt` sits in the run folder, the original template
   remains in `grid_templates/`.
4. Misspell a token in a scratch file and press Run. Expected: the
   validation message (token, line, cell, valid names), no traceback.

## 6. End of session

1. DECISIONS entry (or entries): the validation-timing move and its
   spec-intent grounding; the read-to-validate versus read-to-derive
   distinction against #119(d); rejected alternative (catching the engine's
   exception in the app and reformatting it — rejected because it leaves
   validation timing wrong, keeps the recorded-config hazard one code path
   away, and masks genuine engine bugs behind a pretty printer).
2. `python -m pdsim.gendocs` + stage `docs/PARAMETERS.md` only if registry
   text changed; report either way.
3. Present the commit handoff — summary, exact file list to stage (never
   WIP.md), suggested commit message. **Do not commit.**
4. Report `DOCS CHANGED: [files]` with new DECISIONS numbers, and state
   whether `docs/WIP.md` was updated or left untouched.

Action required: move every layout-file check to config-validation time per §2, surface failures through the app's standard validation channel with no reachable traceback, block Run while a from-file mismatch is unresolved (composition equality included, with the error pointing at the populate button), record the #119(d) read-to-validate distinction in DECISIONS, and end with the commit handoff and DOCS CHANGED report — without committing and without deleting `docs/WIP.md`.
