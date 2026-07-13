"""Tests for the Sweep tab's Streamlit-free helpers (M9.5b, DECISIONS #72).

The tab function itself is a thin rendering shell and stays out of these
unit tests (the AppTest smoke tests cover that the app still renders); every
branch worth testing lives in :mod:`pdsim.ui.sweep_helpers` and is exercised
here directly — the #38 split, applied to sweeps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pdsim.config.scenarios import get_scenario_info
from pdsim.sweep.spec import (
    expand,
    load_sweep_spec,
    sweep_spec_yaml,
    sweep_validation_messages,
)
from pdsim.ui import sweep_helpers


def _tft_invasion_fields(**overrides: object) -> dict:
    """Build the authored-fields dict for the canonical tft_invasion shape.

    Mirrors ``examples/sweeps/tft_invasion.yaml`` (with a scenario base):
    9 invader counts x 10 seeds = 90 members.

    Args:
        **overrides: Field entries to replace.

    Returns:
        A fields dict for :func:`sweep_helpers.build_sweep_spec`.
    """
    fields: dict = {
        "name": "tft_invasion_app",
        "base_kind": "scenario",
        "base_scenario": "reciprocity_takes_over",
        "composition": {
            "vary": "tit_for_tat",
            "counts": [2, 4, 6, 8, 10, 12, 14, 16, 20],
            "fixed": {},
            "fill": {"always_defect": 100},
        },
        "parameters": [],
        "seeds": list(range(1, 11)),
        "metrics": [
            {"metric": "final_share", "strategy": "tit_for_tat"},
            {"metric": "time_to_fixation", "strategy": "tit_for_tat"},
            {"metric": "fixation_flag", "strategy": "tit_for_tat"},
        ],
    }
    fields.update(overrides)
    return fields


class TestParseIntList:
    """Counts/seeds text parsing."""

    def test_commas_and_spaces_both_parse(self) -> None:
        """Comma-separated, space-separated, and mixed all work."""
        assert sweep_helpers.parse_int_list("2, 4, 6") == [2, 4, 6]
        assert sweep_helpers.parse_int_list("2 4 6") == [2, 4, 6]
        assert sweep_helpers.parse_int_list("2,4 6") == [2, 4, 6]

    def test_empty_text_is_an_empty_list(self) -> None:
        """A blank field means "nothing entered yet", not an error."""
        assert sweep_helpers.parse_int_list("") == []
        assert sweep_helpers.parse_int_list("   ") == []

    def test_bad_token_raises_a_plain_sentence(self) -> None:
        """A non-number token names itself in a user-facing message."""
        with pytest.raises(ValueError, match="whole number"):
            sweep_helpers.parse_int_list("2, x, 6")


class TestBuildRange:
    """The counts/seeds convenience range builder."""

    def test_stop_is_included_when_the_step_lands_on_it(self) -> None:
        """build_range(2, 20, 2) ends at 20, matching the widget promise."""
        assert sweep_helpers.build_range(2, 20, 2) == [2, 4, 6, 8, 10, 12, 14, 16, 18, 20]

    def test_stop_is_passed_over_when_off_grid(self) -> None:
        """A stop the step never reaches is simply not included."""
        assert sweep_helpers.build_range(2, 7, 2) == [2, 4, 6]

    def test_single_value_range(self) -> None:
        """A range whose start equals its stop yields exactly one value."""
        assert sweep_helpers.build_range(5, 5, 1) == [5]

    def test_non_positive_step_raises(self) -> None:
        """A zero or negative step is a plain error."""
        with pytest.raises(ValueError, match="positive"):
            sweep_helpers.build_range(2, 10, 0)

    def test_stop_below_start_raises(self) -> None:
        """A backwards range is a plain error, not an empty list."""
        with pytest.raises(ValueError, match="must not be below"):
            sweep_helpers.build_range(10, 2, 2)


class TestParseValueList:
    """Parameter-axis text parsing, by registry kind."""

    def test_float_kind_parses_numbers(self) -> None:
        """A float parameter accepts int-looking tokens too (widened)."""
        values = sweep_helpers.parse_value_list("dynamics.selection_beta", "0.01, 0.1, 1")
        assert values == [0.01, 0.1, 1.0]

    def test_int_kind_parses_whole_numbers(self) -> None:
        """An int parameter parses whole-number tokens."""
        assert sweep_helpers.parse_value_list("dynamics.generations", "10 20") == [10, 20]

    def test_int_kind_rejects_a_fraction(self) -> None:
        """An int parameter refuses '1.5' with a plain message."""
        with pytest.raises(ValueError, match="whole numbers"):
            sweep_helpers.parse_value_list("dynamics.generations", "10, 1.5")

    def test_bool_kind_parses_true_false(self) -> None:
        """A bool parameter reads true/false (and yes/no, 1/0)."""
        values = sweep_helpers.parse_value_list("game.enforce_pd_ordering", "true false")
        assert values == [True, False]

    def test_bool_kind_rejects_other_tokens(self) -> None:
        """A bool parameter refuses anything but a truth word."""
        with pytest.raises(ValueError, match="true or false"):
            sweep_helpers.parse_value_list("game.enforce_pd_ordering", "maybe")

    def test_choice_kind_keeps_raw_tokens(self) -> None:
        """Choice tokens pass through; membership is validate's job."""
        values = sweep_helpers.parse_value_list("matching.matcher", "round_robin random_k")
        assert values == ["round_robin", "random_k"]

    def test_float_kind_rejects_a_word(self) -> None:
        """A non-numeric token on a float axis is a plain error."""
        with pytest.raises(ValueError, match="could not read"):
            sweep_helpers.parse_value_list("dynamics.selection_beta", "0.1, high")


