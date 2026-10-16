from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

load_dotenv()

gpt_llm = ChatGroq(
    model="openai/gpt-oss-20b",
    max_tokens=2048
)

qwen_llm = ChatOllama(
    model="qwen3:8b",
)

embedding_llm = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)