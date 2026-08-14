"""Tests for the structure module: sites, builders, kernel, sampler (M11a Phase A).

The assertions come from the spec's stated numbers (Design 1's degree table,
the #105 kernel corners, Design 2's pinned sampler semantics) — not from the
implementation's own output. The kernel-corner tests run through the pure
functions with no RNG in the assertion path.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

import pdsim
from pdsim.core.structure import (
    SITE_CAPACITY,
    LatticeStructure,
    Site,
    SiteId,
    Structure,
    WellMixedStructure,
    kernel_weights,
    neighbourhood_sample,
    sites_within,
)


def _ids(cols: int, cells: list[tuple[int, int]]) -> set[SiteId]:
    """Convert (row, col) coordinates to row-major site ids.

    Args:
        cols: The lattice's column count.
        cells: Coordinates to convert.

    Returns:
        The corresponding site ids.
    """
    return {row * cols + col for row, col in cells}


# ---------------------------------------------------------------------------
# The Site record and the shared Structure validation
# ---------------------------------------------------------------------------


class _ToyStructure(Structure):
    """Minimal concrete structure for exercising the shared base validation."""

    def distance(self, a: SiteId, b: SiteId) -> int:
        """Return 0 to self, 1 to anyone else (any metric satisfies the base).

        Args:
            a: First site id.
            b: Second site id.

        Returns:
            The toy distance.
        """
        self.site(a)
        self.site(b)
        return 0 if a == b else 1


def test_site_capacity_defaults_to_the_pinned_constant() -> None:
    """The capacity field ships pinned at 1 (Design 12)."""
    site = Site(id=0, neighbours=frozenset())
    assert site.capacity == SITE_CAPACITY == 1
    assert site.coordinate is None  # optional — nothing in the core requires it


def test_structure_rejects_capacity_other_than_one() -> None:
    """The M11a validator pins every site's capacity at 1 (M19 removes it)."""
    with pytest.raises(ValueError, match="capacity"):
        _ToyStructure([Site(id=0, neighbours=frozenset(), capacity=2)])


def test_structure_rejects_duplicate_ids() -> None:
    """Two sites with the same id are always a bug."""
    sites = [Site(id=0, neighbours=frozenset()), Site(id=0, neighbours=frozenset())]
    with pytest.raises(ValueError, match="Duplicate site id"):
        _ToyStructure(sites)


def test_structure_rejects_unknown_neighbour_ids() -> None:
    """A neighbour set may only name sites that exist."""
    with pytest.raises(ValueError, match="do not exist"):
        _ToyStructure([Site(id=0, neighbours=frozenset({7}))])


def test_structure_rejects_self_neighbour() -> None:
    """A site is never its own neighbour (distance to self is 0)."""
    sites = [
        Site(id=0, neighbours=frozenset({0, 1})),
        Site(id=1, neighbours=frozenset({0})),
    ]
    with pytest.raises(ValueError, match="itself"):
        _ToyStructure(sites)


def test_structure_rejects_empty_site_set() -> None:
    """A world with no sites is malformed."""
    with pytest.raises(ValueError, match="at least one site"):
        _ToyStructure([])


def test_sites_are_exposed_in_ascending_id_order() -> None:
    """Ascending-id order is the canonical enumeration (Defining principle 5)."""
    sites = [Site(id=i, neighbours=frozenset()) for i in (3, 0, 2, 1)]
    structure = _ToyStructure(sites)
    assert structure.site_ids == (0, 1, 2, 3)
    assert [site.id for site in structure.sites] == [0, 1, 2, 3]
    assert structure.site_count == 4


def test_unknown_site_lookup_raises_key_error() -> None:
    """Lookups on ids outside the structure fail loudly."""
    structure = _ToyStructure([Site(id=0, neighbours=frozenset())])
    with pytest.raises(KeyError):
        structure.site(99)
    with pytest.raises(KeyError):
        structure.neighbours(99)


