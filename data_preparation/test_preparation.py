import unittest

import pandas as pd

from data_preparation.preparation import build_criticism_matrix


class CriticismMatrixTests(unittest.TestCase):
    def setUp(self):
        self.feedback = pd.DataFrame(
            [
                ["F1", "Gearbox", "Defect", "Delayed shifting"],
                ["F1", "Gearbox", "Difficult to Use", "Delayed shifting"],
                ["F2", "Gearbox", "Wants", "Smoother changes"],
                ["F3", "Gearbox", "Difficult to Use", "Delayed shifting"],
                ["F3", "Gearbox", "Wants", "Smoother changes"],
                ["F4", "Interior", "Likes", "Comfortable"],
                ["F5", "no_class_found", "Defect", "Malfunction"],
                ["F6", None, "Wants", "More features"],
                ["F7", "Seats", "Defect", None],
            ],
            columns=["ID", "Vfc level2 Name", "Feedback Type", "Vfc level3 Name"],
        )

    def test_percentages_use_distinct_ids_and_include_recommendations(self):
        matrix = build_criticism_matrix({"feedback": self.feedback})
        self.assertEqual(matrix.index.tolist(), ["Gearbox", "Seats"])
        self.assertEqual(matrix.loc["Gearbox", "Feedback (%)"], 42.86)
        self.assertEqual(matrix.loc["Seats", "Feedback (%)"], 14.29)
        self.assertEqual(
            matrix.loc["Gearbox", "Issues/recommendations"],
            [
                {"category": "Delayed shifting", "percentage": 66.67},
                {"category": "Smoother changes", "percentage": 66.67},
            ],
        )
        self.assertEqual(
            matrix.loc["Seats", "Issues/recommendations"],
            [{"category": "Unspecified issue/recommendation", "percentage": 100.0}],
        )

    def test_empty_inputs_keep_matrix_columns(self):
        self.assertTrue(build_criticism_matrix({}).empty)
        likes = self.feedback.loc[self.feedback["Feedback Type"].eq("Likes")]
        empty = build_criticism_matrix({"likes": likes})
        self.assertTrue(empty.empty)
        self.assertEqual(empty.columns.tolist(), ["Feedback (%)", "Issues/recommendations"])

    def test_can_group_by_ai_generated_categories(self):
        self.feedback["Issue category"] = "Combined theme"
        matrix = build_criticism_matrix(
            {"feedback": self.feedback}, category_column="Issue category"
        )
        self.assertEqual(
            matrix.loc["Gearbox", "Issues/recommendations"],
            [{"category": "Combined theme", "percentage": 100.0}],
        )

    def test_missing_feedback_ids_are_rejected(self):
        self.feedback.loc[0, "ID"] = None
        with self.assertRaisesRegex(ValueError, "needs an ID"):
            build_criticism_matrix({"feedback": self.feedback})


if __name__ == "__main__":
    unittest.main()
