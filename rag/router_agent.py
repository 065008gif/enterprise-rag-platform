"""
LangGraph router agent for the Enterprise Policy RAG project.

This is the key differentiator layer sitting on top of query_engine.py.
Instead of the caller having to know and pass the right department
filter (as query_engine.query() requires), this module automatically:

1. Classifies which department(s) a question is actually about, using
   the LLM itself rather than brittle keyword matching.
2. Routes to filtered retrieval for each relevant department.
3. When a question genuinely spans multiple departments (e.g. a
   question that needs both Legal's data-sharing rules AND Finance's
   payment terms), retrieves from each department separately and
   synthesizes ONE coherent, reconciled answer with per-department
   attribution - rather than either missing half the departments or
   returning a disjointed answer.
4. Falls back to an unrestricted (all-department) search when the
   classifier is genuinely unsure, rather than confidently guessing
   the wrong single department and missing the right answer entirely.

Entry point:
    route_query(question: str) -> RoutedResult
"""

import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.config import DEPARTMENTS
from rag.query_engine import query as run_query, Settings

from langgraph.graph import StateGraph, END


# --------------------------------------------------------------------
# State shape passed between graph nodes
# --------------------------------------------------------------------

class RouterState(TypedDict):
    question: str
    classified_departments: list  # list[str], empty list means "all departments"
    classification_confident: bool
    per_department_results: dict  # {department: QueryResult-like dict}
    final_answer: str
    final_sources: list


@dataclass
class RoutedResult:
    answer: str
    departments_used: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    classification_confident: bool = True


# --------------------------------------------------------------------
# Node 1: Classify which department(s) the question concerns
# --------------------------------------------------------------------

CLASSIFICATION_PROMPT = """You are a routing classifier for an internal company assistant. The company has four departments: hr, legal, finance, it.

Given the employee's question below, decide which department(s)' documents would most likely contain the answer. A question can genuinely require MORE THAN ONE department when it spans topics (for example, a question combining a legal data-sharing rule with a finance payment term needs both "legal" and "finance").

Respond with ONLY a JSON object, no other text, in this exact format:
{{"departments": ["dept1", "dept2"], "confident": true}}

- "departments" must be a list containing only values from: hr, legal, finance, it
- Use an empty list [] if the question is genuinely unclear which department(s) apply, or if it seems unrelated to any department's typical documents (e.g. general knowledge questions)
- Set "confident" to false if you are genuinely unsure, true otherwise

Question: {question}

JSON response:"""


def classify_departments(state: RouterState) -> RouterState:
    prompt = CLASSIFICATION_PROMPT.format(question=state["question"])
    response = Settings.llm.complete(prompt)
    raw = str(response).strip()

    # Be defensive: strip markdown code fences if the model adds them
    # despite instructions, and find the JSON object within the text.
    if "```" in raw:
        raw = raw.split("```")[1] if raw.count("```") >= 2 else raw
        raw = raw.replace("json", "", 1).strip()

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        parsed = json.loads(raw[start:end])
        departments = [d for d in parsed.get("departments", []) if d in DEPARTMENTS]
        confident = bool(parsed.get("confident", True))
    except (json.JSONDecodeError, ValueError):
        # If classification itself fails to parse, treat as "unsure" and
        # fall back to searching everything rather than crashing or
        # guessing a department at random.
        departments = []
        confident = False

    state["classified_departments"] = departments
    state["classification_confident"] = confident
    return state


# --------------------------------------------------------------------
# Node 2: Retrieve - either single filtered query, multi-department,
# or unrestricted fallback
# --------------------------------------------------------------------

