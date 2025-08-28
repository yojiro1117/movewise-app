import unittest
from movewise.routing import haversine_distance, compute_haversine_matrix


class TestRouting(unittest.TestCase):
    def test_haversine_distance(self):
        # distance between Tokyo Tower and Tokyo Station (~2.9 km)
        tokyo_tower = (35.6586, 139.7454)
        tokyo_station = (35.6812, 139.7671)
        dist = haversine_distance(tokyo_tower, tokyo_station)
        self.assertAlmostEqual(dist, 2.9, delta=0.5)

    def test_haversine_matrix(self):
        coords = [
            (0, 0),
            (0, 1),
            (1, 0),
        ]
        dist_matrix, dur_matrix = compute_haversine_matrix(coords, speed_kmh=60)
        # Distance from (0,0) to (0,1) ~111 km
        self.assertAlmostEqual(dist_matrix[0][1], 111, delta=2)
        # Duration at 60 km/h should be ~1.85 h = 6660 s
        self.assertAlmostEqual(dur_matrix[0][1], 111/60*3600, delta=300)


if __name__ == "__main__":
    unittest.main()
