"""Founding layouts: dealing a resolved composition onto sites (M11a Phase B).

At generation 0 every founding agent acquires a site. *Which* agent lands
*where* is what an "initial layout" decides — and the whole family reduces to
one engine (spec Design 8): **walk the sites in some traversal order and deal
strategies out of the resolved counts**. Only two things vary:

- the **traversal** — row-major, serpentine, tiled, or random; and
- the **dealing discipline** — run-length (each strategy's whole count as one
  consecutive run) or round-robin (one cell at a time, cycling).

**The divisibility problem dissolves.** #67 has already resolved composition
to exact integer counts per strategy, so the counts are authoritative and the
arrangement bends around them. There is no "4 strategies don't divide evenly
into 10 rows" problem because *nothing is being divided* — cells are dealt
from a deck whose composition is already fixed. This is stated because it is
exactly the kind of non-problem a later reader will otherwise try to solve
again.

**Deal order is ascending strategy machine name**, reusing #67's tie-break
convention so the project has one ordering rule for strategies rather than
two. (`build_initial_population` creates agents in composition-declaration
order; that order decides agent ids, not sites.)

**RNG contract (spec Design 9).** The founding draw is the only new draw this
phase introduces. It happens **once per run, at population construction,
before generation 0** — outside the per-generation order entirely, so it
cannot perturb any within-generation sequence. It is gated twice over: only
on a lattice, and only for a layout that actually consumes randomness
(:data:`STOCHASTIC_LAYOUTS`). The four deterministic layouts and
``from_file`` consume nothing at all — the #80/#99 active-flag idiom, where a
draw exists only when its governing flag makes it meaningful.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pdsim.core.occupancy import Occupancy
from pdsim.core.strategies import strategy_name_of
from pdsim.core.structure import LatticeStructure, SiteId, Structure

__all__ = [
    "LAYOUT_CHOICES",
    "STOCHASTIC_LAYOUTS",
    "FoundingView",
    "LayoutFile",
    "build_lattice",
    "deal_layout",
    "found_occupancy",
    "found_population",
    "founding_view",
    "layout_consumes_rng",
    "parse_layout_file",
    "read_layout_file",
    "resolve_layout_path",
]

LAYOUT_CHOICES: tuple[str, ...] = (
    "random",
    "checkerboard",
    "stripes",
    "blocks",
    "patches",
    "central_block",
    "from_file",
)
"""The seven ``structure.initial_layout`` values, in registry order."""

STOCHASTIC_LAYOUTS: frozenset[str] = frozenset({"random", "patches"})
"""The layouts that consume RNG — ``random``'s shuffle and ``patches``' seeds.

