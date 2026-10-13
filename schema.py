from pydantic import BaseModel, Field
from typing import TypedDict, List, Annotated, Literal, Optional

class Task(BaseModel):
    id: int
    title: str
    brief: str = Field(..., description="What to cover")
    goal: str = Field(..., description="One sentence describing what the reader should do/understand.")
    bullets: List[str] = Field(..., min_length=3, max_length=6, description="3–5 concrete, non-overlapping subpoints to cover in this section.",)
    target_words: int = Field(..., description="Target words count (120–550).")
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
    tasks: List[Task] = Field(default_factory=list, description="Specific requirements or restrictions the content must follow, such as word limits, topics to avoid, formatting rules, or sources to use.")

class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None
    snippet: Optional[str] = None
    source: Optional[str] = None

class EvidencePack[BaseModel]:
    evidence: List[EvidenceItem] = Field(default_factory=list)

class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal['closed_booke', 'hybrid', 'open_book']
    queries: List[str] = Field(default_factory= list)

