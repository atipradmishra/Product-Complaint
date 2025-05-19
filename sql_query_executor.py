import sqlite3
import pyodbc
import snowflake.connector
from decimal import Decimal
from config import DB_NAME

def normalize(value):
    if isinstance(value, Decimal):
        return float(value)
    return value

def run_sql_with_connection(sql: str, conn_details: dict):
    source = conn_details.get("source", "").lower()
    print(source)
    try:
        if source == "azure":
            conn_str = (
                f"DRIVER={{{conn_details['driver']}}};"
                f"SERVER={conn_details['server']};"
                f"DATABASE={conn_details['sql_database']};"
                f"UID={conn_details['uid']};"
                f"PWD={conn_details['pwd']};"
                f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=10;"
            )
            conn = pyodbc.connect(conn_str)
        elif source == "sqlite":
            conn = sqlite3.connect(conn_details["sql_database"])
        elif source == "snowflake":
            conn = snowflake.connector.connect(
                user=conn_details["uid"],
                password=conn_details["pwd"],
                account=conn_details["account"],
                warehouse=conn_details["warehouse"],
                database=conn_details["sf_database"],
                schema=conn_details["schema"]
            )
        else:
            return {"error": f"Unknown source: {source}", "columns": [], "rows": []}

        cursor = conn.cursor()
        cursor.execute(sql)
        print(f"Executed SQL: {sql}")
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        data = [{col: normalize(val) for col, val in zip(columns, row)} for row in rows]
        return {"columns": columns, "rows": data}

    except Exception as e:
        return {"error": str(e), "columns": [], "rows": []}
    finally:
        try:
            conn.close()
        except:
            pass

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