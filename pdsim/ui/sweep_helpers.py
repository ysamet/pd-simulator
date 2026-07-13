"""Streamlit-free helpers behind the Sweep tab (M9.5b).

The same split as :mod:`pdsim.ui.helpers` (DECISIONS #38): every branch worth
testing lives here, importable without Streamlit, and the tab function in
``app.py`` stays a thin rendering shell. These helpers turn widget text into
axis values, assemble the authored :class:`~pdsim.sweep.spec.SweepSpec`,
persist it to the file the spawned CLI reads, build the exact launch command,
and read the runner's status/summary files back for the monitor.

The tab changes NOTHING about execution (DECISIONS #72): launching a sweep is
"write the YAML the user could have typed, then run the command they could
have typed" — so everything here is plain file and string work, and the
runner subprocess stays the sole writer of ``sweep_status.json`` (#70).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pdsim.config.registry import ParamValue, get_spec, validate_value
from pdsim.sweep.metrics import get_metric
from pdsim.sweep.runner import SUMMARY_SCHEMA_VERSION
from pdsim.sweep.spec import MetricRef, SweepSpec, save_sweep_spec


def parse_int_list(text: str) -> list[int]:
    """Parse a comma/space-separated list of whole numbers.

    Used for the counts and seeds text fields — ``"2, 4, 6"`` and
    ``"2 4 6"`` both parse to ``[2, 4, 6]``.

    Args:
        text: The raw widget text; empty (or whitespace-only) means an
            empty list, so a blank field is "nothing entered yet", not an
            error.

    Returns:
        The parsed integers, in the order written.

    Raises:
        ValueError: If any token is not a whole number — a plain-language
            message naming the bad token, suitable for ``st.error``.
    """
    values: list[int] = []
    for token in text.replace(",", " ").split():
        try:
            values.append(int(token))
        except ValueError:
            raise ValueError(
                f"Could not read {token!r} as a whole number — "
                "give a comma-separated list like '2, 4, 6'."
            ) from None
    return values


def build_range(start: int, stop: int, step: int) -> list[int]:
    """Build an inclusive-of-start integer range for the convenience builders.

    ``build_range(2, 20, 2)`` is ``[2, 4, ..., 20]`` — the stop value is
    included when the step lands exactly on it.

    Args:
        start: The first value.
        stop: The last candidate value (included when reached exactly).
        step: The increment between values (must be positive).

    Returns:
        The range as a list.

    Raises:
        ValueError: If the step is not positive, or ``stop`` is below
            ``start`` — plain messages for the widget area.
    """
    if step <= 0:
        raise ValueError(f"The range step must be a positive whole number, got {step}.")
    if stop < start:
        raise ValueError(f"The range end ({stop}) must not be below its start ({start}).")
    return list(range(start, stop + 1, step))


def parse_value_list(key: str, text: str) -> list[ParamValue]:
    """Parse a parameter axis's text field by its registry spec's kind.

    An ``"int"`` parameter parses tokens as whole numbers, ``"float"`` as
    numbers, ``"bool"`` as true/false, and ``"choice"`` keeps the raw
    tokens (membership is checked by :func:`validate_parameter_values`).

    Args:
        key: The axis's Parameter Registry key.
        text: The raw widget text (comma/space-separated); empty means an
            empty list.

    Returns:
        The parsed values, ready for ``validate_value``.

    Raises:
        KeyError: If the key is not in the registry (the selectbox only
            offers registry keys, so this is defensive).
        ValueError: If a token cannot be parsed as the spec's kind — a
            plain message naming the token.
    """
    spec = get_spec(key)
    values: list[ParamValue] = []
    for token in text.replace(",", " ").split():
        if spec.kind == "int":
            try:
                values.append(int(token))
            except ValueError:
                raise ValueError(
                    f"{key} expects whole numbers; could not read {token!r}."
                ) from None
        elif spec.kind == "float":
            try:
                values.append(float(token))
            except ValueError:
                raise ValueError(f"{key} expects numbers; could not read {token!r}.") from None
        elif spec.kind == "bool":
            lowered = token.lower()
            if lowered in ("true", "yes", "1"):
                values.append(True)
            elif lowered in ("false", "no", "0"):
                values.append(False)
            else:
                raise ValueError(f"{key} expects true or false; could not read {token!r}.")
        else:  # "choice" — keep the raw token; validate_value checks membership
            values.append(token)
    return values


def validate_parameter_values(key: str, values: Sequence[ParamValue]) -> list[str]:
    """Check each value of a parameter axis against the Parameter Registry.

    Belt-and-braces before :func:`~pdsim.sweep.spec.sweep_validation_messages`
    (which repeats these checks on the whole spec): running them per axis
    lets the tab show each error next to the widget that caused it.

    Args:
        key: The axis's Parameter Registry key.
        values: The parsed candidate values.

    Returns:
        One plain-language message per failing value (empty when all pass).
    """
    try:
        get_spec(key)
    except KeyError as error:
        return [str(error).strip("'")]
    messages: list[str] = []
    for value in values:
        try:
            validate_value(key, value)
        except (ValueError, KeyError) as error:
            messages.append(str(error).strip("'"))
    return messages


def build_sweep_spec(fields: Mapping[str, Any]) -> SweepSpec:
    """Assemble the tab's authored values into a SweepSpec.

    The sweep analog of :func:`pdsim.ui.helpers.build_config`: a plain dict
    in, a validated pydantic model out.

    Args:
        fields: The authored values — ``name``; ``base_kind`` (``"scenario"``
            or ``"path"``) with ``base_scenario`` / ``base_path``; optional
            ``composition`` (a dict with vary/counts/fixed/fill); a
            ``parameters`` list of ``{key, values}`` dicts; ``seeds``; and a
            ``metrics`` list of ``{metric, **params}`` dicts.

    Returns:
        The structurally-validated spec (semantic checks are
        :func:`~pdsim.sweep.spec.sweep_validation_messages`).

    Raises:
        pydantic.ValidationError: On structural problems — the caller shows
            them via :func:`pdsim.ui.helpers.validation_messages`, the same
            extraction the Run lab uses.
    """
    data: dict[str, Any] = {"name": fields.get("name", "")}
    if fields.get("base_kind") == "scenario":
        data["base_scenario"] = fields.get("base_scenario")
    else:
        data["base"] = fields.get("base_path")
    if fields.get("composition"):
        data["composition"] = fields["composition"]
    data["parameters"] = list(fields.get("parameters", []))
    data["seeds"] = list(fields.get("seeds", []))
    data["metrics"] = list(fields.get("metrics", []))
    return SweepSpec.model_validate(data)


def base_population_size(fields: Mapping[str, Any]) -> int | None:
    """Return the authored base config's population size, if loadable.

    Drives the live composition preview: the three-bucket arithmetic needs
    N. When the base cannot be loaded yet (an unknown scenario, a path not
    typed in full), the preview simply does not render — authoring errors
    are reported by the validation area, not here.

    Args:
        fields: The same authored-values dict :func:`build_sweep_spec` takes.

    Returns:
        The base population size, or ``None`` when the base is not loadable.
    """
    from pdsim.config.experiment import load_config
    from pdsim.config.scenarios import get_scenario_info

    try:
        if fields.get("base_kind") == "scenario":
            return get_scenario_info(str(fields.get("base_scenario"))).config.population.size
        return load_config(str(fields.get("base_path"))).population.size
    except Exception:  # any load problem just suppresses the preview
        return None


def authored_spec_path(out_dir: Path | str, name: str) -> Path:
    """Return where the tab persists an authored spec.

    A NAMED file under the sweeps directory — ``<out_dir>/<name>.authored.yaml``
    — not a tempfile, so the user can inspect it and re-launch it from the
    CLI (the reproducibility ethos). The runner's own verbatim copy into
    ``sweeps/<name>/sweep_spec.yaml`` remains the canonical record.

    Args:
        out_dir: The sweeps parent directory.
        name: The sweep name.

    Returns:
        The authored spec's path.
    """
    return Path(out_dir) / f"{name}.authored.yaml"


def write_authored_spec(spec: SweepSpec, path: Path | str) -> Path:
    """Persist an authored spec to the file the spawned CLI reads.

    Args:
        spec: The authored, validated spec.
        path: Destination (from :func:`authored_spec_path`).

    Returns:
        The path written to.
    """
    return save_sweep_spec(spec, path)


def launch_log_path(out_dir: Path | str, name: str) -> Path:
    """Return where a launched sweep's subprocess output is captured.

    Args:
        out_dir: The sweeps parent directory.
        name: The sweep name.

    Returns:
        ``<out_dir>/<name>.launch.log`` — created at launch time, so the
        monitor can always show it.
    """
    return Path(out_dir) / f"{name}.launch.log"


def build_launch_command(spec_path: Path | str, out_dir: Path | str) -> list[str]:
    """Build the exact command the tab launches — the one a user could type.

    The load-bearing principle of the tab (DECISIONS #72): execution is the
    unchanged headless CLI, so a tab-launched sweep is resumable,
    inspectable, and killable by the identical means as a terminal one.

    Args:
        spec_path: The authored spec file.
        out_dir: The sweeps parent directory (the CLI's ``--out``).

    Returns:
        The argv list for ``subprocess.Popen``.
    """
    return [sys.executable, "-m", "pdsim.sweep", str(spec_path), "--out", str(out_dir)]


def sweep_folder_exists(out_dir: Path | str, name: str) -> bool:
    """Report whether a sweep of this name already has a folder.

    Drives the resume-awareness notice: the runner treats an existing
    ``sweeps/<name>/`` as a resume (finished members skipped, #70), so the
    tab surfaces that behaviour rather than hiding it.

    Args:
        out_dir: The sweeps parent directory.
        name: The sweep name.

    Returns:
        True if ``<out_dir>/<name>/`` is an existing directory.
    """
    return (Path(out_dir) / name).is_dir()


def read_sweep_status(out_dir: Path | str, name: str) -> dict[str, Any] | None:
    """Read a sweep's ``sweep_status.json``, the app-poll surface (#70).

    The tab only ever READS this file; the runner subprocess is its sole
    writer. A missing file means the runner has not started (or the folder
    is not a sweep); an unreadable one (caught mid-rewrite) is treated the
    same — the user just presses Refresh again.

    Args:
        out_dir: The sweeps parent directory.
        name: The sweep name.

    Returns:
        The parsed status dict, or ``None`` when absent/unreadable.
    """
    path = Path(out_dir) / name / "sweep_status.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def status_rows(status: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a status dict's ``per_index`` into table rows for the monitor.

    Args:
        status: A dict from :func:`read_sweep_status`.

    Returns:
        One row per member — ``run_index``, ``status``, ``folder``,
        ``error`` — sorted by run index (never completion order).
    """
    rows = [
        {
            "run_index": int(index),
            "status": entry.get("status"),
            "folder": entry.get("folder"),
            "error": entry.get("error"),
        }
        for index, entry in status.get("per_index", {}).items()
    ]
    return sorted(rows, key=lambda row: row["run_index"])


def list_sweep_names(out_dir: Path | str) -> list[str]:
    """List existing sweep folder names, newest first.

    Folder truth, like the Results browser (#50): whatever directories are
    under the sweeps parent right now, most recently modified first (a
    running sweep's folder is touched on every member completion, so it
    naturally sorts to the top).

    Args:
        out_dir: The sweeps parent directory.

    Returns:
        The folder names (empty when the directory does not exist).
    """
    parent = Path(out_dir)
    if not parent.is_dir():
        return []
    folders = [path for path in parent.iterdir() if path.is_dir()]
    folders.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.name for path in folders]


def read_sweep_summary_meta(out_dir: Path | str, name: str) -> dict[str, Any] | None:
    """Read a sweep's ``sweep_summary.json`` (axis/metric columns, spec).

    Honors the schema guard (#47, fourth application): a summary written by
    a NEWER pdsim than this one is rejected with a plain message instead of
    being misread.

    Args:
        out_dir: The sweeps parent directory.
        name: The sweep name.

    Returns:
        The parsed summary metadata, or ``None`` when absent/unreadable.

    Raises:
        ValueError: If the summary's ``schema_version`` is newer than this
            code understands.
    """
    path = Path(out_dir) / name / "sweep_summary.json"
    if not path.is_file():
        return None
    try:
        meta: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(meta.get("schema_version", 0)) > SUMMARY_SCHEMA_VERSION:
        raise ValueError(
            f"Sweep {name} has summary schema_version {meta['schema_version']}; this "
            f"code understands up to {SUMMARY_SCHEMA_VERSION}. Update pdsim to load it."
        )
    return meta


def metric_display_labels(meta: Mapping[str, Any]) -> dict[str, str]:
    """Map summary metric columns to their registry display names.

    The chart's y-label idiom (#71): the display label is looked up here in
    the orchestrating layer and passed into the pure chart builder, so
    ``viz`` never imports the metrics registry.

    Args:
        meta: A dict from :func:`read_sweep_summary_meta` (its ``spec`` key
            holds the sweep's spec as written).

    Returns:
        Metric column label (e.g. ``"final_share[tit_for_tat]"``) → display
        name (e.g. ``"Final share"``). Metrics this build does not know are
        skipped — their column name is its own fallback label.
    """
    labels: dict[str, str] = {}
    for ref_data in meta.get("spec", {}).get("metrics", []):
        try:
            ref = MetricRef.model_validate(ref_data)
            labels[ref.label()] = get_metric(ref.metric).display_name
        except Exception:  # unknown metric or malformed ref: fall back to the column name
            continue
    return labels
