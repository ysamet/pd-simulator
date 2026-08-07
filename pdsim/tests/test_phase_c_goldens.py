"""Golden masters around M11a Phase C (spec Design 9).

Two families, one mechanism:

* **Four NEGATIVE goldens** — sync imitation, sync economy, async
  ``variable_n``, async ``fixed_n``, each WELL-MIXED — pin that Phase C's
  local-birth machinery changed nothing where structure is off (Defining
  principle 1). Their digest constants were captured from the PRE-Phase-C
  engine (2026-08-06, before any Phase C engine edit), so a draw leaking
  past its gate fails here loudly.
* **Four POSITIVE goldens** — sync economy + lattice; async ``fixed_n`` +
  lattice + ``death_birth``; async ``variable_n`` + lattice (all three
  captured from the finished Phase C engine); and sync imitation + lattice
  + ``spatial_interaction`` — the interaction-only case, no births and no
  deaths, structure expressed purely through who plays whom — captured
  from the finished Phase D engine (2026-08-06), discharging #128's
  deferral. The fourth also carries the reload-and-re-run assertion the
  #133(d) technique prescribes.

Both grains from the spec are pinned per golden: the EVENT STREAM (at
``"round"`` granularity, so every per-round draw's consequence is in scope)
and the PERSISTED RUN FOLDER.

What "byte-identity" pins here, stated honestly:

* The stream digest hashes an explicit per-event-type FIELD LIST (the field
  set as of the capture date). Additive default-valued fields on event
  dataclasses are deliberately outside the pin — the #82/#100 additive-field
  precedent: M10a and M10b both grew event payloads while keeping earlier
  modes' recorded data identical. What a new field must NOT do is change
  values inside the pinned fields; the no-draw pins in
  ``test_local_birth.py`` separately assert the new fields stay inert
  (e.g. blocked-parents = 0) on the well-mixed paths.
* The folder digest hashes every parquet's CONTENT (canonical CSV form, so
  the pin survives a pyarrow upgrade that rewrites container bytes) plus
  ``summary.json`` with its three volatile fields (run id, timestamp, code
  version) removed. ``config.yaml`` is deliberately excluded — it grows a
  line whenever a registry parameter is added, exactly as it did at M10a
  and M10b — and is covered instead by the reload-and-re-run assertion:
  the recorded config must re-produce the pinned stream digest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from pdsim.config.experiment import ExperimentConfig, load_config
from pdsim.core import engine
from pdsim.core.events import (
    BirthEvent,
    CycleFinished,
    DeathEvent,
    Event,
    GenerationFinished,
    ImitationEvent,
    MatchFinished,
    RoundPlayed,
    RunFinished,
)
from pdsim.io.results import RunRecorder

# ---------------------------------------------------------------------------
# Digest machinery
# ---------------------------------------------------------------------------

_PINNED_FIELDS: dict[type, tuple[str, ...]] = {
    RoundPlayed: ("agent_ids", "round_index", "actions", "payoffs"),
    MatchFinished: ("agent_ids", "total_payoffs", "n_rounds"),
    BirthEvent: (
        "agent_id",
        "parent_id",
        "strategy",
        "energy",
        "cause",
        "event_index",
        "gen_equiv_time",
    ),
    DeathEvent: ("agent_id", "cause", "event_index", "gen_equiv_time"),
    ImitationEvent: (
        "agent_id",
        "from_strategy",
        "to_strategy",
        "source_agent_id",
        "event_index",
        "gen_equiv_time",
    ),
    GenerationFinished: (
        "index",
        "composition",
        "mean_scores",
        "rounds_played",
        "cooperation",
        "agents",
        "gen_equiv_time",
    ),
    CycleFinished: (
        "index",
        "composition",
        "total_scores",
        "mean_scores",
        "rounds_played",
        "cooperation",
    ),
    RunFinished: ("mode", "completed", "composition", "mean_scores", "total_scores"),
}
"""Per event type: the fields the stream digest hashes (the capture-date set).

