"""Command-line chat with the AI Learning Assistant.

    python main.py           # interactive chat in the terminal
    python main.py --graph   # also export the workflow diagram to graph.png
    python -m app.server     # web UI on http://localhost:8000
"""
import argparse
import logging
import uuid

from app.graph import graph

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EXIT_COMMANDS = {"exit", "quit", "bye"}


def export_graph(path: str = "graph.png") -> None:
    try:
        with open(path, "wb") as f:
            f.write(graph.get_graph().draw_mermaid_png())
        print(f"Workflow diagram saved to {path}")
    except Exception as e:
        logger.warning("Could not render graph diagram: %s", e)


def run_chatbot() -> None:
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    print("AI Learning Assistant started! Type 'exit' to quit.")
    print("=" * 50)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! Have a great day!")
            break

        if user_input.lower() in EXIT_COMMANDS:
            print("Goodbye! Have a great day!")
            break
        if not user_input:
            continue

        try:
            state = graph.invoke({"messages": [{"role": "user", "content": user_input}]}, config)
            print(f"\nAssistant [{state['message_type']}]: {state['messages'][-1].content}")
            for source in state.get("sources", []):
                print(f"  - {source['title']}: {source['url']}")
        except Exception as e:
            logger.error("Error processing message: %s", e)
            print("Sorry, I encountered an error processing your message. Please try again.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graph", action="store_true", help="export the workflow diagram to graph.png")
    args = parser.parse_args()
    if args.graph:
        export_graph()
    run_chatbot()
