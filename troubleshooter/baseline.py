"""RAG-only baseline used for comparison in the evaluation harness:
one retrieval pass over the raw report and a single diagnosis call, with no
triage, grading, code analysis, execution or revision."""

from troubleshooter.agents.common import format_evidence
from troubleshooter.agents.diagnostician import SYSTEM_PROMPT
from troubleshooter.llm import StructuredLLM
from troubleshooter.rag.retriever import HybridRetriever
from troubleshooter.schemas import Diagnosis, Evidence, TroubleshootRequest
from troubleshooter.tools.static_analysis import number_lines


def run_baseline(
    llm: StructuredLLM, retriever: HybridRetriever, request: TroubleshootRequest, k: int = 4
) -> tuple[Diagnosis, list[Evidence]]:
    chunks = retriever.search([request.query], k=k)
    evidence = [
        Evidence(id=f"D{n}", kind="documentation", title=c.title, source=c.url, snippet=c.text, score=c.score)
        for n, c in enumerate(chunks, start=1)
    ]
    prompt = [f"Developer report:\n{request.query}"]
    if request.code:
        prompt.append(f"Submitted code:\n{number_lines(request.code)}")
    prompt.append(f"Evidence:\n{format_evidence(evidence)}")
    diagnosis = llm.generate(Diagnosis, SYSTEM_PROMPT, "\n\n".join(prompt), run_name="baseline_diagnose")
    return diagnosis, evidence
