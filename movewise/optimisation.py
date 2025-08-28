"""
Route optimisation heuristics for MoveWise.

This module implements simple travelling salesman heuristics for
constructing an approximate shortest tour through a set of points.
It provides two main functions:

    - ``nearest_neighbor``: build an initial route by repeatedly
      visiting the nearest unvisited location.
    - ``two_opt``: perform a 2‑opt optimisation on an initial route.

The algorithms operate on a symmetric distance matrix, which can
contain travel times or distances between points. Index 0 is assumed
to be the starting point, but other conventions can be used provided
the matrix is square and distances are non‑negative.
"""

from __future__ import annotations

from typing import List, Sequence


def nearest_neighbor(dist_matrix: Sequence[Sequence[float]], start: int = 0) -> List[int]:
    """Construct an initial route using the nearest neighbor heuristic.

    Args:
        dist_matrix: A square matrix of distances or travel times.
        start: Index of the start location in the matrix.

    Returns:
        A list of indices representing the visiting order, starting
        with ``start`` and including all other indices exactly once.
    """
    n = len(dist_matrix)
    if n == 0:
        return []
    unvisited = set(range(n))
    unvisited.remove(start)
    route = [start]
    current = start
    while unvisited:
        # choose the nearest unvisited neighbor
        next_city = min(unvisited, key=lambda j: dist_matrix[current][j])
        route.append(next_city)
        unvisited.remove(next_city)
        current = next_city
    return route


def two_opt(route: List[int], dist_matrix: Sequence[Sequence[float]]) -> List[int]:
    """Perform 2‑opt optimisation on a given route.

    The algorithm iteratively swaps pairs of edges to reduce the total
    route length until no improvements are found.

    Args:
        route: Initial route as a list of indices.
        dist_matrix: Square matrix of distances corresponding to the
            indices in ``route``.

    Returns:
        An optimised route with potentially shorter total length.
    """
    def tour_length(route: List[int]) -> float:
        length = 0.0
        for i in range(len(route) - 1):
            length += dist_matrix[route[i]][route[i + 1]]
        return length

    improved = True
    best = route.copy()
    best_length = tour_length(best)
    n = len(best)
    while improved:
        improved = False
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                if j - i == 1:
                    continue  # adjacent edges, skip
                new_route = best[:i] + best[i:j][::-1] + best[j:]
                new_length = tour_length(new_route)
                if new_length < best_length:
                    best = new_route
                    best_length = new_length
                    improved = True
                    break
            if improved:
                break
    return best
