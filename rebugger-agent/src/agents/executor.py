from src.core.state import AgentState
from src.tools.browsers import browser_manager
from src.tools.web_tools import (
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
)

from langchain_core.runnables.config import RunnableConfig
from src.utils.logger import get_logger

logger = get_logger("executor")

async def executor_node(state: AgentState, config: RunnableConfig):
    thread_id = config["configurable"].get("thread_id")
    tool_call = state["next_action"]
    logger.info("Executing actions", extra={"data": {
        "count": len(tool_call) if tool_call else 0,
        "names": [a["name"] for a in tool_call] if tool_call else [],
    }})
    if not tool_call:
        print("Executor No action")
        return {
            "steps_count": state.get("steps_count", 0) + 1,
            "history": [{"role": "executor", "content": "No action to execute"}],
            "log": [{"role": "executor", "content": "No action to execute"}]
        }

    ACTION_MAP = {
        "click_element": "click",
        "type_text": "type",
        "select_dropdown": "select",
        "scroll_page": "scroll",
        "wait": "wait",
        "go_back": "back",
        "reload_page": "reload",
        "navigate_to": "navigate",
        "search_web_info": search_web_info
    }
    if len(tool_call) > 1:        
        for action in tool_call:
            tool_name = action["name"]            
            if tool_name in ["request_user_input", "bug_reproduced_successfully", "search_web_info"]:
                logger.warning(f"Invalid batch: {tool_name} must be called alone")
                print("Executor Invalid batch")
                return {
                    "steps_count": state.get("steps_count", 0) + 1,
                    "history": [{"role": "executor", "content": f"Invalid batch: {tool_name} cannot be combined with other tools."}],
                    "log": [{"role": "executor", "content": f"Invalid batch: {tool_name} cannot be combined with other tools."}]
                }
        
        for action in tool_call:
            tool_name = action["name"]
            tool_args = action["args"]
            payload = {
                **tool_args,
                "action_type": ACTION_MAP[tool_name]
            }            
            
            result = await browser_manager.execute_action(payload, thread_id)
            print("Executor result: ", result)
            if result.startswith("Error"):
                return {
                    "steps_count": state.get("steps_count", 0) + 1,
                    "history": [{"role": "executor", "content": f"{result}"}],
                    "log": [{"role": "executor", "content": f"{result}"}]
                }
        return {
            "steps_count": state.get("steps_count", 0) + 1,
            "history": [{"role": "executor", "content": "Executed successfully."}],
            "log": [{"role": "executor", "content": "Executed successfully."}]        
        }
    else:
        action = tool_call[0]
        tool_name = action["name"]
        tool_args = action["args"]
        if tool_name == "request_user_input":
            print("Executor request user input")
            return {
                "steps_count": state.get("steps_count", 0) + 1,
                "wait_for_input": True,
                "input_request_message": tool_args["question"],
                "history": [{"role": "executor", "content": f"Paused: {tool_args['question']}"}],
                "log": [{"role": "executor", "content": f"Paused: {tool_args['question']}"}],
                "next_action": None
            }
        
        if tool_name == "bug_reproduced_successfully":
            print("Executor bug reproduced successfully")
            return {
                "is_reproduced": True,
                "steps_count": state.get("steps_count", 0) + 1,
                "history": [{"role": "executor", "content": "Bug Reproduced"}],
                "log": [{"role": "executor", "content": "Bug Reproduced"}]
            }
        if tool_name == "search_web_info":
            try:
                result = await ACTION_MAP[tool_name].ainvoke(tool_args)
            except Exception as e:
                result = f"Error: {str(e)}"
            print("Executor search web info result: ", result)
            return {
                "steps_count": state.get("steps_count", 0) + 1,
                "history": [{"role": "executor", "content": f"Execution result: {result}"}],
                "log": [{"role": "executor", "content": f"Execution result: {result}"}],
            }

        payload = {
                **tool_args,
                "action_type": ACTION_MAP[tool_name]
        }                
        result = await browser_manager.execute_action(payload, thread_id)  
        print("Executor action result: ", result)
        return {
            "steps_count": state.get("steps_count", 0) + 1,
            "history": [{"role": "executor", "content": f"Execution result: {result}"}],
            "log": [{"role": "executor", "content": f"Execution result: {result}"}],
        }
        

  

   
