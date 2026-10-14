from langgraph.graph import StateGraph, START, END
from state import State
from nodes import *

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