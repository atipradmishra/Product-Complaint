from flask import Blueprint, request, render_template, session, redirect
from gpt_client import create_invoke_chain
from graphqueryagent.graphyquery_prompt import graph_template, graph_kwargs
from sql_query_executor import run_sql
from config import DB_NAME
from datetime import datetime
import sqlite3
import pandas as pd

graph_query_bp = Blueprint('graph_query', __name__)

@graph_query_bp.route("/graph-query", methods=["GET", "POST"])
def graph_query():
    user_query = ""
    chart_labels = []
    chart_values = []
    chart_colors = []
    summary = ""

    if request.method == "POST":
        user_query = request.form.get("graph_query")

        # Step 1: LLM generates insight and SQL
        result = generate_graph_insight(user_query)
        print("🔍 LLM Output:", result)

        if "error" in result:
            summary = result["error"]
        else:
            sql = result.get("sql")
            summary = result.get("summary", "")
            chart_type = result.get("suggested_chart", "bar")
            x_axis = result.get("x_axis")
            y_axis = result.get("y_axis")

            print(f"📊 SQL: {sql}")
            query_result = run_sql(sql)
            print("📈 Query Result:", query_result)

            # Step 2: Extract chart data
            if query_result.get("rows"):
                chart_labels = [row[0] for row in query_result["rows"]]
                chart_values = [row[1] for row in query_result["rows"]]
                chart_colors = get_color_palette(len(chart_labels))

        # Step 3: Store to session history
        if "graph_history" not in session:
            session["graph_history"] = []

        session["graph_history"].append({
            "query": user_query,
            "summary": summary,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        session.modified = True
        chart_colors = get_color_palette(len(chart_labels))
        print(f"I am here {summary}")
    return render_template("graph_query.html",
                           user_query=user_query,
                           summary=summary,
                           chart_colors=chart_colors,
                           chart_labels=chart_labels,
                           chart_values=chart_values,
                           graph_history=session.get("graph_history", []))


@graph_query_bp.route("/clear-graph-history", methods=["POST"])
def clear_graph_history():
    session.pop("graph_history", None)
    return redirect("/graph-query")

def get_color_palette(n):
    base_colors = [
        "rgba(255, 99, 132, 0.7)", "rgba(54, 162, 235, 0.7)", "rgba(255, 206, 86, 0.7)",
        "rgba(75, 192, 192, 0.7)", "rgba(153, 102, 255, 0.7)", "rgba(255, 159, 64, 0.7)"
    ]
    return (base_colors * ((n // len(base_colors)) + 1))[:n]


def generate_graph_insight(user_query: str):
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("""
            SELECT title as product_name, 
                   origin_site_name as origin_site, 
                   lifecycle_state as status, 
                   initial_criticality_classification as criticality, 
                   date_received 
            FROM raw_data
        """, conn)
        conn.close()

        metrics_overview = {
            "top_product": df["product_name"].value_counts().idxmax(),
            "top_site": df["origin_site"].value_counts().idxmax(),
            "top_status": df["status"].value_counts().idxmax(),
            "top_criticality": df["criticality"].value_counts().idxmax(),
            "total_complaints": len(df)
        }

        context = f"""
        User Query: {user_query}

        Metrics Overview:
        - Top Product: {metrics_overview['top_product']}
        - Top Site: {metrics_overview['top_site']}
        - Top Status: {metrics_overview['top_status']}
        - Top Criticality: {metrics_overview['top_criticality']}
        - Total Complaints: {metrics_overview['total_complaints']}
        """

        input_vars = {
            "system_prompt": graph_kwargs["system_prompt"],
            "task": graph_kwargs["task"],
            "instruction": graph_kwargs["instruction"],
            "context": context
        }
        
        return create_invoke_chain(graph_template, input_vars)

    except Exception as e:
        return {"error": str(e)}
