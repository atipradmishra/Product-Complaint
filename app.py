from flask import Flask, render_template, jsonify, request, flash, redirect, url_for
from gpt_client import create_invoke_chain, llm, generate_rag_response
from chatagent.chat_prompt import system_prompt, sql_kwargs
from chatagent.sql_copilot import get_sql_from_question
from sql_query_executor import run_sql
import pandas as pd
from sql_query_executor import run_sql
from db_manager import create_users_table, register_user, authenticate_user
from dataagent.s3_database_upload import upload_s3_database_update
import json
import os
from config import DB_NAME,BUCKET_NAME, aws_access_key, aws_secret_key
import pandas as pd
import boto3
import os
import uuid
import sqlite3
from werkzeug.utils import secure_filename
from datetime import datetime



app = Flask(__name__)
app.secret_key = "dev_zQ0xyfjkundFVF9GiR0PnT8DbTVczXd3yumese3RGlKax6OIOBWku4giwUL45LKIPhnCaxSfNNyuMUU5CgZnrplmlaHBvQAAFx0"

create_users_table()

s3 = boto3.client(
            "s3",
            #aws_access_key_id=aws_access_key,
            aws_access_key_id= os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY'),
            #aws_secret_access_key=aws_secret_key,
            aws_session_token= os.getenv('AWS_SESSION_TOKEN'),
            region_name='us-east-1'
        )


@app.context_processor
def inject_now():
    return {'now': lambda: datetime.now().strftime('%I:%M %p')}

def get_complaints_data():
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT title as product_name FROM raw_data
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df[:10]

@app.route("/")
def dashboard():
    df = get_complaints_data()
    complaint_counts = df['product_name'].value_counts()
    labels = complaint_counts.index.tolist()
    values = complaint_counts.values.tolist()
    with open("data/dummy_data.json") as f:
        data = json.load(f)
    return render_template("dashboard.html", data=data, labels=labels, values=values)

@app.route("/rag-configure")
def rag_configure():
    return render_template("rag_configure.html")

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

@app.route("/copilot-query", methods=["POST"])
def copilot_query():
    data = request.get_json()
    user_query = data.get("message", "")
    print(f"📝 User query received: {user_query}")

    # Step 1: Call the LLM via helper
    generated = get_sql_from_question(user_query)
    print(f"🤖 Raw response from LLM: {generated}")

    # Step 2: Extract SQL
    if isinstance(generated, dict) and "sql" in generated:
        sql = generated["sql"]
        print(f"✅ SQL extracted: {sql}")

        # Step 3: Run query
        #result = run_sql(sql, category="product")
        result = run_sql(sql)

        print(f"📊 Query result: {result}")

        # Step 4: Generate response
        rag_response = generate_rag_response(result, user_query)
        print(f"🤖 RAG response: {rag_response}")

    else:
        sql = ""
        error_msg = generated if isinstance(generated, str) else "No SQL generated"
        result = {"error": error_msg}
        print(f"❌ SQL generation failed: {error_msg}")

    return jsonify({"response": rag_response})

@app.route("/chat-with-rag")
def chat_with_rag():
    return render_template("chat_window.html")

@app.route('/copilot-feedback', methods=['POST'])
def copilot_feedback():
    data = request.json
    feedback_type = data.get('feedback')  # 'up' or 'down'
    response_text = data.get('response')  # The bot response
    # Store it in DB, log it, or process it as needed
    print(f"Feedback received: {feedback_type} for response: {response_text}")
    return {"status": "success"}

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