class TestValidateParameterValues:
    """Per-axis belt-and-braces registry validation."""

    def test_valid_values_produce_no_messages(self) -> None:
        """In-range values pass silently."""
        assert sweep_helpers.validate_parameter_values("dynamics.selection_beta", [0.1, 1.0]) == []

    def test_out_of_range_value_names_the_parameter(self) -> None:
        """An out-of-bounds value yields the registry's plain message."""
        messages = sweep_helpers.validate_parameter_values("dynamics.mutation_rate", [0.5, 2.0])
        assert len(messages) == 1
        assert "dynamics.mutation_rate" in messages[0]

    def test_unknown_key_is_one_plain_message(self) -> None:
        """A key the registry has never heard of reports itself."""
        messages = sweep_helpers.validate_parameter_values("dynamics.telepathy", [1])
        assert len(messages) == 1
        assert "Unknown parameter key" in messages[0]


class TestBuildSweepSpec:
    """Authored fields -> SweepSpec (the build_config analog)."""

    def test_tft_invasion_shape_is_clean_and_expands_to_90(self) -> None:
        """The canonical shape passes the ONE shared validation path."""
        spec = sweep_helpers.build_sweep_spec(_tft_invasion_fields())
        assert sweep_validation_messages(spec) == []
        assert len(expand(spec)) == 90  # 9 counts x 10 seeds

    def test_config_file_base_kind_maps_to_base(self) -> None:
        """base_kind 'path' authors the `base` field, not `base_scenario`."""
        fields = _tft_invasion_fields(
            base_kind="path", base_path="examples/sweeps/tft_invasion_base.yaml"
        )
        spec = sweep_helpers.build_sweep_spec(fields)
        assert spec.base == "examples/sweeps/tft_invasion_base.yaml"
        assert spec.base_scenario is None

    def test_omitted_composition_stays_none(self) -> None:
        """No composition axis authored -> the spec carries none."""
        spec = sweep_helpers.build_sweep_spec(
            _tft_invasion_fields(
                composition=None, parameters=[{"key": "dynamics.selection_beta", "values": [0.1]}]
            )
        )
        assert spec.composition is None

    def test_malformed_shape_raises_validation_error(self) -> None:
        """Structural problems surface as a pydantic ValidationError."""
        fields = _tft_invasion_fields(
            composition={"vary": "tit_for_tat", "counts": "nope", "fill": {"always_defect": 100}}
        )
        with pytest.raises(ValidationError):
            sweep_helpers.build_sweep_spec(fields)

    def test_bad_name_is_flagged_by_the_shared_path(self) -> None:
        """The name rule lives in sweep_validation_messages (one path)."""
        spec = sweep_helpers.build_sweep_spec(_tft_invasion_fields(name="Bad Name"))
        assert any("lowercase token" in message for message in sweep_validation_messages(spec))


