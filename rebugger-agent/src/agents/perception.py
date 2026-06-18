from src.core.state import AgentState
from src.tools.browsers import browser_manager
import base64
from langchain_core.runnables.config import RunnableConfig
from src.utils.logger import get_logger

logger = get_logger("perception")

async def perception_node(state: AgentState, config: RunnableConfig):
    logger.info("Entering perception node", extra={"data": {"step": state.get("steps_count")}})

    thread_id = config["configurable"].get("thread_id")
    if thread_id not in browser_manager.pages:
        logger.info("New browser session", extra={"data": {"thread_id": thread_id, "root_url": state["root_url"]}})
        await browser_manager.start()
        await browser_manager.navigate(state["root_url"], thread_id)

    screenshot_bytes, tree, file_path, current_screenshot_base64 = await browser_manager.capture(thread_id)
    page = await browser_manager.get_page(thread_id)
    current_url = page.url
    return {
        "current_screenshot": file_path,
        "current_screenshot_base64": current_screenshot_base64,
        "accessibility_tree": str(tree),
        "steps_count": state.get("steps_count", 0) + 1,
        "current_url": current_url,
        "log": [{
            "role": "perception", 
            "path": file_path, 
            "type": "image"
        }]
    }