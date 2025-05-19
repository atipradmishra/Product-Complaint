import pandas as pd

def load_column_descriptions(csv_path: str) -> str:
    df = pd.read_csv(csv_path)
    formatted = "\n".join(
        [f"- {row['column_name']}: {row['description']}" for _, row in df.iterrows()]
    )
    return f"Columns and their meanings:\n{formatted}"

# Load column metadata (used only if injected manually)
column_info = load_column_descriptions("data/roche_metadata.csv")

# Template used to construct the full SQL generation prompt
sql_template = """
{system_prompt}

Task:
{task}

{column_info}

Instruction:
{instruction}

Context:
{context}

SQL Dialect:
Use the appropriate dialect such as SQLite, T-SQL (SQL Server), or Snowflake SQL depending on the source system.

Formatting Instruction:
{formatting_instruction}

User Question:
{user_query}

Expected Output:
Return a JSON object like:
{{{{ "sql": "<valid SQL query>" }}}}
"""

# Placeholder dict — values to be filled at runtime from DB
sql_kwargs = {
    "system_prompt": "",
    "task": "",
    "instruction": "",
    "formatting_instruction": ""
}
