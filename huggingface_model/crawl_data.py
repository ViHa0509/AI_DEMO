from flask import Flask, jsonify
from bs4 import BeautifulSoup
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import HumanMessage
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from hashlib import md5
import time
import dotenv
import json
import os
import requests

dotenv.load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# AI Configuration
llm = ChatOpenAI(
    model_name=os.getenv('AI_MODEL_PATH', 'gpt-4'),
    temperature=0.1,
    openai_api_base=os.getenv('AI_MODEL_API'),
    openai_api_key=os.getenv("API_KEY"),
    max_tokens=500,
    request_timeout=60,
    streaming=False
)

prompt = """
Extract structured information from the following HTML source and return it as a JSON object in the format below:

{
  "id": [Unique numeric ID if available; otherwise, generate a hash from the URL or title],
  "title": "[Original English title]",
  "title_vi": "[Title translated to fluent Vietnamese]",
  "summary_en": "[English summary or content if available]",
  "summary_vi": "[Vietnamese translation of the summary]",
  "tags_en": ["tag1", "tag2", "tag3"],
  "tags_vi": ["Translated tag1", "Translated tag2", "Translated tag3"],
  "by": "[Author's name]",
  "score": [Numeric score if available; otherwise, default to 100],
  "url": "[Original source URL]"
}

Instructions:
- Translate `title` and `summary_en` to fluent, formal Vietnamese suitable for news. Avoid literal translation.
- If tags are present in the HTML (e.g., in meta tags, labels, or categories), extract them to `tags_en` and translate them to `tags_vi`.
- Clean all text of HTML tags and whitespace.
- Use intelligent defaults when data is missing.
- Return **only** a valid JSON object. Do **not** include explanations, comments, or formatting like markdown.

HTML source content:
%s
"""


def crawl_articles():
    url = 'https://thehackernews.com/2025/06/botnet-wazuh-server-vulnerability.html'
    article_id = md5(url.encode()).hexdigest()
    options = Options()
    options.headless = False
    #options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = soup.find_all('div', class_='blog-posts')
        prompt_text  = prompt % str(articles)
        response = llm([HumanMessage(content=prompt_text)])
        llm_output = response.content if hasattr(response, 'content') else str(response)
        return llm_output
    finally:
        driver.quit()

@app.route("/crawl", methods=["GET"])
def crawl_endpoint():
    try:
        articles = crawl_articles()
        return articles
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