Everything else is a deterministic function of the config alone, so it draws
nothing: the gate that decides whether the founding draw happens at all
(spec Design 9's active-flag idiom).
"""

EMPTY_TOKEN = "."
"""The layout-file token meaning "this cell has no agent"."""

LAYOUT_FILE_KIND = "lattice_grid"
"""The only ``kind:`` a Phase B layout file may declare.

The discriminator ships from day one so M19's ``site_map`` variant — a
two-column site-id/strategy body, the form that needs no geometry — is a
reader dispatch rather than a format migration. There is therefore never a
layout file in the wild without a ``kind:`` line for the future reader.
"""


@dataclass(frozen=True, slots=True)
class LayoutFile:
    """A parsed layout file: a picture of the world, one token per cell.

    Attributes:
        kind: The header discriminator; ``"lattice_grid"`` in M11a.
        rows: Row count declared in the header.
        cols: Column count declared in the header.
        cells: One entry per cell in row-major order — a strategy machine
            name, or ``None`` where the file wrote ``.`` for an empty site.
    """

    kind: str
    rows: int
    cols: int
    cells: tuple[str | None, ...]
    positions: tuple[tuple[int, int], ...] = ()
    """Per cell: (file line number, cell number in that line), both 1-based.

    Carried so a validation error can say WHERE the bad token sits in the
    file the user actually wrote — the grid's row/column alone points at
    the wrong place once blank lines and comments are in play. Empty for a
    hand-built ``LayoutFile``; the validator then omits locations.
    """

    @property
    def occupied_count(self) -> int:
        """How many cells name a strategy.

        Returns:
            The number of non-empty cells, which is the population size the
            file describes.
        """
        return sum(1 for cell in self.cells if cell is not None)

    def strategy_counts(self) -> dict[str, int]:
        """Count the agents the file asks for, per strategy.

        Returns:
            Machine name → count, in ascending-name order. This *is* the
            file's composition (spec Design 8: a layout file specifies
            composition implicitly, and the file wins).
        """
        counts: dict[str, int] = {}
        for cell in self.cells:
            if cell is not None:
                counts[cell] = counts.get(cell, 0) + 1
        return {name: counts[name] for name in sorted(counts)}


def parse_layout_file(text: str) -> LayoutFile:
    """Parse layout-file text into a :class:`LayoutFile` (pure — no filesystem).

    The format (spec Design 8) is a header of ``kind:``, ``rows:`` and
    ``cols:`` lines, then a body that is a character grid — one token per
    cell, where a token is a strategy machine name or ``.`` for an empty
    site::

        kind: lattice_grid
        rows: 2
        cols: 3

        always_defect always_defect .
        tit_for_tat   .             tit_for_tat

    Tokens are separated by whitespace, or — since DECISIONS #123 — by
    commas: if ANY body line contains a comma, the entire body parses
    comma-separated with each token stripped of surrounding whitespace, so
    mixed-separator files are impossible by construction. ``.`` is the
    empty-site token in BOTH modes; an empty field between commas is an
    error, not an empty site, because a bare gap that silently meant
    "empty" would make a missing token indistinguishable from a typo.

    Blank lines are separators and are ignored; ``#`` begins a comment line.

    Args:
        text: The file's contents.

    Returns:
        The parsed layout, with per-cell file positions for error reporting.

    Raises:
        ValueError: If a header line is missing or malformed, the kind is
            not :data:`LAYOUT_FILE_KIND`, a comma-separated line has an
            empty field, or the body's cell count does not match
            ``rows × cols``. Strategy names are NOT checked here — that
            needs the strategy registry, so it belongs to the caller
            (:func:`validate_layout_file`).
    """
    header: dict[str, str] = {}
    body: list[tuple[int, str]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # The header is over as soon as a line is not `key: value`. Grid rows
        # never contain a colon (machine names are lowercase identifiers), so
        # this split is unambiguous rather than positional.
        if not body and ":" in line and "," not in line:
            key, _, value = line.partition(":")
            header[key.strip().lower()] = value.strip()
            continue
        body.append((line_number, line))

    for required in ("kind", "rows", "cols"):
        if required not in header:
            raise ValueError(
                f"Layout file is missing its {required!r} header line. A layout file "
                f"opens with 'kind: {LAYOUT_FILE_KIND}', then 'rows:' and 'cols:'."
            )
    if header["kind"] != LAYOUT_FILE_KIND:
        raise ValueError(
            f"Layout file declares kind {header['kind']!r}; this version of pdsim "
            f"reads only {LAYOUT_FILE_KIND!r} layouts."
        )
    try:
        rows = int(header["rows"])
        cols = int(header["cols"])
    except ValueError:
        raise ValueError(
            f"Layout file has non-numeric dimensions: rows={header['rows']!r}, "
            f"cols={header['cols']!r}."
        ) from None
    if rows < 1 or cols < 1:
        raise ValueError(f"Layout file dimensions must be at least 1x1, got {rows}x{cols}.")

    # One comma anywhere in the body puts the WHOLE body in comma mode —
    # a per-line choice would let one malformed line silently change how
    # its neighbours parse (DECISIONS #123).
    comma_mode = any("," in line for _, line in body)
    tokens: list[str] = []
    positions: list[tuple[int, int]] = []
    for line_number, line in body:
        if comma_mode:
            fields = [field.strip() for field in line.split(",")]
            for cell_number, field in enumerate(fields, start=1):
                if not field:
                    raise ValueError(
                        f"Layout file has an empty field on line {line_number} "
                        f"(cell {cell_number}). Write {EMPTY_TOKEN!r} for an empty "
                        "site — a bare gap between commas is treated as a mistake, "
                        "not as an empty site, so a missing token cannot hide."
                    )
                tokens.append(field)
                positions.append((line_number, cell_number))
        else:
            for cell_number, field in enumerate(line.split(), start=1):
                tokens.append(field)
                positions.append((line_number, cell_number))
    if len(tokens) != rows * cols:
        raise ValueError(
            f"Layout file declares {rows}x{cols} = {rows * cols} cells but its body "
            f"holds {len(tokens)} tokens. Every cell needs a token; write "
            f"{EMPTY_TOKEN!r} for an empty site."
        )
    cells = tuple(None if token == EMPTY_TOKEN else token for token in tokens)
    return LayoutFile(
        kind=header["kind"], rows=rows, cols=cols, cells=cells, positions=tuple(positions)
    )


def read_layout_file(path: str | Path) -> LayoutFile:
    """Read and parse a layout file from disk.

    Args:
        path: Path to the layout file.

    Returns:
        The parsed layout.

    Raises:
        FileNotFoundError: If the path does not exist, with the resolved
            absolute path in the message — a relative path that looks right
            but resolves somewhere unexpected is the common failure.
        ValueError: If the contents are malformed (see
            :func:`parse_layout_file`).
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Layout file {path!r} does not exist (looked in {file_path.resolve()})."
        ) from None
    return parse_layout_file(text)


