"""One case record. The input snapshot is read-only; each agent has a separate write scope.

Models receive JSON views, never a live mutable state object. Their output schemas do
not contain input fields. Python writes references/checks and records agent outputs.
"""

from copy import deepcopy

# Case contract and workflow version stamped on every case record and run result.
VERSION = "v15"


def new_case(request, reference_facts):
    """Keep one validated input and separate agent-owned assessment sections."""
    return {
        "version": VERSION,
        "input": {**deepcopy(request), "reference_facts": deepcopy(reference_facts)},
        "supervisor": {"intake": {}, "interpretation": [], "exclusions": [], "plans": {},
                       "action_log": [], "review": None},
        "specialists": {},
        "checks": {},
    }


def fact_document(case):
    """The same input shape is shown to every agent and checked for fact references."""
    return deepcopy(case["input"])


def evidence_by_id(case):
    """Read the supplied evidence directly, preserving IDs, attesters and party scope."""
    return {e["id"]: deepcopy(e) for e in case["input"].get("evidence", [])}


def findings(case):
    return [f for branch in case["specialists"].values() for f in branch.get("findings", [])]
