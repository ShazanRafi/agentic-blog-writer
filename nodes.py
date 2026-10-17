from state import State
from langchain_core.messages import SystemMessage, HumanMessage
from schema import Plan, RouterDecision, EvidencePack, RetrievedDocumentIntegrity
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_chroma import Chroma
from llm import gpt_llm, qwen_llm
from typing import List
from langgraph.types import Send
from pathlib import Path
import re
from prompt import ROUTER_PROMPT, RESEARCH_PROMPT, ORCHESTRATOR_PROMPT, WORKER_PROMPT, DOCUMENT_INTEGRITY_PROMPT, DOCUMENT_SUMMARY_PROMPT

def router(state: State) -> dict:

    topic = state['topic']
    document_summary = state.get("summary", "")
    reliability = state.get("reliability", "")
    usefulness = state.get("usefulness", False)

    decider = qwen_llm.with_structured_output(RouterDecision)
    prompt = [
        SystemMessage(
            content= ROUTER_PROMPT
        ),
        HumanMessage(
            content=f"""
                Topic: {topic}
                User-provided document available: {bool(document_summary)}
                Document usefulness: {usefulness}
                Document reliability: {reliability}
                Document summary: {document_summary or "No document provided."}
                Decide the appropriate research mode.
            """
        )
    ]
    decision = decider.invoke(prompt)
    return{
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "queries": decision.queries
    }

def route_next(state: State) -> str:
    return "research" if state["needs_research"] else "orchestrator"

def _tavily_search(query:str, max_results: int = 5) -> List[dict]:
    tool = TavilySearchResults(max_results=max_results)
    results = tool.invoke({'query': query})

    normalized: List[dict] = []
    for r in results or []:
        normalized.append(
            {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "snippet": r.get("content") or r.get("snippet") or "",
                "published_at": r.get("published_date") or r.get("published_at"),
                "source": r.get("source")
            }
        )
    return normalized

def research(state: State) -> dict:

    queries = (state.get('queries') or [])
    max_results = 5
    raw_results: List[dict] = []

    for q in queries:
        raw_results.extend(_tavily_search(q, max_results=max_results))

    if not raw_results:
        return {"evidence": []}

    extractor = qwen_llm.with_structured_output(EvidencePack)

    prompt = [
        SystemMessage(
            content= RESEARCH_PROMPT
        ),
        HumanMessage(
            content=f"""
                    raw_results:\n{raw_results}
                    Topic: {state['topic']}
                    Research mode: {state['mode']}
                    Queries: {queries}
            """
        )
    ]

    pack = extractor.invoke(prompt)

    dedup = {}
    for e in pack.evidence:
        if e.url:
            dedup[e.url] = e.model_dump()

    return {'evidence': list(dedup.values())}


def orchestrator(state: State) -> dict:
    planner = qwen_llm.with_structured_output(Plan)
    prompt = [SystemMessage(
        content=(
                ORCHESTRATOR_PROMPT
            )
        ),
        HumanMessage(content=f"""
                            Topic: {state['topic']}
                            Research evidence: {state.get('evidence', [])}
                            Uploaded document summary: {state.get('summary', 'No document provided.')}
                            Document usefulness: {state.get('usefulness', False)}
                            Document reliability: {state.get('reliability', 'Not available')}
                    """)
        ]
    plan = planner.invoke(prompt)

    return {"plan": plan}

def fanout(state: State):
    return [
        Send(
            "worker",
            {
                "task": task, 
                "topic": state["topic"], 
                "plan": state["plan"], 
                "evidence": state.get("evidence", []), 
                "reliability": state.get("reliability", ""), 
                "document_summary": state.get("summary", 'No document provided')
            },
        )
        for task in state["plan"].tasks
    ]

def worker(payload: dict) -> dict:
    task = payload["task"]
    topic = payload['topic']
    plan = payload['plan']
    evidence = payload.get("evidence", [])
    reliability = payload.get("reliability")
    document_summary = payload.get("document_summary")


    blog_title = plan.blog_title

    prompt = [SystemMessage(
    content=(
        WORKER_PROMPT
    )
), 
    HumanMessage(
        content=(f"""
            Blog: {blog_title}\n
            Topic: {topic}\n\n
            Section: {task.title}\n
            Brief: {task.brief}\n\n
            Research evidence: {evidence}\n\n
            reliability: {reliability}\n\n
            document_summary: {document_summary}\n\n

            Return only the section content in Markdown.
            """
        )
    )
    ]

    section_md = gpt_llm.invoke(prompt).content.strip()
    print("WORKER GENERATED:", repr(section_md[:100]))
    return {"section": [section_md]}

    
def reducer(state: State) -> dict:
    title = state['plan'].blog_title
    body = "\n\n".join(state['section']).strip()

    final_md = f"# {title}\n\n{body}\n"

    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
    safe_title = safe_title.strip().rstrip('.')

    filename = safe_title.lower().replace(" ", "_") + ".md"
    output_path = Path(filename)
    output_path.write_text(final_md, encoding="utf-8")

    return {"final": final_md}


#**********************************************************RAG-SUBGRAPH******************************************************

from state import RAGState
from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

def loader(state: RAGState)->dict:

    filename = state['file_name']

    extension = Path(filename).suffix.lower()

    if(extension == '.pdf'):
        loader = PyPDFLoader(filename)
    elif(extension == ".docx"):
        loader = Docx2txtLoader(filename)
    elif (extension == ".txt"):
        loader = TextLoader(filename, encoding='utf-8')
    else:
        raise ValueError("Unsupported file format")

    docs = loader.load()

    return {'docs': docs}


def docs_splitter(state: RAGState)-> dict:

    docs = state['docs']

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )

    chunks = text_splitter.split_documents(docs)

    return {'splitted_docs': chunks}

def map(state:RAGState)-> dict:
    topic = state['topic']
    splitted_docs = state['splitted_docs']
    extractor = qwen_llm.with_structured_output(RetrievedDocumentIntegrity)

    document_integrity_prompt = [
        SystemMessage(content=DOCUMENT_INTEGRITY_PROMPT),
        HumanMessage(
            content=f"""
                User's research topic: {topic}
                Document content:{splitted_docs}
            """
        )
    ]

    result = extractor.invoke(document_integrity_prompt)

    summarization_prompt = [
        SystemMessage(
            content=DOCUMENT_SUMMARY_PROMPT
        ),
        HumanMessage(
            content=f"""
                    Research topic: {state["topic"]}
                    Document usefulness: {result.usefulness}
                    Document reliability: {result.reliability}
                    xtracted information:{result.extracted_information}
            """
        )
    ]

    summary = qwen_llm.invoke(summarization_prompt)

    return {
        'usefulness': result.usefulness,
        'reliability': result.reliability,
        'extracted_information': result.extracted_information,
        'summary': summary
    }


def route_to_rag(state: RAGState):
    return "rag" if state.get('file_name') else "router"