class TestBasePopulationSize:
    """The live composition preview's N lookup."""

    def test_scenario_base_reports_its_size(self) -> None:
        """A registered scenario's population size comes back."""
        assert sweep_helpers.base_population_size(_tft_invasion_fields()) == 24

    def test_unknown_scenario_is_none(self) -> None:
        """An unknown scenario suppresses the preview, not the app."""
        fields = _tft_invasion_fields(base_scenario="atlantis")
        assert sweep_helpers.base_population_size(fields) is None

    def test_config_file_base_reports_its_size(self, tmp_path: Path) -> None:
        """A loadable config file's population size comes back."""
        config = get_scenario_info("reciprocity_takes_over").config
        path = tmp_path / "base.yaml"
        path.write_text(
            yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
        )
        fields = _tft_invasion_fields(base_kind="path", base_path=str(path))
        assert sweep_helpers.base_population_size(fields) == 24

    def test_missing_config_file_is_none(self) -> None:
        """A path that does not exist suppresses the preview."""
        fields = _tft_invasion_fields(base_kind="path", base_path="no/such/file.yaml")
        assert sweep_helpers.base_population_size(fields) is None


class TestAuthoredSpecPersistence:
    """The named authored file the spawned CLI reads."""

    def test_authored_spec_path_shape(self, tmp_path: Path) -> None:
        """The authored file is <out_dir>/<name>.authored.yaml."""
        path = sweep_helpers.authored_spec_path(tmp_path, "tft_invasion_app")
        assert path == tmp_path / "tft_invasion_app.authored.yaml"

    def test_write_authored_spec_round_trips(self, tmp_path: Path) -> None:
        """load_sweep_spec reads back exactly what was authored."""
        spec = sweep_helpers.build_sweep_spec(_tft_invasion_fields())
        path = sweep_helpers.write_authored_spec(
            spec, sweep_helpers.authored_spec_path(tmp_path, spec.name)
        )
        assert load_sweep_spec(path) == spec

    def test_written_file_matches_the_yaml_preview(self, tmp_path: Path) -> None:
        """The download/preview text and the file share ONE serialization."""
        spec = sweep_helpers.build_sweep_spec(_tft_invasion_fields())
        path = sweep_helpers.write_authored_spec(
            spec, sweep_helpers.authored_spec_path(tmp_path, spec.name)
        )
        assert path.read_text(encoding="utf-8") == sweep_spec_yaml(spec)


class TestBuildLaunchCommand:
    """The exact argv — the command a user could have typed."""

    def test_exact_argv(self) -> None:
        """sys.executable -m pdsim.sweep <spec> --out <dir>, verbatim."""
        command = sweep_helpers.build_launch_command(
            Path("sweeps") / "x.authored.yaml", Path("sweeps")
        )
        assert command == [
            sys.executable,
            "-m",
            "pdsim.sweep",
            str(Path("sweeps") / "x.authored.yaml"),
            "--out",
            "sweeps",
        ]


class TestSweepFolderExists:
    """The resume-awareness probe."""

    def test_existing_folder_is_true(self, tmp_path: Path) -> None:
        """A directory of the sweep's name reports True."""
        (tmp_path / "mysweep").mkdir()
        assert sweep_helpers.sweep_folder_exists(tmp_path, "mysweep") is True

    def test_absent_folder_is_false(self, tmp_path: Path) -> None:
        """No directory -> False (a plain file does not count)."""
        (tmp_path / "notasweep").write_text("x", encoding="utf-8")
        assert sweep_helpers.sweep_folder_exists(tmp_path, "mysweep") is False
        assert sweep_helpers.sweep_folder_exists(tmp_path, "notasweep") is False


class TestReadSweepStatus:
    """The app-poll surface (#70) — read-only."""

    def test_reads_a_status_file(self, tmp_path: Path) -> None:
        """A hand-written status file parses to its dict."""
        folder = tmp_path / "mysweep"
        folder.mkdir()
        status = {
            "name": "mysweep",
            "total": 4,
            "completed": 2,
            "failed": 1,
            "running": 1,
            "per_index": {"0": {"status": "done", "folder": "000_x", "error": None}},
        }
        (folder / "sweep_status.json").write_text(json.dumps(status), encoding="utf-8")
        assert sweep_helpers.read_sweep_status(tmp_path, "mysweep") == status

    def test_absent_file_is_none(self, tmp_path: Path) -> None:
        """No status file yet -> None (the runner has not started)."""
        (tmp_path / "mysweep").mkdir()
        assert sweep_helpers.read_sweep_status(tmp_path, "mysweep") is None

    def test_unreadable_file_is_none(self, tmp_path: Path) -> None:
        """A file caught mid-rewrite is None — refresh again, no crash."""
        folder = tmp_path / "mysweep"
        folder.mkdir()
        (folder / "sweep_status.json").write_text('{"total": ', encoding="utf-8")
        assert sweep_helpers.read_sweep_status(tmp_path, "mysweep") is None


