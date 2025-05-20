import json
import logging
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from gpt_client import llm
from decimal import Decimal


def clean_result_data(result):
    def normalize(value):
        if isinstance(value, str):
            value = value.replace(',', '').replace('−', '-')  # normalize Unicode minus and remove commas
            try:
                return float(value)
            except ValueError:
                return value
        elif isinstance(value, Decimal):
            return float(value)
        return value

    cleaned_rows = []
    for row in result.get("rows", []):
        cleaned_row = {k: normalize(v) for k, v in row.items()}
        cleaned_rows.append(cleaned_row)

    return {
        "columns": result.get("columns", []),
        "rows": cleaned_rows
    }

def qualify_table_names(sql: str, conn_details: dict) -> str:
    """
    Ensures fully-qualified table names in the SQL string for Snowflake.
    """
    if conn_details.get("source", "").lower() == "snowflake":
        db = conn_details.get("sf_database")
        schema = conn_details.get("schema")
        if db and schema:
            import re
            pattern = re.compile(r'\bFROM\s+(?!\b' + db + '\.' + schema + '\.)([a-zA-Z_][\w]*)', re.IGNORECASE)
            sql = pattern.sub(rf"FROM {db}.{schema}.\\1", sql)

            pattern_join = re.compile(r'\bJOIN\s+(?!\b' + db + '\.' + schema + '\.)([a-zA-Z_][\w]*)', re.IGNORECASE)
            sql = pattern_join.sub(rf"JOIN {db}.{schema}.\\1", sql)

    return sql

def generate_rag_response_BKP(result: dict, user_question: str) -> str:
    try:
        result = clean_result_data(result)

        summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a pharma product complain analyst who explains structured JSON data in a friendly and natural tone. Your job is to analyze user queries and provide your response in a concrete and concise manner. Answer the user's question precisely using only the data provided."),
            ("user", "User asked: {question}\n\nHere is the structured data returned:\n{json_data}\n\nWrite a natural language summary of this.")
        ])

        chain = summary_prompt | llm | StrOutputParser()

        response = chain.invoke({
            "question": user_question,
            "json_data": json.dumps(result, indent=2)
        })

        return response

    except Exception as e:
        logging.error(f"Error generating human-readable summary: {e}")
        return f"⚠️ Error generating summary."

def generate_rag_response_BKP2(data: dict, user_question: str) -> str:
    try:
        charts = data.get("charts", [])
        prompt = data.get("prompt", "")

        if not charts or not prompt:
            return "⚠️ Missing charts or prompt data for summary generation."

        summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a pharma product complaint analyst. Analyze the following dashboard charts and generate a clear, leadership-ready summary that includes trends, patterns, outliers, and business insights."),
            ("user", "{prompt}\n\nHere is the structured chart data:\n{json_data}\n\nSummarize this dashboard.")
        ])

        chain = summary_prompt | llm | StrOutputParser()

        response = chain.invoke({
            "prompt": prompt,
            "json_data": json.dumps(charts, indent=2)
        })

        return response

    except Exception as e:
        logging.error(f"Error generating human-readable summary: {e}")
        return "⚠️ Error generating summary."

def generate_rag_response_BKP23(result: dict, user_question: str) -> str:
    try:
        result = clean_result_data(result)

        summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a pharma product complaint analyst who explains structured JSON data in a friendly and natural tone. Your job is to analyze user queries and provide your response in a concrete and concise manner. Answer the user's question precisely using only the data provided."),
            ("user", "User asked: {question}\n\nHere is the structured data returned:\n{json_data}\n\nWrite a natural language summary of this.")
        ])

        chain = summary_prompt | llm | StrOutputParser()

        response = chain.invoke({
            "question": user_question,
            "json_data": json.dumps(result, indent=2)
        })

        return response

    except Exception as e:
        logging.error(f"Error generating human-readable summary: {e}")
        return f"⚠ Error generating summary."
        

def generate_rag_response(result_or_payload: dict, user_question: str = None) -> str:
    try:
        # Dashboard charts summary path
        if "charts" in result_or_payload and "prompt" in result_or_payload:
            charts = result_or_payload.get("charts", [])
            prompt = result_or_payload.get("prompt", "")

            summary_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a pharma product complaint analyst. Analyze the following dashboard charts and generate a clear, leadership-ready summary that includes trends, patterns, outliers, and business insights."),
                ("user", "{prompt}\n\nHere is the structured chart data:\n{json_data}\n\nSummarize this dashboard.")
            ])

            chain = summary_prompt | llm | StrOutputParser()
            response = chain.invoke({
                "prompt": prompt,
                "json_data": json.dumps(charts, indent=2)
            })
            return response

        # Raw SQL result path
        elif user_question:
            result = clean_result_data(result_or_payload)

            summary_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a pharma product complaint analyst who explains structured JSON data in a friendly and natural tone. Your job is to analyze user queries and provide your response in a concrete and concise manner. Answer the user's question precisely using only the data provided."),
                ("user", "User asked: {question}\n\nHere is the structured data returned:\n{json_data}\n\nWrite a natural language summary of this.")
            ])

            chain = summary_prompt | llm | StrOutputParser()

            response = chain.invoke({
                "question": user_question,
                "json_data": json.dumps(result, indent=2)
            })

            return response

        else:
            return "⚠️ Insufficient data provided for summary."

    except Exception as e:
        logging.error(f"Error generating summary: {e}")
        return "⚠️ Error generating summary."
