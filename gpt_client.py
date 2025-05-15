import json
import os
import logging
from langchain_openai import AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

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
        return f"Error parsing JSON: {e}"


def create_invoke_chain(structure: str, context: str, **kwargs):
    try:
        prompt = ChatPromptTemplate.from_template(structure).partial(**kwargs)
        chain = prompt | json_llm | StrOutputParser()
        llm_output = chain.invoke({"context": context})
        parsed_output = parse_json(llm_output)
        return parsed_output
    except Exception as e:
        logging.error(f"Error creating invoke chain: {e}")
        return f"Error creating invoke chain: {e}"

def create_text_chain(structure: str, context: str, **kwargs):
    try:
        prompt = ChatPromptTemplate.from_template(structure).partial(**kwargs)
        chain = prompt | llm | StrOutputParser()
        return chain.invoke({"context": context})
    except Exception as e:
        logging.error(f"Error creating text invoke chain: {e}")
        return f"Error: {e}"

def generate_rag_response(result: dict, user_question: str):
    try:
        summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a pharma product complain analyst who explains structured JSON data in a friendly and natural tone.Your job is to analyze user quires and provide your response in concrete and concise manner. Answer the user's question precisely using only the data provided."),
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
        return f"Error generating summary: {e}"

def test_call():
    return create_invoke_chain("I am going to Paris, what should I see? Answer in json format", "")