# ---------------------------------------------------------------------------
# Lattice degree counts — the Design 1 degree table, asserted exactly
# ---------------------------------------------------------------------------


def _degrees(structure: LatticeStructure) -> dict[SiteId, int]:
    """Map every site id to its neighbour count.

    Args:
        structure: The lattice under test.

    Returns:
        Site id → degree.
    """
    return {site_id: len(structure.neighbours(site_id)) for site_id in structure.site_ids}


def test_moore_torus_degree_is_uniformly_eight() -> None:
    """Moore + torus: every cell has 8 neighbours — no corners exist."""
    degrees = _degrees(LatticeStructure(5, 5, "moore", "torus"))
    assert set(degrees.values()) == {8}


def test_von_neumann_torus_degree_is_uniformly_four() -> None:
    """Von Neumann + torus: every cell has 4 neighbours — no corners exist."""
    degrees = _degrees(LatticeStructure(5, 5, "von_neumann", "torus"))
    assert set(degrees.values()) == {4}


def test_moore_bounded_degrees_interior_eight_corner_three() -> None:
    """Moore + bounded on 5×5: interior 8, corner 3, edge 5."""
    lattice = LatticeStructure(5, 5, "moore", "bounded")
    degrees = _degrees(lattice)
    corners = _ids(5, [(0, 0), (0, 4), (4, 0), (4, 4)])
    interior = _ids(5, [(r, c) for r in (1, 2, 3) for c in (1, 2, 3)])
    for site_id in corners:
        assert degrees[site_id] == 3
    for site_id in interior:
        assert degrees[site_id] == 8
    for site_id in set(lattice.site_ids) - corners - interior:
        assert degrees[site_id] == 5  # non-corner edge cells


def test_von_neumann_bounded_degrees_interior_four_corner_two() -> None:
    """Von Neumann + bounded on 5×5: interior 4, corner 2, edge 3."""
    lattice = LatticeStructure(5, 5, "von_neumann", "bounded")
    degrees = _degrees(lattice)
    corners = _ids(5, [(0, 0), (0, 4), (4, 0), (4, 4)])
    interior = _ids(5, [(r, c) for r in (1, 2, 3) for c in (1, 2, 3)])
    for site_id in corners:
        assert degrees[site_id] == 2
    for site_id in interior:
        assert degrees[site_id] == 4
    for site_id in set(lattice.site_ids) - corners - interior:
        assert degrees[site_id] == 3


def test_one_by_n_line_lattice_is_legitimate() -> None:
    """A 1×N line (the prime-N resolution) works: a ring under torus."""
    ring = LatticeStructure(1, 5, "von_neumann", "torus")
    assert set(_degrees(ring).values()) == {2}
    assert ring.distance(0, 4) == 1  # wraps: one step the short way round
    line = LatticeStructure(1, 5, "von_neumann", "bounded")
    degrees = _degrees(line)
    assert degrees[0] == degrees[4] == 1  # the ends
    assert degrees[1] == degrees[2] == degrees[3] == 2
    assert line.distance(0, 4) == 4  # no wrap


def test_lattice_rejects_bad_arguments() -> None:
    """Dimensions below 1 and unknown choice strings fail loudly."""
    with pytest.raises(ValueError, match="at least 1"):
        LatticeStructure(0, 5, "moore", "torus")
    with pytest.raises(ValueError, match="neighbourhood_shape"):
        LatticeStructure(3, 3, "hexagon", "torus")
    with pytest.raises(ValueError, match="boundary"):
        LatticeStructure(3, 3, "moore", "klein_bottle")


# ---------------------------------------------------------------------------
# Moore versus von Neumann neighbour sets at radius 1 AND radius 2
# ---------------------------------------------------------------------------


def test_moore_neighbour_set_at_radius_one() -> None:
    """Moore radius 1 from an interior cell: the 8 surrounding cells."""
    lattice = LatticeStructure(7, 7, "moore", "bounded")
    origin = 3 * 7 + 3
    expected = _ids(7, [(r, c) for r in (2, 3, 4) for c in (2, 3, 4) if (r, c) != (3, 3)])
    assert set(sites_within(lattice, origin, 1)) == expected
    assert lattice.neighbours(origin) == frozenset(expected)


