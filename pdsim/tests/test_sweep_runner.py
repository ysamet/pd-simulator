"""Tests for the sweep runner and charts (``pdsim/sweep/runner.py``, #70/#71).

Runs tiny sweeps end to end at ``processes=1`` (serial path — same worker as
the Pool path, fast and deterministic): the summary parquet's columns, the
status/resume file, failure isolation, the schema guard, and the metric-vs-axis
chart builder. The multiprocessing Pool path shares the identical worker and is
exercised by the owner's CLI validation run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pdsim.sweep import runner
from pdsim.sweep.runner import run_sweep
from pdsim.sweep.spec import SweepSpec
from pdsim.viz import charts

_BASE = {
    "seed": 1,
    "population": {"size": 12, "composition": {"tit_for_tat": 2, "always_defect": 10}},
    "match": {"length_mode": "fixed", "rounds_per_match": 4},
    "dynamics": {"generations": 3, "selection_beta": 1.0, "mutation_rate": 0.0},
}


def _write_base(tmp_path: Path) -> Path:
    """Write the shared base config into the test dir.

    Args:
        tmp_path: pytest's per-test directory.

    Returns:
        The base config path.
    """
    import yaml

    path = tmp_path / "base.yaml"
    path.write_text(yaml.safe_dump(_BASE), encoding="utf-8")
    return path


def _spec(tmp_path: Path, **overrides: object) -> SweepSpec:
    """Build a tiny 2x2 sweep spec over the written base.

    Args:
        tmp_path: pytest's per-test directory.
        **overrides: SweepSpec field overrides.

    Returns:
        The validated spec.
    """
    fields: dict = {
        "name": "tiny",
        "base": str(_write_base(tmp_path)),
        "composition": {"vary": "tit_for_tat", "counts": [2, 6], "fill": {"always_defect": 100}},
        "seeds": [1, 2],
        "metrics": [
            {"metric": "final_share", "strategy": "tit_for_tat"},
            {"metric": "fixation_flag", "strategy": "tit_for_tat"},
        ],
    }
    fields.update(overrides)
    return SweepSpec.model_validate(fields)


class TestEndToEnd:
    """A tiny sweep produces the full folder layout (DECISIONS #70)."""

    def test_folder_layout_and_summary_columns(self, tmp_path: Path) -> None:
        """Every artifact appears and the summary is wide + index-sorted."""
        folder = run_sweep(_spec(tmp_path), out_dir=tmp_path / "sweeps", processes=1, quiet=True)
        names = {p.name for p in folder.iterdir()}
        assert {
            "sweep_spec.yaml",
            "runs",
            "sweep_status.json",
            "sweep_summary.parquet",
            "sweep_summary.json",
        } <= names
        assert any(name.endswith(".html") for name in names)  # metric-vs-axis chart

        frame = pd.read_parquet(folder / "sweep_summary.parquet")
        assert list(frame["run_index"]) == [0, 1, 2, 3]  # sorted by index, not completion
        assert list(frame.columns) == [
            "run_index",
            "run_id",
            "status",
            "seed",
            "tit_for_tat",
            "final_share[tit_for_tat]",
            "fixation_flag[tit_for_tat]",
        ]
        assert (frame["status"] == "done").all()
        # Member folders are named <NNN>_<axis-slug>.
        member_names = sorted(p.name for p in (folder / "runs").iterdir())
        assert member_names[0].startswith("000_tit_for_tat2")

    def test_status_and_schema_guard(self, tmp_path: Path) -> None:
        """sweep_status.json and the schema_version guard (#70, 4th #47 use)."""
        folder = run_sweep(_spec(tmp_path), out_dir=tmp_path / "sweeps", processes=1, quiet=True)
        status = json.loads((folder / "sweep_status.json").read_text(encoding="utf-8"))
        assert status["total"] == 4
        assert status["completed"] == 4
        assert status["failed"] == 0
        meta = json.loads((folder / "sweep_summary.json").read_text(encoding="utf-8"))
        assert meta["schema_version"] == 1
        assert meta["axis_columns"] == ["tit_for_tat"]
        assert meta["metric_columns"] == ["final_share[tit_for_tat]", "fixation_flag[tit_for_tat]"]

    def test_member_configs_reproduce_standalone(self, tmp_path: Path) -> None:
        """Hard rule 8: each member's config.yaml re-runs on its own."""
        from pdsim.config.experiment import load_config
        from pdsim.core import engine

        folder = run_sweep(_spec(tmp_path), out_dir=tmp_path / "sweeps", processes=1, quiet=True)
        member = sorted((folder / "runs").iterdir())[0]
        config = load_config(member / "config.yaml")
        events = list(engine.run(config))
        assert events[-1].mode == "evolution"


class TestResume:
    """Finalized members are skipped; missing ones re-run (DECISIONS #70)."""

    def test_full_resume_skips_everything(self, tmp_path: Path) -> None:
        """A second run over a complete sweep re-runs nothing."""
        spec = _spec(tmp_path)
        out = tmp_path / "sweeps"
        folder = run_sweep(spec, out_dir=out, processes=1, quiet=True)
        before = {p.name: p.stat().st_mtime_ns for p in (folder / "runs").iterdir()}
        run_sweep(spec, out_dir=out, processes=1, resume=True, quiet=True)
        after = {p.name: p.stat().st_mtime_ns for p in (folder / "runs").iterdir()}
        assert before == after  # nothing re-written

    def test_deleted_member_is_rerun(self, tmp_path: Path) -> None:
        """Deleting a member folder makes exactly that member re-run."""
        from pdsim.io.results import _rmtree_robust

        spec = _spec(tmp_path)
        out = tmp_path / "sweeps"
        folder = run_sweep(spec, out_dir=out, processes=1, quiet=True)
        victim = sorted((folder / "runs").iterdir())[1]
        victim_name = victim.name
        _rmtree_robust(victim)
        assert not (folder / "runs" / victim_name).exists()
        run_sweep(spec, out_dir=out, processes=1, resume=True, quiet=True)
        assert (folder / "runs" / victim_name).is_dir()  # came back
        frame = pd.read_parquet(folder / "sweep_summary.parquet")
        assert (frame["status"] == "done").all()


class TestFailureIsolation:
    """One bad member does not sink the sweep (DECISIONS #59/#70)."""

    def test_failed_member_marked_and_others_complete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A member whose run raises is marked failed; the rest finish."""
        real_execute = runner.execute_run

        def flaky_execute(config, **kwargs):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN003, ANN202
            """Fail for the 6-invader members, delegate otherwise."""
            if config.population.composition.get("tit_for_tat") == 6:
                raise RuntimeError("injected failure")
            return real_execute(config, **kwargs)

        monkeypatch.setattr(runner, "execute_run", flaky_execute)
        folder = run_sweep(_spec(tmp_path), out_dir=tmp_path / "sweeps", processes=1, quiet=True)

        frame = pd.read_parquet(folder / "sweep_summary.parquet")
        statuses = dict(zip(frame["tit_for_tat"], frame["status"], strict=False))
        assert statuses[2] == "done"
        assert statuses[6] == "failed"
        # Failed rows keep their axis columns but null metrics.
        failed = frame[frame["status"] == "failed"]
        assert failed["final_share[tit_for_tat]"].isna().all()
        status = json.loads((folder / "sweep_status.json").read_text(encoding="utf-8"))
        assert status["completed"] == 2
        assert status["failed"] == 2


class TestSweepChart:
    """The pure metric-vs-axis builder (DECISIONS #71)."""

    def test_builder_returns_figure_with_spread_band(self) -> None:
        """Mean line + a min-max band reflecting replicate spread."""
        frame = pd.DataFrame(
            {
                "tit_for_tat": [2, 2, 6, 6],
                "seed": [1, 2, 1, 2],
                "final_share[tit_for_tat]": [0.0, 0.2, 0.9, 1.0],
            }
        )
        figure = charts.sweep_metric_chart(
            frame, "tit_for_tat", "final_share[tit_for_tat]", metric_label="Final share"
        )
        assert figure.layout.yaxis.title.text == "Final share"
        # Three traces: band-high, band-low (filled), and the mean line.
        assert len(figure.data) == 3
        mean_trace = figure.data[-1]
        assert list(mean_trace.x) == [2, 6]
        assert list(mean_trace.y) == [pytest.approx(0.1), pytest.approx(0.95)]

    def test_export_writes_one_html_per_pair(self, tmp_path: Path) -> None:
        """export_sweep_charts writes a file per (metric x axis)."""
        frame = pd.DataFrame(
            {"tit_for_tat": [2, 6], "seed": [1, 1], "final_share[tit_for_tat]": [0.1, 0.9]}
        )
        written = charts.export_sweep_charts(
            frame, tmp_path, axes=["tit_for_tat"], metrics=["final_share[tit_for_tat]"]
        )
        assert len(written) == 1
        assert written[0].is_file()
        assert written[0].suffix == ".html"
