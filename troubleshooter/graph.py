from langgraph.graph import END, START, StateGraph

from troubleshooter.agents.code_analyst import CodeAnalyst
from troubleshooter.agents.diagnostician import Diagnostician
from troubleshooter.agents.reporter import Reporter
from troubleshooter.agents.researchers import DocResearcher, GitHubResearcher
from troubleshooter.agents.supervisor import Supervisor
from troubleshooter.agents.triage import TriageAgent
from troubleshooter.agents.validator import Validator
from troubleshooter.config import Settings
from troubleshooter.llm import StructuredLLM
from troubleshooter.rag.retriever import HybridRetriever
from troubleshooter.state import (
    CODE_ANALYST,
    DIAGNOSTICIAN,
    DOC_RESEARCHER,
    GITHUB_RESEARCHER,
    REPORTER,
    SUPERVISOR,
    TRIAGE,
    VALIDATOR,
    GraphState,
)

WORKERS = (DOC_RESEARCHER, CODE_ANALYST, GITHUB_RESEARCHER, DIAGNOSTICIAN, VALIDATOR)


def build_graph(llm: StructuredLLM, retriever: HybridRetriever, settings: Settings):
    """Hub-and-spoke topology: every worker reports back to the supervisor,
    which is the only node that chooses what runs next."""
    graph = StateGraph(GraphState)
    graph.add_node(TRIAGE, TriageAgent(llm, settings))
    graph.add_node(SUPERVISOR, Supervisor(settings))
    graph.add_node(DOC_RESEARCHER, DocResearcher(llm, retriever, settings))
    graph.add_node(CODE_ANALYST, CodeAnalyst(llm, settings))
    graph.add_node(GITHUB_RESEARCHER, GitHubResearcher(settings))
    graph.add_node(DIAGNOSTICIAN, Diagnostician(llm))
    graph.add_node(VALIDATOR, Validator(settings))
    graph.add_node(REPORTER, Reporter(settings))

    graph.add_edge(START, TRIAGE)
    graph.add_edge(TRIAGE, SUPERVISOR)
    for worker in WORKERS:
        graph.add_edge(worker, SUPERVISOR)
    graph.add_conditional_edges(
        SUPERVISOR,
        lambda state: state["next_step"],
        {name: name for name in (*WORKERS, REPORTER)},
    )
    graph.add_edge(REPORTER, END)
    return graph.compile()