def test_von_neumann_neighbour_set_at_radius_one() -> None:
    """Von Neumann radius 1 from an interior cell: the 4 orthogonal cells."""
    lattice = LatticeStructure(7, 7, "von_neumann", "bounded")
    origin = 3 * 7 + 3
    expected = _ids(7, [(2, 3), (4, 3), (3, 2), (3, 4)])
    assert set(sites_within(lattice, origin, 1)) == expected
    assert lattice.neighbours(origin) == frozenset(expected)


def test_moore_neighbour_set_at_radius_two() -> None:
    """Moore radius 2: the full 5×5 block around the origin, minus the origin."""
    lattice = LatticeStructure(7, 7, "moore", "bounded")
    origin = 3 * 7 + 3
    expected = _ids(7, [(r, c) for r in range(1, 6) for c in range(1, 6) if (r, c) != (3, 3)])
    assert set(sites_within(lattice, origin, 2)) == expected
    assert len(expected) == 24


def test_von_neumann_neighbour_set_at_radius_two() -> None:
    """Von Neumann radius 2: the Manhattan diamond — 12 cells, diagonals cost 2."""
    lattice = LatticeStructure(7, 7, "von_neumann", "bounded")
    origin = 3 * 7 + 3
    offsets = [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),  # distance 1
        (-2, 0),
        (2, 0),
        (0, -2),
        (0, 2),  # distance 2, straight
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),  # distance 2, diagonal
    ]
    expected = _ids(7, [(3 + dr, 3 + dc) for dr, dc in offsets])
    assert set(sites_within(lattice, origin, 2)) == expected
    assert len(expected) == 12


def test_torus_neighbour_sets_wrap_at_the_corner() -> None:
    """Under torus the corner's neighbourhood wraps to the opposite edges."""
    moore = LatticeStructure(5, 5, "moore", "torus")
    expected = _ids(5, [(4, 4), (4, 0), (4, 1), (0, 4), (0, 1), (1, 4), (1, 0), (1, 1)])
    assert moore.neighbours(0) == frozenset(expected)
    von_neumann = LatticeStructure(5, 5, "von_neumann", "torus")
    assert von_neumann.neighbours(0) == frozenset(_ids(5, [(4, 0), (1, 0), (0, 4), (0, 1)]))


def test_neighbour_relation_agrees_with_the_metric() -> None:
    """The shape IS the metric: neighbours are exactly the sites at distance 1."""
    for shape in ("moore", "von_neumann"):
        for boundary in ("torus", "bounded"):
            lattice = LatticeStructure(5, 6, shape, boundary)
            for site_id in lattice.site_ids:
                assert lattice.neighbours(site_id) == frozenset(
                    sites_within(lattice, site_id, 1)
                ), (shape, boundary, site_id)


# ---------------------------------------------------------------------------
# Distance: symmetry and the triangle inequality, for both metrics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["moore", "von_neumann"])
@pytest.mark.parametrize("boundary", ["torus", "bounded"])
def test_distance_is_a_metric(shape: str, boundary: str) -> None:
    """distance(a,a)=0, symmetry, and the triangle inequality all hold."""
    lattice = LatticeStructure(4, 5, shape, boundary)
    ids = lattice.site_ids
    for a in ids:
        assert lattice.distance(a, a) == 0
        for b in ids:
            assert lattice.distance(a, b) == lattice.distance(b, a)
    for a in ids:
        for b in ids:
            direct = lattice.distance(a, b)
            for c in ids:
                assert direct <= lattice.distance(a, c) + lattice.distance(c, b)


def test_distance_worked_example_from_the_spec() -> None:
    """Spec Design 0's example: (2,3)→(4,6) is Chebyshev 3, Manhattan 5."""
    moore = LatticeStructure(7, 7, "moore", "bounded")
    von_neumann = LatticeStructure(7, 7, "von_neumann", "bounded")
    a, b = 2 * 7 + 3, 4 * 7 + 6
    assert moore.distance(a, b) == 3
    assert von_neumann.distance(a, b) == 5


