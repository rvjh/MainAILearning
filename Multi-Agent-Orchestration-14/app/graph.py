"""LangGraph: collect then supervise; one risk follow-up max."""
from typing import TypedDict
from langgraph.graph import END, START, StateGraph

class TeamState(TypedDict, total=False):
    case_id: str
    backend: str
    model: str | None
    timeout: float
    round_no: int
    results: dict
    decision: dict

def collect_node(state: TeamState) -> TeamState:
    from . import team
    return team.collect_round(state)

def supervise_node(state: TeamState) -> TeamState:
    from . import team
    return team.decide_round(state)

def after_supervise(state: TeamState) -> str:
    if state.get('decision', {}).get('action') == 'FOLLOW_UP':
        return 'collect'
    return 'end'

def build_team_graph():
    graph = StateGraph(TeamState)
    graph.add_node('collect', collect_node)
    graph.add_node('supervise', supervise_node)
    graph.add_edge(START, 'collect')
    graph.add_edge('collect', 'supervise')
    graph.add_conditional_edges('supervise', after_supervise, {'collect': 'collect', 'end': END})
    return graph.compile()

TEAM_GRAPH = build_team_graph()
