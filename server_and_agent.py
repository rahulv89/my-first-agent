from langchain_groq import ChatGroq

from langchain_core.prompts import ChatPromptTemplate
from langchain.prompts import PromptTemplate

from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers import JsonOutputParser

from newspaper import Article

from dotenv import load_dotenv
import os
import requests

load_dotenv()
GROQ_API_KEY=os.getenv("GROQ_API_KEY")
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY")

llm = ChatGroq(
    model="llama3-8b-8192",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    api_key=GROQ_API_KEY,
)

email_prompt=PromptTemplate(
    template="""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
    You are a seasoned marketer who is an expert at writing a marketing email tailored to a specific brand name, product name and product description.
    <|eot_id|><|start_header_id|>user<|end_header_id|>
    Your brand name is {brand_name}, and the name of this specific product is {product_name}
    Write me a great marketing email in less than 200 words, about the {product_name} is described at {product_description}. \n

    Do not add any preamble or explanations
    <|eot_id|>
    <|start_header_id|>assistant<|end_header_id|>
    """,
    input_variables=["brand_name", "product_name", "product_description"],
)

email_creator_chain = email_prompt | llm | StrOutputParser()

extractor_prompt=PromptTemplate(
    template="""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
    You are an expert at inferring brand keywords from a website.
    <|eot_id|><|start_header_id|>user<|end_header_id|>
    The website title is at {website_title} and website content is at {website_content}. \n
    Return a JSON with a single key 'keywords' with no more than 3 keywords and no premable or explaination. \n
    <|eot_id|>
    <|start_header_id|>assistant<|end_header_id|>
    """,
    input_variables=["website_title", "website_content"],
)

extractor_chain = extractor_prompt | llm | JsonOutputParser()


def is_URL_malicious_suspicious(brand_url):
  url = "https://www.virustotal.com/api/v3/urls"
  payload = { "url": brand_url }
  headers = {
      "accept": "application/json",
      "content-type": "application/x-www-form-urlencoded",
      "x-apikey": VIRUSTOTAL_API_KEY
  }
  response = requests.post(url, data=payload, headers=headers)
  response_json = response.json()
  analysis_url = "https://www.virustotal.com/api/v3/analyses/"+str(response_json["data"]["id"])
  headers_analysis_call = {
    "accept": "application/json",
    "x-apikey": VIRUSTOTAL_API_KEY
  }
  response_analysis = requests.get(analysis_url, headers=headers_analysis_call)
  response_analysis_json = response_analysis.json()
  num_malicious_detections = response_analysis_json["data"]["attributes"]["stats"]["malicious"]
  num_suspicious_detections = response_analysis_json["data"]["attributes"]["stats"]["suspicious"]
  return sum([num_malicious_detections, num_suspicious_detections])    


from typing import TypedDict, List
from langgraph.graph import StateGraph, START, END

class GraphState(TypedDict):
    brand_name: str
    product_name: str
    product_description: str
    brand_url: str
    article_title: str
    article_text: str
    email: str
    num_steps: int

def entry_node(state):
  brand_url = state["brand_url"]
  if is_URL_malicious_suspicious(brand_url) > 0:
    state["brand_url"] = ""
  num_steps = int(state['num_steps'])
  num_steps += 1
  return state

def router(state):
  num_steps = int(state['num_steps'])
  num_steps += 1
  brand_url = state["brand_url"]
  if len(brand_url) > 3:
    article = Article(brand_url)
    article.download()
    article.parse()
    article_title = article.title
    article_text = article.text
    state['article_title'] = article_title
    state['article_text'] = article_text
    return "route_to_keyword_extractor"
  else:
    return "route_to_email_creation"

def extract_keyword(state):
  num_steps = int(state['num_steps'])
  num_steps += 1
  brand_url = state["brand_url"]
  article = Article(brand_url)
  article.download()
  article.parse()
  article_title = article.title
  article_text = article.text

  keywords = extractor_chain.invoke({
    "website_title": article_title,
    "website_content": article_text,
  })
  state["product_description"] = ' '.join(keywords['keywords']) + " " + state["product_description"]
  return state

def create_email(state):
    brand_name = state["brand_name"]
    product_name = state["product_name"]
    product_description = state["product_description"]
    email = email_creator_chain.invoke({
        "brand_name": brand_name,
        "product_name": product_name,
        "product_description": product_description,
    })
    state["email"] = email
    num_steps = int(state['num_steps'])
    num_steps += 1
    return {"email":email, "num_steps":num_steps}


workflow = StateGraph(GraphState)

workflow.add_node("email_creator_node", create_email)
workflow.add_node("entry_node",entry_node)
workflow.add_node("keyword_extractor_node", extract_keyword)

workflow.set_entry_point("entry_node")

workflow.add_conditional_edges(
    "entry_node",
    router,
    {
        "route_to_keyword_extractor": "keyword_extractor_node",
        "route_to_email_creation": "email_creator_node",
    }
)

workflow.add_edge("keyword_extractor_node","email_creator_node")

workflow.add_edge("email_creator_node", END)

graph = workflow.compile()

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from langserve import add_routes
import pydantic
import pydantic.dataclasses
from pydantic.dataclasses import dataclass

app = FastAPI(
    title="Email Generator Agent",
    version="1.0",
    description="Generate marketing emails based on your product description"
)

@app.get("/")
async def redirect_root_to_docs():
  return RedirectResponse("/docs")

# @dataclass
# class Input:
# 	input: dict

# @dataclass
# class Output:
#     ouptut: dict


add_routes(
    app,
    graph,
    path="/generatemail",
)

if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app,host="localhost", port=8000)