class TestStatusRows:
    """The per-index monitor table."""

    def test_rows_are_sorted_by_run_index(self) -> None:
        """JSON string keys become ints, sorted numerically (not '10'<'2')."""
        status = {
            "per_index": {
                "10": {"status": "done", "folder": "010_x", "error": None},
                "2": {"status": "failed", "folder": None, "error": "boom"},
            }
        }
        rows = sweep_helpers.status_rows(status)
        assert [row["run_index"] for row in rows] == [2, 10]
        assert rows[0]["error"] == "boom"
        assert rows[1]["folder"] == "010_x"

    def test_empty_status_is_an_empty_table(self) -> None:
        """A skeleton status renders as no rows."""
        assert sweep_helpers.status_rows({"per_index": {}}) == []
        assert sweep_helpers.status_rows({}) == []


class TestListSweepNames:
    """The monitor's folder listing (folder truth, newest first)."""

    def test_missing_parent_is_empty(self, tmp_path: Path) -> None:
        """No sweeps directory yet -> an empty list, not an error."""
        assert sweep_helpers.list_sweep_names(tmp_path / "nowhere") == []

    def test_newest_first_and_files_ignored(self, tmp_path: Path) -> None:
        """Directories sort by modification time; loose files are skipped."""
        (tmp_path / "older").mkdir()
        (tmp_path / "newer").mkdir()
        (tmp_path / "stray.authored.yaml").write_text("x", encoding="utf-8")
        os.utime(tmp_path / "older", (1_000_000, 1_000_000))
        os.utime(tmp_path / "newer", (2_000_000, 2_000_000))
        assert sweep_helpers.list_sweep_names(tmp_path) == ["newer", "older"]


class TestReadSweepSummaryMeta:
    """sweep_summary.json reading, with the schema guard honored."""

    def _write_meta(self, tmp_path: Path, meta: dict) -> None:
        """Write a summary metadata file under tmp_path/mysweep/."""
        folder = tmp_path / "mysweep"
        folder.mkdir(exist_ok=True)
        (folder / "sweep_summary.json").write_text(json.dumps(meta), encoding="utf-8")

    def test_reads_the_metadata(self, tmp_path: Path) -> None:
        """A schema-1 summary parses to its dict."""
        meta = {
            "schema_version": 1,
            "name": "mysweep",
            "axis_columns": ["tit_for_tat"],
            "metric_columns": ["final_share[tit_for_tat]"],
        }
        self._write_meta(tmp_path, meta)
        assert sweep_helpers.read_sweep_summary_meta(tmp_path, "mysweep") == meta

    def test_absent_file_is_none(self, tmp_path: Path) -> None:
        """No summary yet (sweep still running) -> None."""
        (tmp_path / "mysweep").mkdir()
        assert sweep_helpers.read_sweep_summary_meta(tmp_path, "mysweep") is None

    def test_newer_schema_is_rejected_plainly(self, tmp_path: Path) -> None:
        """A future schema_version raises the update-pdsim message (#47)."""
        self._write_meta(tmp_path, {"schema_version": 99})
        with pytest.raises(ValueError, match="Update pdsim"):
            sweep_helpers.read_sweep_summary_meta(tmp_path, "mysweep")


class TestMetricDisplayLabels:
    """Metric column -> display name for the chart's y-label."""

    def test_labels_from_the_recorded_spec(self) -> None:
        """Each recorded MetricRef maps its column to its display name."""
        meta = {
            "spec": {
                "metrics": [
                    {"metric": "final_share", "strategy": "tit_for_tat"},
                    {"metric": "min_cooperation"},
                ]
            }
        }
        labels = sweep_helpers.metric_display_labels(meta)
        assert labels["final_share[tit_for_tat]"] == "Final share"
        assert labels["min_cooperation"] == "Minimum cooperation rate"

    def test_unknown_metric_is_skipped(self) -> None:
        """A metric this build does not know falls back to its column name."""
        meta = {"spec": {"metrics": [{"metric": "telepathy_index"}]}}
        assert sweep_helpers.metric_display_labels(meta) == {}


class TestStreamlitFree:
    """The module must import without Streamlit (the #38 contract)."""

    def test_import_does_not_pull_streamlit(self) -> None:
        """A fresh interpreter imports sweep_helpers with no streamlit."""
        code = (
            "import sys; import pdsim.ui.sweep_helpers; "
            "sys.exit(1 if 'streamlit' in sys.modules else 0)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stderr