def retrieve_node(state: RouterState) -> RouterState:
    departments = state["classified_departments"]
    question = state["question"]

    if not departments:
        # No confident single department (or genuinely cross-cutting/
        # unclear) - search across everything and let the reranker sort
        # out what's relevant, exactly as query_engine.query() does by
        # default with department_filter=None.
        result = run_query(question, department_filter=None)
        state["per_department_results"] = {"_unfiltered": result}
        return state

    if len(departments) == 1:
        # Single clear department - one filtered call, no synthesis needed.
        result = run_query(question, department_filter=departments)
        state["per_department_results"] = {departments[0]: result}
        return state

    # Multiple departments genuinely relevant - retrieve separately
    # from EACH so a department with fewer/less-similar chunks doesn't
    # get crowded out by another department's more numerous chunks in
    # a single combined top-k search. This is the cross-department
    # synthesis case.
    per_dept_results = {}
    for dept in departments:
        per_dept_results[dept] = run_query(question, department_filter=[dept])
    state["per_department_results"] = per_dept_results
    return state


# --------------------------------------------------------------------
# Node 3: Synthesize a final answer (only does real synthesis work
# when multiple departments were queried separately; otherwise it's a
# straight passthrough of the single query's result)
# --------------------------------------------------------------------

SYNTHESIS_PROMPT = """You are an internal assistant. Below are answers gathered separately from different company departments' documents, in response to the same employee question. Combine them into ONE coherent, well-organized answer that clearly attributes each part to its department. If two departments' answers conflict or one has no relevant information, say so explicitly rather than ignoring the discrepancy.

Question: {question}

{department_answers}

Combined answer:"""


def synthesize_node(state: RouterState) -> RouterState:
    per_dept = state["per_department_results"]

    if len(per_dept) == 1:
        # Single result (either one confident department, or the
        # unfiltered fallback) - no synthesis LLM call needed, just
        # pass through what query_engine already produced.
        only_result = next(iter(per_dept.values()))
        state["final_answer"] = only_result.answer
        state["final_sources"] = only_result.sources
        return state

    # Multiple departments were queried separately - combine them.
    dept_blocks = []
    all_sources = []
    for dept, result in per_dept.items():
        dept_blocks.append(f"[{dept.upper()} department's documents say:]\n{result.answer}")
        all_sources.extend(result.sources)

    departments_text = "\n\n".join(dept_blocks)
    prompt = SYNTHESIS_PROMPT.format(
        question=state["question"], department_answers=departments_text
    )
    response = Settings.llm.complete(prompt)

    state["final_answer"] = str(response).strip()
    state["final_sources"] = all_sources
    return state


# --------------------------------------------------------------------
# Build the graph
# --------------------------------------------------------------------

def _build_graph():
    graph = StateGraph(RouterState)
    graph.add_node("classify", classify_departments)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


def route_query(question: str) -> RoutedResult:
    """Main entry point: classify, retrieve, and synthesize automatically -
    the caller does not need to know or specify which department(s) to
    search, unlike query_engine.query()."""
    graph = _get_graph()

    initial_state: RouterState = {
        "question": question,
        "classified_departments": [],
        "classification_confident": True,
        "per_department_results": {},
        "final_answer": "",
        "final_sources": [],
    }

    final_state = graph.invoke(initial_state)

    departments_used = sorted(
        d for d in final_state["per_department_results"].keys() if d != "_unfiltered"
    )
    # If we used the unfiltered fallback, report departments actually
    # found in the returned sources instead of the placeholder key.
    if not departments_used and final_state["final_sources"]:
        departments_used = sorted({s["department"] for s in final_state["final_sources"]})

    return RoutedResult(
        answer=final_state["final_answer"],
        departments_used=departments_used,
        sources=final_state["final_sources"],
        classification_confident=final_state["classification_confident"],
    )


if __name__ == "__main__":
    print("Testing router_agent.py...\n")

    test_questions = [
        "What is the leave carry-forward limit for privilege leave?",
        "What is our data retention policy for personal data?",
        (
            "If we share customer data with a new analytics vendor, what "
            "data-sharing rules apply, and what payment terms would govern "
            "the vendor contract?"
        ),
        "What is the capital of France?",
    ]

    for q in test_questions:
        print(f"Q: {q}")
        result = route_query(q)
        print(f"Classified/used departments: {result.departments_used} "
              f"(confident: {result.classification_confident})")
        print(f"A: {result.answer}")
        print(f"Sources: {[s['source_file'] for s in result.sources]}")
        print()
