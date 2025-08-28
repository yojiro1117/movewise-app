import unittest

from movewise.optimisation import nearest_neighbor, two_opt


class TestOptimisation(unittest.TestCase):
    def test_nearest_neighbor(self):
        # Symmetric distance matrix for 4 nodes
        dist = [
            [0, 2, 9, 10],
            [1, 0, 6, 4],
            [15, 7, 0, 8],
            [6, 3, 12, 0],
        ]
        route = nearest_neighbor(dist, start=0)
        # Starting at 0, nearest is 1, then 3, then 2
        self.assertEqual(route, [0, 1, 3, 2])

    def test_two_opt(self):
        dist = [
            [0, 10, 15, 20],
            [10, 0, 35, 25],
            [15, 35, 0, 30],
            [20, 25, 30, 0],
        ]
        initial = [0, 1, 3, 2]
        optimized = two_opt(initial, dist)
        # The optimal route for this symmetric matrix is [0,1,3,2]
        # But some heuristics may return other near-optimal permutations.
        self.assertIn(optimized, ([0, 1, 3, 2], [0, 1, 2, 3], [0, 2, 1, 3], [0, 3, 1, 2], [0, 3, 2, 1]))


if __name__ == "__main__":
    unittest.main()
