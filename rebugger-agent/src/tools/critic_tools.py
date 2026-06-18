from langchain_core.tools import tool
from tavily import TavilyClient
from src.core.config import Settings
from src.utils.logger import get_logger

logger = get_logger("critic_tools")

tavily = TavilyClient(api_key=Settings.TAVILY_API_KEY)

@tool
def approve_action(reason: str):
    """
    Call this tool only if the proposed action is logical, the selector exists 
    in the tree, and it directly helps in reproducing the bug.
    Args:
        reason: Brief explanation of why this action is correct.
    """
    return "APPROVED"

@tool
def reject_action(feedback: str):
    """
    Call this tool if the proposed action is wrong, the selector is missing, 
    the proposed action is repetitive, or it doesn't make sense.
    Args:
        feedback: Brief explanation of why the proposed action was rejected 
                  and what the planner should do instead.
    """
    return "REJECTED"

@tool
async def search_web_info(thought: str, query: str):
    """
    Searches the internet for real-time information (gold prices, current time, news, etc.)
    using Tavily Search API. Returns a concise summary of the findings.
    
    Args:
        thought (str): Why you need to perform this search.
        query (str): The specific search query.
    Returns:
        str: A summary of the search results, or an error message starting with 'Error:' if the search fails.
    """
    try:
        
        response = tavily.search(query=query, search_depth="basic", include_answer=True)
        print(f"Tavily Search Response: {response}")
        
        if response.get("answer"):
            return f"Search Result: {response['answer']}"
        
        context = "\n".join([f"- {res['content']}" for res in response['results'][:3]])
        return f"Search Results for '{query}':\n{context}"
        
    except Exception as e:
        return f"Error searching Tavily: {str(e)}"

critic_tools = [approve_action, reject_action, search_web_info]