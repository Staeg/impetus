"""Hex math utilities using axial coordinates (q, r).

Pointy-top hexagons. Used by both client and server.
"""

import math
from typing import Iterator


# Axial direction vectors for the 6 neighbors of a hex (flat-top)
AXIAL_DIRECTIONS = [
    (1, 0), (1, -1), (0, -1),
    (-1, 0), (-1, 1), (0, 1),
]


def hex_neighbor(q: int, r: int, direction: int) -> tuple[int, int]:
    """Return the neighbor of (q, r) in the given direction (0-5)."""
    dq, dr = AXIAL_DIRECTIONS[direction]
    return (q + dq, r + dr)


def hex_neighbors(q: int, r: int) -> list[tuple[int, int]]:
    """Return all 6 neighbors of hex (q, r)."""
    return [(q + dq, r + dr) for dq, dr in AXIAL_DIRECTIONS]


def hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """Manhattan distance between two hexes in axial coords."""
    s1 = -q1 - r1
    s2 = -q2 - r2
    return max(abs(q1 - q2), abs(r1 - r2), abs(s1 - s2))


def axial_to_cube(q: int, r: int) -> tuple[int, int, int]:
    """Convert axial (q, r) to cube (x, y, z)."""
    x = q
    z = r
    y = -x - z
    return (x, y, z)


def cube_to_axial(x: int, y: int, z: int) -> tuple[int, int]:
    """Convert cube (x, y, z) to axial (q, r)."""
    return (x, z)


def hex_ring(center_q: int, center_r: int, radius: int) -> list[tuple[int, int]]:
    """Return all hexes at exactly `radius` distance from center."""
    if radius == 0:
        return [(center_q, center_r)]
    results = []
    # Start at the hex `radius` steps in direction 4 (-1, 1)
    q = center_q + AXIAL_DIRECTIONS[4][0] * radius
    r = center_r + AXIAL_DIRECTIONS[4][1] * radius
    for direction in range(6):
        for _ in range(radius):
            results.append((q, r))
            q, r = hex_neighbor(q, r, direction)
    return results


def hex_spiral(center_q: int, center_r: int, radius: int) -> list[tuple[int, int]]:
    """Return all hexes within `radius` of center, spiraling outward."""
    results = [(center_q, center_r)]
    for r in range(1, radius + 1):
        results.extend(hex_ring(center_q, center_r, r))
    return results


def generate_hex_grid(side_length: int) -> set[tuple[int, int]]:
    """Generate all hex coords for a hexagonal grid of given side length.

    A side-7 grid has hexes at distance 0..6 from center, for a total of 127 hexes.
    """
    hexes = set()
    for q in range(-(side_length - 1), side_length):
        for r in range(-(side_length - 1), side_length):
            if hex_distance(0, 0, q, r) < side_length:
                hexes.add((q, r))
    return hexes


def axial_to_pixel(q: int, r: int, hex_size: float) -> tuple[float, float]:
    """Convert axial coords to pixel coords (pointy-top hex)."""
    x = hex_size * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
    y = hex_size * (3 / 2 * r)
    return (x, y)


def pixel_to_axial(px: float, py: float, hex_size: float) -> tuple[int, int]:
    """Convert pixel coords to the nearest axial hex coord (pointy-top hex)."""
    q_frac = (math.sqrt(3) / 3 * px - 1 / 3 * py) / hex_size
    r_frac = (2 / 3 * py) / hex_size
    return axial_round(q_frac, r_frac)


def axial_round(q_frac: float, r_frac: float) -> tuple[int, int]:
    """Round fractional axial coords to the nearest hex."""
    s_frac = -q_frac - r_frac
    q = round(q_frac)
    r = round(r_frac)
    s = round(s_frac)
    q_diff = abs(q - q_frac)
    r_diff = abs(r - r_frac)
    s_diff = abs(s - s_frac)
    if q_diff > r_diff and q_diff > s_diff:
        q = -r - s
    elif r_diff > s_diff:
        r = -q - s
    return (q, r)


def hex_vertices(q: int, r: int, hex_size: float) -> list[tuple[float, float]]:
    """Return the 6 corner vertices of a pointy-top hex at (q, r)."""
    cx, cy = axial_to_pixel(q, r, hex_size)
    vertices = []
    for i in range(6):
        angle = math.radians(-90 + 60 * i)
        vx = cx + hex_size * math.cos(angle)
        vy = cy + hex_size * math.sin(angle)
        vertices.append((vx, vy))
    return vertices


def hexes_are_adjacent(q1: int, r1: int, q2: int, r2: int) -> bool:
    """Check if two hexes are adjacent."""
    return hex_distance(q1, r1, q2, r2) == 1
