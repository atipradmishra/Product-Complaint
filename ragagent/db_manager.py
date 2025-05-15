import sqlite3
import hashlib
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
