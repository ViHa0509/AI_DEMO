from dotenv import load_dotenv
from typing import Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain.tools.tavily_search import TavilySearchResults
from sentence_transformers import SentenceTransformer

from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langchain_core.messages import HumanMessage, AIMessage
import os
import json
import yaml
import logging
from langsmith import traceable

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Setting up the embedding model details
model_name = "sentence-transformers/all-mpnet-base-v2"
model_kwargs = {'device': 'cpu'}
encode_kwargs = {'normalize_embeddings': True}
TABLE_NAME = "langchain_pg_embedding"
CONNECTION_STRING = os.getenv("PGVECTOR_CONN")

with open('prompt.yaml', 'r') as file:
    global prompt_data
    prompt_data = yaml.safe_load(file)

llm = ChatOpenAI(
    model_name=os.getenv('AI_MODEL_PATH', 'gpt-4'),
    temperature=0.3,
    openai_api_base=os.getenv('AI_MODEL_API'),
    openai_api_key=os.getenv("API_KEY"),
    max_tokens=500,
    request_timeout=60,
    streaming=False
)

class MessageClassifier(BaseModel):
    message_type : Literal["adviser", "conversation", "search"] = Field(
        ...,
        description="Classify if the message requires an adviser or friendly."
    )

class State(TypedDict):
    messages: Annotated[list, add_messages]
    message_type: str | None

def classify_message_with_structured_output(state: State):
    last_message = state["messages"][-1]
    classifier_llm = llm.with_structured_output(MessageClassifier)

    result = classifier_llm.invoke([
        {"role": "system", "content": prompt_data['classify_prompt']},
        {"role": "user", "content": last_message.content}
    ])
    return {"message_type": result.message_type}

# Classify message using prompt engineering
def classify_message(state: State) -> dict:
    last_message = state["messages"][-1]

    messages = [
        {"role": "system", "content": prompt_data['classify_prompt']},
        {"role": "assistant", "content": """Respond ONLY with a JSON object. e.g {"message_type": "adviser" or "conversation" or "search"}.Do not include Markdown, code blocks, or extra text"""},
        {"role": "user", "content": last_message.content}
    ]
    response = llm.invoke(messages)
    try:
        if "```" in response.content:
            content = response.content.strip().replace("```", "").replace("json", "")
            return json.loads(content)
    except Exception as e:
        logging.error(f"Error parsing JSON response: {e}")
        
    return {"message_type": "unknown"}

def router(state: State):
    message_type = state.get("message_type", "conversation")
    return {"next": message_type}

def get_retriever():
    embedder = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs=model_kwargs,
        encode_kwargs=encode_kwargs
    )

    # === Vectorstore Setup ===
    vectorstore = PGVector(
        collection_name=TABLE_NAME,
        connection_string=CONNECTION_STRING,
        embedding_function=embedder
    )

    # === Retriever ===
    return vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 5, "score_threshold": 0.85}
    )

# === Define Tools ===
def vector_lookup_function(query: str) -> str:
    logger.info(f"Processing skill query: {query}")
    retriever = get_retriever()
    results = retriever.invoke(query)
    if not results:
        return None

    # Process metadata incrementally
    combined_result = json.dumps([result.metadata for result in results], indent=2)
    return combined_result

def get_messages(state: State, prompt: str, data: list[dict[str, str]] = None):
    history = [
        {"role": "user" if isinstance(msg, HumanMessage) else "assistant", "content": msg.content} 
        for msg in state["messages"]
    ]

    # Prepend system message if needed
    system_prompt = prompt_data[prompt]
    if data is not None:
        system_prompt = system_prompt.format(data=data)
        return [{"role": "user", "content": system_prompt}] + history

    return [{"role": "system", "content": system_prompt}] + history

@traceable(name="LLM Answer Node")
def adviser_agent(state: State):
    last_message = state["messages"][-1]
    data = vector_lookup_function(last_message.content)
    messages = get_messages(state=state, prompt="skill_prompt", data=data)
    reply = llm.invoke(messages)
    return {"messages": [{"role": "assistant", "content": reply.content}]}

@traceable(name="LLM Answer Node")
def conversation_agent(state: State):
    messages = get_messages(state=state, prompt="small_talk_prompt", data=None)
    reply = llm.invoke(messages)
    return {"messages": [{"role": "assistant", "content": reply.content}]}

def format_tavily_markdown(results: list[dict]) -> str:
    output = ["### 🔍 Top Search Results:\n"]
    for r in results:
        output.append(f"- [{r['title']}]({r['url']})\n  \n  {r['content'][:200]}...\n")
    return "\n".join(output)

@traceable(name="LLM Answer Node")
def tavily_search(state: State):
    #messages = get_messages(state=state, prompt="tavily_search", data=None)
    query = state["messages"][-1].content
    tavily_tool = TavilySearchResults()
    results = tavily_tool.invoke({"query":query})
    print(results)
    reply = format_tavily_markdown(results)  
    return {"messages": [{"role": "assistant", "content": reply}]}

graph_builder = StateGraph(State)
graph_builder.add_node("classifier", classify_message)
graph_builder.add_node("router", router)
graph_builder.add_node("conversation", conversation_agent)
graph_builder.add_node("adviser", adviser_agent)
graph_builder.add_node("search", tavily_search)

graph_builder.add_edge(START, "classifier")
graph_builder.add_edge("classifier", "router")
graph_builder.add_conditional_edges(
    "router",
    lambda state: state.get("next"),
    {"conversation": "conversation", "adviser": "adviser", "search": "search"}
)

graph_builder.add_edge("conversation", END)
graph_builder.add_edge("search", END)
graph_builder.add_edge("adviser", END)
graph = graph_builder.compile()
is_display = True

if is_display:
    from IPython.display import Image, display
    try:
        with open("graph.png", "wb") as f:
            f.write(graph.get_graph().draw_mermaid_png())
    except Exception:
        # This requires some extra dependencies and is optional
        logging.info(f"Failed to display graph.")
        pass

def run_chatbot():
    state = {"messages": [], "message_type": None}
    config = {}

    while True:
        print("============ User Message ============")
        user_input = input("Message: ")
        if user_input == "exit":
            print("Bye")
            break
        
        # Add the new user message to the current state's messages
        state["messages"] = add_messages(state["messages"],[{"role":"user", "content": user_input}])
        
        # Stream the graph and keep updating the state
        state = graph.invoke(state)

        response = state["messages"][-1]
        print("============ AI Message ============")
        print(response.content)

        # Add assistant message to the chat history
        state["messages"] = add_messages(state["messages"], [response])

if __name__ == "__main__":
    run_chatbot()