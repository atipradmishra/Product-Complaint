import json
import os
import logging

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')

llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.5
)
# Bind for structured JSON output
json_llm = llm.bind(response_format={"type": "json_object"})

def parse_json(json_string):
    try:
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON: {e}")
        return {"error": str(e)}

def create_invoke_chain(prompt_template, input_variables):
    try:
        # Support both raw strings and ChatPromptTemplate objects
        if isinstance(prompt_template, str):
            prompt_template = ChatPromptTemplate.from_template(prompt_template)

        chain = prompt_template | json_llm | StrOutputParser()
        response = chain.invoke(input_variables)
        return parse_json(response)
    except Exception as e:
        logging.error(f"Error creating invoke chain: {e}")
        return {"error": str(e)}

def create_text_chain(structure: str, context: str, **kwargs):
    try:
        prompt = ChatPromptTemplate.from_template(structure).partial(**kwargs)
        chain = prompt | llm | StrOutputParser()
        return chain.invoke({"context": context})
    except Exception as e:
        logging.error(f"Error creating text invoke chain: {e}")
        return f"Error: {e}"

def test_call():
    # Simple test with plain text
    return create_text_chain("Tell me about {context}", context="Paris")

def suggest_follow_up_questions(user_question, rag_response):
    prompt = f"""
        The user asked: "{user_question}"
        The assistant replied: "{rag_response}"

        Now suggest 3 concise follow-up questions the user might ask next. Avoid repeating the same question.
        Just return the questions as a plain list.
        """
    try:
        response = llm.invoke(prompt)
        raw_output = response.content.strip().split("\n")
        return [q.lstrip("-•0123456789. ").strip() for q in raw_output if q.strip()]
    except Exception as e:
        logging.error(f"Failed to generate follow-ups: {e}")
        return []

