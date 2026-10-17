from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from dotenv import load_dotenv

load_dotenv()

gpt_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    max_tokens=3000
)

qwen_llm = ChatOllama(
    model="qwen3:8b",
)

