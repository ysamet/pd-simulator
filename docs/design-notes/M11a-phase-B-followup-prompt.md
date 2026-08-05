# M11a — Phase B follow-up: grid visibility, layout-file usability

You are Claude Code working in the pdsim repository. This is a **small-fix
prompt**, not a phase: it repairs one defect found in the owner's manual
validation of Phase B and adds three usability improvements to the
layout-file mechanism, plus one documentation discharge. Phase C has not
started. Where this prompt and the frozen spec ever appear to disagree, the
spec wins — stop and report rather than improvising.

## 0. Session start

1. **`docs/WIP.md` exists and is Phase C's baton. Read it for context but DO
   NOT delete it** — you are not the Phase C session. Update it only if this
   session changes Phase C's entry point (unlikely), and say in your handback
   whether you touched it.
2. Read: `docs/specs/M11a-population-structure-spec.md` Design 8, Design 9
   (the RNG inventory — the founding-layout row), Design 10, and the
   Validation section; `docs/DECISIONS.md` #114 and #116–#120; `CLAUDE.md`.
3. Standing rules: the spec is frozen — every deviation or extension this
   session ships becomes a `docs/DECISIONS.md` entry (numbering from the
   current tail), never a spec-body edit; **never run `git commit`**;
   validation is app-first; all CLAUDE.md hard rules apply.

## 1. Fix — the grid must render for every lattice configuration

**Observed defect (owner's manual validation):** in the Run lab, with
`structure.kind = lattice`, the grid preview disappears when
`dynamics.reproduction_mode` is switched to `energy_economy`, and likewise
when `dynamics.time_model` is switched to `asynchronous`.

**Required behaviour:** in evolution run mode, any configuration with
`structure.kind = lattice` shows the founding grid preview and its readouts
(site count, occupancy, founding isolation), regardless of
`reproduction_mode` and `time_model`. The reason this is not cosmetic: every
scenario the later phases validate by eye is a non-imitation configuration —
the flagship and the drifting frontier are synchronous economy runs, and
`donation_game_threshold` is asynchronous `fixed_n`. A grid gated to sync
imitation makes Phase C's V4/V5 and Phase D's V6 unwatchable. (The grid
staying absent in tournament run mode is accepted and unchanged.)

**Procedure:**

1. **First diagnose and report the cause.** Two hypotheses from the design
   layer: (a) the preview sits inside a panel conditional keyed to the
   sync-imitation branch; (b) the gating was deliberate because
   `founding_view()`'s replay exactness (founding draw = the run's first
   draw) was only pinned for the imitation path.
2. If (a): fix the conditional. If (b): establish exactness rather than hide
   the grid. Spec Design 9 defines the founding draw as happening **once per
   run, at population construction, before generation 0, outside the
   per-generation order** — in every mode. Pin replay-versus-engine
   placement tests for a sync-economy lattice run and an async lattice run,
   mirroring the existing imitation pin, then unhide.
3. **If exactness genuinely fails** — some draw precedes founding under
   economy or async — **stop and report.** That contradicts Design 9 and
   needs a design-layer decision, not a workaround.
4. Also verify the **post-run grid in the results browser** renders for
   economy and async lattice runs (the `AgentSnapshot.site_id` path), and
   that the live view behaves during a run in those modes.
5. Write whatever visibility conditional survives in a form Phase E can fold
   into the greying/visibility predicate table — a named predicate, not an
   inline tangle.
6. Log the cause and the fix as a DECISIONS entry.

## 2. `grid_templates/` — a default home for layout files

**Observed:** the app currently resolves a bare layout filename against the
project root.

**Required:**

- Create `grid_templates/` at the repository root. It ships with a short
  `README.md` stating the format rules (header, tokens, both separators, the
  `.` empty-site token, where machine names come from) and **two example
  templates using real registered machine names** — one whitespace-separated,
  one comma-separated — sized small (e.g. 4×6) so they render instantly.
- **Resolution rule:** a `structure.layout_file` value containing no path
  separator resolves against `grid_templates/`; a value containing a
  separator (or an absolute path) is used as given. Update the registry help
  text to say exactly this. Log the rule as a DECISIONS entry (Design 8 is
  silent on resolution — this is an extension, not a contradiction).
- **Pin copy-not-move:** the recorder copies the layout file into the run
  folder; add or extend the test so it asserts the **original file still
  exists** after the run completes, alongside the copy.

## 3. Surface the strategy token spellings

Tokens in a layout file are strategy **machine names exactly as registered**.
Make that impossible to get wrong via three surfaces that cannot drift:

