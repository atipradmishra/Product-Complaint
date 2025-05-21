from flask import Flask, render_template, jsonify, request, flash, redirect, session, url_for
from gpt_client import create_invoke_chain, llm
from chatagent.sql_copilot import get_sql_from_question
from chatagent.rag_synthesizer import generate_rag_response
from sql_query_executor import run_sql_with_connection, run_sql
from db_manager import create_chart_config_table, create_chat_logs_table, create_users_table, delete_chart_config_by_id, fetch_query_logs, get_all_chart_configs, get_metadata_column_names, get_recent_chat_history, register_user, authenticate_user, init_admin_prompts, save_admin_prompts, load_admin_prompts, log_chat_interaction, save_chart_config_to_db, save_or_update_chart_config,save_query_log_to_db
from dataagent.s3_database_upload import upload_s3_database_update
import json
import os
from cryptography.fernet import Fernet
from config import DB_NAME,BUCKET_NAME, aws_access_key, aws_secret_key, FERNET_KEY
import pandas as pd
import boto3
import uuid
import sqlite3
from werkzeug.utils import secure_filename
from datetime import datetime
import pyodbc
import snowflake.connector
from auth_routes import auth_bp
from graphqueryagent.querygraph_copilot import graph_query_bp

app = Flask(__name__)
app.register_blueprint(graph_query_bp)
app.register_blueprint(auth_bp, url_prefix='/auth')
app.secret_key = "dev_secret_key_here"

@app.before_request
def require_login():
    if request.endpoint and (
        request.endpoint.startswith("auth.")
        or request.endpoint.startswith("static")
        or request.endpoint in {"home"}
    ):
        return  # allow login, register, static, and home

    if "username" not in session:
        return redirect(url_for("auth.login"))
    
@app.route("/")
def home():
    # Redirect logged-in users to dashboard, others to login
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))  # <-- Fix redirect target

