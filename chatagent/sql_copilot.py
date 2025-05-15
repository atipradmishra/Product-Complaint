from gpt_client import create_invoke_chain
from chatagent.chat_prompt import system_prompt  

# Build the full template dynamically
sql_prompt_template = """{system_prompt}

User question:
{context}

Return a JSON object like:
{{ "sql": "<sqlite query>" }}
"""

sql_kwargs = {
    "system_prompt": system_prompt
}

def get_sql_from_question(question_text: str):
    return create_invoke_chain(sql_prompt_template, question_text, **sql_kwargs)
