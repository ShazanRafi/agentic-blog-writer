from state import State
from langchain_core.messages import SystemMessage, HumanMessage
from schema import Plan, RouterDecision, EvidencePack, RetrievedDocumentIntegrity, Bookends
from langchain_community.tools.tavily_search import TavilySearchResults
from llm import gemini_llm
from typing import List
from langgraph.types import Send
from pathlib import Path
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from prompt import ROUTER_PROMPT, RESEARCH_PROMPT, ORCHESTRATOR_PROMPT, WORKER_PROMPT, DOCUMENT_INTEGRITY_PROMPT, DOCUMENT_SUMMARY_PROMPT, BOOKENDS_PROMPT, EDITOR_PROMPT


DOC_CHAR_LIMIT = 80_000
#*******************************************************helping functions*****************************************************
def text_of(msg) -> str:
    """Return plain text from a model reply, whether .content is a string or a list of blocks."""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)

def to_chunk_dicts(splitted_docs) -> List[dict]:
    """LangChain Documents -> plain dicts with a human-readable label (page number when known)."""
    chunks = []
    for i, d in enumerate(splitted_docs or []):
        page = (d.metadata or {}).get("page")
        label = f"p.{page + 1}" if isinstance(page, int) else f"chunk {i + 1}"
        text = d.page_content.strip()
        if text:
            chunks.append({"label": label, "text": text})
    return chunks

def retrieve(items: List[dict], query: str, k: int = 5) -> List[dict]:
    """Pick the k items whose "text" best matches the query (TF-IDF + cosine similarity),
    returned in their original order. Falls back to the first k items if nothing matches."""
    if not items:
        return []
    if not query.strip():
        return items[:k]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform([it["text"] for it in items])
        scores = cosine_similarity(vectorizer.transform([query]), matrix).ravel()
    except ValueError:  # empty vocabulary
        return items[:k]
    ranked = [i for i in scores.argsort()[::-1][:k] if scores[i] > 0]
    if not ranked:
        return items[:k]
    return [items[i] for i in sorted(ranked)]

def format_doc_excerpts(chunks: List[dict]) -> str:
    return "\n\n".join(f"[Document {c['label']}]\n{c['text']}" for c in chunks) or "None."


def evidence_as_items(evidence: List[dict]) -> List[dict]:
    return [{**e, "text": f"{e.get('title', '')} {e.get('snippet', '')}"} for e in evidence or []]


def format_evidence(items: List[dict]) -> str:
    lines = []
    for e in items:
        date = f" ({e['published_at']})" if e.get("published_at") else ""
        lines.append(f"- {e.get('title', '')}{date}\n  URL: {e.get('url', '')}\n  {e.get('snippet', '')}")
    return "\n".join(lines) or "None."

def bullets(items) -> str:
    return "\n".join(f"- {x}" for x in items) or "- None"

#*************************
def router(state: State) -> dict:

    topic = state['topic']
    document_summary = state.get("summary", "")
    reliability = state.get("reliability", "")
    usefulness = state.get("usefulness", False)

    decider = gemini_llm.with_structured_output(RouterDecision)
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

    extractor = gemini_llm.with_structured_output(EvidencePack)

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
    planner = gemini_llm.with_structured_output(Plan)
    prompt = [SystemMessage(
        content=(
                ORCHESTRATOR_PROMPT
            )
        ),
        HumanMessage(content=f"""
                            Topic: {state['topic']}
                            Research mode: {state.get('mode', 'closed_book')}
                            Research evidence: {format_evidence(state.get('evidence', []))}
                            Uploaded document summary: {state.get('summary', 'No document provided.')}
                            Extracted document information: {bullets(state.get('extracted_information', []))}
                            Document usefulness: {state.get('usefulness', False)}
                            Document reliability: {state.get('reliability', 'Not available')}
                    """)
        ]
    plan = planner.invoke(prompt)

    return {"plan": plan}

