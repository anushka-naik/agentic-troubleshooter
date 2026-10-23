from troubleshooter.agents.common import Stopwatch, describe_error, step
from troubleshooter.config import Settings
from troubleshooter.llm import StructuredLLM
from troubleshooter.rag.retriever import HybridRetriever, RetrievedChunk
from troubleshooter.schemas import Evidence, RelevanceGrades
from troubleshooter.state import DOC_RESEARCHER, GITHUB_RESEARCHER, GraphState
from troubleshooter.tools.github_search import search_issues

GRADER_PROMPT = """You review documentation excerpts retrieved for a Python debugging investigation.
Mark an excerpt relevant only if it explains the failure mechanism or a fix for this specific problem.
Excerpts that merely mention the same exception type in an unrelated context are not relevant.
Return chunk IDs exactly as written."""


class DocResearcher:
    """Retrieve, then grade: a corrective-RAG step that filters noisy matches
    before they reach the diagnosis and reports coverage to the supervisor."""

    def __init__(self, llm: StructuredLLM, retriever: HybridRetriever, settings: Settings):
        self.llm = llm
        self.retriever = retriever
        self.settings = settings

    def __call__(self, state: GraphState) -> dict:
        watch = Stopwatch()
        plan = state["plan"]
        parsed = state["parsed"]

        queries = list(plan.search_queries)
        if parsed.found:
            queries.append(f"{parsed.exception_type}: {parsed.message or ''}")
        candidates = self.retriever.search(queries, k=self.settings.retrieval_k)

        grades = self.llm.generate(
            RelevanceGrades,
            GRADER_PROMPT,
            self._grading_prompt(state, candidates),
            run_name="grade_documents",
        )
        by_id = {c.chunk_id: c for c in candidates}
        relevant = [by_id[i] for i in grades.relevant_ids if i in by_id]

        coverage = grades.coverage
        if len(relevant) < self.settings.min_relevant_chunks and coverage == "sufficient":
            coverage = "partial"
        if not relevant:
            coverage = "insufficient"

        evidence = [
            Evidence(
                id=f"D{n}",
                kind="documentation",
                title=chunk.title,
                source=chunk.url,
                snippet=chunk.text,
                score=chunk.score,
            )
            for n, chunk in enumerate(relevant, start=1)
        ]
        return {
            "evidence": evidence,
            "doc_coverage": coverage,
            "completed": [DOC_RESEARCHER],
            "llm_calls": 1,
            "steps": step(
                DOC_RESEARCHER,
                f"Retrieved {len(candidates)} chunks, kept {len(relevant)} as relevant (coverage: {coverage})",
                watch,
                queries=queries,
                kept=[c.title for c in relevant],
                discarded=[c.title for c in candidates if c not in relevant],
                missing=grades.missing_information,
            ),
        }

    @staticmethod
    def _grading_prompt(state: GraphState, candidates: list[RetrievedChunk]) -> str:
        excerpts = "\n\n".join(f'<chunk id="{c.chunk_id}" title="{c.title}">\n{c.text}\n</chunk>' for c in candidates)
        return (
            f"Problem: {state['plan'].problem_summary}\n"
            f"Error:\n{describe_error(state['parsed'])}\n\n"
            f"Retrieved excerpts:\n{excerpts}"
        )


class GitHubResearcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def __call__(self, state: GraphState) -> dict:
        watch = Stopwatch()
        query = self._build_query(state)
        try:
            issues = search_issues(query, token=self.settings.github_token)
        except Exception as exc:  # network failures must not abort the investigation
            return {
                "completed": [GITHUB_RESEARCHER],
                "steps": step(GITHUB_RESEARCHER, f"GitHub search unavailable: {exc}", watch, query=query),
            }

        evidence = [
            Evidence(
                id=f"G{n}",
                kind="github_issue",
                title=f"{issue.repository}: {issue.title} [{issue.state}, {issue.comments} comments]",
                source=issue.url,
                snippet=issue.body or issue.title,
            )
            for n, issue in enumerate(issues, start=1)
        ]
        return {
            "evidence": evidence,
            "completed": [GITHUB_RESEARCHER],
            "steps": step(
                GITHUB_RESEARCHER,
                f"Found {len(issues)} related GitHub issues",
                watch,
                query=query,
                issues=[i.url for i in issues],
            ),
        }

    @staticmethod
    def _build_query(state: GraphState) -> str:
        parsed = state["parsed"]
        plan = state["plan"]
        terms = []
        if parsed.found:
            message = (parsed.message or "").replace('"', "").replace("'", "")
            terms.append(f"{parsed.exception_type} {message}")
        else:
            terms.append(plan.problem_summary)
        terms.extend(plan.libraries[:2])
        return " ".join(terms)[:200]
