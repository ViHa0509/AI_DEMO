from typing import Optional
import asyncio
import sys
from pydantic import BaseModel, Field
from flask import Flask, request, jsonify, session, render_template
import uuid
from huggingface_hub import hf_hub_download
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage
from langchain_community.chat_models.llamacpp import ChatLlamaCpp

app = Flask(__name__)
app.secret_key = "your_secret_key" 

# Download model file
model_path = hf_hub_download(
    repo_id="unsloth/Phi-4-mini-instruct-GGUF",
    filename="Phi-4-mini-instruct-Q4_K_M.gguf"
)

llm = ChatLlamaCpp(
    model_path=model_path,
    temperature=0.1,
    max_tokens=512,
    top_p=0.95,
    n_ctx=2048,
    streaming=True,
    n_gpu_layers=-1,
    verbose=False,
)


class InMemoryHistory(BaseChatMessageHistory, BaseModel):
    """In memory implementation of chat message history."""

    messages: list[BaseMessage] = Field(default_factory=list)

    def add_messages(self, messages: list[BaseMessage]) -> None:
        """Add a list of messages to the store"""
        self.messages.extend(messages)

    def clear(self) -> None:
        self.messages = []

# Here we use a global variable to store the chat message history.
# This will make it easier to inspect it to see the underlying results.
store = {}

def get_by_session_id(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = InMemoryHistory()
    return store[session_id]


prompt = ChatPromptTemplate.from_messages([
    ("system", "You're a helpful assistant"),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])

chain = prompt | llm
chain_with_history = RunnableWithMessageHistory(
    chain,
    # Uses the get_by_session_id function defined in the example
    # above.
    get_by_session_id,
    input_messages_key="question",
    history_messages_key="history",
)

# Step 6: Flask routes
@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("input")
    session_id = session.get("id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["id"] = session_id

    # result = chain_with_history.invoke(
    #     {"input": user_input},
    #     config={"configurable": {"session_id": session_id}}
    # )

    result = chain_with_history.invoke(
        {"ability": "math", "question": user_input}, 
        config={"configurable": {"session_id": session_id}}
    )
    
    return jsonify({"response": result.content})

@app.route("/reset", methods=["POST"])
def reset():
    session_id = session.get("id")
    if session_id in store:
        store[session_id].clear()
    return jsonify({"message": "Chat history reset."})

@app.route("/")
def index():
    return render_template("index.html")


# Step 7: Run the app
if __name__ == "__main__":
    print("Current working directory:", )
    app.run(debug=True, use_reloader=False)