def test_distance_rejects_unknown_ids() -> None:
    """Out-of-range site ids fail loudly rather than computing nonsense."""
    lattice = LatticeStructure(3, 3, "moore", "torus")
    with pytest.raises(KeyError):
        lattice.distance(0, 9)
    with pytest.raises(KeyError):
        lattice.distance(-1, 0)


# ---------------------------------------------------------------------------
# The four kernel corners from #105 — pure functions, no RNG
# ---------------------------------------------------------------------------


def test_kernel_corner_radius_one_makes_decay_irrelevant() -> None:
    """R = 1: all candidates sit at distance 1, so β changes nothing."""
    lattice = LatticeStructure(7, 7, "moore", "torus")
    origin = 3 * 7 + 3
    candidates = sites_within(lattice, origin, 1)
    assert len(candidates) == 8
    for decay in (0.0, 2.5, 10.0):
        weights = kernel_weights(lattice, origin, candidates, decay)
        assert np.all(weights == weights[0])  # equal raw weights = uniform draw


def test_kernel_corner_zero_decay_is_a_uniform_disc() -> None:
    """β = 0 with R = n: every site within n weighs exactly 1."""
    lattice = LatticeStructure(7, 7, "moore", "torus")
    origin = 3 * 7 + 3
    candidates = sites_within(lattice, origin, 3)
    distances = {lattice.distance(origin, s) for s in candidates}
    assert distances == {1, 2, 3}  # genuinely mixed distances
    weights = kernel_weights(lattice, origin, candidates, 0.0)
    assert np.all(weights == 1.0)


def test_kernel_corner_large_decay_is_steeply_viscous() -> None:
    """Large β with R = n: distant sites stay reachable but steeply down-weighted."""
    lattice = LatticeStructure(7, 7, "moore", "torus")
    origin = 3 * 7 + 3
    candidates = sites_within(lattice, origin, 3)
    weights = kernel_weights(lattice, origin, candidates, 10.0)
    assert np.all(weights > 0.0)  # reachable: never zero inside the support
    by_distance = {
        d: weights[[lattice.distance(origin, s) for s in candidates].index(d)] for d in (1, 2, 3)
    }
    assert by_distance[1] > by_distance[2] > by_distance[3]
    assert by_distance[2] / by_distance[1] < 1e-4  # exp(-10) per extra step


def test_kernel_corner_unlimited_radius_zero_decay_recovers_well_mixed() -> None:
    """radius=None with β = 0: every other site, uniformly — by parameters."""
    lattice = LatticeStructure(7, 7, "moore", "torus")
    origin = 3 * 7 + 3
    candidates = sites_within(lattice, origin, None)
    assert set(candidates) == set(lattice.site_ids) - {origin}
    weights = kernel_weights(lattice, origin, candidates, 0.0)
    assert np.all(weights == 1.0)


def test_candidate_lists_are_ascending_by_site_id() -> None:
    """The determinism rule: candidates enumerate in ascending id order."""
    lattice = LatticeStructure(6, 6, "von_neumann", "torus")
    for radius in (1, 2, None):
        candidates = sites_within(lattice, 14, radius)
        assert list(candidates) == sorted(candidates)


def test_kernel_weights_reject_negative_decay() -> None:
    """A negative β would prefer FARTHER sites — always a bug, never a model."""
    lattice = LatticeStructure(3, 3, "moore", "torus")
    with pytest.raises(ValueError, match="decay"):
        kernel_weights(lattice, 0, (1, 2), -0.5)


def test_sites_within_rejects_negative_radius() -> None:
    """A negative radius is a programming error, not an empty neighbourhood."""
    lattice = LatticeStructure(3, 3, "moore", "torus")
    with pytest.raises(ValueError, match="radius"):
        sites_within(lattice, 0, -1)


