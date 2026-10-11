from pathlib import Path

import pandas as pd


def read_csv_files():
    csv_directory = Path(__file__).parent
    return {
        csv_file.stem: pd.read_csv(csv_file)
        for csv_file in csv_directory.glob("*.csv")
    }


def build_criticism_matrix(tables, category_column="Vfc level3 Name"):
    """Return part-level feedback percentages and category shares within each part.

    Distinct feedback IDs stand in for respondents. Categories can overlap when
    one feedback entry mentions multiple issues or recommendations for a part.
    """
    columns = ["Vehicle part", "Feedback (%)", "Issues/recommendations"]
    if not tables:
        return pd.DataFrame(columns=columns).set_index("Vehicle part")

    feedback = pd.concat(tables.values(), ignore_index=True)
    if feedback["ID"].isna().any():
        raise ValueError("Every feedback entry needs an ID to calculate percentages.")
    total_feedback = feedback["ID"].nunique()
    criticism = feedback.loc[
        feedback["Feedback Type"].isin(["Defect", "Difficult to Use", "Wants"])
        & feedback["Vfc level2 Name"].notna()
        & feedback["Vfc level2 Name"].ne("no_class_found")
    ].copy()
    criticism[category_column] = criticism[category_column].fillna(
        "Unspecified issue/recommendation"
    )
    rows = []
    for part, comments in criticism.groupby("Vfc level2 Name"):
        part_feedback = comments["ID"].nunique()
        category_counts = (
            comments.groupby(category_column)["ID"]
            .nunique()
            .sort_values(ascending=False, kind="stable")
        )
        rows.append(
            {
                "Vehicle part": part,
                "Feedback (%)": round(100 * part_feedback / total_feedback, 2),
                "Issues/recommendations": [
                    {
                        "category": category,
                        "percentage": round(100 * count / part_feedback, 2),
                    }
                    for category, count in category_counts.items()
                ],
            }
        )
    return (
        pd.DataFrame(rows, columns=columns)
        .set_index("Vehicle part")
        .sort_values("Feedback (%)", ascending=False, kind="stable")
    )
