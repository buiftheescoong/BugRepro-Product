import asyncio
from langchain_core.tools import tool
from src.tools.browsers import browser_manager
from tavily import TavilyClient
from src.core.config import Settings
from src.utils.logger import get_logger

logger = get_logger("web_tools")

tavily = TavilyClient(api_key=Settings.TAVILY_API_KEY)

@tool
async def click_element(thought: str, selector: str, xpath: str = ""):
    """
    Executes a mouse click on a specific web element.
    Args:
        thought (str): A brief explanation of why this action is being taken.
        selector (str): The selector of the target element. Use the 'selector' field from the Accessibility Tree. If the user provided an XPath or CSS selector via User Input, use that selector exactly as given.
        xpath (str): The stable XPath of the target element. Use the 'xpath' field from the Accessibility Tree. Leave empty if not available.
    """
    return "Handed by Executor"

@tool
async def type_text(thought: str, selector: str, value: str, xpath: str = ""):
    """
    Enters text into an input field or textarea. It clears existing text before typing.
    Args:
        thought (str): A brief explanation of why this action is being taken.
        selector (str): The selector of the target element. Use the 'selector' field from the Accessibility Tree. If the user provided an XPath or CSS selector via User Input, use that selector exactly as given.
        value (str): The string content to be typed into the element.
        xpath (str): The stable XPath of the target element. Use the 'xpath' field from the Accessibility Tree. Leave empty if not available.
    """
    return "Handed by Executor"

@tool
async def select_dropdown(thought: str, selector: str, value: str, xpath: str = ""):
    """
    Selects an option from a <select> dropdown element.
    Args:
        thought (str): A brief explanation of why this action is being taken.
        selector (str): The selector of the target select element. Use the 'selector' field from the Accessibility Tree. If the user provided an XPath or CSS selector via User Input, use that selector exactly as given.
        value (str): The 'value' attribute or visible 'label' of the option to select. Refer to the 'options' list in the accessibility tree for valid values.
        xpath (str): The stable XPath of the target element. Use the 'xpath' field from the Accessibility Tree. Leave empty if not available.
    """
    return "Handed by Executor"

@tool
async def scroll_page(thought: str, direction: str = "down", selector: str = "N/A", xpath: str = ""):
    """
    Scrolls the page or a specific element into view.
    Use this when the target element is not visible in the current screenshot.
    Args:
        thought (str): A brief explanation of why this action is being taken.
        direction (str): The direction to scroll. Choices are 'up' or 'down'. Default is 'down'.
        selector (str): Optional. The selector of a specific element to scroll into view (Use the 'selector' field from the Accessibility Tree or a user-provided XPath/CSS selector). If 'N/A', the whole page will be scrolled.
        xpath (str): The stable XPath of the target element. Use the 'xpath' field from the Accessibility Tree. Leave empty if not available.
    """
    return "Handed by Executor"

@tool
async def wait(thought: str):
    """
    Pauses the agent execution for a specific duration. 
    Use this when the page is loading, an animation is playing, or a result hasn't appeared yet.
    Args:
        thought (str): A brief explanation of why this action is being taken.
    """
    return "Handed by Executor"
@tool
async def go_back(thought: str):
    """
    Navigates back to the previous page in the browser's history.
    Use this if you accidentally clicked a wrong link or reached a wrong page.
    Args:
        thought (str): A brief explanation of why this action is being taken.
    """
    return "Handed by Executor"

@tool
async def reload_page(thought: str):
    """
    Reloads (refreshes) the current page, equivalent to pressing F5.
    Use this when:
    - The bug description mentions that a reload/refresh step is required to trigger the bug.
    - Data appears stale after an action and a page refresh is needed to verify the bug state.
    - The UI is in an inconsistent state that requires a reload to proceed.
    Args:
        thought (str): A brief explanation of why this reload is needed.
    """
    return "Handed by Executor"

@tool
async def navigate_to(thought: str, url: str):
    """
    Navigates the browser to a specific URL.
    Use this when you need to jump directly to a page or start the reproduction from a specific entry point.
    Args:
        thought (str): A brief explanation of why this navigation is being taken.
        url (str): The full destination URL.
    """
    return "Handed by Executor"

@tool
async def request_user_input(thought: str, question: str):
    """
    Suspends the agent's execution to ask the user for specific information.
    Use this ONLY when:
    1. You are stuck due to missing secure data or an error message indicating that your guess failed.
    2. You need clarification on ambiguous instructions from the bug report.
    3. The target element is not present in the Accessibility Tree (e.g., a custom component, a div with a click handler). Ask the user to provide an XPath or CSS selector for the element.
    Args:
        thought (str): A brief explanation of why this action is being taken.
        question (str): A clear, polite instruction or question for the user explaining what info is needed.
    """
    return "Handed by Executor"

@tool
async def bug_reproduced_successfully(thought: str):
    """
    Terminates the workflow and marks the bug as successfully reproduced.
    Call this tool only when both of the following conditions are satisfied:
    1. The bug has been fully reproduced following the action flow and conditions specified in the bug description.
    2. The "Current Screenshot" is considered equivalent to the "Target Screenshot" if they share the same error or UI state, regardless of differences in specific field values or data.
    Args:
        thought (str): A brief explanation of why this action is being taken.
    """
    return "Handed by Executor"

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
web_tools = [
    click_element, 
    type_text, 
    select_dropdown, 
    scroll_page,
    wait,
    go_back,
    reload_page,
    navigate_to,
    request_user_input, 
    bug_reproduced_successfully, 
    search_web_info
]