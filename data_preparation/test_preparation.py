import unittest

import pandas as pd

from data_preparation.preparation import build_criticism_matrix


class CriticismMatrixTests(unittest.TestCase):
    def test_counts_distinct_criticism_and_excludes_unclassified_parts(self):
        feedback = pd.DataFrame(
            [
                ["F1", "F70", "Interior", "Defect"],
                ["F1", "F70", "Interior", "Difficult to Use"],
                ["G1", "G60", "Gearbox", "Defect"],
                ["F2", "F70", "Gearbox", "Likes"],
                ["F3", "F70", "Seats", "Wants"],
                ["F4", "F70", None, "Defect"],
                ["F5", "F70", "no_class_found", "Defect"],
            ],
            columns=["ID", "Derivate (e-code)", "Vfc level2 Name", "Feedback Type"],
        )
        expected = pd.DataFrame(
            [[0, 1], [1, 0]],
            index=pd.Index(["Gearbox", "Interior"], name="Vehicle part"),
            columns=pd.Index(["F70", "G60"], name="Vehicle model"),
        )
        pd.testing.assert_frame_equal(
            build_criticism_matrix({"feedback": feedback}), expected
        )
        self.assertTrue(build_criticism_matrix({}).empty)
        self.assertTrue(
            build_criticism_matrix(
                {"likes": feedback.loc[feedback["Feedback Type"].eq("Likes")]}
            ).empty
        )


if __name__ == "__main__":
    unittest.main()