# ---------------------------------------------------------------------------
# WellMixedStructure — the degenerate fully-connected builder
# ---------------------------------------------------------------------------


def test_well_mixed_every_site_adjacent_to_every_other() -> None:
    """The fully-connected corner: neighbours = everyone else."""
    world = WellMixedStructure(6)
    assert world.site_count == 6
    for site_id in world.site_ids:
        assert world.neighbours(site_id) == frozenset(set(world.site_ids) - {site_id})


def test_well_mixed_distance_never_differentiates() -> None:
    """Distance is 0 to self and one shared constant to everyone else."""
    world = WellMixedStructure(5)
    distances = {world.distance(a, b) for a in world.site_ids for b in world.site_ids if a != b}
    assert len(distances) == 1  # all distinct pairs at the same distance
    assert world.distance(2, 2) == 0


def test_well_mixed_kernel_weights_are_uniform_for_any_decay() -> None:
    """The builder's tested property: β cannot matter when distance is constant."""
    world = WellMixedStructure(8)
    candidates = sites_within(world, 3, None)
    assert set(candidates) == set(world.site_ids) - {3}
    for decay in (0.0, 0.7, 13.0):
        weights = kernel_weights(world, 3, candidates, decay)
        assert np.all(weights == weights[0])


def test_well_mixed_rejects_empty_world() -> None:
    """At least one site is required."""
    with pytest.raises(ValueError, match="at least 1"):
        WellMixedStructure(0)


# ---------------------------------------------------------------------------
# neighbourhood_sample — the pinned Design 2 semantics
# ---------------------------------------------------------------------------


def _torus() -> LatticeStructure:
    """Build the 5×5 Moore torus most sampler tests run on.

    Returns:
        The lattice.
    """
    return LatticeStructure(5, 5, "moore", "torus")


def test_sample_clamps_to_the_eligible_count() -> None:
    """Fewer eligible than requested: return them all — clamp, don't raise (#81)."""
    lattice = _torus()
    origin = 12
    eligible = frozenset(list(lattice.neighbours(origin))[:3])
    drawn = neighbourhood_sample(
        lattice,
        origin,
        radius=1,
        decay=0.0,
        size=8,
        rng=np.random.default_rng(0),
        eligible=eligible,
    )
    assert sorted(drawn) == sorted(eligible)


def test_sample_returns_empty_tuple_when_nothing_is_eligible() -> None:
    """No eligible site at all: the empty tuple — place_offspring's failure signal."""
    lattice = _torus()
    drawn = neighbourhood_sample(
        lattice,
        12,
        radius=1,
        decay=0.0,
        size=3,
        rng=np.random.default_rng(0),
        eligible=frozenset(),
    )
    assert drawn == ()
    far_only = frozenset({0})  # site 0 is outside radius 1 of site 12
    assert 0 not in sites_within(lattice, 12, 1)
    drawn = neighbourhood_sample(
        lattice,
        12,
        radius=1,
        decay=0.0,
        size=3,
        rng=np.random.default_rng(0),
        eligible=far_only,
    )
    assert drawn == ()


def test_sample_size_zero_returns_empty_and_consumes_no_rng() -> None:
    """size=0 is an empty request: nothing returned, generator untouched."""
    lattice = _torus()
    rng = np.random.default_rng(7)
    state_before = rng.bit_generator.state
    drawn = neighbourhood_sample(
        lattice,
        12,
        radius=1,
        decay=0.0,
        size=0,
        rng=rng,
        eligible=frozenset(lattice.neighbours(12)),
    )
    assert drawn == ()
    assert rng.bit_generator.state == state_before


def test_sample_draws_distinct_sites_without_replacement() -> None:
    """A draw never returns the same site twice."""
    lattice = _torus()
    drawn = neighbourhood_sample(
        lattice,
        12,
        radius=None,
        decay=0.0,
        size=10,
        rng=np.random.default_rng(3),
        eligible=frozenset(set(lattice.site_ids) - {12}),
    )
    assert len(drawn) == 10
    assert len(set(drawn)) == 10
    assert all(isinstance(site_id, int) for site_id in drawn)  # plain ints, not numpy


