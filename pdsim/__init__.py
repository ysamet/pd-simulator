"""pdsim — an evolutionary Prisoner's Dilemma simulation platform.

Agents holding strategies play repeated Prisoner's Dilemma matches; evolutionary
selection then reshapes the population generation by generation. See
``docs/DESIGN.md`` for the model and architecture specification.

Package layout (mirrors ``docs/DESIGN.md`` §3):

* ``pdsim.core``   — headless simulation engine (no UI/plotting imports).
* ``pdsim.config`` — Parameter Registry + experiment configuration.
* ``pdsim.io``     — result persistence (run folders).
* ``pdsim.viz``    — Plotly figure builders.
* ``pdsim.ui``     — Streamlit app (thin layer over the engine).
"""

__version__ = "0.1.0"
