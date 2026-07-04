"""Configuration layer: Parameter Registry + experiment configuration.

* :mod:`pdsim.config.registry` — the single source of truth for every tunable
  parameter (hard rule 3).
* :mod:`pdsim.config.experiment` — the :class:`ExperimentConfig` pydantic
  models and YAML load/save.

Headless (hard rule 4): nothing here imports UI or plotting code.

The most-used names are re-exported so callers can write
``from pdsim.config import ExperimentConfig, load_config``.
"""

from pdsim.config.experiment import ExperimentConfig, load_config, save_config
from pdsim.config.registry import ParameterSpec, all_specs, get_spec, register, validate_value

__all__ = [
    "ExperimentConfig",
    "ParameterSpec",
    "all_specs",
    "get_spec",
    "load_config",
    "register",
    "save_config",
    "validate_value",
]