def test_sample_site_weights_combine_multiplicatively() -> None:
    """A zero second weight kills a site outright: exp(−β·d) × 0 = 0."""
    lattice = _torus()
    origin = 12
    a, b = sorted(lattice.neighbours(origin))[:2]
    eligible = frozenset({a, b})
    for seed in range(10):
        drawn = neighbourhood_sample(
            lattice,
            origin,
            radius=1,
            decay=0.0,
            size=1,
            rng=np.random.default_rng(seed),
            eligible=eligible,
            site_weights={a: 0.0, b: 1.0},
        )
        assert drawn == (b,)
    # And a zero-weight site cannot be forced in by a large size: the clamp
    # counts DRAWABLE sites, so size=2 over {weight 0, weight 1} returns one.
    drawn = neighbourhood_sample(
        lattice,
        origin,
        radius=1,
        decay=0.0,
        size=2,
        rng=np.random.default_rng(0),
        eligible=eligible,
        site_weights={a: 0.0, b: 1.0},
    )
    assert drawn == (b,)


def test_sample_site_weights_outweigh_the_kernel_when_large_enough() -> None:
    """The combined weight is the PRODUCT: a big fitness beats a small distance."""
    lattice = LatticeStructure(7, 7, "moore", "torus")
    origin = 3 * 7 + 3  # (3, 3)
    near = 3 * 7 + 4  # (3, 4), distance 1
    far = 3 * 7 + 0  # (3, 0), distance 3 around the torus
    assert lattice.distance(origin, far) == 3
    # Kernel alone favours near by e^2 ≈ 7.4; the second weight favours far
    # by 1000, so the product favours far by ≈ 135. Seeded, hence exact.
    rng = np.random.default_rng(42)
    draws = [
        neighbourhood_sample(
            lattice,
            origin,
            radius=3,
            decay=1.0,
            size=1,
            rng=rng,
            eligible=frozenset({near, far}),
            site_weights={near: 1.0, far: 1000.0},
        )[0]
        for _ in range(200)
    ]
    assert draws.count(far) > 180


def test_sample_all_zero_weights_fall_back_to_uniform() -> None:
    """Every combined weight zero → uniform over the candidates (#63 contract)."""
    lattice = _torus()
    origin = 12
    eligible = frozenset(sorted(lattice.neighbours(origin))[:3])
    weights = {site_id: 0.0 for site_id in eligible}
    drawn = neighbourhood_sample(
        lattice,
        origin,
        radius=1,
        decay=0.0,
        size=2,
        rng=np.random.default_rng(1),
        eligible=eligible,
        site_weights=weights,
    )
    assert len(drawn) == 2
    assert set(drawn) <= eligible


def test_sample_same_seed_same_draw() -> None:
    """Reproducibility: identical inputs and seed give the identical tuple."""
    lattice = _torus()
    eligible = frozenset(set(lattice.site_ids) - {12})
    first = neighbourhood_sample(
        lattice,
        12,
        radius=2,
        decay=0.8,
        size=5,
        rng=np.random.default_rng(99),
        eligible=eligible,
    )
    second = neighbourhood_sample(
        lattice,
        12,
        radius=2,
        decay=0.8,
        size=5,
        rng=np.random.default_rng(99),
        eligible=eligible,
    )
    assert first == second


def test_sample_is_independent_of_eligible_construction_order() -> None:
    """The ascending-site-id rule at work: how the eligible set was built is invisible."""
    lattice = _torus()
    members = [1, 3, 7, 11, 13, 17, 23]
    forward = frozenset(members)
    backward = frozenset(reversed(members))
    accumulated: set[int] = set()
    for member in sorted(members, key=lambda m: (m % 3, -m)):  # a scrambled order
        accumulated.add(member)
    draws = [
        neighbourhood_sample(
            lattice,
            12,
            radius=None,
            decay=0.3,
            size=4,
            rng=np.random.default_rng(5),
            eligible=eligible,
        )
        for eligible in (forward, backward, frozenset(accumulated))
    ]
    assert draws[0] == draws[1] == draws[2]


