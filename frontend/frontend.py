import html
import os
import queue
import re
import tempfile
import threading
import time

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from backend import app  

st.set_page_config(page_title="Blog Agent", page_icon="✍️", layout="wide")

# ------------------------------------------------------------------ styling
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap');

:root {
    --ink: #1B2140;
    --paper: #EEF0F8;
    --sheet: #FFFFFF;
    --marker: #FFD84D;
    --blue: #3D4FD6;
    --muted: #6B7194;
    --line: #D9DDEE;
}

/* base ------------------------------------------------------------- */
.stApp { background: var(--paper); }
html, body, .stApp, [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {
    font-family: 'Bricolage Grotesque', system-ui, sans-serif;
    color: var(--ink);
}
.stApp button, .stApp input, .stApp textarea { font-family: 'Bricolage Grotesque', system-ui, sans-serif; }
h1, h2, h3 { font-family: 'Bricolage Grotesque', system-ui, sans-serif; letter-spacing: -0.02em; color: var(--ink); }
.stApp a { color: var(--blue); }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2.5rem; max-width: 980px; }

/* hero ------------------------------------------------------------- */
.hero h1 { font-size: 3rem; font-weight: 800; margin: 0 0 .25rem 0; padding: 0; }
.hero p { color: var(--muted); font-size: 1.1rem; margin: 0 0 1.5rem 0; max-width: 34rem; }

/* inputs ----------------------------------------------------------- */
[data-baseweb="input"], [data-baseweb="base-input"] { background: var(--sheet) !important; border-radius: 8px; }
.stTextInput input {
    background: var(--sheet) !important; color: var(--ink) !important;
    border: 1.5px solid var(--line); border-radius: 8px;
    padding: .8rem 1rem; font-size: 1.05rem;
}
.stTextInput input::placeholder { color: var(--muted); opacity: 1; }
.stTextInput input:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(61,79,214,.15); }
label, [data-testid="stWidgetLabel"] p { font-weight: 600; color: var(--ink); }
[data-testid="stTooltipIcon"] svg { color: var(--muted); }

/* file uploader ---------------------------------------------------- */
[data-testid="stFileUploaderDropzone"] {
    background: var(--sheet); border: 1.5px dashed var(--line); border-radius: 8px;
}
[data-testid="stFileUploader"] * { color: var(--ink); }
[data-testid="stFileUploaderDropzoneInstructions"] * { color: var(--muted); }

/* tooltips (rendered outside .stApp, so no .stApp prefix) ----------- */
[data-baseweb="tooltip"], [data-baseweb="tooltip"] > div,
[data-baseweb="popover"] > div, [data-testid="stTooltipContent"] {
    background: var(--ink) !important; color: #fff !important; border-radius: 8px;
}
[data-baseweb="tooltip"] *, [data-testid="stTooltipContent"] * { color: #fff !important; }

/* buttons ---------------------------------------------------------- */
/* labels live in a <p> inside the button; make them follow the button's color */
.stApp button p, .stApp button span, .stApp button [data-testid="stMarkdownContainer"] {
    color: inherit !important;
}
/* secondary: light face, dark text */
button[kind="secondary"], [data-testid="stBaseButton-secondary"] {
    background: var(--sheet) !important; color: var(--ink) !important;
    border: 1.5px solid var(--line) !important; border-radius: 8px; font-weight: 600;
}
button[kind="secondary"]:hover, [data-testid="stBaseButton-secondary"]:hover {
    background: var(--paper) !important; color: var(--ink) !important; border-color: var(--blue) !important;
}
/* primary: dark face, light text; marker yellow on hover */
button[kind="primary"], [data-testid="stBaseButton-primary"] {
    background: var(--ink) !important; color: #fff !important; border: none !important;
    border-radius: 8px; padding: .55rem 1.4rem; font-weight: 600;
    transition: background .15s, color .15s;
}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
    background: var(--marker) !important; color: var(--ink) !important;
}
button[kind="primary"]:disabled, [data-testid="stBaseButton-primary"]:disabled {
    background: var(--line) !important; color: var(--muted) !important;
}