def fanout(state: State):
    doc_chunks = to_chunk_dicts(state.get("splitted_docs"))
    return [
        Send(
            "worker",
            {
                "task": task, 
                "topic": state["topic"], 
                "plan": state["plan"], 
                "evidence": state.get("evidence", []), 
                "usefulness": state.get("usefulness", False),
                "reliability": state.get("reliability", ""), 
                "document_summary": state.get("summary", 'No document provided'),
                "doc_chunks": doc_chunks
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

    query = " ".join([task.title, task.brief, task.goal, *task.bullets, *task.doc_points])

    doc_use = []
    if payload.get("usefulness"):
        doc_use = retrieve(payload.get("doc_chunks") or [], query, k=5)
    web_use = retrieve(evidence_as_items(payload.get("evidence", [])), query, k=4)

    outline = "\n".join(f"{t.id}. {t.title}: {t.goal}" for t in plan.tasks)

    prompt = [SystemMessage(
    content=(
        WORKER_PROMPT
    )
), 
    HumanMessage(
        content=(f"""
            Blog title: {plan.blog_title}
            Topic: {topic}
            Central thesis: {plan.thesis}
            Audience: {plan.audience}
            Tone: {plan.tone}
            Blog kind: {plan.blog_kind}
            Overall constraints: {"; ".join(plan.constraints) or "None"}

            FULL OUTLINE (other writers cover the other sections; do not repeat them):
            {outline}

            YOUR SECTION
            Title: {task.title}
            Brief: {task.brief}
            Goal: {task.goal}
            Bullets (cover all, in order):
            {bullets(task.bullets)}
            Target word count: {task.target_words}
            requires_code: {task.requires_code}
            requires_citations: {task.requires_citations}

            Document points:
            {bullets(task.doc_points)}

            Do NOT explain in detail (covered in other sections):
            {bullets(task.avoid)}

            DOCUMENT SUMMARY (reliability: {reliability or "n/a"}):
            {document_summary}

            DOCUMENT EXCERPTS MOST RELEVANT TO THIS SECTION:
            {format_doc_excerpts(doc_use)}

            WEB EVIDENCE MOST RELEVANT TO THIS SECTION:
            {format_evidence(web_use)}

            Return only the section content in Markdown.
            """
        )
    )
    ]

    section_md = text_of(gemini_llm.invoke(prompt)).strip()

    print("WORKER GENERATED:", repr(section_md[:100]))

    return {"section": [{"id": task.id, "title": task.title, "md": section_md, "context": doc_use}]}

def _write_bookends(plan, body: str):
    """Introduction and conclusion, written after the sections so they match them."""
    try:
        writer = gemini_llm.with_structured_output(Bookends)
        out = writer.invoke([
            SystemMessage(content=BOOKENDS_PROMPT),
            HumanMessage(content=f"""
Title: {plan.blog_title}
Thesis: {plan.thesis}
Audience: {plan.audience}
Tone: {plan.tone}

SECTIONS:
{body}
"""),
        ])
        return out.introduction.strip(), out.conclusion.strip()
    except Exception as exc:  
        print("Intro/conclusion step failed:", exc)
        return "", ""


def _edit(draft: str, plan, source_pack: List[dict], evidence: List[dict]) -> str:
    """Fact-check against the sources and polish. Falls back to the draft on any problem."""
    try:
        reply = text_of(gemini_llm.invoke([
            SystemMessage(content=EDITOR_PROMPT),
            HumanMessage(content=f"""
            Blog thesis: {plan.thesis}

            DRAFT:
            {draft}

            SOURCE MATERIAL: uploaded document excerpts
            {format_doc_excerpts(source_pack)}

            SOURCE MATERIAL: web evidence
            {format_evidence(evidence)}
            """),
        ])).strip()

        fenced = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", reply, re.DOTALL)
        if fenced:
            reply = fenced.group(1).strip()
        if reply.startswith("# "):  # editor repeated the title
            reply = reply.split("\n", 1)[1].lstrip() if "\n" in reply else ""

        if len(reply) < 0.6 * len(draft):
            print("Editor output looked truncated; keeping the unedited draft.")
            return draft
        return reply
    except Exception as exc:
        print("Editor step failed:", exc)
        return draft


def _sources_block(text: str, evidence: List[dict]) -> str:
    """Only list web sources that the blog actually links to."""
    used = [e for e in evidence if e.get("url") and e["url"] in text]
    if not used:
        return ""
    lines = [f"- [{e.get('title') or e['url']}]({e['url']})" for e in used]
    return "\n## Sources\n\n" + "\n".join(lines) + "\n"
    
def reducer(state: State) -> dict:
    plan = state['plan']
    title = plan.blog_title
    evidence = state.get("evidence", [])
    sections = sorted(state['section'], key=lambda s: s['id'])
    body = "\n\n".join(s['md'] for s in sections).strip()

    seen, source_pack = set(), []
    for s in sections:
        for c in s.get("context", []):
            if c["text"] not in seen:
                seen.add(c["text"])
                source_pack.append(c)

    intro, conclusion = _write_bookends(plan, body)
    parts = [p for p in [intro, body, f"## Conclusion\n\n{conclusion}" if conclusion else ""] if p]
    draft = "\n\n".join(parts)

    edited = _edit(draft, plan, source_pack, evidence)

    final_md = f"# {title}\n\n{edited}\n{_sources_block(edited, evidence)}"

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
    extractor = gemini_llm.with_structured_output(RetrievedDocumentIntegrity)

    pages = []
    for i, d in enumerate(state['docs']):
        page = (d.metadata or {}).get("page")
        label = f"[p.{page + 1}]" if isinstance(page, int) else f"[part {i + 1}]"
        pages.append(f"{label}\n{d.page_content.strip()}")
    doc_text = "\n\n".join(pages)[:DOC_CHAR_LIMIT]

    document_integrity_prompt = [
        SystemMessage(content=DOCUMENT_INTEGRITY_PROMPT),
        HumanMessage(
            content=f"""
                User's research topic: {topic}
                Document content:{doc_text}
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

    summary = text_of(gemini_llm.invoke(summarization_prompt))

    return {
        'usefulness': result.usefulness,
        'reliability': result.reliability,
        'extracted_information': result.extracted_information,
        'summary': summary
    }


def route_to_rag(state: RAGState):
    return "rag" if state.get('file_name') else "router"


