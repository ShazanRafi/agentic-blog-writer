from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.types import Send
from dotenv import load_dotenv
from typing import TypedDict, Annotated, List
# import sqlite3
from schema import Plan, Task, EvidenceItem, EvidencePack, RouterDecision
import operator
from pathlib import Path
import re

load_dotenv()

llm = ChatGroq(
    model="openai/gpt-oss-20b"
)

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

def router(state: State) -> dict:

    topic = state['topic']
    decider = llm.with_structured_output(RouterDecision)
    prompt = [
        SystemMessage(
            content= """You are a routing module for a technical blog planner.

Decide whether web research is needed BEFORE planning.

Modes:
- closed_book (needs_research=false):
  Evergreen topics where correctness does not depend on recent facts (concepts, fundamentals).
- hybrid (needs_research=true):
  Mostly evergreen but needs up-to-date examples/tools/models to be useful.
- open_book (needs_research=true):
  Mostly volatile: weekly roundups, "this week", "latest", rankings, pricing, policy/regulation.

If needs_research=true:
- Output 3–10 high-signal queries.
- Queries should be scoped and specific (avoid generic queries like just "AI" or "LLM").
- If user asked for "last week/this week/latest", reflect that constraint IN THE QUERIES.
"""
        ),
        HumanMessage(
            content=f"Topic: {topic}"
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
    max_results = 6
    raw_results: List[dict] = []

    for q in queries:
        raw_results.extend(_tavily_search(q, max_results=max_results))

    if not raw_results:
        return {"evidence": []}

    extractor = llm.with_structured_output(EvidencePack)
    prompt = [
        SystemMessage(
            content= """You are a research synthesizer for technical writing.

Given raw web search results, produce a deduplicated list of EvidenceItem objects.

Rules:
- Only include items with a non-empty url.
- Prefer relevant + authoritative sources (company blogs, docs, reputable outlets).
- If a published date is explicitly present in the result payload, keep it as YYYY-MM-DD.
  If missing or unclear, set published_at=null. Do NOT guess.
- Keep snippets short.
- Deduplicate by URL.
"""
        ),
        HumanMessage(
            content=f"raw_results:\n{raw_results}"
        )
    ]

    pack = extractor.invoke(prompt)

    dedup = {}
    for e in pack.evidence:
        if e.url:
            dedup[e.url] = e

    return {'evidence': list(dedup.values())}


def orchestrator(state: State) -> dict:
    planner = llm.with_structured_output(Plan)
    prompt = [SystemMessage(
        content=(
                """You are a senior technical writer and developer advocate.
Your job is to produce a highly actionable outline for a technical blog post.

Hard requirements:
- Create 3-5 sections (tasks) suitable for the topic and audience.
- Each task must include:
  1) goal (1 sentence)
  2) 3–6 bullets that are concrete, specific, and non-overlapping
  3) target word count (120–300)
  4) "Every task must contain a 'brief' field describing what that section should cover."

Quality bar:
- Assume the reader is a developer; use correct terminology.
- Bullets must be actionable: build/compare/measure/verify/debug.
- Ensure the overall plan includes at least 2 of these somewhere:
  * minimal code sketch / MWE (set requires_code=True for that section)
  * edge cases / failure modes
  * performance/cost considerations
  * security/privacy considerations (if relevant)
  * debugging/observability tips

Grounding rules:
- Mode closed_book: keep it evergreen; do not depend on evidence.
- Mode hybrid:
  - Use evidence for up-to-date examples (models/tools/releases) in bullets.
  - Mark sections using fresh info as requires_research=True and requires_citations=True.
- Mode open_book:
  - Set blog_kind = "news_roundup".
  - Every section is about summarizing events + implications.
  - DO NOT include tutorial/how-to sections unless user explicitly asked for that.
  - If evidence is empty or insufficient, create a plan that transparently says "insufficient sources"
    and includes only what can be supported.

Output must strictly match the Plan schema.
"""
            )
        ),
        HumanMessage(content=f"Topic: {state['topic']}")
        ]
    plan = planner.invoke(prompt)

    return {"plan": plan}

def fanout(state: State):
    return [
        Send(
            "worker",
            {"task": task, "topic": state["topic"], "plan": state["plan"]},
        )
        for task in state["plan"].tasks
    ]

def worker(payload: dict) -> dict:
    task = payload["task"]
    topic = payload['topic']
    plan = payload['plan']
    blog_title = plan.blog_title

    prompt = [SystemMessage(
    content=(
        "You are a senior technical writer and developer advocate. Write ONE section of a technical blog post in Markdown.\n\n"
        "Hard constraints:\n"
        "- Follow the provided Goal and cover ALL Bullets in order (do not skip or merge bullets).\n"
        "- Stay close to the Target words (±15%).\n"
        "- Output ONLY the section content in Markdown (no blog title H1, no extra commentary).\n\n"
        "Technical quality bar:\n"
        "- Be precise and implementation-oriented (developers should be able to apply it).\n"
        "- Prefer concrete details over abstractions: APIs, data structures, protocols, and exact terms.\n"
        "- When relevant, include at least one of:\n"
        "  * a small code snippet (minimal, correct, and idiomatic)\n"
        "  * a tiny example input/output\n"
        "  * a checklist of steps\n"
        "  * a diagram described in text (e.g., 'Flow: A -> B -> C')\n"
        "- Explain trade-offs briefly (performance, cost, complexity, reliability).\n"
        "- Call out edge cases / failure modes and what to do about them.\n"
        "- If you mention a best practice, add the 'why' in one sentence.\n\n"
        "Markdown style:\n"
        "- Start with a '## <Section Title>' heading.\n"
        "- Use short paragraphs, bullet lists where helpful, and code fences for code.\n"
        "- Avoid fluff. Avoid marketing language.\n"
        "- If you include code, keep it focused on the bullet being addressed.\n"
    )
), 
    HumanMessage(
        content=(
            f"Blog: {blog_title}\n"
            f"Topic: {topic}\n\n"
            f"Section: {task.title}\n"
            f"Brief: {task.brief}\n\n"
            "Return only the section content in Markdown."
        )
    )
    ]

    
    
    section_md = llm.invoke(prompt).content.strip()

    print("WORKER GENERATED:", repr(section_md[:100]))

    return {"section": [section_md]}

def reducer(state: dict) -> dict:
    title = state['plan'].blog_title
    body = "\n\n".join(state['section']).strip()

    final_md = f"# {title}\n\n{body}\n"

    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
    safe_title = safe_title.strip().rstrip('.')

    filename = safe_title.lower().replace(" ", "_") + ".md"
    output_path = Path(filename)
    output_path.write_text(final_md, encoding="utf-8")

    return {"final": final_md}


graph = StateGraph(State)

graph.add_node("router", router)
graph.add_node("research", research)
graph.add_node('orchestrator', orchestrator)
graph.add_node('worker', worker)
graph.add_node('reducer', reducer, defer=True)

graph.add_edge(START, 'router')
graph.add_conditional_edges(
    'router', route_next, {
        'research': 'research',
        "orchestrator": "orchestrator"
    }
)
graph.add_edge("research", "orchestrator")
graph.add_conditional_edges("orchestrator", fanout, ["worker"])
graph.add_edge("worker", "reducer")
graph.add_edge("reducer", END)

app = graph.compile()


print(app.invoke({"topic": "future of neural networks"}))