def test_sample_rejects_negative_size_and_negative_site_weights() -> None:
    """Negative sizes and negative weights are programming errors."""
    lattice = _torus()
    with pytest.raises(ValueError, match="size"):
        neighbourhood_sample(
            lattice,
            12,
            radius=1,
            decay=0.0,
            size=-1,
            rng=np.random.default_rng(0),
            eligible=frozenset({11}),
        )
    with pytest.raises(ValueError, match="site_weights"):
        neighbourhood_sample(
            lattice,
            12,
            radius=1,
            decay=0.0,
            size=1,
            rng=np.random.default_rng(0),
            eligible=frozenset({11}),
            site_weights={11: -1.0},
        )


# ---------------------------------------------------------------------------
# The Phase E precomputation: draw-neutrality safeguard (a), the equality pin
# (#156). The cache may change WHEN arrays are built, never what they contain
# — so every cached candidate list and weight vector is asserted IDENTICAL
# (== and bit-for-bit) to a fresh direct enumeration through sites_within and
# kernel_weights. The geometries deliberately include a large-radius Moore
# case and a bounded (non-torus) grid — the regimes outside golden coverage.
# ---------------------------------------------------------------------------


_REACH_GEOMETRIES = [
    ("moore", "torus", 5),  # the large-radius Moore case the spec names
    ("moore", "bounded", 5),  # large radius against a real rim
    ("von_neumann", "bounded", 2),  # the other metric, corner-degree regime
    ("moore", "torus", 1),  # the classic Hammond-Axelrod corner
    ("von_neumann", "torus", None),  # unlimited reach
]
"""(shape, boundary, radius) cases for the equality pin, on a 9×7 grid."""


@pytest.mark.parametrize(("shape", "boundary", "radius"), _REACH_GEOMETRIES)
def test_reach_cache_equals_fresh_enumeration(
    shape: str, boundary: str, radius: int | None
) -> None:
    """Cached candidates and weights are identical to a direct enumeration.

    The cache is populated for EVERY origin/decay combination first and
    asserted afterwards — interleaving population and assertion would let a
    mis-keyed cache (say, one ignoring the origin) hand back a stale entry
    that a build-then-check-one-at-a-time loop could never catch.
    """
    lattice = LatticeStructure(9, 7, shape, boundary)
    origins = [0, 6, 31, 62]  # corner, corner, interior, corner (9×7 row-major)
    decays = [0.0, 0.7]
    for origin in origins:  # populate every entry before asserting any
        lattice.reach(origin, radius)
    for origin in origins:
        entry = lattice.reach(origin, radius)
        fresh_candidates = sites_within(lattice, origin, radius)
        assert entry.candidates == fresh_candidates
        assert entry.distances.tolist() == [
            lattice.distance(origin, site) for site in fresh_candidates
        ]
        for decay in decays:
            table = lattice.distance_weight_table(radius, decay, up_to=entry.max_distance)
            cached_weights = table[entry.distances]
            fresh_weights = kernel_weights(lattice, origin, fresh_candidates, decay)
            # Bit-for-bit, not approximately: the sampler feeds these to the
            # normalisation and the draw, so any float wobble IS a stream
            # change.
            assert np.array_equal(cached_weights, fresh_weights)


def test_reach_cache_actually_memoises() -> None:
    """Repeat calls return the STORED entry, not a rebuilt one.

    Identity (`is`), not equality: equal-but-rebuilt entries would make the
    equality pin pass while the precomputation silently did nothing — this
    is the test that the flat-in-R bench claim rests on.
    """
    lattice = LatticeStructure(6, 6, "moore", "torus")
    first = lattice.reach(7, 2)
    assert lattice.reach(7, 2) is first
    table = lattice.distance_weight_table(2, 0.5, up_to=first.max_distance)
    assert lattice.distance_weight_table(2, 0.5, up_to=first.max_distance) is table


