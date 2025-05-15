import pandas as pd

def load_column_descriptions(csv_path: str) -> str:
    df = pd.read_csv(csv_path)
    formatted = "\n".join(
        [f"- {row['column_name']}: {row['description']}" for _, row in df.iterrows()]
    )
    return f"Table: raw_data\n\nColumns and their meanings:\n{formatted}"