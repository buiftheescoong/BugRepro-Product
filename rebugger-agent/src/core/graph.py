from langgraph.graph import StateGraph, END
from src.core.state import AgentState
from src.agents.perception import perception_node
from src.agents.planner import planner_node
from src.agents.executor import executor_node
from src.agents.critic import critic_node
from src.agents.search import search_node
from src.core.config import settings
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from src.utils.logger import get_logger
logger = get_logger("graph")

def router_logic(state: AgentState):
        if state.get("wait_for_input", False):
            logger.info("Router: stopping (waiting for user input)")
            return "stop"
        if state["is_reproduced"]:
            logger.info("Router: stopping (bug reproduced)")
            return "stop"
        if state["steps_count"] > settings.MAX_STEPS:
            logger.warning("Router: stopping (max steps reached)", extra={"data": {"steps": state["steps_count"]}})
            return "stop"
        if state.get("next_action"):
            return "continue"
        return "plan"

def router_after_critic(state: AgentState):
    tool_call = state.get("search_action")
    if tool_call and tool_call.get("name") == "search_web_info":
        return "search"
    if state.get("critic_feedback") is not None:
        if state.get("review_count", 0) < 3:
            return "re-plan"
        else:
            state["user_provided_input"] = None
            logger.warning("Critic router: max reviews reached, forcing execution", extra={"data": {"review_count": state.get("review_count")}})
    return "continue"
def create_rebugger_graph(checkpointer):
    workflow = StateGraph(AgentState)
    workflow.add_node("perceive", perception_node)
    workflow.add_node("plan", planner_node)
    workflow.add_node("execute", executor_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("search", search_node)
    workflow.set_entry_point("perceive")
    workflow.add_edge("perceive", "plan")
    workflow.add_edge("plan", "critic")
    workflow.add_conditional_edges(
        "critic",
        router_after_critic,
        {
            "re-plan": "plan",
            "continue": "execute",
            "search": "search"
        }
    )
    workflow.add_edge("search", "critic")
    workflow.add_conditional_edges("execute", router_logic, {"continue": "perceive", "stop": END, "plan": "plan"})
    return workflow.compile(checkpointer=checkpointer)

def create_experiment_graph(checkpointer, critic_enabled: bool = True):
    """Experiment variant: critic_enabled=False bypasses Critic node (Planner → Executor directly)."""
    workflow = StateGraph(AgentState)
    workflow.add_node("perceive", perception_node)
    workflow.add_node("plan", planner_node)
    workflow.add_node("execute", executor_node)
    workflow.set_entry_point("perceive")
    workflow.add_edge("perceive", "plan")

    if critic_enabled:
        workflow.add_node("critic", critic_node)
        workflow.add_node("search", search_node)
        workflow.add_edge("plan", "critic")
        workflow.add_conditional_edges(
            "critic",
            router_after_critic,
            {"re-plan": "plan", "continue": "execute", "search": "search"}
        )
        workflow.add_edge("search", "critic")
    else:
        workflow.add_edge("plan", "execute")

    workflow.add_conditional_edges("execute", router_logic, {"continue": "perceive", "stop": END, "plan": "plan"})

    return workflow.compile(checkpointer=checkpointer)