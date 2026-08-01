"""Population structure: the graph of sites (DESIGN §2.12; M11a, DECISIONS #103-#110).

M11a gives the world a shape. The population stops being a bare list and
becomes a set of **sites** — exclusive containers, each holding at most one
agent — connected by a neighbour relation, with a notion of *distance*
between them. Both "who you play" and "where your children land" will be
decided by that distance (in later M11a phases; this module ships first).

**Phase A status — wired to nothing.** No engine code imports this module
yet. It exists so the abstraction can be judged on its own: the well-mixed
engine does not route through structure code at all, which is what keeps
every existing seeded run byte-identical by construction (spec Defining
principle 1).

The three forward-guards for M19's geographic structures (#104):

1. The core abstraction is a **graph of sites, never a rectangle** — the
   rectangular lattice is ONE builder over it; the core never knows about
   rows and columns.
2. The **capacity field ships now**, pinned at 1 (Design 12), so per-site
   capacity above 1 is later a parameter change, not a migration of the
   placement seam.
3. **Distance is a method the structure supplies**, not a constant the
   kernel assumes — an irregular site set with shared-border adjacency can
   define its own metric without any kernel change.

A functional-programming note (a learning thread of this project):
:func:`sites_within` and :func:`kernel_weights` are *pure functions* — same
inputs, same outputs, no side effects, and no randomness. The random draw
lives only in :func:`neighbourhood_sample`, which composes the two pure
functions with one seeded draw at the end. Tests can therefore pin the
candidate sets and weights exactly, with no RNG in the assertion path.

**The determinism rule (spec Design 2 — a rule, not advice):** every
candidate site list is built in ascending site-id order before any draw
touches it. Without this, draw outcomes would depend on set iteration
order — a reproducibility bug that survives every test until a Python
version changes hashing, and then every golden master breaks at once with
no code diff to blame.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np

SiteId = int
"""Type alias: sites are identified by plain integers, dealt in ascending order."""

SITE_CAPACITY: Final[int] = 1
"""How many agents a site may hold — pinned at 1 for all of M11 (Design 12).

The *field* exists so the placement seam can read ``occupants < capacity``
from day one; the *knob* is deferred to M19, because capacity above 1 forces
questions M11a has no answers to (what the kernel does at distance zero,
what colour a mixed cell is, what k even means). ``Final`` (new concept)
marks a name as a constant to type checkers — reassigning it elsewhere is
flagged as an error.
"""

WELL_MIXED_DISTANCE: Final[int] = 1
"""The distance between any two distinct sites in a well-mixed structure.

