import os
import json
import yaml
import logging
import time 
import re
import requests

from dotenv import load_dotenv
from typing import Annotated, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain.tools.tavily_search import TavilySearchResults
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langchain_core.messages import HumanMessage
from langsmith import traceable
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from scan_url import VirusTotalChecker

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Setting up the embedding model details
model_name = "sentence-transformers/all-mpnet-base-v2"
model_kwargs = {'device': 'cpu'}
encode_kwargs = {'normalize_embeddings': True}
TABLE_NAME = "langchain_pg_embedding"
CONNECTION_STRING = os.getenv("PGVECTOR_CONN")

# Load prompts from YAML file
def load_prompts():
    try:
        with open('prompt.yaml', 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logger.error("prompt.yaml file not found")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        return {}

prompt_data = load_prompts()

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
    message_type : Literal["adviser", "conversation", "search", "crawl"] = Field(
        ...,
        description="Classify if the message requires an adviser or friendly."
    )

class State(TypedDict):
    messages: Annotated[list, add_messages]
    message_type: str | None

# Enhanced classification with fallback
def classify_message(state: State) -> dict:
    """Enhanced classification with keyword fallback for local models."""
    last_message = state["messages"][-1]
    user_message = last_message.content

    # Simplified prompt for local models
    
    message_classify = prompt_data.get("classify_prompt_2").format(user_message=user_message)

    messages = [
        {"role": "user", "content": message_classify}
    ]
    
    response = llm.invoke(messages)
    result = response.content.strip().lower()
    
    # Clean and validate response
    if result in ["adviser", "conversation", "search", "crawl"]:
        logger.info(f"LLM classification: {result}")
        return {"message_type": result}

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
    """Perform vector similarity search for skill-related queries."""
    try:
        logger.info(f"Processing skill query: {query}")
        retriever = get_retriever()
        results = retriever.invoke(query)
        
        if not results:
            logger.info("No results found for the query")
            return "No relevant information found for your query."

        # Process metadata incrementally
        combined_result = json.dumps([result.metadata for result in results], indent=2)
        logger.info(f"Found {len(results)} relevant results")
        return combined_result
        
    except Exception as e:
        logger.error(f"Error in vector lookup: {e}")
        return "Sorry, I encountered an error while searching for information."

def get_messages(state: State, prompt: str, data: list[dict[str, str]] = None):
    """Build message list for LLM with proper error handling."""
    try:
        history = [
            {"role": "user" if isinstance(msg, HumanMessage) else "assistant", "content": msg.content} 
            for msg in state["messages"]
        ]

        # Get system prompt with error handling
        system_prompt = prompt_data.get(prompt, "You are a helpful assistant.")
        
        if data is not None:
            try:
                system_prompt = system_prompt.format(data=data)
            except KeyError as e:
                logger.warning(f"Missing format key in prompt: {e}")
                # Fall back to appending data as context
                system_prompt = f"{system_prompt}\n\nContext data: {data}"
            
            return [{"role": "system", "content": system_prompt}] + history

        return [{"role": "system", "content": system_prompt}] + history
        
    except Exception as e:
        logger.error(f"Error building messages: {e}")
        # Fallback to basic message structure
        return [{"role": "system", "content": "You are a helpful assistant."}] + [
            {"role": "user", "content": state["messages"][-1].content}
        ]

@traceable(name="Adviser Agent")
def adviser_agent(state: State):
    """Handle skill and career-related queries with vector lookup."""
    try:
        last_message = state["messages"][-1]
        data = vector_lookup_function(last_message.content)
        messages = get_messages(state=state, prompt="skill_prompt", data=data)
        reply = llm.invoke(messages)
        return {"messages": [{"role": "assistant", "content": reply.content}]}
    except Exception as e:
        logger.error(f"Error in adviser_agent: {e}")
        return {"messages": [{"role": "assistant", "content": "I'm sorry, I encountered an error while processing your request. Please try again."}]}

@traceable(name="Conversation Agent")
def conversation_agent(state: State):
    """Handle general conversation and small talk."""
    try:
        messages = get_messages(state=state, prompt="small_talk_prompt", data=None)
        reply = llm.invoke(messages)
        return {"messages": [{"role": "assistant", "content": reply.content}]}
    except Exception as e:
        logger.error(f"Error in conversation_agent: {e}")
        return {"messages": [{"role": "assistant", "content": "I'm having trouble responding right now. How else can I help you?"}]}

def format_tavily_markdown(results: list[dict]) -> str:
    output = ["### 🔍 Top Search Results:\n"]
    for r in results:
        output.append(f"- [{r['title']}]({r['url']})\n  \n  {r['content'][:200]}...\n")
    return "\n".join(output)

def extract_article_data(articles):
    extracted_articles = []
    print(type(articles))
    article_container = articles[0].find('div', class_='post')
    if not article_container:
        return extracted_articles
    
    # Extract Title from the meta tag
    title_meta = article_container.find('meta', itemprop='headline')
    title = title_meta['content'] if title_meta and 'content' in title_meta.attrs else "Title not found"

    # Extract Author from the meta tag
    author_meta = article_container.find('div', itemprop='author')
    author_name_meta = author_meta.find('meta', itemprop='name') if author_meta else None
    author = author_name_meta['content'] if author_name_meta and 'content' in author_name_meta.attrs else "Unknown author"

    # Extract a summary from the first few paragraphs
    summary_paragraphs = article_container.find('div', id='articlebody').find_all('p')
    # Join the text of the first 3 paragraphs to create a summary
    summary = ' '.join([p.get_text(strip=True) for p in summary_paragraphs[:3]])
    
    # Extract Tags
    tags_container = article_container.find('div', class_='tags')
    tags = []
    if tags_container:
        tag_elements = tags_container.find_all('a', rel='tag')
        tags = [tag.get_text(strip=True) for tag in tag_elements]

    # Extract URL
    url_meta = article_container.find('link', itemprop='mainEntityOfPage url')
    url = url_meta['href'] if url_meta and 'href' in url_meta.attrs else "URL not found"

    # Create the dictionary for the LLM
    extracted_data = {
        "id": url, # Using URL as a unique ID
        "title": title,
        "summary_en": summary,
        "tags_en": tags,
        "by": author,
        "url": url
    }
    extracted_articles.append(extracted_data)
    
    return extracted_articles

@traceable(name="Conversation Agent")
def crawl_data_from_web(state: State):
    """Handle crawl data from website."""
    #try:
    last_message = state["messages"][-1]
    print(f"Last message content: {last_message.content}")
    webUrl = re.search(r"https?://[^\s '\"`]+", last_message.content).group(0)
    print(f"web url: {webUrl}")
    
    is_safe_link = VirusTotalChecker.is_url_safe(webUrl)
    if not is_safe_link:
        logger.error(f"Unsafe URL detected: {webUrl}")
        return {"messages": [{"role": "assistant", "content": "The provided URL is unsafe. Please provide a different URL."}]}
    
    response = requests.get(webUrl)
    print(response.status_code)

    if response.status_code != 200:
        logger.error(f"Failed to fetch web content from {webUrl}. Status code: {response.status_code}")
        return {"messages": [{"role": "assistant", "content": "I couldn't fetch the web content. Please check the URL and try again."}]}
    
    time.sleep(2)
    soup = BeautifulSoup(response.text, 'html.parser')
    articles = soup.find_all('div', class_='blog-posts')
    extracted_articles = extract_article_data(articles)
    print(extracted_articles)
    messages = get_messages(state=state, prompt="extract_data_1", data=extracted_articles)
    reply = llm.invoke(messages)

    return {"messages": [{"role": "assistant", "content": reply.content}]}
    # except Exception as e:
    #     logger.error(f"Error in crawl_agent: {e}")
    #     return {"messages": [{"role": "assistant", "content": "I'm having trouble responding right now. How else can I help you?"}]}

def format_tavily_markdown(results: list[dict]) -> str:
    output = ["###Top Search Results:\n"]
    for r in results:
        output.append(f"- [{r['title']}]({r['url']})\n  \n  {r['content'][:200]}...\n")
    return "\n".join(output)

@traceable(name="Search Agent")
def tavily_search(state: State):
    """Handle search queries using Tavily API."""
    try:
        query = state["messages"][-1].content
        logger.info(f"Performing search for: {query}")
        
        tavily_tool = TavilySearchResults()
        results = tavily_tool.invoke({"query": query})
        
        if not results:
            return {"messages": [{"role": "assistant", "content": "I couldn't find any relevant search results for your query."}]}
        
        logger.info(f"Search results: {results}")
        reply = format_tavily_markdown(results)  
        return {"messages": [{"role": "assistant", "content": reply}]}
        
    except Exception as e:
        logger.error(f"Error in tavily_search: {e}")
        return {"messages": [{"role": "assistant", "content": "I'm sorry, I couldn't perform the search at this time. Please try again later."}]}

graph_builder = StateGraph(State)
graph_builder.add_node("classifier", classify_message)  # Use enhanced classifier
graph_builder.add_node("router", router)
graph_builder.add_node("conversation", conversation_agent)
graph_builder.add_node("adviser", adviser_agent)
graph_builder.add_node("search", tavily_search)
graph_builder.add_node("crawl", crawl_data_from_web)

graph_builder.add_edge(START, "classifier")
graph_builder.add_edge("classifier", "router")
graph_builder.add_conditional_edges(
    "router",
    lambda state: state.get("next"),
    {"conversation": "conversation", "adviser": "adviser", "search": "search", "crawl": "crawl"}
)

graph_builder.add_edge("conversation", END)
graph_builder.add_edge("search", END)
graph_builder.add_edge("adviser", END)
graph_builder.add_edge("crawl", END)
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
    """Main chatbot interaction loop with improved error handling."""
    state = {"messages": [], "message_type": None}
    
    print("AI Learning Assistant started! Type 'exit' to quit.")
    print("=" * 50)

    while True:
        try:
            print("\nUser Message")
            user_input = input("You: ").strip()
            
            if user_input.lower() in ["exit", "quit", "bye"]:
                print("Goodbye! Have a great day!")
                break
            
            if not user_input:
                print("Please enter a message.")
                continue
            
            # Add the new user message to the current state's messages
            state["messages"] = add_messages(state["messages"], [{"role": "user", "content": user_input}])
            
            # Process through the graph
            try:
                state = graph.invoke(state)
                response = state["messages"][-1]
                
                print("\nAI Response")
                print(f"Assistant: {response.content}")
                
                # Add assistant message to the chat history
                state["messages"] = add_messages(state["messages"], [response])
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                print("Sorry, I encountered an error processing your message. Please try again.")
                
        except KeyboardInterrupt:
            print("\nGoodbye! Have a great day!")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            print("An unexpected error occurred. Please try again.")

if __name__ == "__main__":
    run_chatbot()