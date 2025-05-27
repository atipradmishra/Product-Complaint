import sqlite3
from config import DB_NAME

def get_kpi_cards():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Total Complaints
    cursor.execute("SELECT COUNT(*) FROM raw_data")
    total_complaints = cursor.fetchone()[0]

    # Site with Highest Complaints
    cursor.execute("""
        SELECT origin_site_name, COUNT(*) as count 
        FROM raw_data 
        GROUP BY origin_site_name 
        ORDER BY count DESC 
        LIMIT 1
    """)
    site_row = cursor.fetchone()
    top_site = site_row[0] if site_row else "N/A"

    # Average TAT (in days)
    cursor.execute("""
        SELECT AVG(julianday(date_closed) - julianday(date_criticality_determined))
        FROM raw_data
        WHERE date_closed IS NOT NULL AND date_criticality_determined IS NOT NULL
    """)
    avg_tat = cursor.fetchone()[0]
    avg_tat = round(avg_tat, 1) if avg_tat else "N/A"

    conn.close()

    return [
        {"label": "Total Complaints", "value": total_complaints},
        {"label": "Top Complaint Site", "value": top_site},
        {"label": "Avg TAT (days)", "value": avg_tat}
    ]