The constant's value is arbitrary by design: in a well-mixed world distance
never differentiates anything, so all that matters is that every distinct
pair sits at the SAME distance. The tested property is that kernel weights
over it are uniform for any decay — exp(-β·1) is the same number for every
candidate, so the normalised draw is uniform no matter what β is.
"""


@dataclass(frozen=True, slots=True)
class Site:
    """One exclusive container in the world's structure (DESIGN §2.12, #104).

    Attributes:
        id: Unique integer identifier. All site orderings in this project are
            ascending-id (spec Defining principle 5).
        neighbours: The ids of the sites adjacent to this one. Adjacency is
            symmetric and never includes the site itself.
        capacity: How many agents the site can hold — always
            :data:`SITE_CAPACITY` (1) in M11a, validated by
            :class:`Structure`. M19 turns this into a tunable parameter.
        coordinate: Optional ``(row, col)`` grid position. The lattice
            builder fills it in and the renderer will use it to draw the
            grid, but nothing in the core requires it: M19's site sets (e.g.
            municipalities with shared-border adjacency) have ids and
            neighbours but no natural rows and columns.
    """

    id: SiteId
    neighbours: frozenset[SiteId]
    capacity: int = SITE_CAPACITY
    coordinate: tuple[int, int] | None = None


class Structure(ABC):
    """The immutable topology: sites, the neighbour relation, and distance.

    This is ALL the core ever sees (spec Design 0). A ``Structure`` is a pure
    value derived once from the config and never changed during a run — which
    is what lets it be shared, cached, and (in Phase E) precomputed. The
    mutable per-run counterpart, ``Occupancy`` (site → agent bookkeeping), is
    a separate object that arrives in Phase B; keeping the two apart is the
    difference between M19 writing a builder and M19 writing an engine
    (spec Design 3).

    Subclasses build the site set and supply the metric; everything else —
    lookups, the neighbour relation, the shared validation — lives here.
    """

    def __init__(self, sites: Iterable[Site]) -> None:
        """Store and validate the site set, in ascending-id order.

        Args:
            sites: The structure's sites, in any order; they are sorted by id
                here so every downstream enumeration is ascending (spec
                Defining principle 5).

        Raises:
            ValueError: If the site set is empty, ids repeat, a capacity is
                not :data:`SITE_CAPACITY` (the M11a pin — M19 removes this
                validator when capacity becomes tunable), a neighbour set
                names an unknown site, or a site lists itself as a
                neighbour.
        """
        ordered = sorted(sites, key=lambda site: site.id)
        if not ordered:
            raise ValueError("A structure needs at least one site.")
        self._sites: dict[SiteId, Site] = {}
        for site in ordered:
            if site.id in self._sites:
                raise ValueError(f"Duplicate site id {site.id}; site ids must be unique.")
            if site.capacity != SITE_CAPACITY:
                raise ValueError(
                    f"Site {site.id} has capacity {site.capacity}; M11a pins every "
                    f"site's capacity at {SITE_CAPACITY} (Design 12 — the knob is M19)."
                )
            self._sites[site.id] = site
        known = self._sites.keys()
        for site in ordered:
            if site.id in site.neighbours:
                raise ValueError(f"Site {site.id} lists itself as a neighbour.")
            unknown = site.neighbours - known
            if unknown:
                raise ValueError(
                    f"Site {site.id} has neighbour id(s) {sorted(unknown)} that do not "
                    "exist in the structure."
                )

    @property
    def sites(self) -> tuple[Site, ...]:
        """All sites, in ascending-id order.

        Returns:
            An immutable snapshot of the site records.
        """
        return tuple(self._sites.values())

    @property
    def site_ids(self) -> tuple[SiteId, ...]:
        """All site ids, in ascending order.

        Returns:
            The ids, ascending — the canonical enumeration order for every
            candidate list in this project.
        """
        return tuple(self._sites.keys())

    @property
    def site_count(self) -> int:
        """Number of sites in the structure.

        Returns:
            The site count (the outer bound on how many agents can exist).
        """
        return len(self._sites)

    def site(self, site_id: SiteId) -> Site:
        """Look up one site record by id.

        Args:
            site_id: The site to look up.

        Returns:
            The :class:`Site` record.

        Raises:
            KeyError: If no site with this id exists.
        """
        try:
            return self._sites[site_id]
        except KeyError:
            raise KeyError(
                f"Unknown site id {site_id!r}; this structure has sites "
                f"0..{max(self._sites)} ({self.site_count} sites)."
            ) from None

    def neighbours(self, site_id: SiteId) -> frozenset[SiteId]:
        """Return the ids adjacent to a site.

        Args:
            site_id: The site whose neighbours are wanted.

        Returns:
            The neighbour ids (never including ``site_id`` itself).

        Raises:
            KeyError: If no site with this id exists.
        """
        return self.site(site_id).neighbours

    @abstractmethod
    def distance(self, a: SiteId, b: SiteId) -> int:
        """Return the distance between two sites, in the structure's metric.

        Distance is STRUCTURE-SUPPLIED (forward-guard 3): the lattice hands
        out Chebyshev or Manhattan distance depending on its neighbourhood
        shape, the well-mixed structure a constant, and an M19 builder
        whatever suits its geography. Every metric must satisfy
        ``distance(a, a) == 0``, symmetry, and the triangle inequality.

        Args:
            a: First site id.
            b: Second site id.

        Returns:
            The non-negative integer distance.

        Raises:
            KeyError: If either id names no site in this structure.
        """


class WellMixedStructure(Structure):
    """The degenerate fully-connected structure: every site adjacent to every other.

    This is the aspatial world expressed inside the spatial abstraction —
    distance never differentiates anything (all distinct pairs sit at
    :data:`WELL_MIXED_DISTANCE`), so kernel weights are uniform for any
    decay and reach radii change nothing. It exists to make the abstraction
    honest: the well-mixed world genuinely IS the fully-connected corner of
    the same model, not a separate ontology.

    **Not a live execution path in M11a** (spec Design 0): the
    ``structure.kind = well_mixed`` engine does not route through this class
    — nothing on that path imports this module, which is what makes
    byte-identity to every pre-M11a run trivially true. This builder is the
    thing M19 and future work reason against.
    """

    def __init__(self, site_count: int) -> None:
        """Build a fully-connected structure of ``site_count`` sites.

        Args:
            site_count: How many sites to create (ids ``0..site_count-1``,
                no coordinates — a well-mixed world has no geometry).

        Raises:
            ValueError: If ``site_count`` is less than 1.
        """
        if site_count < 1:
            raise ValueError(f"site_count must be at least 1, got {site_count}.")
        all_ids = frozenset(range(site_count))
        super().__init__(
            Site(id=site_id, neighbours=all_ids - {site_id}) for site_id in range(site_count)
        )

    def distance(self, a: SiteId, b: SiteId) -> int:
        """Return 0 for a site to itself, :data:`WELL_MIXED_DISTANCE` otherwise.

        Args:
            a: First site id.
            b: Second site id.

        Returns:
            0 if ``a == b``, else the uniform constant distance.

        Raises:
            KeyError: If either id names no site in this structure.
        """
        self.site(a)
        self.site(b)
        return 0 if a == b else WELL_MIXED_DISTANCE


class LatticeStructure(Structure):
    """The rectangular builder: rows × cols cells with a shape and a boundary.

    The neighbourhood shape IS the distance metric (spec Design 0):
    ``"moore"`` means Chebyshev distance — the LARGER of the row and column
    differences, so a diagonal step costs 1 and radius 1 holds 8 cells —
    while ``"von_neumann"`` means Manhattan distance — their SUM, so a
    diagonal step costs 2 and radius 1 holds the 4 orthogonal cells. One
    decision about what "distance" means, handed to both the birth and the
    interaction kernel — never a per-kernel knob.

    The boundary decides whether the world has a rim: ``"torus"`` wraps both
    axes (the left edge is adjacent to the right, the top to the bottom), so
    every cell has the same degree and no corners exist; ``"bounded"`` has
    real edges and corners with fewer neighbours (3 under Moore, 2 under
    von Neumann) — degree the model, not an artifact, which is what M19's
    coastlines need.

    Site ids are dealt row-major: ``id = row * cols + col``, ascending.
    """

    def __init__(self, rows: int, cols: int, neighbourhood_shape: str, boundary: str) -> None:
        """Build the lattice and precompute every site's radius-1 neighbour set.

        Args:
            rows: Number of rows (at least 1; a 1×N line is a legitimate
                one-dimensional lattice).
            cols: Number of columns (at least 1).
            neighbourhood_shape: ``"moore"`` (Chebyshev metric, 8 neighbours
                at radius 1) or ``"von_neumann"`` (Manhattan metric, 4).
            boundary: ``"torus"`` (both axes wrap; uniform degree) or
                ``"bounded"`` (hard edges; corner and edge cells have fewer
                neighbours).

        Raises:
            ValueError: If a dimension is below 1 or a choice string is
                unknown (defensive — the Parameter Registry validates these
                upstream).
        """
        if rows < 1 or cols < 1:
            raise ValueError(f"Lattice dimensions must be at least 1×1, got {rows}×{cols}.")
        if neighbourhood_shape not in ("moore", "von_neumann"):
            raise ValueError(
                f"Unknown neighbourhood_shape {neighbourhood_shape!r}; "
                "expected 'moore' or 'von_neumann'."
            )
        if boundary not in ("torus", "bounded"):
            raise ValueError(f"Unknown boundary {boundary!r}; expected 'torus' or 'bounded'.")
        self._rows = rows
        self._cols = cols
        self._neighbourhood_shape = neighbourhood_shape
        self._boundary = boundary
        # The radius-1 step set: Moore includes diagonals, von Neumann only
        # the orthogonal steps. Neighbour sets fall out of stepping once in
        # each direction and applying the boundary rule.
        if neighbourhood_shape == "moore":
            steps = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0)]
        else:
            steps = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        sites = []
        for row in range(rows):
            for col in range(cols):
                neighbour_ids = set()
                for dr, dc in steps:
                    if boundary == "torus":
                        # `%` wraps negative and overflowing indices back
                        # onto the grid, which is exactly what a torus is.
                        nr, nc = (row + dr) % rows, (col + dc) % cols
                    else:
                        nr, nc = row + dr, col + dc
                        if not (0 <= nr < rows and 0 <= nc < cols):
                            continue
                    if (nr, nc) != (row, col):
                        neighbour_ids.add(nr * cols + nc)
                sites.append(
                    Site(
                        id=row * cols + col,
                        neighbours=frozenset(neighbour_ids),
                        coordinate=(row, col),
                    )
                )
        super().__init__(sites)

    @property
    def rows(self) -> int:
        """Number of rows in the lattice.

        Returns:
            The row count.
        """
        return self._rows

    @property
    def cols(self) -> int:
        """Number of columns in the lattice.

        Returns:
            The column count.
        """
        return self._cols

    @property
    def neighbourhood_shape(self) -> str:
        """The configured shape — ``"moore"`` or ``"von_neumann"``.

        Returns:
            The shape string (which is also the name of the metric).
        """
        return self._neighbourhood_shape

    @property
    def boundary(self) -> str:
        """The configured boundary rule — ``"torus"`` or ``"bounded"``.

        Returns:
            The boundary string.
        """
        return self._boundary

    def distance(self, a: SiteId, b: SiteId) -> int:
        """Return the lattice distance between two sites, per the shape's metric.

        Chebyshev (``"moore"``): the larger of the row and column
        differences. Manhattan (``"von_neumann"``): their sum. Under a torus
        each axis difference is the SHORTER way around the wrap — going left
        off the edge and arriving from the right is one step, not cols − 1.

        Args:
            a: First site id.
            b: Second site id.

        Returns:
            The non-negative integer distance.

        Raises:
            KeyError: If either id is outside the lattice.
        """
        for site_id in (a, b):
            if not 0 <= site_id < self._rows * self._cols:
                raise KeyError(
                    f"Unknown site id {site_id!r}; this lattice has sites "
                    f"0..{self._rows * self._cols - 1}."
                )
        # divmod(id, cols) inverts the row-major dealing: id -> (row, col).
        row_a, col_a = divmod(a, self._cols)
        row_b, col_b = divmod(b, self._cols)
        row_diff = abs(row_a - row_b)
        col_diff = abs(col_a - col_b)
        if self._boundary == "torus":
            row_diff = min(row_diff, self._rows - row_diff)
            col_diff = min(col_diff, self._cols - col_diff)
        if self._neighbourhood_shape == "moore":
            return max(row_diff, col_diff)
        return row_diff + col_diff


def sites_within(structure: Structure, origin: SiteId, radius: int | None) -> tuple[SiteId, ...]:
    """Enumerate the candidate sites within reach of an origin (pure, RNG-free).

    This is the support half of the reach kernel (spec Design 2): a site is
    a candidate exactly when its distance from the origin is at most the
    support radius R. The origin itself is never a candidate — under M11a's
    capacity-1 sites it is the only site at distance zero, and the
    distance-zero question is explicitly deferred to M19 (Design 12).

    Args:
        structure: The topology to enumerate over.
        origin: The site reach is measured from.
        radius: The support radius R — the hard edge beyond which a site is
            simply not a candidate. ``None`` means unlimited reach (every
            other site is a candidate). ``0`` yields no candidates.

    Returns:
        The candidate site ids in ASCENDING ID ORDER (the determinism rule —
        this ordering is what every later draw relies on).

    Raises:
        KeyError: If ``origin`` names no site in the structure.
        ValueError: If ``radius`` is negative.
    """
    structure.site(origin)
    if radius is not None and radius < 0:
        raise ValueError(f"radius must be non-negative or None (unlimited), got {radius}.")
    if radius is None:
        return tuple(site_id for site_id in structure.site_ids if site_id != origin)
    return tuple(
        site_id
        for site_id in structure.site_ids
        if site_id != origin and structure.distance(origin, site_id) <= radius
    )


def kernel_weights(
    structure: Structure, origin: SiteId, sites: Sequence[SiteId], decay: float
) -> np.ndarray:
    """Compute the exp(−β·d) weight for each candidate site (pure, RNG-free).

    This is the preference half of the reach kernel (spec Design 2): among
    the reachable, closer sites get more weight, and β (the decay) sets how
    steeply. β = 0 makes every candidate equally weighted — a uniform disc;
    large β makes distant candidates reachable but very unlikely. The
    weights are UNNORMALISED (they need not sum to 1); the sampler
    normalises at draw time, and equality of raw weights is what "uniform"
    means in the tests.

    Args:
        structure: The topology supplying the metric.
        origin: The site distances are measured from.
        sites: The candidate site ids (typically from :func:`sites_within`).
        decay: β — the non-negative decay rate.

    Returns:
        A float array, aligned with ``sites``, of exp(−β·distance) values.
        Every value is strictly positive (exp never reaches zero).

    Raises:
        KeyError: If ``origin`` or any candidate names no site.
        ValueError: If ``decay`` is negative (that would make FARTHER sites
            preferred — always a bug, never a model).
    """
    if decay < 0:
        raise ValueError(f"decay must be non-negative, got {decay}.")
    distances = np.array([structure.distance(origin, site_id) for site_id in sites], dtype=float)
    return np.exp(-decay * distances)


def neighbourhood_sample(
    structure: Structure,
    origin: SiteId,
    *,
    radius: int | None,
    decay: float,
    size: int,
    rng: np.random.Generator,
    eligible: frozenset[SiteId],
    site_weights: Mapping[SiteId, float] | None = None,
) -> tuple[SiteId, ...]:
    """Draw up to ``size`` sites near an origin, weighted by the reach kernel.

    THE one primitive (spec Design 2): all call sites that need "sample
    sites near an origin" — synchronous placement, synchronous interaction,
    the asynchronous partner draw, and the asynchronous ``fixed_n``
    breeder/victim draw — run this same algorithm: enumerate the sites
    within R of the origin, filter to an eligible set, weight by
    exp(−β·d) (times an optional second weight), and draw without
    replacement. Only the eligible set and the second weight differ between
    call sites. In Phase A nothing calls it yet.

    The pinned semantics (spec Design 2 — no call site improvises):

    - ``eligible`` is an explicit frozenset, not a predicate: the caller
      already holds the occupancy map, so it hands over "the empty sites"
      or "the occupied sites minus self" as data — and a set is trivially
      inspectable in a failing test, where a closure is not.
    - ``radius=None`` means unlimited reach, matching the nullable
      parameter it implements.
    - The combined weight on a site is ``exp(−β·d) * site_weights[site]``.
      ``site_weights`` is the hook the fitness-weighted breeder draw uses
      (Design 7); every other call site leaves it ``None``. If every
      combined weight is zero, the draw falls back to UNIFORM over the
      candidates — matching the #63 non-negative-shift idiom's existing
      contract. A site whose individual combined weight is zero is simply
      never drawn (so with some-but-not-all zeros, fewer than ``size``
      sites may return).
    - FEWER than ``size`` sites return when fewer are eligible — the #81
      clamp idiom (a small neighbourhood is a fact about the world, not an
      error).
    - An EMPTY TUPLE returns when no site is eligible at all — this is
      ``place_offspring``'s failure signal (Design 4, Phase C).

    Determinism: the candidate list is built in ascending site-id order
    before the draw (via :func:`sites_within`), and ``eligible`` is only
    ever membership-tested — its iteration order can never influence the
    outcome. Same seed, same inputs, same draw.

    Args:
        structure: The topology to sample over.
        origin: The site reach is measured from (never itself a candidate).
        radius: Support radius R; ``None`` for unlimited reach.
        decay: β — the non-negative distance decay.
        size: How many sites to draw (the draw is clamped to the number of
            drawable candidates; ``0`` returns an empty tuple and consumes
            no RNG).
        rng: The run's seeded generator. Consumed only when at least one
            candidate is drawable.
        eligible: The site ids that may be drawn (candidates outside it are
            filtered away before weighting).
        site_weights: Optional second weight per site, multiplied into the
            kernel weight. Sites missing from the mapping are an error —
            the caller supplies a weight for every site it declares
            eligible.

    Returns:
        The drawn site ids, in draw order, as plain ints.

    Raises:
        KeyError: If ``origin`` names no site, or a candidate is missing
            from ``site_weights``.
        ValueError: If ``radius`` is negative, ``decay`` is negative,
            ``size`` is negative, or a site weight is negative.
    """
    if size < 0:
        raise ValueError(f"size must be non-negative, got {size}.")
    candidates = [
        site_id for site_id in sites_within(structure, origin, radius) if site_id in eligible
    ]
    if not candidates or size == 0:
        return ()
    weights = kernel_weights(structure, origin, candidates, decay)
    if site_weights is not None:
        second = np.array([site_weights[site_id] for site_id in candidates], dtype=float)
        if np.any(second < 0):
            raise ValueError("site_weights must be non-negative.")
        weights = weights * second
    total = weights.sum()
    if total > 0.0:
        # Zero-weight candidates can never be drawn; dropping them up front
        # keeps the clamp honest (numpy would refuse to draw more sites than
        # have positive probability).
        drawable = weights > 0.0
        pool = [site_id for site_id, keep in zip(candidates, drawable, strict=True) if keep]
        probabilities = weights[drawable] / weights[drawable].sum()
    else:
        # All combined weights zero -> uniform over the candidates (the #63
        # shift idiom's fallback, applied to the combined vector).
        pool = candidates
        probabilities = None
    count = min(size, len(pool))
    drawn = rng.choice(pool, size=count, replace=False, p=probabilities)
    return tuple(int(site_id) for site_id in drawn)
