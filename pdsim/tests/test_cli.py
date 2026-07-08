"""Tests for the headless CLI (``pdsim/run.py``, ``python -m pdsim.run``).

Calls :func:`pdsim.run.main` directly with injected argv — same code path
as the subprocess, without the interpreter-startup cost. Exit codes and
plain-language (traceback-free) error output are part of the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdsim.run import main

TINY_YAML = """
seed: 7
population:
  size: 4
  composition:
    tit_for_tat: 2
    always_defect: 2
match:
  rounds_per_match: 5
dynamics:
  generations: 2
"""


def _write_config(tmp_path: Path, text: str = TINY_YAML) -> Path:
    """Write a config YAML into the test's tmp directory.

    Args:
        tmp_path: pytest's per-test directory.
        text: YAML content.

    Returns:
        The config file path.
    """
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestSuccessfulRuns:
    """Exit code 0 and a complete run folder."""

    def test_yaml_run_records_a_folder(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A tiny config runs end to end and records everything."""
        out = tmp_path / "runs"
        code = main([str(_write_config(tmp_path)), "--out", str(out), "--quiet"])
        assert code == 0
        output = capsys.readouterr().out
        assert "Run complete: 2 generations" in output
        assert "Recorded to" in output
        folders = [p for p in out.iterdir() if p.is_dir()]
        assert len(folders) == 1
        names = {p.name for p in folders[0].iterdir()}
        assert {"config.yaml", "timeseries.parquet", "summary.json"} <= names
        assert any(name.endswith(".html") for name in names)  # chart export
        assert (out / "index.csv").exists()

    def test_quiet_suppresses_progress_lines(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--quiet drops the per-period lines but keeps the summary."""
        main([str(_write_config(tmp_path)), "--out", str(tmp_path / "runs"), "--quiet"])
        output = capsys.readouterr().out
        assert "generation 1:" not in output
        assert "Run complete" in output


class TestFailures:
    """Exit code 1 and plain-language messages, never tracebacks."""

    def test_invalid_config_value(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A registry-range violation prints the registry's own message."""
        bad = TINY_YAML.replace("generations: 2", "generations: 2\n  mutation_rate: 1.5")
        code = main([str(_write_config(tmp_path, bad)), "--out", str(tmp_path / "runs")])
        assert code == 1
        error_output = capsys.readouterr().err
        assert "at most" in error_output
        assert "Traceback" not in error_output

    def test_unknown_scenario(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--scenario with a typo lists the registered scenarios."""
        code = main(["--scenario", "definitely_not_a_scenario"])
        assert code == 1
        assert "classic_tournament" in capsys.readouterr().err

    def test_yaml_and_scenario_are_mutually_exclusive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Providing both (or neither) input source is a usage error."""
        config = _write_config(tmp_path)
        assert main([str(config), "--scenario", "classic_tournament"]) == 1
        assert "exactly one" in capsys.readouterr().err
        assert main([]) == 1

    def test_missing_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A nonexistent path fails cleanly."""
        assert main(["definitely/not/a/file.yaml"]) == 1
        assert "error:" in capsys.readouterr().err

    def test_ctrl_c_discards_the_partial_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """DECISIONS #53: an interrupted run leaves no ghost folder.

        Simulates Ctrl+C by making the engine raise KeyboardInterrupt after
        its first event.
        """
        from collections.abc import Iterator

        from pdsim.core import engine

        real_run = engine.run

        def interrupted_run(*args: object, **kwargs: object) -> Iterator[object]:
            """Yield one real event, then act like Ctrl+C."""
            yield next(iter(real_run(*args, **kwargs)))
            raise KeyboardInterrupt

        monkeypatch.setattr(engine, "run", interrupted_run)
        out = tmp_path / "runs"
        code = main([str(_write_config(tmp_path)), "--out", str(out), "--quiet"])
        assert code == 130
        assert "discarded" in capsys.readouterr().err
        assert not any(p.is_dir() for p in out.iterdir())  # no ghost folder
