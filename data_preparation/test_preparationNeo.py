import unittest

from data_preparation.preparationNeo import calculateCommentProbabilities


class CommentProbabilityTests(unittest.TestCase):
    def test_counts_repeats_per_key_without_changing_input(self):
        comments = {
            "Drivetrain": (12.5, ["Noise", "Noise", "Malfunction"]),
            "Seats": (5.0, ["Noise"]),
            "Interior": (2.0, []),
        }
        self.assertEqual(
            calculateCommentProbabilities(comments),
            {
                "Drivetrain": (12.5, {"Noise": 66.67, "Malfunction": 33.33}),
                "Seats": (5.0, {"Noise": 100.0}),
                "Interior": (2.0, {}),
            },
        )
        self.assertEqual(comments["Drivetrain"][1], ["Noise", "Noise", "Malfunction"])
        self.assertEqual(calculateCommentProbabilities({}), {})


if __name__ == "__main__":
    unittest.main()
