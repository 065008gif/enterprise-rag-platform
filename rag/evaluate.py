"""
Retrieval evaluation harness for the Enterprise Policy RAG project.

This proves retrieval quality with real metrics instead of anecdotal
"it seemed to work" observations - directly addressing the "Evaluating"
techniques called out in the production RAG reference material.

Metrics computed, per query and averaged overall:

- Hit Rate @ K: did the expected source document appear ANYWHERE in the
  top-K retrieved+reranked chunks? (1 if yes, 0 if no)
- Mean Reciprocal Rank (MRR): 1 / (rank position of the first chunk
  from the expected source document), or 0 if it never appears. This
  rewards the expected source appearing EARLY, not just somewhere in
  the results - a source ranked #1 scores much better than one ranked #4.

The evaluation set below is hand-written against the actual content of
our 12 synthetic documents (see data/raw/), each with a question, the
expected department, and the expected source filename.

Run:
    python rag/evaluate.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.query_engine import retrieve_only
from rag.router_agent import route_query


# --------------------------------------------------------------------
# Evaluation set: (question, expected_department, expected_source_file)
# --------------------------------------------------------------------

EVAL_SET = [
    # HR
    ("What is the annual entitlement for casual leave?", "hr", "HR_Leave_and_Attendance_Policy.pdf"),
    ("How many days can privilege leave be carried forward?", "hr", "HR_Leave_and_Attendance_Policy.pdf"),
    ("What happens if an employee is late more than 4 times in a month?", "hr", "HR_Leave_and_Attendance_Policy.pdf"),
    ("What is the probation period for a new hire?", "hr", "HR_Employee_Onboarding_SOP.docx"),
    ("Who assigns a buddy to a new employee?", "hr", "HR_Employee_Onboarding_SOP.docx"),
    ("What is the compensation band for a Manager role?", "hr", "HR_Compensation_Bands_FY26.xlsx"),

    # Legal
    ("How long must Tier 4 personal data be retained before deletion?", "legal", "Legal_Data_Privacy_and_Retention_Policy.pdf"),
    ("What must happen before personal data is shared with a third-party vendor?", "legal", "Legal_Data_Privacy_and_Retention_Policy.pdf"),
    ("Who must approve a vendor contract above 1 crore?", "legal", "Legal_Vendor_Contract_Approval_Policy.pdf"),
    ("What is the maximum notice period for an auto-renewal clause?", "legal", "Legal_Vendor_Contract_Approval_Policy.pdf"),
    ("How long does a standard template NDA take to be approved?", "legal", "Legal_NDA_Execution_SOP.docx"),
    ("Who can negotiate NDA terms with a counterparty?", "legal", "Legal_NDA_Execution_SOP.docx"),

    # Finance
    ("What is the per diem for domestic travel?", "finance", "Finance_Travel_and_Expense_Policy.pdf"),
    ("What hotel category can a B3-B4 band employee book?", "finance", "Finance_Travel_and_Expense_Policy.pdf"),
    ("How many quotations are required for a purchase between 50,000 and 5 lakh?", "finance", "Finance_Procurement_and_Purchase_Order_Policy.pdf"),
    ("What are the standard payment terms for vendor invoices?", "finance", "Finance_Procurement_and_Purchase_Order_Policy.pdf"),
    ("What is the annual budget for the IT department?", "finance", "Finance_Departmental_Budget_FY26.xlsx"),

    # IT
    ("What is the minimum password length required?", "it", "IT_Information_Security_Policy.pdf"),
    ("How quickly must a Severity-1 security incident be escalated?", "it", "IT_Information_Security_Policy.pdf"),
    ("How soon must access be revoked after an employee's last working day?", "it", "IT_Asset_Provisioning_and_Deprovisioning_SOP.docx"),
    ("What is the renewal date for the GitHub Enterprise license?", "it", "IT_Software_License_Inventory.xlsx"),
]


def evaluate(top_k_for_hit_rate: int = 4):
    """Runs every question in EVAL_SET through retrieve_only() (filtered
    to the expected department, matching how a well-routed query would
    behave) and computes Hit Rate and MRR against the expected source
    file."""

    print(f"Running evaluation on {len(EVAL_SET)} questions...\n")

    hits = 0
    reciprocal_ranks = []
    results_detail = []

    for question, expected_dept, expected_source in EVAL_SET:
        nodes = retrieve_only(question, department_filter=[expected_dept])

        rank = None
        for i, node in enumerate(nodes, start=1):
            source_file = node.node.metadata.get("source_file", "")
            if source_file == expected_source:
                rank = i
                break

        hit = rank is not None and rank <= top_k_for_hit_rate
        reciprocal_rank = (1.0 / rank) if rank else 0.0

        if hit:
            hits += 1
        reciprocal_ranks.append(reciprocal_rank)

        results_detail.append({
            "question": question,
            "expected_source": expected_source,
            "found_at_rank": rank,
            "hit": hit,
        })

        status = f"HIT (rank {rank})" if hit else ("MISS (found lower)" if rank else "MISS (not found)")
        print(f"[{status:20}] {question}")

    n = len(EVAL_SET)
    hit_rate = hits / n
    mrr = sum(reciprocal_ranks) / n

    print("\n" + "=" * 60)
    print(f"Hit Rate @ {top_k_for_hit_rate}: {hit_rate:.1%} ({hits}/{n})")
    print(f"Mean Reciprocal Rank (MRR): {mrr:.3f}")
    print("=" * 60)

    misses = [r for r in results_detail if not r["hit"]]
    if misses:
        print(f"\n{len(misses)} question(s) did not hit the expected source in top {top_k_for_hit_rate}:")
        for m in misses:
            print(f"  - {m['question']!r} (expected: {m['expected_source']}, "
                  f"found at rank: {m['found_at_rank']})")

    return {"hit_rate": hit_rate, "mrr": mrr, "details": results_detail}


def evaluate_end_to_end():
    """
    Stronger, more complete evaluation: runs every question through the
    FULL pipeline via route_query() - including automatic department
    classification - rather than pre-filtering to the known-correct
    department. This measures true end-to-end accuracy: does the router
    both (a) pick a sensible department on its own, and (b) then
    retrieve the right source document.

    A question "hits" here if the expected source file appears anywhere
    in the sources of the final routed answer. Since route_query() may
    consult multiple departments (for genuinely cross-cutting questions)
    or fall back to an unrestricted search, rank position is less
    directly comparable to the filtered-retrieval evaluation above, so
    this reports Hit Rate and also whether the classifier's chosen
    department(s) included the expected one - a distinct, useful signal
    about routing accuracy specifically.
    """
    print(f"Running END-TO-END evaluation (full router, automatic "
          f"classification) on {len(EVAL_SET)} questions...\n")

    source_hits = 0
    department_hits = 0
    results_detail = []

    for question, expected_dept, expected_source in EVAL_SET:
        result = route_query(question)

        found_sources = {s["source_file"] for s in result.sources}
        source_hit = expected_source in found_sources
        department_hit = expected_dept in result.departments_used

        if source_hit:
            source_hits += 1
        if department_hit:
            department_hits += 1

        results_detail.append({
            "question": question,
            "expected_department": expected_dept,
            "classified_departments": result.departments_used,
            "expected_source": expected_source,
            "found_sources": sorted(found_sources),
            "source_hit": source_hit,
            "department_hit": department_hit,
        })

        status = "HIT " if source_hit else "MISS"
        dept_note = "" if department_hit else "  [wrong/missing department]"
        print(f"[{status}] {question}{dept_note}")

    n = len(EVAL_SET)
    source_hit_rate = source_hits / n
    department_hit_rate = department_hits / n

    print("\n" + "=" * 60)
    print(f"End-to-end Source Hit Rate: {source_hit_rate:.1%} ({source_hits}/{n})")
    print(f"Department Classification Accuracy: {department_hit_rate:.1%} ({department_hits}/{n})")
    print("=" * 60)

    misses = [r for r in results_detail if not r["source_hit"]]
    if misses:
        print(f"\n{len(misses)} question(s) missed the expected source end-to-end:")
        for m in misses:
            print(f"  - {m['question']!r}")
            print(f"    expected: {m['expected_source']} (dept: {m['expected_department']})")
            print(f"    classified departments: {m['classified_departments']}")
            print(f"    sources found: {m['found_sources']}")

    return {
        "source_hit_rate": source_hit_rate,
        "department_hit_rate": department_hit_rate,
        "details": results_detail,
    }


if __name__ == "__main__":
    filtered_results = evaluate()
    print("\n\n")
    end_to_end_results = evaluate_end_to_end()

    print("\n\n" + "#" * 60)
    print("SUMMARY")
    print("#" * 60)
    print(f"Filtered retrieval (department pre-applied):")
    print(f"  Hit Rate@4: {filtered_results['hit_rate']:.1%}   MRR: {filtered_results['mrr']:.3f}")
    print(f"End-to-end (automatic routing via LangGraph agent):")
    print(f"  Source Hit Rate: {end_to_end_results['source_hit_rate']:.1%}")
    print(f"  Department Classification Accuracy: {end_to_end_results['department_hit_rate']:.1%}")