def validate_layout_file(
    layout: LayoutFile,
    *,
    rows: int,
    cols: int,
    known_strategies: frozenset[str],
    population_size: int,
) -> None:
    """Check a parsed layout against the run it is being used for.

    The three validators from spec Design 8, plus the population-size check
    that makes "the file wins on composition" implementable: the file decides
    *which* strategy each agent has, so the only thing the user must keep in
    step is *how many* agents there are.

    Args:
        layout: The parsed layout file.
        rows: The run's resolved ``structure.rows``.
        cols: The run's resolved ``structure.cols``.
        known_strategies: Every registered strategy machine name.
        population_size: The run's ``population.size``.

    Raises:
        ValueError: If the header dimensions disagree with the resolved grid,
            a token names an unregistered strategy, or the file's agent count
            differs from the population size. Every message names both
            numbers and says which knob to change.
    """
    if (layout.rows, layout.cols) != (rows, cols):
        raise ValueError(
            f"Layout file is {layout.rows}x{layout.cols} but this run's grid is "
            f"{rows}x{cols}. Change the file's header, or set structure.rows / "
            "structure.cols to match it."
        )
    offenders: list[str] = []
    for index, cell in enumerate(layout.cells):
        if cell is None or cell in known_strategies:
            continue
        if index < len(layout.positions):
            line_number, cell_number = layout.positions[index]
            offenders.append(f"{cell!r} (line {line_number}, cell {cell_number})")
        else:
            offenders.append(repr(cell))
    if offenders:
        raise ValueError(
            f"Layout file names unregistered strategies: {'; '.join(offenders)}. "
            f"Every non-'{EMPTY_TOKEN}' token must be a strategy machine name, "
            f"spelled exactly as registered. Valid names: "
            f"{', '.join(sorted(known_strategies))}."
        )
    if layout.occupied_count != population_size:
        raise ValueError(
            f"Layout file places {layout.occupied_count} agents but population.size is "
            f"{population_size}. The file decides WHICH strategy each agent has; the "
            "population size must still agree with how many cells it fills."
        )


def layout_consumes_rng(kind: str, initial_layout: str) -> bool:
    """Report whether founding will draw from the run's generator.

    The gate from spec Design 9, in one place so the engine, the tests, and
    the no-draw assertions all read the same predicate.

    Args:
        kind: ``structure.kind`` — ``"well_mixed"`` or ``"lattice"``.
        initial_layout: ``structure.initial_layout``.

    Returns:
        True only for a lattice with a stochastic layout.
    """
    return kind == "lattice" and initial_layout in STOCHASTIC_LAYOUTS


def _centre_ordered_sites(structure: LatticeStructure) -> tuple[SiteId, ...]:
    """Order every site by how far it sits from the grid's centre.

    The footprint rule for ``blocks``, ``checkerboard`` and ``patches`` when
    the population is smaller than the site count (spec Design 8): they
    occupy a **centred contiguous** block, because a patterned arrangement
    is a statement about contiguous structure and would be destroyed by
    scattering its cells. (``stripes`` used this ball too until #127/#150
    gave it its own full-width band — see :func:`_stripes_footprint` — and
    ``central_block`` has its definitional rectangle, #125.)

    Distance here is Chebyshev (the larger of the row and column offsets)
    regardless of the run's neighbourhood shape, so the footprint is a
    centred rectangle for every configuration — under the von Neumann metric
    the same rule would carve a diamond, which is not what "central block"
    describes.

    Args:
        structure: The lattice to order.

    Returns:
        Every site id, nearest-to-centre first, ties broken ascending by id.
    """
    centre_row = (structure.rows - 1) / 2.0
    centre_col = (structure.cols - 1) / 2.0

    def key(site_id: SiteId) -> tuple[float, SiteId]:
        row, col = divmod(site_id, structure.cols)
        return (max(abs(row - centre_row), abs(col - centre_col)), site_id)

    return tuple(sorted(structure.site_ids, key=key))


def _footprint(structure: LatticeStructure, size: int, layout: str) -> tuple[SiteId, ...]:
    """Choose which sites are occupied at all, in traversal-independent form.

    Args:
        structure: The lattice.
        size: How many agents there are.
        layout: The layout name.

    Returns:
        Exactly ``size`` site ids: the whole grid (ascending) when the
        population fills it, a centred block otherwise. ``random`` is handled
        by its caller, which scatters over the whole grid instead;
        ``stripes`` and ``central_block`` have their own footprints.
    """
    if size >= structure.site_count:
        return structure.site_ids
    return tuple(sorted(_centre_ordered_sites(structure)[:size]))


