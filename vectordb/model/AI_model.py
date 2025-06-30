import os
from dotenv import load_dotenv
from langchain_openai.chat_models import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    model_name=os.getenv('AI_MODEL_PATH', 'gpt-4'),
    temperature=0.1,
    openai_api_base=os.getenv('AI_MODEL_API'),
    openai_api_key=os.getenv("API_KEY"),
    max_tokens=500,
    request_timeout=60,
    streaming=False
)