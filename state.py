from typing import TypedDict, Annotated, List
from schema import Plan, Task, EvidenceItem
from langchain_core.documents import Document
import operator

class State(TypedDict):
    topic: str
    needs_research: bool
    mode: str
    queries: List[str]
    evidence: List[EvidenceItem]
    task: List[Task]
    plan: Plan
    section: Annotated[List[str], operator.add]
    final: str

class RAGState(TypedDict):
    topic:str
    file_name: str
    docs: List[Document]
    splitted_docs: List[Document]
    embedded_chunk: List[Document]
    usefulness: bool
    reliability: str
    extracted_information: List[str]
    summary: str