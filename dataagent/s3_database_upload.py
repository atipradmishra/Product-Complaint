# s3_database_upload.py
import os
import uuid
import sqlite3
from flask import redirect, flash
from config import DB_NAME


def upload_s3_database_update(s3, bucket, folder, filename, data_path, data_df):
    try:
        s3_key = f"{folder}/{uuid.uuid4()}_{filename}"
        s3.upload_file(data_path, bucket, s3_key)
        print(f"✅ Uploaded to S3: s3://{bucket}/{s3_key}")

        with sqlite3.connect(DB_NAME) as conn:
        #    conn.execute("""
        #            INSERT INTO data_files_metadata (file_name, s3_path, is_processed, created_at)
        #            VALUES (?, ?, ?)
        #        """, (filename, s3_key, 0))


            data_df.to_sql('raw_data', conn, if_exists='append', index=False)
            #data_df.to_sql('product_complaint_tbl', conn, if_exists='append', index=False)


        flash('✅ File validated, uploaded, and saved to DB!')
    except Exception as e:
        print(f"❌ Upload/DB error: {e}")
        flash(f"Error during upload/DB write: {e}")
    finally:
        if os.path.exists(data_path):
            os.remove(data_path)

    return redirect('/data-management')
