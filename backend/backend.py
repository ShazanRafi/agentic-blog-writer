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

graph.add_conditional_edges(
    START, route_to_rag, {
        'rag': 'rag',
        'router': 'router'
    }
)
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


if __name__ == "__main__":
    result = app.invoke({
        "topic": "future of neural networks",
        "file_name": ""
    })

    print("\n--- ROUTER INSIGHTS ---")
    print("Research mode:", result.get("mode"))
    print("Research needed:", result.get("needs_research"))
    print("Queries:", result.get("queries"))

    print("\n--- RESEARCH INSIGHTS ---")
    print("Evidence:", result.get("evidence"))

    print("\n--- ORCHESTRATOR PLAN ---")
    plan = result.get("plan")

    if plan:
        print("Blog title:", plan.blog_title)
        print("Audience:", plan.audience)
        print("Tone:", plan.tone)
        print("Blog type:", plan.blog_kind)

        for task in plan.tasks:
            print(f"\nSection {task.id}: {task.title}")
            print("Goal:", task.goal)
            print("Target words:", task.target_words)
            print("Bullets:", task.bullets)

    print("\n--- FINAL BLOG ---")
    print(result.get("final", "No blog generated."))