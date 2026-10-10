"""Wires the agents into a LangGraph pipeline and runs it.

    supervisor (case record -> delegate / clarify -> reconcile) -> verification
"""

import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app import agents, case, knowledge
from app.supervisor import supervise
from app.schema import load_request


class State(TypedDict, total=False):
    case_record: dict
    request: dict
    result: dict


def build():
    graph = StateGraph(State)
    graph.add_node("supervisor", supervise)
    graph.add_node("verification", agents.verification)

    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "verification")
    graph.add_edge("verification", END)
    return graph.compile()


def run(request, on_event=None):
    """Validate a request, run the pipeline and return (result, events).

    on_event(event) is called for each trace event as it happens (used by the UI).
    """
    request = load_request(request)
    knowledge.vector_store()  # reuse the existing legal index
    events, final = [], {}
    started = time.time()
    for mode, chunk in build().stream({"request": request},
                                      stream_mode=["custom", "updates"]):
        if mode == "custom":
            events.append(chunk)
            if on_event:
                on_event(chunk)
        elif "verification" in chunk:
            final = chunk["verification"]["result"]
    final["seconds"] = round(time.time() - started, 1)
    final["workflow"] = f"supervisor-{case.VERSION}"
    return final, events
