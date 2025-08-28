import unittest
import random
from movewise.routing import compute_haversine_matrix
from movewise.optimisation import nearest_neighbor, two_opt
from movewise.schedule import schedule_route


class TestSimulation(unittest.TestCase):
    def test_random_cases(self):
        # Perform a handful of random simulations to verify that the
        # pipeline functions end-to-end without raising exceptions.
        for _ in range(10):
            n = random.randint(3, 6)
            coords = []
            for _ in range(n):
                # generate random coordinates near Tokyo (lat 35.6-35.8, lon 139.6-139.8)
                lat = 35.6 + random.random() * 0.2
                lon = 139.6 + random.random() * 0.2
                coords.append((lat, lon))
            dist_matrix, dur_matrix = compute_haversine_matrix(coords, speed_kmh=40)
            route = nearest_neighbor(dist_matrix, start=0)
            route = two_opt(route, dist_matrix)
            stay = [10] * n  # 10 minutes stay at each location
            open_hours = [None] * n
            # All durations in seconds
            schedule = schedule_route(route, dur_matrix, stay, open_hours, "09:00")
            # Ensure schedule covers all stops
            self.assertEqual(len(schedule), n)


if __name__ == "__main__":
    unittest.main()
