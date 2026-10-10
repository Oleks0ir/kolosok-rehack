from pathlib import Path

import pandas as pd


def read_csv_files():
    csv_directory = Path(__file__).parent
    return {
        csv_file.stem: pd.read_csv(csv_file)
        for csv_file in csv_directory.glob("*.csv")
    }


def build_criticism_matrix(tables):
    """Count distinct defect/usability feedback IDs per vehicle part and model."""
    if not tables:
        return pd.DataFrame().rename_axis(index="Vehicle part", columns="Vehicle model")

    feedback = pd.concat(tables.values(), ignore_index=True)
    criticism = feedback.loc[
        feedback["Feedback Type"].isin(["Defect", "Difficult to Use"])
        & feedback["Vfc level2 Name"].notna()
        & feedback["Vfc level2 Name"].ne("no_class_found")
    ]
    return (
        criticism.groupby(["Vfc level2 Name", "Derivate (e-code)"])["ID"]
        .nunique()
        .unstack(fill_value=0)
        .rename_axis(index="Vehicle part", columns="Vehicle model")
    )