Listing fields explicitly — instead of hashing ``repr(event)`` — is what
makes the pin about BEHAVIOUR: an additive default-valued field (the
#82/#100 precedent) does not break the golden, while any changed value
inside the pinned fields does.
"""


def _signature(event: Event) -> str:
    """Render one event as a deterministic line for hashing.

    Args:
        event: Any engine event.

    Returns:
        ``TypeName|repr(field)=...`` over the type's pinned fields. ``repr``
        of ints, floats, strings, dicts, tuples, and frozen dataclasses is
        deterministic for a fixed run, so equal streams give equal lines.
    """
    fields = _PINNED_FIELDS[type(event)]
    parts = [type(event).__name__]
    parts.extend(f"{name}={getattr(event, name)!r}" for name in fields)
    return "|".join(parts)


def stream_digest(config: ExperimentConfig) -> str:
    """Digest a config's full event stream at round granularity.

    Args:
        config: The experiment to run.

    Returns:
        The SHA-256 hex digest over the newline-joined event signatures.
    """
    hasher = hashlib.sha256()
    for event in engine.run(config, granularity="round"):
        hasher.update(_signature(event).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


_VOLATILE_SUMMARY_KEYS = ("run_id", "timestamp", "code_version", "duration_seconds")
"""summary.json fields that legitimately differ between recordings."""


def folder_digest(config: ExperimentConfig, out_dir: Path) -> str:
    """Record a run and digest the persisted folder's content.

    Every parquet is hashed in canonical CSV form (value-grain, so the pin
    survives container-format churn), ``summary.json`` with its volatile
    fields removed, and any ``layout.txt`` copy verbatim. ``config.yaml``
    is excluded on the grounds in the module docstring.

    Args:
        config: The experiment to run and record.
        out_dir: Where the run folder is created (a tmp path in tests).

    Returns:
        The SHA-256 hex digest over the folder's canonical content.
    """
    recorder = RunRecorder(config, out_dir=out_dir)
    for event in engine.run(config):
        recorder.add(event)
    folder = recorder.finalize()
    hasher = hashlib.sha256()
    for path in sorted(folder.iterdir()):
        if path.suffix == ".parquet":
            hasher.update(path.name.encode("utf-8"))
            frame = pd.read_parquet(path)
            hasher.update(frame.to_csv(index=False).encode("utf-8"))
        elif path.name == "summary.json":
            summary = json.loads(path.read_text(encoding="utf-8"))
            for key in _VOLATILE_SUMMARY_KEYS:
                summary.pop(key, None)
            hasher.update(json.dumps(summary, sort_keys=True).encode("utf-8"))
        elif path.name == "layout.txt":
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# The four negative configurations (well-mixed; spec Design 9)
# ---------------------------------------------------------------------------


def _negative_config(name: str) -> ExperimentConfig:
    """Build one of the four pinned well-mixed configurations.

    Args:
        name: ``"sync_imitation"``, ``"sync_economy"``, ``"async_variable_n"``,
            or ``"async_fixed_n"``.

    Returns:
        A validated config. Small populations and short horizons — the pin
        needs coverage of every draw kind, not statistical power.
    """
    if name == "sync_imitation":
        return ExperimentConfig.model_validate(
            {
                "seed": 17,
                "population": {"size": 8, "composition": {"tit_for_tat": 4, "always_defect": 4}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 3},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "dynamics": {"generations": 4, "mutation_rate": 0.05},
            }
        )
    if name == "sync_economy":
        return ExperimentConfig.model_validate(
            {
                "seed": 23,
                "population": {
                    "size": 4,
                    "composition": {"always_cooperate": 2, "always_defect": 2},
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 2},
                "dynamics": {
                    "generations": 6,
                    "reproduction_mode": "energy_economy",
                    "mutation_rate": 0.05,
                    "initial_energy": 480.0,
                    "basic_living_cost": 5.0,
                    "reproduction_threshold": 500.0,
                    "offspring_stake": 400.0,
                    "carrying_capacity": 10,
                    "base_hazard": 0.05,
                    "max_age": 12,
                },
            }
        )
    if name == "async_variable_n":
        return ExperimentConfig.model_validate(
            {
                "seed": 7,
                "population": {"size": 10, "composition": {"tit_for_tat": 5, "always_defect": 5}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "match": {"length_mode": "fixed", "rounds_per_match": 4},
                "dynamics": {
                    "generations": 4,
                    "time_model": "asynchronous",
                    "reproduction_threshold": 60.0,
                    "offspring_stake": 50.0,
                    "basic_living_cost": 25.0,
                    "carrying_capacity": 30,
                    "mutation_rate": 0.02,
                },
            }
        )
    if name == "async_fixed_n":
        return ExperimentConfig.model_validate(
            {
                "seed": 13,
                "population": {"size": 8, "composition": {"tit_for_tat": 4, "always_defect": 4}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "dynamics": {
                    "generations": 3,
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "moran_rule": "random",
                    "fixed_n_death_rule": "pure_random",
                    "mutation_rate": 0.05,
                },
            }
        )
    raise ValueError(f"Unknown negative golden {name!r}.")


NEGATIVE_STREAM_DIGESTS = {
    "sync_imitation": "b7175f1a0b2680988aecbc78ce572ad8134d98c2497928a86bb1fd55c749b3be",
    "sync_economy": "4e549367a49720ab9f1c78cc9aa413c1295f22137af246dd49d27f3353571394",
    "async_variable_n": "d96657b4380f8f9ac3e7b1c87d455f6e07b42ee6faedf43b8367a49c0b4d867a",
    "async_fixed_n": "4f4af54fe9c55bd63e6edef96221463a37e545e12d04bd604337388c43be2941",
}
"""Pre-Phase-C event-stream digests, captured 2026-08-06 from the unmodified engine."""

NEGATIVE_FOLDER_DIGESTS = {
    "sync_imitation": "76d8b887c952eecf31163a66d7f5503bcfd995fecb0cd60c1cdaade4c633aec8",
    "sync_economy": "b61becbd1ba514fbd16f76925f22d50efea80face05abc1ce84731832d3ee5fe",
    "async_variable_n": "e9a34f1e71e9c2e99b162dac880465fdaf157b000855be3ae3f713b717bc109e",
    "async_fixed_n": "eaa264412b23a8da89cb73778bec5217f24810d070b4ceae5cc2dd9c12cff7cc",
}
"""Pre-Phase-C run-folder digests, captured 2026-08-06 from the unmodified engine."""


class TestNegativeGoldens:
    """Defining principle 1, executably: well-mixed is byte-identical."""

    @pytest.mark.parametrize("name", sorted(NEGATIVE_STREAM_DIGESTS))
    def test_event_stream_matches_the_pre_phase_c_capture(self, name: str) -> None:
        """The full round-grain stream digest equals the pre-Phase-C constant."""
        assert stream_digest(_negative_config(name)) == NEGATIVE_STREAM_DIGESTS[name]

    @pytest.mark.parametrize("name", sorted(NEGATIVE_FOLDER_DIGESTS))
    def test_run_folder_matches_the_pre_phase_c_capture(self, name: str, tmp_path: Path) -> None:
        """The persisted folder's content digest equals the pre-Phase-C constant."""
        assert folder_digest(_negative_config(name), tmp_path) == NEGATIVE_FOLDER_DIGESTS[name]

    @pytest.mark.parametrize("name", sorted(NEGATIVE_STREAM_DIGESTS))
    def test_the_recorded_config_reruns_to_the_pinned_stream(
        self, name: str, tmp_path: Path
    ) -> None:
        """config.yaml coverage: the recorded config reproduces the pinned stream.

        The folder digest excludes ``config.yaml`` (it grows a line per new
        registry parameter — the additive precedent), so its semantics are
        pinned this way instead: whatever the file now says must re-run to
        the exact pre-Phase-C stream.
        """
        config = _negative_config(name)
        recorder = RunRecorder(config, out_dir=tmp_path)
        for event in engine.run(config):
            recorder.add(event)
        folder = recorder.finalize()
        reloaded = load_config(folder / "config.yaml")
        assert stream_digest(reloaded) == NEGATIVE_STREAM_DIGESTS[name]


# ---------------------------------------------------------------------------
# The four positive configurations (lattice; spec Design 9; the fourth is
# Phase D's, per #128)
# ---------------------------------------------------------------------------


def _positive_config(name: str) -> ExperimentConfig:
    """Build one of the four pinned lattice configurations.

    Args:
        name: ``"sync_economy_lattice"``, ``"async_fixed_n_lattice"``,
            ``"async_variable_n_lattice"``, or
            ``"sync_imitation_spatial_lattice"`` (Phase D's).

    Returns:
        A validated config on a small grid with a deterministic layout (so
        the founding draw gate stays closed and the pinned stream starts at
        the first generation's match phase).
    """
    if name == "sync_economy_lattice":
        return ExperimentConfig.model_validate(
            {
                "seed": 31,
                "population": {
                    "size": 6,
                    "composition": {"always_cooperate": 3, "always_defect": 3},
                },
                "match": {"length_mode": "fixed", "rounds_per_match": 2},
                "structure": {
                    "kind": "lattice",
                    "rows": 3,
                    "cols": 4,
                    "initial_layout": "stripes",
                },
                "dynamics": {
                    "generations": 6,
                    "reproduction_mode": "energy_economy",
                    "mutation_rate": 0.05,
                    "initial_energy": 480.0,
                    "basic_living_cost": 5.0,
                    "reproduction_threshold": 500.0,
                    "offspring_stake": 400.0,
                    "carrying_capacity": 12,
                    "base_hazard": 0.05,
                    "max_age": 12,
                },
            }
        )
    if name == "async_fixed_n_lattice":
        return ExperimentConfig.model_validate(
            {
                "seed": 37,
                "population": {"size": 9, "composition": {"tit_for_tat": 5, "always_defect": 4}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "structure": {
                    "kind": "lattice",
                    "rows": 3,
                    "cols": 3,
                    "initial_layout": "stripes",
                },
                "dynamics": {
                    "generations": 3,
                    "time_model": "asynchronous",
                    "async_population": "fixed_n",
                    "moran_rule": "death_birth",
                    "fixed_n_death_rule": "pure_random",
                    "mutation_rate": 0.05,
                },
            }
        )
    if name == "async_variable_n_lattice":
        return ExperimentConfig.model_validate(
            {
                "seed": 41,
                "population": {"size": 10, "composition": {"tit_for_tat": 5, "always_defect": 5}},
                "matching": {"matcher": "random_k", "opponents_per_agent": 2},
                "match": {"length_mode": "fixed", "rounds_per_match": 4},
                "structure": {
                    "kind": "lattice",
                    "rows": 4,
                    "cols": 5,
                    "initial_layout": "stripes",
                },
                "dynamics": {
                    "generations": 4,
                    "time_model": "asynchronous",
                    "reproduction_threshold": 60.0,
                    "offspring_stake": 50.0,
                    "basic_living_cost": 25.0,
                    "carrying_capacity": 20,
                    "mutation_rate": 0.02,
                },
            }
        )
    if name == "sync_imitation_spatial_lattice":
        # Phase D's golden (#128 discharged): the interaction-only case —
        # imitation reproduction, so no births and no deaths, and the
        # lattice expressed PURELY through who plays whom. k = 3 sits below
        # the Moore neighbourhood size of 8, so the kernel genuinely
        # samples (a forced-draw configuration would pin less).
        return ExperimentConfig.model_validate(
            {
                "seed": 43,
                "population": {"size": 9, "composition": {"tit_for_tat": 5, "always_defect": 4}},
                "matching": {"spatial_interaction": True, "opponents_per_agent": 3},
                "match": {"length_mode": "fixed", "rounds_per_match": 3},
                "structure": {
                    "kind": "lattice",
                    "rows": 3,
                    "cols": 3,
                    "initial_layout": "stripes",
                },
                "dynamics": {"generations": 4, "mutation_rate": 0.05},
            }
        )
    raise ValueError(f"Unknown positive golden {name!r}.")


POSITIVE_STREAM_DIGESTS = {
    "sync_economy_lattice": "03cf9dfed314380d386323581c8ca9af2e9742cbe804053ee81ac0ed41a6c6fa",
    "async_fixed_n_lattice": "8d03522a6736c341e584264c9312201c210c20f68e358a9d814f4bc5d01f7e87",
    "async_variable_n_lattice": "e1b02eab771b28372079eb15c6d16e44acad4af9b5cc8964436d978d943e32c7",
    "sync_imitation_spatial_lattice": (
        "a2bd4367d7062f845df214e0432fe37194b46981278830132d59738a845d957f"
    ),
}
"""Event-stream digests: the first three captured 2026-08-06 from the finished
Phase C engine; the fourth captured 2026-08-06 from the finished Phase D
engine (#128 discharged)."""

POSITIVE_FOLDER_DIGESTS = {
    "sync_economy_lattice": "fd63020abf59c72903ec6ede50ff31f89d9b6982b5ce1c0988f4383c06c080df",
    "async_fixed_n_lattice": "b5022f06c5ba00508f90e4f68f401f04ea7bb0dfc36d64fd07490590203f3dbd",
    "async_variable_n_lattice": "b88a197558da5634a6437dd85b71d4807f896f8adef04c0fe23641d6faaa4d46",
    "sync_imitation_spatial_lattice": (
        "d49ea44ad0eeea9a3e1ab850c47f07e2017ac87b17741283f4aeb8c48f9f0968"
    ),
}
"""Run-folder digests, captured as the stream digests above."""


class TestPositiveGoldens:
    """Phase C's and D's new behaviour, sealed for later phases to build on."""

    @pytest.mark.parametrize("name", sorted(POSITIVE_STREAM_DIGESTS))
    def test_event_stream_matches_the_capture(self, name: str) -> None:
        """The full round-grain stream digest equals the pinned constant."""
        assert stream_digest(_positive_config(name)) == POSITIVE_STREAM_DIGESTS[name]

    @pytest.mark.parametrize("name", sorted(POSITIVE_FOLDER_DIGESTS))
    def test_run_folder_matches_the_capture(self, name: str, tmp_path: Path) -> None:
        """The persisted folder's content digest equals the pinned constant."""
        assert folder_digest(_positive_config(name), tmp_path) == POSITIVE_FOLDER_DIGESTS[name]

    def test_the_phase_d_recorded_config_reruns_to_the_pinned_stream(self, tmp_path: Path) -> None:
        """config.yaml coverage for the Phase D golden (#133(d) verbatim).

        The folder digest excludes ``config.yaml``, so — exactly as for the
        negative goldens — the recorded config's semantics are pinned by
        reloading it and re-running to the pinned stream digest. The three
        Phase C positives keep their recorded scope; this assertion is part
        of the FOURTH golden's capture technique.
        """
        config = _positive_config("sync_imitation_spatial_lattice")
        recorder = RunRecorder(config, out_dir=tmp_path)
        for event in engine.run(config):
            recorder.add(event)
        folder = recorder.finalize()
        reloaded = load_config(folder / "config.yaml")
        assert stream_digest(reloaded) == POSITIVE_STREAM_DIGESTS["sync_imitation_spatial_lattice"]
