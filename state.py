from typing import TypedDict, Annotated, List
from schema import Plan, Task, EvidenceItem
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