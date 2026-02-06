"""Tests for hex math and hex map."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.hex_utils import (
    hex_neighbors, hex_distance, hex_ring, hex_spiral,
    generate_hex_grid, axial_to_pixel, pixel_to_axial,
    hexes_are_adjacent, axial_round,
)
from server.hex_map import HexMap
from shared.constants import MAP_SIDE_LENGTH, FACTION_START_HEXES


class TestHexUtils:
    def test_hex_distance_same(self):
        assert hex_distance(0, 0, 0, 0) == 0

    def test_hex_distance_adjacent(self):
        assert hex_distance(0, 0, 1, 0) == 1
        assert hex_distance(0, 0, 0, 1) == 1
        assert hex_distance(0, 0, 1, -1) == 1

    def test_hex_distance_far(self):
        assert hex_distance(0, 0, 3, -1) == 3
        assert hex_distance(-2, 0, 2, 0) == 4

    def test_hex_neighbors_count(self):
        assert len(hex_neighbors(0, 0)) == 6

    def test_hex_neighbors_adjacent(self):
        for nq, nr in hex_neighbors(0, 0):
            assert hex_distance(0, 0, nq, nr) == 1

    def test_hex_ring_size(self):
        ring0 = hex_ring(0, 0, 0)
        assert len(ring0) == 1
        ring1 = hex_ring(0, 0, 1)
        assert len(ring1) == 6
        ring2 = hex_ring(0, 0, 2)
        assert len(ring2) == 12

    def test_hex_spiral_size(self):
        spiral = hex_spiral(0, 0, 2)
        # 1 + 6 + 12 = 19
        assert len(spiral) == 19

    def test_generate_hex_grid_side7(self):
        grid = generate_hex_grid(7)
        # Side 7 hex grid: 3*7^2 - 3*7 + 1 = 127
        assert len(grid) == 127

    def test_generate_hex_grid_center(self):
        grid = generate_hex_grid(7)
        assert (0, 0) in grid

    def test_pixel_roundtrip(self):
        for q, r in [(0, 0), (3, -2), (-1, 4)]:
            px, py = axial_to_pixel(q, r, 30)
            rq, rr = pixel_to_axial(px, py, 30)
            assert (rq, rr) == (q, r)

    def test_hexes_are_adjacent(self):
        assert hexes_are_adjacent(0, 0, 1, 0) is True
        assert hexes_are_adjacent(0, 0, 2, 0) is False

    def test_axial_round(self):
        assert axial_round(0.1, -0.1) == (0, 0)
        assert axial_round(0.9, 0.1) == (1, 0)


class TestHexMap:
    def test_initial_ownership(self):
        hm = HexMap()
        # Center is neutral
        assert hm.ownership[(0, 0)] is None
        # Faction starts are owned
        for fid, (q, r) in FACTION_START_HEXES.items():
            assert hm.ownership[(q, r)] == fid

    def test_faction_territories(self):
        hm = HexMap()
        for fid in FACTION_START_HEXES:
            terr = hm.get_faction_territories(fid)
            assert len(terr) == 1

    def test_neutral_hexes_count(self):
        hm = HexMap()
        neutral = hm.get_neutral_hexes()
        # 127 total - 6 faction starts = 121 neutral
        assert len(neutral) == 121

    def test_reachable_neutral(self):
        hm = HexMap()
        # Mountain starts at (1, -1), should have neutral neighbors
        reachable = hm.get_reachable_neutral_hexes("mountain")
        assert len(reachable) > 0
        for q, r in reachable:
            assert hm.ownership[(q, r)] is None

    def test_factions_are_neighbors(self):
        hm = HexMap()
        # All factions surround center, so adjacent factions should be neighbors
        assert hm.are_factions_neighbors("mountain", "mesa") is True
        assert hm.are_factions_neighbors("mountain", "jungle") is True

    def test_claim_hex(self):
        hm = HexMap()
        hm.claim_hex((0, 0), "mountain")
        assert hm.ownership[(0, 0)] == "mountain"
        terr = hm.get_faction_territories("mountain")
        assert (0, 0) in terr

    def test_border_hex_pairs(self):
        hm = HexMap()
        pairs = hm.get_border_hex_pairs("mountain", "mesa")
        assert len(pairs) > 0
        for (q1, r1), (q2, r2) in pairs:
            assert hexes_are_adjacent(q1, r1, q2, r2)
