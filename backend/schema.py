from pydantic import BaseModel, Field
from typing import List, Annotated, Literal, Optional

class Task(BaseModel):
    id: int
    title: str
    brief: str = Field(..., description="What to cover")
    goal: str = Field(..., description="One sentence describing what the reader should do/understand.")
    bullets: List[str] = Field(..., min_length=3, max_length=6, description="3–6 concrete, non-overlapping subpoints to cover in this section.",)
    target_words: int = Field(..., description="Target words count (120–300).")
    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False 

class Plan(BaseModel):
    blog_title: str = Field(..., description="title of the blog")
    audience: str = Field(description="The intended readers of the content, including their knowledge level and background.")
    tone: str = Field (description = "The writing style and mood of the content, such as formal, conversational, professional, friendly, or persuasive.")
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task] = Field(default_factory=list,min_length=3,max_length=5, description="Specific requirements or restrictions the content must follow, such as word limits, topics to avoid, formatting rules, or sources to use.")

class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None
    snippet: Optional[str] = None
    source: Optional[str] = None

class EvidencePack(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal['closed_booke', 'hybrid', 'open_book']
    queries: List[str] = Field(default_factory= list)

class RetrievedDocumentIntegrity(BaseModel):

    usefulness: bool = Field(
        description="""Whether the document contains meaningful information relevant to the user's topic and useful for generating an informative, evidence-based blog. Return False if the document is irrelevant, mostly empty, spam, or lacks substantive information."""
    )

    reliability: Literal["Correct", "Ambiguous", "Incorrect"] = Field(
        description="""Assess the document's factual reliability based on available evidence. Correct: the claims assessed are largely supported by credible evidence. Ambiguous: evidence is insufficient, claims are unclear, or the document contains conflicting information. Incorrect: substantial claims are contradicted by credible evidence. Do not assume that an unverified claim is automatically incorrect. If external verification is unavailable, acknowledge this uncertainty."""
    )

    extracted_information: List[str] = Field(
        description="""Extract all significant information useful for generating a high-quality blog about the user's topic. Include: (1) key findings and main arguments, (2) specific facts and supporting evidence, (3) numerical statistics, percentages, measurements, and their context, (4) conclusions and insights presented by the author, (5) important examples, case studies, and comparisons, (6) limitations, assumptions, contradictions, and caveats, and (7) relevant dates, named entities, and definitions. Preserve exact numerical values and their units. Distinguish the author's claims from independently verified facts. Retain page numbers or source references when available. Avoid generic summaries, repetition, unsupported inferences, and information irrelevant to the user's topic. Do not invent details missing from the document."""
    )