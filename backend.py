from langgraph.graph import StateGraph, START, END
from state import State, RAGState
from nodes import *

subgraph = StateGraph(RAGState)

subgraph.add_node("loader", loader)
subgraph.add_node("docs_splitter", docs_splitter)
subgraph.add_node("map", map)

subgraph.add_edge(START, 'loader')
subgraph.add_edge('loader', 'docs_splitter')
subgraph.add_edge('docs_splitter', 'map')
subgraph.add_edge('map', END)

rag = subgraph.compile()

graph = StateGraph(State)

graph.add_node("rag", rag)
graph.add_node("router", router)
graph.add_node("research", research)
graph.add_node('orchestrator', orchestrator)
graph.add_node('worker', worker)
graph.add_node('reducer', reducer, defer=True)

graph.add_edge(START, 'rag')
graph.add_edge('rag', 'router')
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






# print(app.invoke({"topic": "future of neural networks"}))