def _stripes_footprint(structure: LatticeStructure, size: int) -> tuple[SiteId, ...]:
    """The sparse ``stripes`` footprint: a centred FULL-WIDTH horizontal band.

    ``stripes``' purpose is broad horizontal bands, and the generic centred
    blob destroys exactly the property the layout is named for — so when N
    is below the site count, ``stripes`` occupies a band spanning every
    column instead (#127, implemented under #150; this cannot arise under
    ``fixed_n``, where a validator requires N = site count).

    The rule: the band is ``ceil(N / cols)`` rows tall, centred vertically
    by integer division. Every band row is full-width except — when N is
    not a multiple of the column count — the band's LAST row, which holds
    the remainder centred horizontally, again by integer division. Dealing
    inside the band is unchanged: run-length, row-major, ascending machine
    name, and no RNG on any path.

    Args:
        structure: The lattice.
        size: How many agents there are.

    Returns:
        Exactly ``size`` site ids in ascending order: the whole grid when
        the population fills it, the centred band otherwise.
    """
    if size >= structure.site_count:
        return structure.site_ids
    cols = structure.cols
    band_rows = -(-size // cols)  # ceil(size / cols) in pure integer form
    top = (structure.rows - band_rows) // 2
    remainder = size % cols
    full_rows = band_rows if remainder == 0 else band_rows - 1
    sites = [row * cols + col for row in range(top, top + full_rows) for col in range(cols)]
    if remainder:
        last_row = top + band_rows - 1
        start = (cols - remainder) // 2
        sites.extend(last_row * cols + col for col in range(start, start + remainder))
    return tuple(sites)


def _central_block_footprint(structure: LatticeStructure, size: int) -> tuple[SiteId, ...]:
    """The `central_block` footprint: a centred RECTANGLE of exactly N cells.

    Design 8 defines this layout's footprint definitionally — "a centred
    rectangle sized to N" — which is NOT the generic centred blob the other
    patterned layouts use (#125; the two coincide only when the blob happens
    to be a rectangle, e.g. a perfect-square N on an even grid). The
    rectangle is the most-square factor pair of N that fits the grid, in
    either orientation, so a wide grid gets a wide block and a tall grid a
    tall one; a prime N makes a single line, the same reading the grid's own
    auto-sizing gives prime populations.

    When NO exact rectangle of N cells fits — a prime N larger than both
    grid dimensions — the footprint falls back to the generic centred blob:
    the most compact centred shape that always exists, keeping the layout
    total rather than refusing a legal configuration.

    Args:
        structure: The lattice.
        size: How many agents there are.

    Returns:
        Exactly ``size`` site ids in ascending order: the whole grid when
        the population fills it, the centred rectangle otherwise.
    """
    if size >= structure.site_count:
        return structure.site_ids
    rows, cols = structure.rows, structure.cols
    for divisor in range(math.isqrt(size), 0, -1):
        if size % divisor:
            continue
        a, b = divisor, size // divisor
        for block_rows, block_cols in ((a, b), (b, a)):
            if block_rows <= rows and block_cols <= cols:
                top = (rows - block_rows) // 2
                left = (cols - block_cols) // 2
                return tuple(
                    row * cols + col
                    for row in range(top, top + block_rows)
                    for col in range(left, left + block_cols)
                )
    return _footprint(structure, size, "central_block")


def _row_major(structure: LatticeStructure, footprint: Sequence[SiteId]) -> list[SiteId]:
    """Traverse a footprint row by row, always left to right.

    Args:
        structure: The lattice (for the row/column inversion).
        footprint: The occupied sites.

    Returns:
        The footprint in row-major order.
    """
    return sorted(footprint)


def _serpentine(structure: LatticeStructure, footprint: Sequence[SiteId]) -> list[SiteId]:
    """Traverse a footprint boustrophedon — alternate rows run right to left.

    Why this matters twice over. For ``blocks`` it keeps a run of one
    strategy spatially contiguous where it spills from one row into the next
    (a row-major sweep would drop it from the right edge back to the left).
    For ``checkerboard`` it is what makes the literal chessboard come out:
    round-robin dealing along a snake alternates strategies between vertically
    adjacent cells too, which a row-major sweep only manages when the column
    count happens to be odd.

    Args:
        structure: The lattice (for the row/column inversion).
        footprint: The occupied sites.

    Returns:
        The footprint in serpentine order.
    """
    included = set(footprint)
    ordered: list[SiteId] = []
    for row in range(structure.rows):
        columns = range(structure.cols) if row % 2 == 0 else reversed(range(structure.cols))
        ordered.extend(
            site_id
            for site_id in (row * structure.cols + col for col in columns)
            if site_id in included
        )
    return ordered


def _tiled(structure: LatticeStructure, footprint: Sequence[SiteId]) -> list[SiteId]:
    """Traverse a footprint tile by tile, tiles in serpentine order.

    This is what makes ``blocks`` compact in *two* dimensions rather than one:
    a run-length deal along this order fills chunky rectangles instead of
    horizontal bands. The tile size is derived, not a parameter — roughly the
    square root of each dimension, which degrades gracefully at any grid size
    (a 1-row lattice tiles into segments of a line).

    Args:
        structure: The lattice.
        footprint: The occupied sites.

    Returns:
        The footprint in tiled-serpentine order.
    """
    included = set(footprint)
    tile_rows = max(1, math.isqrt(structure.rows))
    tile_cols = max(1, math.isqrt(structure.cols))
    ordered: list[SiteId] = []
    band_index = 0
    for tile_top in range(0, structure.rows, tile_rows):
        lefts = list(range(0, structure.cols, tile_cols))
        if band_index % 2 == 1:
            lefts.reverse()
        for tile_left in lefts:
            for row in range(tile_top, min(tile_top + tile_rows, structure.rows)):
                for col in range(tile_left, min(tile_left + tile_cols, structure.cols)):
                    site_id = row * structure.cols + col
                    if site_id in included:
                        ordered.append(site_id)
        band_index += 1
    return ordered


def _run_length(order: Sequence[SiteId], counts: Mapping[str, int]) -> dict[SiteId, str]:
    """Deal each strategy's whole count as one consecutive run.

    Args:
        order: The traversal order to deal along.
        counts: Machine name → count.

    Returns:
        Site id → strategy machine name.
    """
    placement: dict[SiteId, str] = {}
    position = 0
    for name in sorted(counts):
        for _ in range(counts[name]):
            placement[order[position]] = name
            position += 1
    return placement


def _round_robin(order: Sequence[SiteId], counts: Mapping[str, int]) -> dict[SiteId, str]:
    """Deal one cell at a time, cycling over the strategies still holding agents.

    With two equal counts this reproduces the literal checkerboard; with four
    unequal ones it produces maximal interleaving — which is the *purpose*
    #109 assigns this layout (the anti-cluster baseline). Generalise by
    purpose, not by appearance: the job is "no strategy next to itself where
    avoidable", not "look like a chessboard".

    Args:
        order: The traversal order to deal along.
        counts: Machine name → count.

    Returns:
        Site id → strategy machine name.
    """
    remaining = {name: counts[name] for name in sorted(counts)}
    placement: dict[SiteId, str] = {}
    position = 0
    while position < len(order) and any(remaining.values()):
        for name in list(remaining):
            if remaining[name] == 0:
                continue
            placement[order[position]] = name
            remaining[name] -= 1
            position += 1
            if position >= len(order):
                break
    return placement


def _patches(
    structure: LatticeStructure,
    footprint: Sequence[SiteId],
    counts: Mapping[str, int],
    rng: np.random.Generator,
) -> dict[SiteId, str]:
    """Grow one patch per strategy from an RNG-placed seed.

    One seed site per strategy is drawn (the single RNG draw), then the
    patches grow outward simultaneously, each strategy's quota its growth
    budget. Everything after the seed draw is deterministic: growth claims
    the lowest-id unclaimed site adjacent to the patch, falling back to the
    nearest unclaimed footprint site when a patch is walled in.

    Args:
        structure: The lattice (for adjacency and distance).
        footprint: The occupied sites.
        counts: Machine name → count.
        rng: The run's seeded generator.

    Returns:
        Site id → strategy machine name.
    """
    names = sorted(counts)
    available = sorted(footprint)
    # ONE draw, whatever the strategy count: seeds without replacement.
    seeds = rng.choice(len(available), size=len(names), replace=False)
    placement: dict[SiteId, str] = {}
    remaining = dict(counts)
    frontier: dict[str, list[SiteId]] = {}
    for name, seed_index in zip(names, seeds, strict=True):
        site_id = available[int(seed_index)]
        placement[site_id] = name
        remaining[name] -= 1
        frontier[name] = [site_id]
    unclaimed = [site_id for site_id in available if site_id not in placement]
    while any(remaining[name] > 0 for name in names) and unclaimed:
        progressed = False
        for name in names:
            if remaining[name] <= 0:
                continue
            candidates = sorted(
                site_id
                for claimed in frontier[name]
                for site_id in structure.neighbours(claimed)
                if site_id not in placement and site_id in set(unclaimed)
            )
            if candidates:
                chosen = candidates[0]
            else:
                # Walled in: jump to the nearest unclaimed site, measured from
                # the patch's seed. Deterministic, and it keeps the quota
                # honest rather than silently under-filling the deck.
                origin = frontier[name][0]
                chosen = min(
                    unclaimed, key=lambda site_id: (structure.distance(origin, site_id), site_id)
                )
            placement[chosen] = name
            frontier[name].append(chosen)
            remaining[name] -= 1
            unclaimed.remove(chosen)
            progressed = True
            if not unclaimed:
                break
        if not progressed:
            break
    return placement


def deal_layout(
    structure: LatticeStructure,
    counts: Mapping[str, int],
    layout: str,
    rng: np.random.Generator,
    layout_file: LayoutFile | None = None,
) -> dict[SiteId, str]:
    """Deal a resolved composition onto sites, by the chosen layout.

    Args:
        structure: The lattice to deal onto.
        counts: Machine name → exact agent count (already #67-resolved).
        layout: One of :data:`LAYOUT_CHOICES`.
        rng: The run's seeded generator. Consumed only by the layouts in
            :data:`STOCHASTIC_LAYOUTS` — exactly one draw, and none at all
            for the rest.
        layout_file: The parsed file, required when ``layout`` is
            ``"from_file"`` and ignored otherwise.

    Returns:
        Site id → strategy machine name, for the occupied sites only. Sites
        absent from the mapping are empty.

    Raises:
        ValueError: If the layout name is unknown, ``from_file`` arrives
            without a file, or the counts do not fit the grid.
    """
    if layout not in LAYOUT_CHOICES:
        raise ValueError(f"Unknown initial_layout {layout!r}; expected one of {LAYOUT_CHOICES}.")
    if layout == "from_file":
        if layout_file is None:
            raise ValueError("initial_layout='from_file' needs a parsed layout file.")
        return {site_id: name for site_id, name in enumerate(layout_file.cells) if name is not None}

    size = sum(counts.values())
    if size > structure.site_count:
        raise ValueError(
            f"{size} agents cannot be placed on {structure.site_count} sites — "
            "every site holds at most one agent."
        )
    if layout == "random":
        # "Random" means random: a scattered start over the WHOLE grid, the
        # closest spatial analogue of the well-mixed baseline. One draw.
        scattered = rng.permutation(structure.site_count)[:size]
        order = [int(site_id) for site_id in scattered]
        return _run_length(order, counts)

    if layout == "central_block":
        # The definitional footprint (Design 8, #125): a centred RECTANGLE
        # sized to N, dealt run-length row-major inside. On a full grid the
        # rectangle is the whole world and the picture coincides with
        # `stripes` — inherent, since the layout's defining feature is the
        # empty frame and a full world has none.
        rectangle = _central_block_footprint(structure, size)
        return _run_length(_row_major(structure, rectangle), counts)
    if layout == "stripes":
        # `stripes` sweeps its full-width band (#127/#150) row-major, so a
        # strategy's run breaks at the row edge — a "stripe" can be a
        # fragment of a row, because stripe boundaries fall where the
        # COUNTS fall.
        return _run_length(_row_major(structure, _stripes_footprint(structure, size)), counts)

    footprint = _footprint(structure, size, layout)
    if layout == "patches":
        return _patches(structure, footprint, counts, rng)
    if layout == "checkerboard":
        return _round_robin(_serpentine(structure, footprint), counts)
    # `blocks` — the one layout left after the dispatch above.
    return _run_length(_tiled(structure, footprint), counts)


def found_occupancy(
    structure: Structure,
    agents: Sequence[object],
    counts: Mapping[str, int],
    layout: str,
    rng: np.random.Generator,
    layout_file: LayoutFile | None = None,
) -> Occupancy:
    """Place every founding agent on a site, and return the occupancy.

    Agents are matched to sites **by strategy**: the deal decides which
    strategy sits in which site, and the agents carrying that strategy are
    assigned to those sites in ascending agent-id order. Under ``from_file``
    the file also decides *which* strategy each agent carries — the file wins
    on composition (spec Design 8), so an agent's ``strategy`` attribute is
    overwritten to match the cell it lands in.

    Args:
        structure: The lattice (a well-mixed structure has no layout).
        agents: The founding agents, in ascending id order. Each must expose
            ``agent_id`` and ``strategy``; typed loosely to keep this module
            free of an import cycle with the agent module.
        counts: Machine name → count, matching the agents.
        layout: One of :data:`LAYOUT_CHOICES`.
        rng: The run's seeded generator.
        layout_file: The parsed file when ``layout`` is ``"from_file"``.

    Returns:
        A fully populated :class:`~pdsim.core.occupancy.Occupancy`.

    Raises:
        TypeError: If ``structure`` is not a lattice — only the lattice
            builder has a geometry to lay agents out on.
        ValueError: If the deal cannot be matched to the agents.
    """
    if not isinstance(structure, LatticeStructure):
        raise TypeError(
            "Founding layouts are defined on a lattice; a well-mixed run places nobody "
            "(and must not route through structure code at all — spec principle 1)."
        )
    placement = deal_layout(structure, counts, layout, rng, layout_file)
    occupancy = Occupancy(structure)

    # Bucket the agents by the strategy they were built with, keeping each
    # bucket in ascending id order so the assignment is deterministic.
    by_strategy: dict[str, list[object]] = {}
    for agent in agents:
        name = strategy_name_of(agent.strategy)  # type: ignore[attr-defined]
        by_strategy.setdefault(name, []).append(agent)
    if layout == "from_file":
        # The file wins: agents are handed out in ascending id order and take
        # whatever strategy their cell names. Sorting the sites keeps that
        # assignment reproducible.
        from pdsim.core.strategies.registry import create_strategy

        instances: dict[str, object] = {}
        ordered_agents = sorted(agents, key=lambda a: a.agent_id)  # type: ignore[attr-defined]
        ordered_sites = sorted(placement)
        if len(ordered_agents) != len(ordered_sites):
            raise ValueError(
                f"Layout file places {len(ordered_sites)} agents but the population has "
                f"{len(ordered_agents)}."
            )
        for agent, site_id in zip(ordered_agents, ordered_sites, strict=True):
            name = placement[site_id]
            if name not in instances:
                instances[name] = create_strategy(name)
            agent.strategy = instances[name]  # type: ignore[attr-defined]
            occupancy.occupy(site_id, agent.agent_id)  # type: ignore[attr-defined]
        return occupancy

    cursors: dict[str, int] = dict.fromkeys(by_strategy, 0)
    for site_id in sorted(placement):
        name = placement[site_id]
        bucket = by_strategy.get(name, [])
        index = cursors.get(name, 0)
        if index >= len(bucket):
            raise ValueError(
                f"The {layout!r} layout dealt more {name!r} agents than the population "
                "holds; the deal and the resolved composition have diverged."
            )
        occupancy.occupy(site_id, bucket[index].agent_id)  # type: ignore[attr-defined]
        cursors[name] = index + 1
    return occupancy


GRID_TEMPLATES_DIR = Path("grid_templates")
"""Default home for hand-authored layout files (DECISIONS #122).

Relative to the working directory, like ``runs/`` and ``sweeps/`` — the
project's directory convention. It ships in the repository with a README
stating the format and two commented examples.
"""


def resolve_layout_path(layout_file: str, config_dir: Path | None = None) -> Path:
    """Resolve a configured layout-file value to an actual path.

    The rule (DECISIONS #122 — spec Design 8 is silent on resolution, so
    this is an extension): a value containing **no path separator** is a
    template name and resolves against :data:`GRID_TEMPLATES_DIR`; a value
    containing a separator, or an absolute path, is used as given. One
    exception outranks the template folder: a recorded run keeps a copy of
    its layout beside its ``config.yaml`` under a bare name (hard rule 8),
    and that copy must win — otherwise re-running an old folder could
    silently read a same-named template written later.

    Args:
        layout_file: The configured value — a bare template name, or a path.
        config_dir: The folder the config was loaded from, when it came from
            a file; ``None`` for an in-memory config (the app).

    Returns:
        The first path that exists in precedence order (beside-config for
        bare names, then ``grid_templates/``, then as given); when nothing
        exists, the most likely intended path — so the caller's
        FileNotFoundError names the place the user should look.
    """
    given = Path(layout_file)
    bare = given.name == layout_file and not given.is_absolute()
    if bare:
        if config_dir is not None and (Path(config_dir) / layout_file).is_file():
            return Path(config_dir) / layout_file
        return GRID_TEMPLATES_DIR / layout_file
    if given.is_file() or config_dir is None:
        return given
    beside = Path(config_dir) / given.name
    return beside if beside.is_file() else given


def build_lattice(config: object) -> LatticeStructure:
    """Build the lattice a config describes.

    Args:
        config: A validated ``ExperimentConfig`` (typed loosely to keep this
            module importable from the config layer without a cycle). Its
            ``structure.rows`` / ``cols`` are already resolved to plain
            numbers by ``_resolve_structure_dimensions``.

    Returns:
        The immutable topology.

    Raises:
        ValueError: If the dimensions are still unresolved — a standalone
            ``StructureConfig`` never reaches the engine, so this is a
            programming error rather than a user one.
    """
    structure = config.structure  # type: ignore[attr-defined]
    if structure.rows is None or structure.cols is None:
        raise ValueError(
            "Lattice dimensions are unresolved; build the structure from a validated "
            "ExperimentConfig, which always stores plain numbers (hard rule 8)."
        )
    return LatticeStructure(
        rows=structure.rows,
        cols=structure.cols,
        neighbourhood_shape=structure.neighbourhood_shape,
        boundary=structure.boundary,
    )


def found_population(
    config: object,
    agents: Sequence[object],
    rng: np.random.Generator,
    config_dir: Path | None = None,
) -> Occupancy | None:
    """Give every founding agent a site, or return ``None`` for a well-mixed run.

    This is the engine's single entry point into structure code, called once
    per run at population construction — before generation 0, and before any
    other draw. A well-mixed run returns here before building any structure
    at all and consumes no randomness, which is what makes byte-identity to
    every pre-M11a run true by construction rather than by test (spec
    Defining principle 1).

    Args:
        config: The validated ``ExperimentConfig``.
        agents: The founding agents, ascending by id.
        rng: The run's seeded generator.
        config_dir: Folder to resolve a relative ``layout_file`` against when
            the working directory does not hold it.

    Returns:
        The founding occupancy, or ``None`` when ``structure.kind`` is
        ``"well_mixed"``.

    Raises:
        FileNotFoundError: If a needed layout file is missing.
        ValueError: If a layout file disagrees with the run it is used for.
    """
    structure_config = config.structure  # type: ignore[attr-defined]
    if structure_config.kind != "lattice":
        return None

    structure = build_lattice(config)
    layout = structure_config.initial_layout
    layout_file: LayoutFile | None = None
    if layout == "from_file":
        from pdsim.core.strategies.registry import all_strategy_names

        path = resolve_layout_path(structure_config.layout_file or "", config_dir)
        layout_file = read_layout_file(path)
        validate_layout_file(
            layout_file,
            rows=structure.rows,
            cols=structure.cols,
            known_strategies=frozenset(all_strategy_names()),
            population_size=len(agents),
        )

    counts: dict[str, int] = {}
    for agent in agents:
        name = strategy_name_of(agent.strategy)  # type: ignore[attr-defined]
        counts[name] = counts.get(name, 0) + 1
    return found_occupancy(structure, agents, counts, layout, rng, layout_file)


@dataclass(frozen=True, slots=True)
class FoundingView:
    """Everything the app needs to draw and describe a founding arrangement.

    A pure function of (config, seed), computed without running anything —
    the paint-time resolver pattern Design 11 mandates, so the panel and the
    engine can never disagree about what the grid looks like.

    Attributes:
        rows: Resolved grid rows.
        cols: Resolved grid columns.
        site_count: ``rows × cols`` — the world's capacity, since every site
            holds at most one agent.
        layout: The ``initial_layout`` that produced this arrangement.
        placements: Site id → strategy machine name, occupied sites only.
        isolated: How many agents have no occupied neighbour (Design 8's
            mandatory guard — a scattered start under a sparse population
            can strand agents, which is correct but bewildering unless the
            app says so).
    """

    rows: int
    cols: int
    site_count: int
    layout: str
    placements: dict[SiteId, str]
    isolated: int

    @property
    def occupied(self) -> int:
        """How many sites hold an agent.

        Returns:
            The occupied-site count.
        """
        return len(self.placements)

    @property
    def occupancy_fraction(self) -> float:
        """What share of the world is occupied.

        Returns:
            Occupied sites divided by site count, between 0 and 1.
        """
        return self.occupied / self.site_count if self.site_count else 0.0


def founding_view(config: object, config_dir: Path | None = None) -> FoundingView | None:
    """Replay a run's founding arrangement from its config alone.

    The grid renderer needs "which strategy sits in which cell" even for runs
    that persist no per-agent data at all — synchronous imitation writes
    empty snapshots by design, and VT-2 confirmed that its agent ids are
    preserved across generations, so occupancy never changes after founding
    and there is nothing to record (spec Design 10's nothing-to-persist
    branch).

    Replay is exact because the founding draw is the FIRST draw of the run:
    a fresh generator seeded identically reproduces it before anything else
    has touched the stream.

    Args:
        config: The validated ``ExperimentConfig``.
        config_dir: Folder to resolve a relative ``layout_file`` against.

    Returns:
        The founding view, or ``None`` for a run with no structure (well
        mixed, or a tournament — where nothing is born or dies, so space has
        nothing to do).

    Raises:
        FileNotFoundError: If a needed layout file is missing.
        ValueError: If a layout file disagrees with the run it is used for.
    """
    if config.structure.kind != "lattice":  # type: ignore[attr-defined]
        return None
    if getattr(config, "mode", "evolution") != "evolution":
        return None
    # Deferred import: the dynamics module imports this one, so a top-level
    # import here would close the cycle.
    from pdsim.core.dynamics import build_initial_population

    agents = build_initial_population(config)  # type: ignore[arg-type]
    rng = np.random.default_rng(config.seed)  # type: ignore[attr-defined]
    occupancy = found_population(config, agents, rng, config_dir)
    if occupancy is None:
        return None
    by_id = {agent.agent_id: agent for agent in agents}
    structure = occupancy.structure
    assert isinstance(structure, LatticeStructure)  # built by found_population
    return FoundingView(
        rows=structure.rows,
        cols=structure.cols,
        site_count=structure.site_count,
        layout=config.structure.initial_layout,  # type: ignore[attr-defined]
        placements={
            site_id: strategy_name_of(by_id[agent_id].strategy)
            for agent_id, site_id in occupancy.sites_by_agent().items()
        },
        isolated=len(occupancy.isolated_agents()),
    )