@app.route("/dashboard")
def dashboard():
    chart_configs = get_all_chart_configs()
    chart_data = []

    for cfg in chart_configs:
        try:
            print(f"🧠 SQL for '{cfg['chart_title']}':\n{cfg['sql_query']}")

            result = run_sql(cfg["sql_query"])

            if not result["rows"]:
                print(f"⚠️ NO DATA returned for chart: {cfg['chart_title']}")

            print(f"📊 SQL Result for '{cfg['chart_title']}':", result)

            # Convert structured rows to list of dicts
            if isinstance(result, dict) and "columns" in result and "rows" in result:
                result = [dict(zip(result["columns"], row)) for row in result["rows"]]
                print("📎 After dict conversion:", result[:2])

            labels = []
            values = []

            for row in result:
                if not isinstance(row, dict):
                    continue

                group_val = row.get(cfg["group_by"])
                if group_val is None:
                    continue
                labels.append(group_val)

                # Dynamically pick the numeric value (not the group_by column)
                value = next(
                    (v for k, v in row.items()
                     if k != cfg["group_by"] and isinstance(v, (int, float))),
                    0
                )
                values.append(value)

            # Generate one color per data point if it's pie/doughnut
            color_palette = [
                "rgba(255, 99, 132, 0.7)",
                "rgba(54, 162, 235, 0.7)",
                "rgba(255, 206, 86, 0.7)",
                "rgba(75, 192, 192, 0.7)",
                "rgba(153, 102, 255, 0.7)",
                "rgba(255, 159, 64, 0.7)"
            ]
            bg_colors = color_palette * ((len(labels) // len(color_palette)) + 1)

            chart_data.append({
                "chart_type": cfg["chart_type"],
                "labels": labels,
                "data": values,
                "metric_label": cfg["metric"].capitalize(),
                "backgroundColor": bg_colors[:len(labels)]
            })

        except Exception as e:
            print(f"⚠️ Failed to process chart: {cfg.get('chart_title', 'Unknown')} — {e}")
            continue
    
    # ✅ Use correct agent ID from session
    #rag_agent_id = session.get("agent_id")



    def get_sqlite_agent_id():
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM connections WHERE LOWER(source) = 'sqlite' ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def is_sqlite_agent(agent_id):
        if not agent_id:
            return False
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT source FROM connections WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        conn.close()
        return row and row[0].lower() == "sqlite"

    # ✅ Verify session agent_id and fallback only if source isn't SQLite
    rag_agent_id = session.get("agent_id")

    if not is_sqlite_agent(rag_agent_id):
        rag_agent_id = get_sqlite_agent_id()
        session["agent_id"] = rag_agent_id

    print("✅ Final agent_id being used:", rag_agent_id)

    summary_text = ""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    today = datetime.today().strftime('%Y-%m-%d')

    c.execute("SELECT summary FROM daily_ai_summary WHERE date = ? AND agent_id = ?", (today,rag_agent_id,))
    result = c.fetchone()

    if result:
        summary_text = result[0]
    else:
        # summary = generate_ai_summary(rag_agent_id)
        admin_prompts = load_admin_prompts(rag_agent_id)
        summary_prompt = admin_prompts.get("dashboard_summary_prompt", "") if admin_prompts else ""

        if summary_prompt:
                summary_payload = {
                    "charts": chart_data,
                    "prompt": summary_prompt
                }
                summary = generate_rag_response(summary_payload)
                summary_text = summary
                c.execute("INSERT INTO daily_ai_summary (summary, agent_id, date) VALUES (?, ?,?)", (summary, rag_agent_id, today))
                conn.commit()
        else:
            summary = ""

    # def generate_ai_summary(agent_id):
    #     admin_prompts = load_admin_prompts(agent_id)
    #     summary_prompt = admin_prompts.get("dashboard_summary_prompt", "") if admin_prompts else ""

    #     if summary_prompt:
    #         try:
    #             summary_payload = {
    #                 "charts": chart_data,
    #                 "prompt": summary_prompt
    #             }
    #             summary = generate_rag_response(summary_payload)
                
    #             return summary
    #         except Exception as e:
    #             print(f"⚠️ Failed to generate AI summary: {e}")
    #             return ""

    return render_template(
        "dashboard.html",
        chart_configs=chart_configs,
        chart_data_json=json.dumps(chart_data),
        ai_summary=summary_text
    )

fernet = Fernet(FERNET_KEY)

init_admin_prompts()
create_users_table()
create_chat_logs_table()
create_chart_config_table()


s3 = boto3.client(
    "s3",
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name='eu-central-1'
)

@app.context_processor
def inject_now():
    return {'now': lambda: datetime.now().strftime('%I:%M %p')}

    
@app.route("/rag-configure")
def rag_configure():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, agent_name, source 
        FROM connections
        ORDER BY agent_name
    """)
    rows = cursor.fetchall()
    conn.close()

    agents = [
        {"id": row[0], "name": row[1], "source": row[2]}
        for row in rows
    ]

    return render_template("rag_configure.html", agents=agents)


@app.route("/rag-dashboard")
def rag_dashboard():
    return render_template("rag_dashboard.html")

@app.route("/chat-with-rag")
def chat_with_rag():
    prefill = request.args.get("prefill", "")
    chat_history = get_recent_chat_history(limit=10)
    return render_template("chat_window.html", prefill=prefill, chat_history=chat_history)

@app.route("/admin/prompts", methods=["GET"])
def admin_prompt_settings_page():
    return render_template("query_analyzer.html")

@app.route("/admin/save_prompts", methods=["POST"])
def save_prompts():
    data = request.get_json()
    save_admin_prompts(data)
    return jsonify({"status": "success"})


@app.route("/admin/load_prompts1", methods=["GET"])
def load_prompts1():
    agent_id = request.args.get("rag_agent_id")
    data = load_admin_prompts(agent_id)
    if data:
        return jsonify(data)
    return jsonify({"error": "Prompt data not found"}), 404

@app.route("/admin/load_prompts", methods=["GET"])
def load_prompts():
    rag_agent_id = request.args.get("rag_agent_id")
    if not rag_agent_id or rag_agent_id == "null":
        rag_agent_id = None
    else:
        try:
            rag_agent_id = int(rag_agent_id)
        except ValueError:
            return jsonify({"error": "Invalid agent ID"}), 400

    # ✅ Save selected agent in session
    session["agent_id"] = rag_agent_id

    data = load_admin_prompts(rag_agent_id=rag_agent_id)
    if data:
        return jsonify(data)
    return jsonify({"error": "Prompt data not found"}), 404

@app.route("/get-connections", methods=["GET"])
def get_connections():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, agent_name FROM connections")
    agents = cursor.fetchall()
    conn.close()
    return jsonify([{"id": row[0], "name": row[1]} for row in agents])


@app.route("/get-connection/<int:agent_id>", methods=["GET"])
def get_connection(agent_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM connections WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    column_names = [desc[0] for desc in cursor.description]
    conn.close()

    if not row:
        return jsonify({"error": "Agent not found"}), 404

    result = dict(zip(column_names, row))
    if result.get("pwd"):
        try:
            result["pwd"] = fernet.decrypt(result["pwd"].encode()).decode()
        except:
            result["pwd"] = ""

    return jsonify(result)


@app.route("/connect-agent", methods=["POST"])
def connect_agent():
    data = request.get_json()
    agent_id = data.get("agent_id")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM connections WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        column_names = [desc[0] for desc in cursor.description]
        conn.close()

        if not row:
            return jsonify({"status": "error", "message": "Agent not found"}), 404

        connection = dict(zip(column_names, row))
        if connection.get("pwd"):
            try:
                connection["pwd"] = fernet.decrypt(connection["pwd"].encode()).decode()
            except Exception as e:
                print(f"❌ Password decryption failed: {e}")

        source = connection.get("source", "").lower()

        if source == "sqlite":
            if not connection.get("sql_database"):
                connection["sql_database"] = DB_NAME
            sqlite3.connect(connection["sql_database"]).close()

        elif source == "azure":
            conn_str = (
                f"DRIVER={{{connection['driver']}}};"
                f"SERVER={connection['server']};"
                f"DATABASE={connection['sql_database']};"
                f"UID={connection['uid']};"
                f"PWD={connection['pwd']};"
                f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=5;"
            )
            pyodbc.connect(conn_str).close()
        elif source == "snowflake":
            snowflake.connector.connect(
                user=connection["uid"],
                password=connection["pwd"],
                account=connection["account"],
                warehouse=connection["warehouse"],
                database=connection["sf_database"],
                schema=connection["schema"]
            ).close()
        else:
            return jsonify({"status": "error", "message": f"Unknown source: {source}"}), 400

        return jsonify({"status": "success", "message": f"Connected to {source} DB"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/copilot-query", methods=["POST"])
def copilot_query():
    data = request.get_json()
    user_query = data.get("message", "")
    agent_id = data.get("agent_id")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM connections WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        column_names = [desc[0] for desc in cursor.description]
        conn.close()

        if not row:
            return jsonify({"response": "Selected agent not found."})
        session["agent_id"] = agent_id
        connection = dict(zip(column_names, row))
        if connection.get("pwd"):
            try:
                connection["pwd"] = fernet.decrypt(connection["pwd"].encode()).decode()
            except Exception as e:
                print(f"❌ Password decryption failed: {e}")

        source = connection.get("source", "").lower()

        # ✅ Fallback for SQLite database
        if source == "sqlite" and not connection.get("sql_database"):
            connection["sql_database"] = DB_NAME

        # ✅ Handle source-specific metadata + table name
        if source == "snowflake":
            table_name = get_first_table_name_snowflake(connection)
            column_info = get_snowflake_table_metadata(connection)
            generated = get_sql_from_question(
                user_query,
                table_name=table_name,
                conn_details=connection,
                column_info=column_info
            )
        elif source == "azure":
            conn_str = (
                f"DRIVER={{{connection['driver']}}};"
                f"SERVER={connection['server']};"
                f"DATABASE={connection['sql_database']};"
                f"UID={connection['uid']};"
                f"PWD={connection['pwd']};"
                f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=5;"
            )
            table_name = get_first_table_name_azure(conn_str)
            generated = get_sql_from_question(
                user_query,
                table_name=table_name,
                conn_details=connection
            )
        elif source == "sqlite":
            def get_first_table_name_sqlite(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 1")
                    result = cursor.fetchone()
                    return result[0] if result else None
                except Exception:
                    return None

            table_name = get_first_table_name_sqlite(connection["sql_database"])
            from chatagent.sql_copilot import load_column_info_from_db
            column_info = load_column_info_from_db(connection)
            generated = get_sql_from_question(
                user_query,
                table_name=table_name,
                conn_details=connection,
                column_info=column_info
            )
        else:
            generated = get_sql_from_question(user_query)

        # ✅ Run the query and generate a summary
        if isinstance(generated, dict) and "sql" in generated:
            sql = generated["sql"]

            # ✅ Remove 'dbo.' for non-SQL Server engines
            if source in ["sqlite", "snowflake", "mysql", "postgresql", "oracle"]:
                sql = sql.replace("dbo.", "")

            result = run_sql_with_connection(sql, connection)

            print(f"📄 Generated SQL:\n{sql}")
            print(f"📊 Query Result Rows:\n{result['rows']}")
            rag_response = generate_rag_response(result, user_query)
            log_chat_interaction(user_query, sql, result, rag_response)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("sqlquery_log.txt", "a", encoding="utf-8") as log_file:
                log_file.write(f"{timestamp} | USER QUERY: {user_query} | SQL: {sql} | RESULT: {rag_response}\n")

            save_query_log_to_db(timestamp, user_query, sql, rag_response)

        else:
            raise ValueError("No SQL generated.")

    except Exception as e:
        print(f"❌ Error: {e}")
        rag_response = "Sorry, something went wrong while processing your request."

    return jsonify({"response": rag_response})





def get_first_table_name_azure(conn_str):
    try:
        with pyodbc.connect(conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT TOP 1 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception:
        return None

def get_first_table_name_snowflake(conn_details):
    try:
        conn = snowflake.connector.connect(
            user=conn_details["uid"],
            password=conn_details["pwd"],
            account=conn_details["account"],
            warehouse=conn_details["warehouse"],
            database=conn_details["sf_database"],
            schema=conn_details["schema"]
        )
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        result = cursor.fetchone()
        return result[1] if result else None
    except Exception:
        return None

def get_snowflake_table_metadata(conn_details):
    try:
        conn = snowflake.connector.connect(
            user=conn_details["uid"],
            password=conn_details["pwd"],
            account=conn_details["account"],
            warehouse=conn_details["warehouse"],
            database=conn_details["sf_database"],
            schema=conn_details["schema"]
        )
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[1] for row in cursor.fetchall()]

        metadata_lines = []
        for table in tables:
            cursor.execute(f"DESC TABLE {table}")
            columns = [row[0] for row in cursor.fetchall()]
            metadata_lines.append(f"Table: {table}")
            metadata_lines.extend([f"- {col}" for col in columns])

        return "\n".join(metadata_lines)
    except Exception as e:
        return f"⚠️ Failed to load metadata from Snowflake: {e}"

@app.route("/rag-agents/add", methods=["GET", "POST"])
def add_agent():

    folders = {
        "Product Complaint": "ProductComplaint"
    }

    if request.method == "POST":
        name = request.form.get("name")
        bucket = request.form.get("bucket")
        folder = request.form.get("folder")
        model = request.form.get("model")
        temperature = request.form.get("temperature")
        prompt = request.form.get("prompt")

        metadata_file = request.files.get("metadata_file")
        uploaded_file = request.files.get("uploaded_file")

        # if metadata_file:
        #     metadata_file.save(os.path.join("uploads", metadata_file.filename))
        # if uploaded_file:
        #     uploaded_file.save(os.path.join("uploads", uploaded_file.filename))

        flash("RAG Agent successfully added!", "success")

    return render_template("add_edit_agent.html", folders=folders) 

@app.route("/save-connection", methods=["POST"])
def save_connection():
    try:
        data = request.form
        # Hash the password (encrypt using bcrypt)
        plain_password = data.get("pwd", "")
        encrypted_pwd = fernet.encrypt(plain_password.encode()).decode()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT,
                source TEXT, uid TEXT, pwd TEXT,
                server TEXT, sql_database TEXT, port TEXT, driver TEXT,
                account TEXT, sf_database TEXT, warehouse TEXT, schema TEXT
    
            )

        ''')

        cursor.execute('''
                INSERT INTO connections (
                    agent_name, source, uid, pwd,
                    server, sql_database, port, driver,
                    account, sf_database, warehouse, schema
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get("modal_agent_name"),
                data.get("source"),
                data.get("uid"), encrypted_pwd,
                data.get("server"), data.get("sql_database"), data.get("port"), data.get("driver"),
                data.get("account"), data.get("sf_database"), data.get("warehouse"), data.get("schema")
            ))

        conn.commit()
        conn.close()
        return jsonify({"message": "Connection details saved successfully"})
    except Exception as e:
        return jsonify({"message": f"Error saving connection: {str(e)}"}), 500

@app.route("/data-management")
def data_management():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM data_files_metadata 
    """)
    rows = cursor.fetchall()
    print(rows)
    conn.close()

    columns = ["id","file_name","file_path", "is_processed","created_at"]
    files = []
    for row in rows:
        files.append(dict(zip(columns, row)))

    return render_template("data_management.html", files=files)

@app.route("/data-dashboard")
def data_dashboard():
    return render_template("data_dashboard.html")

@app.route('/upload-validate-file', methods=['POST'])
def upload_validate_file():

    print("📥 Inside upload_validate_file()")
    bucket = request.form.get('bucket')
    folder = request.form.get('folder')
    metadata_file = request.files.get('metadata_file')
    data_file = request.files.get('data_file')

    print(f'📄 metadata_file: {metadata_file}')
    print(f'📄 data_file: {data_file}')

    if not metadata_file or not data_file or not folder or not bucket:
        flash('All fields including bucket and folder selection are required.')
        return redirect('/data-management')

    # Ensure temp directory exists
    os.makedirs('temp_uploads', exist_ok=True)

    # Save files temporarily
    metadata_path = os.path.join('temp_uploads', secure_filename(metadata_file.filename))
    data_path = os.path.join('temp_uploads', secure_filename(data_file.filename))
    metadata_file.save(metadata_path)
    data_file.save(data_path)

    print(f'📂 Temp file saved at: {data_path}')

    # Validate file structure
    try:
        metadata_df = pd.read_csv(metadata_path)
        data_df = pd.read_excel(data_path)

        required_columns = metadata_df['column_name'].dropna().tolist()
        data_columns = data_df.columns.tolist()

        if not all(col in data_columns for col in required_columns):
            missing = list(set(required_columns) - set(data_columns))
            flash(f'Missing columns in uploaded XLSX: {missing}')
            print(f'❌ Missing columns: {missing}')
            return redirect('/data-management')

        # If validation passes, delegate remaining upload steps
        return upload_s3_database_update(s3, bucket, folder, data_file.filename, data_path, data_df)

        #return upload_s3_database_update(bucket, folder, data_file.filename, data_path, data_df)

    except Exception as e:
        print(f'❌ Validation error: {e}')
        flash(f'Error: {e}')
        return redirect('/data-management')
    finally:
        # Clean only metadata, as data file might still be needed in the second function
        if os.path.exists(metadata_path):
            os.remove(metadata_path)

@app.route("/query-analyzer", methods=["GET"])
def query_analyzer():
    return render_template("query_analyzer.html")

@app.route('/copilot-feedback', methods=['POST'])
def copilot_feedback():
    data = request.json
    feedback_type = data.get('feedback')  # 'up' or 'down'
    response_text = data.get('response')  # The bot response
    # Store it in DB, log it, or process it as needed
    print(f"Feedback received: {feedback_type} for response: {response_text}")
    return {"status": "success"}

def connect_agent_handler(agent_id, connection):
    source = connection.get("source", "").lower()

    if source == "sqlite":
        try:
            test_conn = sqlite3.connect(connection["sql_database"])
            test_conn.close()
            return {"status": "success", "message": "Connected to SQLite DB"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif source == "azure":
        try:
            conn_str = (
                f"DRIVER={{{connection['driver']}}};"
                f"SERVER={connection['server']};"
                f"DATABASE={connection['sql_database']};"
                f"UID={connection['uid']};"
                f"PWD={connection['pwd']};"
                f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=5;"
            )
            test_conn = pyodbc.connect(conn_str)
            test_conn.close()
            return {"status": "success", "message": "Connected to Azure SQL database"}
        except Exception as e:
            return {"status": "error", "message": f"Azure SQL connection failed: {str(e)}"}

    elif source == "snowflake":
        try:
            conn = snowflake.connector.connect(
                user=connection["uid"],
                password=connection["pwd"],
                account=connection["account"],
                warehouse=connection["warehouse"],
                database=connection["sf_database"],
                schema=connection["schema"]
            )
            conn.close()
            return {"status": "success", "message": "Connected to Snowflake"}
        except Exception as e:
            return {"status": "error", "message": f"Snowflake connection failed: {str(e)}"}

    return {"status": "error", "message": f"Unknown source type: {source}"}

@app.route("/data-dash-config")
def dashboard_config():
    columns = get_metadata_column_names()  # read from roche_metadata.csv
    chart_configs = get_all_chart_configs()  # 🧠 fetch saved configs
    return render_template("dashboard_config.html", columns=columns, saved_configs=chart_configs)

@app.route("/dashboard/save-one-config", methods=["POST"])
def save_one_chart_config():
    config = request.get_json()
    prompt = config.get("prompt_text", "")
    try:
        from chatagent.sql_copilot import get_sql_from_question
        result = get_sql_from_question(prompt)
        sql = result["sql"] if isinstance(result, dict) and "sql" in result else ""
        if not sql.strip():
            return jsonify({"error": "SQL generation failed"}), 400
        config["sql_query"] = sql
        new_id = save_or_update_chart_config(config)
        return jsonify({"status": "success", "config_id": new_id})
    except Exception as e:
        print(f"❌ Error saving chart config: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/dashboard/delete-config/<int:config_id>", methods=["POST"])
def delete_chart_config(config_id):
    delete_chart_config_by_id(config_id)
    return jsonify({"status": "deleted"})

@app.route("/debug-connections")
def debug_connections():
    import sqlite3
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, agent_name FROM connections")
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

def get_first_table_name_sqlite(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 1")
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception:
        return None

@app.route("/query-log-analyzer")
def query_log_analyzer():
    logs = fetch_query_logs(limit=300)
    return render_template("query_log_analyzer.html", logs=logs)


@app.route("/admin/save-summary-prompt", methods=["POST"])
def save_summary_prompt():
    data = request.get_json()
    prompt = data.get("summary_prompt", "")
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE admin_prompts SET dashboard_summary_prompt = ? WHERE id = 1", (prompt,))
        conn.commit()
    return jsonify({"status": "success"})

#@app.route("/graph-query")
#def graph_query():
#    return render_template("graph_query.html")

@app.route("/deviation-analysis")
def deviation_analysis():
    #logs = fetch_query_logs(limit=300)
    return render_template("work_in_progress.html")

@app.route("/root-cause")
def root_cause():
    #logs = fetch_query_logs(limit=300)
    return render_template("work_in_progress.html")

@app.route("/analysis-history")
def analysis_history():
    #logs = fetch_query_logs(limit=300)
    return render_template("work_in_progress.html")

@app.route("/user-feedback")
def user_feedback():
    #logs = fetch_query_logs(limit=300)
    return render_template("work_in_progress.html")

@app.route("/fine-tuning")
def fine_tuning():
    #logs = fetch_query_logs(limit=300)
    return render_template("work_in_progress.html")

@app.route("/settings")
def settings():
    #logs = fetch_query_logs(limit=300)
    return render_template("work_in_progress.html")

@app.route("/processed-data")
def processed_data():
    #logs = fetch_query_logs(limit=300)
    return render_template("work_in_progress.html")

@app.route("/update-connection", methods=["POST"])
def update_connection():
    try:
        data = request.form
        agent_id = data.get("id")

        encrypted_pwd = fernet.encrypt(data.get("pwd", "").encode()).decode()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE connections
            SET agent_name=?, source=?, uid=?, pwd=?, server=?, sql_database=?, port=?, driver=?, schema=?, 
                account=?, sf_database=?, warehouse=?
            WHERE id = ?
        """, (
            data.get("agent_name"), data.get("source"), data.get("uid"), encrypted_pwd,
            data.get("server"), data.get("sql_database"), data.get("port"), data.get("driver"),
            data.get("schema"), data.get("account"), data.get("sql_database"), data.get("warehouse"),
            agent_id
        ))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Agent updated successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
