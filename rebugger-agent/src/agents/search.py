from src.tools.critic_tools import search_web_info
from src.core.state import AgentState
from src.utils.logger import get_logger

logger = get_logger("search")

async def search_node(state: AgentState):
    tool_call = state["search_action"]
    query = tool_call.get("args", {}).get("query", "")
    logger.info("Web search", extra={"data": {"query": query}})

    result = await search_web_info.ainvoke(tool_call["args"])
    logger.info("Search completed", extra={"data": {"result_length": len(str(result))}})
    return {
        "steps_count": state.get("steps_count", 0) + 1,
        "history": [{"role": "critic_search", "content": f"Search Result: {result}"}],
        "log": [{"role": "critic_search", "content": f"Search Result: {result}"}],
        "search_action": None
    }