/* sidebar ---------------------------------------------------------- */
[data-testid="stSidebar"] { background: var(--ink); }
[data-testid="stSidebar"] * { color: #E4E7F7; }
[data-testid="stSidebar"] h1 { font-size: 1.5rem; font-weight: 800; color: #fff; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    font-size: .95rem; font-weight: 600; color: #9AA1D0; margin-top: 1.5rem;
}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: #9AA1D0; }
[data-testid="stSidebar"] button {
    width: 100%; justify-content: flex-start; text-align: left;
    background: rgba(255,255,255,.08) !important; color: #E4E7F7 !important;
    border: none !important; border-radius: 8px;
}
[data-testid="stSidebar"] button:hover { background: rgba(255,255,255,.18) !important; color: #fff !important; }
[data-testid="stSidebar"] button:disabled { opacity: .45; }
[data-testid="stSidebar"] button p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* pipeline stepper (the one loud element) --------------------------- */
.pipe { display: flex; align-items: center; flex-wrap: wrap; gap: .35rem; margin: 1rem 0 .5rem 0; }
.step {
    display: flex; align-items: center; gap: .5rem;
    padding: .4rem .75rem; border-radius: 6px;
    font-weight: 600; font-size: .95rem; color: var(--muted);
}
.step .dot { width: .6rem; height: .6rem; border-radius: 50%; border: 2px solid var(--line); }
.step.done { color: var(--blue); }
.step.done .dot { background: var(--blue); border-color: var(--blue); }
.step.active { background: var(--marker); color: var(--ink); }
.step.active .dot { background: var(--ink); border-color: var(--ink); }
.step.skipped { text-decoration: line-through; opacity: .55; }
.step .sub { font-weight: 400; font-size: .85rem; opacity: .8; }
.pipe .link { width: 1.2rem; height: 2px; background: var(--line); }

/* result chips ----------------------------------------------------- */
.chips { display: flex; flex-wrap: wrap; gap: .5rem; margin: 0 0 1.25rem 0; }
.chip {
    background: var(--sheet); border: 1px solid var(--line); border-radius: 999px;
    padding: .25rem .8rem; font-size: .85rem; color: var(--muted);
}
.chip b { color: var(--ink); margin-left: .25rem; }

/* tabs ------------------------------------------------------------- */
.stTabs [data-baseweb="tab-list"] { gap: 1.25rem; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding-left: 0; padding-right: 0; background: transparent; }
.stTabs [data-baseweb="tab"] p { color: var(--muted); }
.stTabs [aria-selected="true"] p { color: var(--ink); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--marker); height: 4px; }

/* the reading sheet (needs Streamlit >= 1.39 for st.container(key=...)) */
.st-key-sheet {
    background: var(--sheet); border-radius: 8px; border: 1px solid var(--line);
    padding: 2.5rem 3rem; margin-top: 1rem;
}
.st-key-sheet h1 { font-size: 2.2rem; font-weight: 800; line-height: 1.15; margin-bottom: 1.2rem; }
.st-key-sheet h2 { font-size: 1.5rem; font-weight: 600; margin-top: 2rem; }
.st-key-sheet p, .st-key-sheet li {
    font-family: 'Source Serif 4', Georgia, serif; font-size: 1.1rem; line-height: 1.75;
    max-width: 42rem; color: var(--ink);
}
.st-key-sheet code { background: var(--paper); color: var(--ink); border-radius: 4px; padding: .1rem .35rem; }

/* expanders, alerts, captions -------------------------------------- */
[data-testid="stExpander"] { background: var(--sheet); border: 1px solid var(--line); border-radius: 8px; }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary { background: transparent; }
[data-testid="stExpander"] * { color: var(--ink); }
[data-testid="stExpander"] a { color: var(--blue); }
[data-testid="stAlert"] * { color: var(--ink) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: var(--muted); }
.source-title { font-weight: 600; }

@media (max-width: 640px) {
    .hero h1 { font-size: 2.2rem; }
    .st-key-sheet { padding: 1.5rem 1.25rem; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ------------------------------------------------------------------ constants
STEPS = [
    ("rag", "Document"),
    ("router", "Strategy"),
    ("research", "Research"),
    ("orchestrator", "Outline"),
    ("worker", "Writing"),
    ("reducer", "Assemble"),
]
ALLOWED_TYPES = ["pdf", "docx", "txt"]


# ------------------------------------------------------------------ utilities
def save_upload(uploaded_file) -> str:
    """The backend loader needs a file path, so write the upload to a temp file."""
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


def safe_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title).strip().rstrip(".")
    return (cleaned.lower().replace(" ", "_") or "blog") + ".md"


# def to_text(value) -> str:
#     """LangChain messages carry text in .content; plain strings pass through."""
#     return str(getattr(value, "content", value) or "")

def to_text(value) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content or "")


def normalize_section(item, position: int) -> dict:
    """Workers return a dict (id, title, md); older runs return a bare string."""
    if isinstance(item, dict):
        return {
            "id": item.get("id", position),
            "title": item.get("title", ""),
            "md": item.get("md", ""),
        }
    return {"id": position, "title": "", "md": str(item)}


def stepper_html(states: dict, details: dict) -> str:
    parts = []
    for i, (key, label) in enumerate(STEPS):
        sub = details.get(key)
        sub_html = f'<span class="sub">{html.escape(str(sub))}</span>' if sub else ""
        parts.append(
            f'<div class="step {states[key]}"><span class="dot"></span>'
            f"<span>{label}</span>{sub_html}</div>"
        )
        if i < len(STEPS) - 1:
            parts.append('<div class="link"></div>')
    return f'<div class="pipe">{"".join(parts)}</div>'


def chip(label, value):
    return f'<span class="chip">{label}<b>{html.escape(str(value))}</b></span>'


def chips_html(res: dict) -> str:
    chips = [
        chip("Mode", res.get("mode") or "n/a"),
        chip("Web research", "yes" if res.get("needs_research") else "no"),
        chip("Queries", len(res.get("queries") or [])),
        chip("Sources", len(res.get("evidence") or [])),
    ]
    if res.get("reliability"):
        chips.append(chip("Document", res["reliability"]))
    return f'<div class="chips">{"".join(chips)}</div>'


# ---- blocks shown both live (while generating) and in the result tabs ----
def show_document(res: dict):
    st.markdown(
        f"**Useful for this topic:** {'yes' if res.get('usefulness') else 'no'}  \n"
        f"**Reliability:** {res.get('reliability') or 'n/a'}"
    )
    summary = to_text(res.get("summary"))
    if summary:
        st.markdown("**Summary**")
        st.markdown(summary)
    info = res.get("extracted_information") or []
    if info:
        st.markdown("**Extracted information**")
        for line in info:
            st.markdown(f"- {line}")


def show_strategy(res: dict):
    st.markdown(
        f"**Mode:** {res.get('mode') or 'n/a'}  \n"
        f"**Research needed:** {'yes' if res.get('needs_research') else 'no'}"
    )
    queries = res.get("queries") or []
    if queries:
        st.markdown("**Search queries**")
        for q in queries:
            st.markdown(f"- {q}")
    else:
        st.caption("No search queries were needed.")


def show_sources(evidence: list):
    if not evidence:
        st.info("This blog didn’t use web sources.")
        return
    for e in evidence:
        url = html.escape(e.get("url") or "")
        title = html.escape(e.get("title") or e.get("url") or "Untitled")
        st.markdown(
            f'<div class="source-title"><a href="{url}" target="_blank">{title}</a></div>',
            unsafe_allow_html=True,
        )
        meta = " · ".join(x for x in [e.get("source"), e.get("published_at")] if x)
        if meta:
            st.caption(meta)
        if e.get("snippet"):
            st.caption(e["snippet"])


def show_plan(plan):
    thesis = getattr(plan, "thesis", "")
    if thesis:
        st.markdown(f"**Thesis:** {thesis}")
    st.markdown(
        f"**Audience:** {plan.audience}  \n**Tone:** {plan.tone}  \n**Type:** {plan.blog_kind}"
    )
    if plan.constraints:
        st.markdown("**Constraints**")
        for c in plan.constraints:
            st.markdown(f"- {c}")
    for task in plan.tasks:
        with st.expander(f"{task.id}. {task.title} · about {task.target_words} words"):
            st.markdown(f"**Goal:** {task.goal}")
            st.markdown(f"**Brief:** {task.brief}")
            for b in task.bullets:
                st.markdown(f"- {b}")
            doc_points = getattr(task, "doc_points", [])
            if doc_points:
                st.markdown("**Uses from your document**")
                for d in doc_points:
                    st.markdown(f"- {d}")


# ------------------------------------------------------------------ background job
class Job:
    """Runs the agent in a background thread so the page can stay responsive
    (and so the Cancel button can stop listening at any moment).

    The thread never touches Streamlit. It only pushes graph updates into a
    queue; the page drains the queue and does all the drawing.
    """

    def __init__(self, topic: str, file_path: str):
        self.topic = topic
        self.file_path = file_path
        self.queue: "queue.Queue" = queue.Queue()
        self.cancel_event = threading.Event()
        self.started = time.time()
        self.finished = False
        self.error = None

        self.result: dict = {"section": []}
        self.feed: list = []  # (kind, label, expanded, payload)
        self.states = {k: "pending" for k, _ in STEPS}
        self.details: dict = {}
        self.sections_done = 0
        if not file_path:
            self.states["rag"] = "skipped"
        self._activate_next()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # -- thread side --------------------------------------------------
    def _run(self):
        stream = None
        try:
            stream = app.stream(
                {"topic": self.topic, "file_name": self.file_path},
                stream_mode="updates",
            )
            for chunk in stream:
                if self.cancel_event.is_set():
                    break
                self.queue.put(("update", chunk))
        except Exception as exc:  # surfaced on the page
            self.queue.put(("error", str(exc)))
        finally:
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
            if self.file_path and os.path.exists(self.file_path):
                try:
                    os.remove(self.file_path)
                except OSError:
                    pass
            self.queue.put(("done", None))

    def cancel(self):
        self.cancel_event.set()

    # -- page side ----------------------------------------------------
    def _activate_next(self):
        if "active" not in self.states.values():
            for k, _ in STEPS:
                if self.states[k] == "pending":
                    self.states[k] = "active"
                    break

    def _finish(self, node: str):
        self.states[node] = "done"
        self._activate_next()

    def drain(self) -> bool:
        """Pull everything the thread has produced. Returns True if anything changed."""
        changed = False
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            changed = True
            if kind == "update":
                for node, update in payload.items():
                    if update:
                        self._apply(node, update)
            elif kind == "error":
                self.error = payload
            elif kind == "done":
                self.finished = True
        return changed

    def _apply(self, node: str, update: dict):
        res = self.result

        if node == "worker":
            for item in update.get("section", []):
                self.sections_done += 1
                sec = normalize_section(item, self.sections_done)
                res["section"].append(sec)
                label = f"Section {sec['id']}" + (f": {sec['title']}" if sec["title"] else "")
                self.feed.append(("section", label, False, sec))
            total = len(res["plan"].tasks) if res.get("plan") else "?"
            self.details["worker"] = f"{self.sections_done}/{total}"
            if total == "?" or self.sections_done >= total:
                self._finish("worker")
            return

        res.update(update)

        if node == "rag":
            self.feed.append(("rag", "Document check", False, dict(res)))
        elif node == "router":
            if not res.get("needs_research"):
                self.states["research"] = "skipped"
            self.details["router"] = res.get("mode")
            self.feed.append(("router", f"Strategy · {res.get('mode')}", True, dict(res)))
        elif node == "research":
            n = len(res.get("evidence") or [])
            self.details["research"] = f"{n} sources"
            self.feed.append(("research", f"Research · {n} sources", False, list(res.get("evidence") or [])))
        elif node == "orchestrator":
            plan = res["plan"]
            self.feed.append(("orchestrator", f"Outline · {plan.blog_title}", True, plan))

        self._finish(node)


def render_progress(job: Job):
    st.markdown(stepper_html(job.states, job.details), unsafe_allow_html=True)
    if job.feed:
        st.markdown("**What the agent is finding**")
    for kind, label, expanded, payload in job.feed:
        with st.expander(label, expanded=expanded):
            if kind == "rag":
                show_document(payload)
            elif kind == "router":
                show_strategy(payload)
            elif kind == "research":
                show_sources(payload)
            elif kind == "orchestrator":
                show_plan(payload)
            elif kind == "section":
                st.markdown(payload["md"])


def generating_view(job: Job):
    st.markdown(
        f'<div class="hero"><h1>Writing your blog</h1><p>{html.escape(job.topic)}</p></div>',
        unsafe_allow_html=True,
    )

    btn_col, timer_col = st.columns([1, 3], vertical_alignment="center")
    with btn_col:
        if st.button("Cancel generation"):
            job.cancel()
            st.session_state["job"] = None
            st.session_state["notice"] = "Generation cancelled. Nothing was saved."
            st.rerun()
    timer = timer_col.empty()

    box = st.empty()
    first = True
    while True:
        changed = job.drain()
        if changed or first:
            with box.container():
                render_progress(job)
            first = False
        if job.finished:
            break
        # this update also gives Streamlit a chance to interrupt the loop when Cancel is clicked
        timer.caption(f"Running for {int(time.time() - job.started)}s")
        time.sleep(0.4)

    st.session_state["job"] = None
    if job.error:
        st.session_state["error"] = job.error
    elif not job.cancel_event.is_set():
        st.session_state["history"].append(job.result)
        st.session_state["current"] = job.result
    st.rerun()


def render_result(res: dict):
    plan = res.get("plan")
    final = res.get("final", "")
    title = plan.blog_title if plan else "blog"

    if not final:
        st.warning("The agent finished but didn’t produce a blog. Try a more specific topic.")
        return

    st.markdown(chips_html(res), unsafe_allow_html=True)

    has_doc = bool(res.get("summary") or res.get("reliability"))
    names = ["Blog", "Markdown", "Outline", "Research"] + (["Document"] if has_doc else [])
    tabs = st.tabs(names)

    with tabs[0]:
        with st.container(key="sheet"):
            st.markdown(final)

    with tabs[1]:
        st.code(final, language="markdown")

    with tabs[2]:
        if plan:
            show_plan(plan)

    with tabs[3]:
        show_strategy(res)
        st.markdown("**Sources**")
        show_sources(res.get("evidence") or [])

    if has_doc:
        with tabs[4]:
            show_document(res)

    st.download_button(
        "Download .md",
        data=final,
        file_name=safe_filename(title),
        mime="text/markdown",
        type="primary",
    )


# ------------------------------------------------------------------ session state
st.session_state.setdefault("history", [])
st.session_state.setdefault("current", None)
st.session_state.setdefault("uploader_key", 0)
st.session_state.setdefault("job", None)
st.session_state.setdefault("last_topic", "")

busy = st.session_state["job"] is not None


# ------------------------------------------------------------------ sidebar
st.sidebar.title("Blog Agent")

if st.sidebar.button("New blog", disabled=busy):
    st.session_state["current"] = None
    st.session_state["uploader_key"] += 1  # clears the file uploader
    st.rerun()

st.sidebar.header("Past blogs")

if not st.session_state["history"]:
    st.sidebar.caption("Blogs you write in this session appear here.")

for idx in range(len(st.session_state["history"]) - 1, -1, -1):
    item = st.session_state["history"][idx]
    label = item["plan"].blog_title if item.get("plan") else f"Blog {idx + 1}"
    if st.sidebar.button(label, key=f"hist_{idx}", disabled=busy):
        st.session_state["current"] = item
        st.rerun()


# ------------------------------------------------------------------ main page
if st.session_state["job"] is not None:
    generating_view(st.session_state["job"])

elif st.session_state["current"] is None:
    st.markdown(
        '<div class="hero"><h1>Blog Agent</h1>'
        "<p>Give it a topic. Add a document if you have one, and the agent will "
        "check it, research the gaps, and write the blog.</p></div>",
        unsafe_allow_html=True,
    )

    notice = st.session_state.pop("notice", None)
    if notice:
        st.info(notice)
    error = st.session_state.pop("error", None)
    if error:
        st.error(f"The agent stopped with an error: {error}")

    topic = st.text_input(
        "Topic",
        value=st.session_state["last_topic"],
        placeholder="e.g. The future of neural networks",
    )
    uploaded = st.file_uploader(
        "Reference document (optional)",
        type=ALLOWED_TYPES,
        key=f"uploader_{st.session_state['uploader_key']}",
        help="PDF, DOCX or TXT. The agent rates how useful and reliable it is before using it.",
    )

    if st.button("Write blog", type="primary", disabled=not topic.strip()):
        file_path = save_upload(uploaded) if uploaded else ""
        st.session_state["last_topic"] = topic.strip()
        st.session_state["job"] = Job(topic.strip(), file_path)
        st.rerun()

else:
    render_result(st.session_state["current"])