def test_weight_table_regrowth_keeps_existing_values_exact() -> None:
    """Unlimited radius on a bounded grid: the table grows, values do not move.

    A 5×5 bounded Moore grid: the centre's farthest candidate sits at
    distance 2, a corner's at distance 4 — the same (None, β) table must
    serve both, regrowing for the corner without changing what the centre
    already looked up.
    """
    lattice = LatticeStructure(5, 5, "moore", "bounded")
    centre = lattice.reach(12, None)
    small = lattice.distance_weight_table(None, 0.3, up_to=centre.max_distance)
    centre_before = small[centre.distances].copy()
    corner = lattice.reach(0, None)
    assert corner.max_distance > centre.max_distance  # the regrowth premise
    grown = lattice.distance_weight_table(None, 0.3, up_to=corner.max_distance)
    assert len(grown) > len(small)
    assert np.array_equal(grown[centre.distances], centre_before)
    assert np.array_equal(
        grown[corner.distances], kernel_weights(lattice, 0, corner.candidates, 0.3)
    )


def test_sample_draws_identically_cold_and_warm() -> None:
    """The same seed draws the same sites through a cold and a warm cache.

    Two identical lattices: one fresh per draw (every draw a cache miss),
    one reused across all draws (every draw after the first a hit). If the
    cache changed anything the streams would diverge somewhere across the
    mixed radii, decays, and eligible sets.
    """
    warm = LatticeStructure(6, 6, "moore", "torus")
    plans = [
        (7, 1, 0.0, 3),
        (7, 2, 0.7, 4),
        (14, 2, 0.7, 4),  # same (radius, decay), different origin
        (14, None, 1.3, 5),
        (0, 1, 0.0, 8),
    ]
    eligible = frozenset(range(36)) - {7}
    cold_rng = np.random.default_rng(99)
    warm_rng = np.random.default_rng(99)
    for origin, radius, decay, size in plans:
        cold = neighbourhood_sample(
            LatticeStructure(6, 6, "moore", "torus"),  # fresh: cold cache
            origin,
            radius=radius,
            decay=decay,
            size=size,
            rng=cold_rng,
            eligible=eligible,
        )
        again = neighbourhood_sample(
            warm, origin, radius=radius, decay=decay, size=size, rng=warm_rng, eligible=eligible
        )
        assert cold == again


# ---------------------------------------------------------------------------
# The import guard, retired and replaced (Phase B)
# ---------------------------------------------------------------------------
#
# Phase A's guard asserted that NO engine module imported this one — the
# executable form of "wired to nothing". Phase B is the phase that wires it,
# so that assertion is now false by design and has been removed rather than
# weakened into a list of exceptions that would grow every phase.
#
# What it protected is still protected, by better tests than an import scan:
# the well-mixed path must build no structure and consume no randomness. That
# is asserted directly in test_layouts.py (`TestWellMixedIsUntouched`), which
# checks the occupancy is None and the RNG stream is unmoved — a property the
# import scan could only ever approximate.


def test_ui_and_io_layers_do_not_reach_into_structure_internals() -> None:
    """Hard rule 4's direction of travel, kept honest as the module gets wired.

    The structure module is core; the UI may consume it, but nothing under
    core/, config/, or io/ may import UI or plotting code. This is the check
    that survives Phase B — the one about which way the dependency points.
    """
    package_root = Path(pdsim.__file__).parent
    forbidden = re.compile(r"import\s+streamlit|from\s+streamlit|import\s+plotly|from\s+plotly")
    offenders = []
    for area in ("core", "config", "io"):
        for path in (package_root / area).rglob("*.py"):
            if "tests" in path.parts:
                continue
            if forbidden.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(package_root)))
    assert offenders == [], (
        f"Hard rule 4: the headless layers must not import UI or plotting code: {offenders}"
    )
