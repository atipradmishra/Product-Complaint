import json
import sqlite3
import hashlib

import pandas as pd
from config import BUCKET_NAME,DB_NAME

# Create users table
def create_users_table():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password BLOB NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_agents (
            agent_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            model TEXT NOT NULL,
            temperature REAL DEFAULT 0.7,
            s3_folder TEXT, 
            prompt TEXT,
            is_active BOOLEAN DEFAULT TRUE CHECK(is_active IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_files_metadata (
            file_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT,
            s3_path TEXT,
            is_processed BOOLEAN DEFAULT TRUE CHECK(is_processed IN (0, 1)),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata_files (
            metadata_files_id INTEGER PRIMARY KEY AUTOINCREMENT,
            rag_agent_id INTEGER,
            filename TEXT,
            s3_path TEXT,
            json_data TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rag_agent_id) REFERENCES rag_agents (rag_agent_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_logs (
            feedback_logs_id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            answer TEXT NOT NULL,
            user_feedback BOOLEAN DEFAULT 1,
            feedback_comment TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_query TEXT,
            generated_sql TEXT,
            result_value REAL
        )
    """)
    conn.commit()
    conn.close()

# Register new user
def register_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Authenticate user
def authenticate_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, hashed_password))
    user = c.fetchone()
    conn.close()
    return user is not None

# Initializes the admin_prompts table if it doesn't exist.
# This table stores global one-time configuration prompts for:
# (1) SQL Query Generator and (2) Query Synthesizer.
# Ensures a single row (id=1) is created to hold the latest prompt settings.
def init_admin_prompts():
    with sqlite3.connect(DB_NAME) as conn:
        # Create the table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sql_system_prompt TEXT,
                sql_task TEXT,
                sql_instruction TEXT,
                synthesizer_system_prompt TEXT,
                synthesizer_task TEXT,
                synthesizer_instruction TEXT,
                dashboard_summary_prompt TEXT
                -- note: rag_agent_id not included here to avoid redefinition if it already exists
            );
        """)

        # Add rag_agent_id column if it doesn't exist
        cursor = conn.execute("PRAGMA table_info(admin_prompts)")
        columns = [row[1] for row in cursor.fetchall()]
        if "rag_agent_id" not in columns:
            conn.execute("ALTER TABLE admin_prompts ADD COLUMN rag_agent_id INTEGER")



#Save prompt data from UI
#This function is called when the "Save All Prompts" button is clicked:

def save_admin_prompts(prompt_data):
    rag_agent_id = prompt_data.get("rag_agent_id")

    try:
        rag_agent_id = int(rag_agent_id)
    except (TypeError, ValueError):
        rag_agent_id = None

    is_default = rag_agent_id is None

    with sqlite3.connect(DB_NAME) as conn:
        if is_default:
            # Update the default row (id = 1)
            conn.execute("""
                UPDATE admin_prompts SET
                    sql_system_prompt = ?,
                    sql_task = ?,
                    sql_instruction = ?,
                    synthesizer_system_prompt = ?,
                    synthesizer_task = ?,
                    synthesizer_instruction = ?,
                    dashboard_summary_prompt = ?
                WHERE id = 1
            """, (
                prompt_data["sql_system_prompt"],
                prompt_data["sql_task"],
                prompt_data["sql_instruction"],
                prompt_data["synthesizer_system_prompt"],
                prompt_data["synthesizer_task"],
                prompt_data["synthesizer_instruction"],
                prompt_data["dashboard_summary_prompt"]
            ))
        else:
            # Update or insert by rag_agent_id
            cur = conn.execute("SELECT id FROM admin_prompts WHERE rag_agent_id = ?", (rag_agent_id,))
            row = cur.fetchone()

            if row:
                conn.execute("""
                    UPDATE admin_prompts SET
                        sql_system_prompt = ?,
                        sql_task = ?,
                        sql_instruction = ?,
                        synthesizer_system_prompt = ?,
                        synthesizer_task = ?,
                        synthesizer_instruction = ?,
                        dashboard_summary_prompt = ?
                    WHERE rag_agent_id = ?
                """, (
                    prompt_data["sql_system_prompt"],
                    prompt_data["sql_task"],
                    prompt_data["sql_instruction"],
                    prompt_data["synthesizer_system_prompt"],
                    prompt_data["synthesizer_task"],
                    prompt_data["synthesizer_instruction"],
                    prompt_data["dashboard_summary_prompt"],
                    rag_agent_id
                ))
            else:
                conn.execute("""
                    INSERT INTO admin_prompts (
                        sql_system_prompt, sql_task, sql_instruction,
                        synthesizer_system_prompt, synthesizer_task, synthesizer_instruction, dashboard_summary_prompt,
                        rag_agent_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    prompt_data["sql_system_prompt"],
                    prompt_data["sql_task"],
                    prompt_data["sql_instruction"],
                    prompt_data["synthesizer_system_prompt"],
                    prompt_data["synthesizer_task"],
                    prompt_data["synthesizer_instruction"],
                    prompt_data["dashboard_summary_prompt"],
                    rag_agent_id
                ))


def save_admin_prompts_BKP(prompt_data):
    rag_agent_id = prompt_data.get("rag_agent_id")
    with sqlite3.connect(DB_NAME) as conn:
        # Check if record already exists
        cur = conn.execute("SELECT id FROM admin_prompts WHERE rag_agent_id = ?", (rag_agent_id,))
        row = cur.fetchone()

        if row:
            # Update existing
            conn.execute("""
                UPDATE admin_prompts SET
                    sql_system_prompt = ?,
                    sql_task = ?,
                    sql_instruction = ?,
                    synthesizer_system_prompt = ?,
                    synthesizer_task = ?,
                    synthesizer_instruction = ?,
                    dashboard_summary_prompt = ?
                WHERE rag_agent_id = ?
            """, (
                prompt_data["sql_system_prompt"],
                prompt_data["sql_task"],
                prompt_data["sql_instruction"],
                prompt_data["synthesizer_system_prompt"],
                prompt_data["synthesizer_task"],
                prompt_data["synthesizer_instruction"],
                prompt_data["dashboard_summary_prompt"],
                rag_agent_id
            ))
        else:
            # Insert new
            conn.execute("""
                INSERT INTO admin_prompts (
                    sql_system_prompt, sql_task, sql_instruction,
                    synthesizer_system_prompt, synthesizer_task, synthesizer_instruction,
                    dashboard_summary_prompt,rag_agent_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?,?)
            """, (
                prompt_data["sql_system_prompt"],
                prompt_data["sql_task"],
                prompt_data["sql_instruction"],
                prompt_data["synthesizer_system_prompt"],
                prompt_data["synthesizer_task"],
                prompt_data["synthesizer_instruction"],
                prompt_data["dashboard_summary_prompt"],
                rag_agent_id
            ))


def migrate_default_prompt_to_agent(rag_agent_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        # Get the default (id=1) prompt
        cur = conn.execute("""
            SELECT sql_system_prompt, sql_task, sql_instruction,
                   synthesizer_system_prompt, synthesizer_task, synthesizer_instruction,dashboard_summary_prompt
            FROM admin_prompts WHERE id = 1
        """)
        row = cur.fetchone()

        if not row:
            print("⚠️ No default prompt found to migrate.")
            return False

        # Check if this agent already has a prompt
        cur = conn.execute("SELECT 1 FROM admin_prompts WHERE rag_agent_id = ?", (rag_agent_id,))
        if cur.fetchone():
            print(f"⚠️ Agent {rag_agent_id} already has a prompt. Migration skipped.")
            return False

        # Insert a new row for the agent
        conn.execute("""
            INSERT INTO admin_prompts (
                sql_system_prompt, sql_task, sql_instruction,
                synthesizer_system_prompt, synthesizer_task, synthesizer_instruction,
                dashboard_summary_prompt,rag_agent_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?,?)
        """, (*row, rag_agent_id))

        print(f"✅ Default prompt migrated to agent_id {rag_agent_id}.")
        return True




# Loads the latest saved prompts for both the SQL Query Generator and Query Synthesizer.
# Returns a dictionary containing system prompt, task, and instruction for each.
# Used globally in the application to apply admin-defined prompt logic.

def load_admin_prompts(rag_agent_id=None):
    with sqlite3.connect(DB_NAME) as conn:
        print(f"I am in load_admin_prompts+{rag_agent_id}")
        #rag_agent_id = 3
        if rag_agent_id:
            cur = conn.execute("""
                SELECT
                    sql_system_prompt, sql_task, sql_instruction,
                    synthesizer_system_prompt, synthesizer_task, synthesizer_instruction,
                    dashboard_summary_prompt,rag_agent_id
                FROM admin_prompts
                WHERE rag_agent_id = ?
                LIMIT 1
            """, (rag_agent_id,))
        else:
            cur = conn.execute("""
                SELECT
                    sql_system_prompt, sql_task, sql_instruction,
                    synthesizer_system_prompt, synthesizer_task, synthesizer_instruction,
                    dashboard_summary_prompt,rag_agent_id
                FROM admin_prompts
                WHERE id = 1
            """)
            print (f"Checking Now:+{cur}")

        row = cur.fetchone()
        if row:
            return {
                "sql_system_prompt": row[0],
                "sql_task": row[1],
                "sql_instruction": row[2],
                "synthesizer_system_prompt": row[3],
                "synthesizer_task": row[4],
                "synthesizer_instruction": row[5],
                "dashboard_summary_prompt": row[6],
                "rag_agent_id": row[7]
            }
        return None



# Creates a table to store chat history between the user and RAG agent, including queries, SQL, results, responses, and optional feedback.    
def create_chat_logs_table():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_query TEXT,
                generated_sql TEXT,
                query_result TEXT,
                rag_response TEXT,
                feedback TEXT  -- optional
            )
        """)

# Fetches the most recent chat interactions (user query + RAG response) from the chat_logs table, ordered by latest timestamp.
def get_recent_chat_history(limit=10):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.execute("""
            SELECT user_query, rag_response, timestamp
            FROM chat_logs
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        return list(reversed(cur.fetchall()))

def log_chat_interaction(user_query, sql, result, rag_response):
    """
    Stores a single user interaction (query, SQL, result, response) into the chat_logs table.
    """
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            INSERT INTO chat_logs (user_query, generated_sql, query_result, rag_response)
            VALUES (?, ?, ?, ?)
        """, (
            user_query,
            sql,
            #json.dumps(result),  # Store dict as JSON string
            json.dumps(result, default=str),  # ✅ Safe conversion

            rag_response
        ))

def get_metadata_column_names(csv_path="data/roche_metadata.csv") -> list:
    try:
        df = pd.read_csv(csv_path)
        return df["column_name"].dropna().tolist()
    except Exception as e:
        print(f"⚠️ Error reading metadata CSV: {e}")
        return []

# Creates a table to store each chart's configuration such as chart type, axes, aggregation, prompt, and SQL    
def create_chart_config_table():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chart_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chart_title TEXT,
                chart_type TEXT,
                metric TEXT,
                group_by TEXT,
                prompt_text TEXT,
                sql_query TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()

# Saves a single chart configuration (title, axes, chart type, etc.) to the chart_configs table
def save_chart_config_to_db(config):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            INSERT INTO chart_configs
            (chart_title, chart_type, metric, group_by, prompt_text, sql_query)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            config["chart_title"],
            config["chart_type"],
            config["metric"],
            config["group_by"],
            config["prompt_text"],
            config["sql_query"]
        ))

def get_all_chart_configs():
    """Fetch all saved chart configurations from the database."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row  # Access rows like dictionaries
        cur = conn.execute("""
            SELECT id, chart_title, chart_type, metric, group_by, prompt_text, sql_query
            FROM chart_configs
            ORDER BY created_at ASC
        """)
        rows = cur.fetchall()
        print("🧪 Chart Configs Fetched:", [dict(row) for row in rows])
        return [dict(row) for row in rows]

        # return [dict(row) for row in cur.fetchall()]

def save_or_update_chart_config(config):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        if config.get("config_id"):
            cur.execute("""
                UPDATE chart_configs
                SET chart_title = ?, chart_type = ?, metric = ?, group_by = ?, prompt_text = ?, sql_query = ?
                WHERE id = ?
            """, (
                config["chart_title"], config["chart_type"], config["metric"],
                config["group_by"], config["prompt_text"], config["sql_query"], config["config_id"]
            ))
            new_id = config["config_id"]
        else:
            cur.execute("""
                INSERT INTO chart_configs
                (chart_title, chart_type, metric, group_by, prompt_text, sql_query)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                config["chart_title"], config["chart_type"], config["metric"],
                config["group_by"], config["prompt_text"], config["sql_query"]
            ))
            new_id = cur.lastrowid
        conn.commit()
    return new_id

def delete_chart_config_by_id(config_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM chart_configs WHERE id = ?", (config_id,))
        conn.commit()

# Save query log
def save_query_log_to_db(timestamp, user_query, generated_sql, result_value):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO query_logs (timestamp, user_query, generated_sql, result_value)
        VALUES (?, ?, ?, ?)
    """, (timestamp, user_query, generated_sql, result_value))
    conn.commit()
    conn.close()

# Fetch query logs
def fetch_query_logs(limit=300):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, user_query, generated_sql, result_value
        FROM query_logs
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "timestamp": row[0],
            "user_query": row[1],
            "sql": row[2],
            "value": row[3]
        }
        for row in rows]
