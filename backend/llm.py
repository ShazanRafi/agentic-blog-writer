import os
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()

gpt_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    max_tokens=2000
)

qwen_llm = ChatOllama(
    model="qwen3:8b",
)

 
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
gemini_llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    max_retries=6,
)