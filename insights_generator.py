# insights_generator.py

import sqlite3
import json
from datetime import datetime
from db_manager import load_admin_prompts
from chatagent.rag_synthesizer import generate_rag_response
from config import DB_NAME

def get_dashboard_insights(chart_data, rag_agent_id):
    """
    Returns a list of AI-generated dashboard insights (notifications).
    Caches the result in the dashboard_insights table by date and agent_id.
    Falls back to most recent previous day's insights if today’s aren't available.
    """
    today = datetime.today().strftime('%Y-%m-%d')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Try today’s insights
    cursor.execute("""
        SELECT insights, date FROM dashboard_insights 
        WHERE date = ? AND agent_id = ?
    """, (today, rag_agent_id))
    result = cursor.fetchone()

    if result:
        conn.close()
        return json.loads(result[0]), result[1]

    # Fallback: fetch most recent past insights
    cursor.execute("""
        SELECT insights, date FROM dashboard_insights 
        WHERE date < ? AND agent_id = ?
        ORDER BY date DESC LIMIT 1
    """, (today, rag_agent_id))
    result = cursor.fetchone()
    # result = None

    if result:
        conn.close()
        return json.loads(result[0]), result[1]

    # If no cached insights at all, generate fresh
    admin_prompts = load_admin_prompts(rag_agent_id)
    notif_prompt = admin_prompts.get("dashboard_notifications_prompt", "") if admin_prompts else ""

    notifications = []
    if notif_prompt:
        notif_payload = {
            "charts": chart_data,
            "prompt": notif_prompt
        }
        try:
            notif_response = generate_rag_response(notif_payload)
            notifications = [line.strip() for line in notif_response.split("\n") if line.strip()]

            if "⚠️ Error" not in notif_response:
                cursor.execute("""
                    INSERT INTO dashboard_insights (insights, agent_id, date)
                    VALUES (?, ?, ?)
                """, (json.dumps(notifications), rag_agent_id, today))
                conn.commit()
            else:
                print("⛔ Skipping save: insights contain error placeholder.")

            conn.commit()
            conn.close()
            return notifications, today
        except Exception as e:
            print(f"⚠️ Notification generation failed: {e}")

    conn.close()
    return notifications, None