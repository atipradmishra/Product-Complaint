import sqlite3
from config import DB_NAME

def run_sql(sql: str):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return {"columns": columns, "rows": rows}
    except Exception as e:
        return {"error": str(e), "columns": [], "rows": []}
    finally:
        if conn:
            conn.close()