1. **In the app:** beside the Layout file widget (visible when
   `initial_layout = from_file`), render the currently registered machine
   names — a caption or small expander, generated from the strategy registry
   at paint time, never hardcoded.
2. **In the parser's error:** an unregistered token error names the offending
   token, its line and column, and lists the valid machine names.
3. **In the registry text:** the `layout_file` help and the `from_file` enum
   explanation state that tokens are registry machine names and point at the
   in-app list and the `grid_templates/` examples.

Rerun `python -m pdsim.gendocs` and stage the regenerated
`docs/PARAMETERS.md`.

## 4. Comma as an alternative separator

Extend the layout-file body parser, per the design-layer decision:

- **Detection rule:** if any body line contains a comma, the entire body
  parses comma-separated, with each token stripped of surrounding
  whitespace; otherwise the body parses whitespace-separated exactly as now.
  Comma presence decides for the whole body, so mixed-separator files are
  impossible by construction.
- `.` remains the empty-site token in **both** modes. An empty field between
  commas (`,,` or a trailing/leading comma producing a blank token) is a
  **validation error** telling the user to write `.` for an empty site —
  bare gaps must not silently mean "empty", or a missing token becomes
  indistinguishable from a typo.
- The header (`kind:`, `rows:`, `cols:`) is unchanged.
- Tests: a comma-separated file parses identically to its
  whitespace-separated twin; the blank-field error fires with a useful
  message; whitespace files still parse byte-for-byte as before.
- Log as a DECISIONS entry: the extension, the detection rule, and the
  rejected alternatives (a `separator:` header field — more machinery for no
  ambiguity gained; treating blank fields as empty sites — rejected for the
  typo-masking reason above).

## 5. Discharge the calibration guide's pending-measurement note

`docs/explainers/calibration-guide.md` carries #114's softened wording and
flags the empirical half as pending Phase B's measurement. The measurement
ran (see the Phase B DECISIONS entry recording it): the shifted-weight
spread **plateaus** — per-time selection strength drifts down across the run
in all three variants tested. Update the guide's pending flag to record the
finding and cite the DECISIONS entry number, keeping the honest limits (one
seed, one population size, one death rule — enough to refute the
strengthens-over-time claim, not to characterise the plateau). The guide is
a standing reference, not a frozen spec — editing it directly is correct
(#113). Do not touch the M11a spec body.

## 6. Non-goals

No Phase C work: no `place_offspring`, no `vacate()` callers, no
`boundary_order`, no birth-kernel parameters. No pixel-array fallback. No
predicate-table build (Phase E) — only the named-predicate shape from
section 1 step 5. Behaviour of the engine is unchanged; the existing
byte-identity suite must stay green (run it and report).

## 7. Validation (app-first) — what the owner will do

With the venv active (`.venv\Scripts\Activate.ps1`),
`streamlit run pdsim/ui/app.py`, Run lab, evolution mode:

- Set `structure.kind = lattice`, then switch `reproduction_mode` to
  `energy_economy` — **the grid stays visible**. Switch `time_model` to
  `asynchronous` — **still visible**. Press Run in each and confirm the
  post-run grid appears in the results browser.
- Set `initial_layout = from_file` and type just the example template's bare
  filename — it resolves from `grid_templates/` and renders as authored.
  Confirm the registered machine names are listed beside the widget.
- Load the comma-separated example — renders identically to the
  whitespace one.
- Break a token's spelling in a scratch file — the error names the token,
  the line, and the valid names.
- After a run using a template, confirm the original file is still in
  `grid_templates/` and a copy sits in the run folder.

## 8. End of session

1. Re-check CLAUDE.md's doc triggers; DECISIONS entries per sections 1, 2,
   and 4; regenerated `docs/PARAMETERS.md` staged if registry text changed.
2. Present the commit handoff — summary, exact file list to stage (never
   WIP.md), suggested commit message. **Do not commit.**
3. Report `DOCS CHANGED: [files]` (or `DOCS UNCHANGED`), calling out new
   DECISIONS numbers.
4. State explicitly: the diagnosed cause of the grid disappearance, whether
   `docs/WIP.md` was updated or left untouched, and the byte-identity suite
   result.

Action required: diagnose and fix the grid's disappearance under `energy_economy` and `asynchronous` (stop and report if founding-replay exactness genuinely fails), create `grid_templates/` with the bare-filename resolution rule and examples, surface the strategy machine names in app, error, and help text, add the comma separator per the stated detection rule, discharge the calibration guide's pending-measurement flag, log every extension in DECISIONS, and end with the commit handoff and DOCS CHANGED report — without committing and without deleting `docs/WIP.md`.
