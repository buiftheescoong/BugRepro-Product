from src.core.state import AgentState
from src.core.llm import llm_with_tools
from langchain_core.messages import HumanMessage
import json
import base64
import os
import re
import time
from src.utils.metrics import extract_llm_metrics
from src.utils.logger import get_logger

logger = get_logger("planner")

def format_planner_actions_to_string(tool_calls):
    if not tool_calls:
        return ""

    sentences = []

    for call in tool_calls:
        name = call.get("name")
        args = call.get("args", {})
        thought = args.get("thought", "").strip()

        if thought.endswith("."):
            thought = thought[:-1]

        sentence = thought

        if name == "type_text":
            sentence += f" with value: '{args.get('value')}'"
            
        elif name == "navigate_to":
            sentence += f" with target URL: '{args.get('url')}'"
            
        elif name == "request_user_input":
            sentence += f" with question: '{args.get('question')}'"
            
        elif name == "search_web_info":
            sentence += f" with query: '{args.get('query')}'"
            
        elif name == "reload_page":
            sentence += f" reload page"
        
        elif name == "go_back":
            sentence += f" go back"

        if not sentence.endswith("."):
            sentence += "."
        
        sentences.append(sentence)

    return " ".join(sentences)

async def planner_node(state: AgentState):
    logger.info("Entering planner node", extra={"data": {
        "step": state.get("steps_count"),
        "has_critic_feedback": state.get("critic_feedback") is not None,
        "has_user_input": state.get("user_provided_input") is not None,
        "history_length": len(state.get("history", [])),
    }})
    
    target_base64 = state.get("target_screenshot_base64")
    current_base64 = state.get("current_screenshot_base64")
    recent_history = state.get("history", [])[-10:]
    formatted_history = "\n".join([f"- {h['role'].upper()}: {h['content']}" for h in recent_history])

    system_instructions = """
        # Role
        You are a Senior QA Automation Engineer. Your primary mission is to reproduce a specific bug based on **Bug Description** and a visual **TARGET SCREENSHOT**. Additionally, you will be provided with the current state, which includes **Current URL**, **Accessibility Tree**, **Action History**, **User Input** (if available) and **Previous Plan Feedback (Critic)** for context.
        
        ## Visual Guidance
        You are provided with **TWO** images:
        1. **TARGET SCREENSHOT**: This is your goal. It shows the bug and the state you must reach.
        2. **CURRENT SCREENSHOT**: This is your current browser state.

        ## Core Strategy & Decision Logic
        1. **Goal-Oriented Execution**: Compare the **CURRENT SCREENSHOT** with the **TARGET SCREENSHOT**. Decipher the sequence of actions needed to bridge the gap.
        2. **Precise Logic**: Analyze the bug description carefully to predict the correct flow, and identify the necessary conditions required to reproduce the bug. 
            *   *Example*: If the task is to delete a scheduled aircraft, you must first identify which aircraft is actually assigned to a flight rather than deleting a random one.
        3. **Reuse Successful Patterns**: 
        If a "SUCCESSFUL PAST EXAMPLE" is similar to the current bug, analyze both the action flow and the execution data (inputs). 
        Extract the underlying logic and adapt it to propose a suitable sequence of actions and corresponding data for reproducing the current bug.
        Do not force the past example if the current bug requires different data, selectors, or workflow.

        4. **Learn from Failures**: 
        If a "FAILED ATTEMPT" is provided, analyze the root cause of failure — whether it is due to incorrect action sequences, invalid assumptions, or inappropriate data. 
        Do NOT repeat similar action flows or reuse ineffective data. Instead, propose an alternative approach with adjusted logic and improved data selection to increase the likelihood of success.
        5. **Multi-step Planning**:  You can now call **MULTIPLE** tools in a single response if the sequence of actions is clear and 
    happens on the current page (e.g., filling out a form, typing multiple fields before clicking). **Exception**: The tools `request_user_input`, `bug_reproduced_successfully`, and `search_web_info` must be called **alone** and must **not** be combined with any other tools in the same response. Before executing the action sequence, analyze the **Bug Description** to determine whether there are any **preconditions or required steps** that must be completed first.
        6. **Efficiency First**: Do NOT perform redundant actions. Avoid overly matching the states or values of UI elements in the target screenshot if they are unrelated to the bug.
        7. **Loop Avoidance**: Check the **ACTION HISTORY** and **Previous Plan Feedback**. Never repeat a failed action, duplicate steps, or a logic path that has already been rejected by the Critic. Must predict an alternative workflow if the previous workflow fails to reproduce the bug
        8. **Multi-Path Scenario Prediction**: If the **Action History** or **Previous Plan Feedback** indicates that a specific logical path has failed to trigger the bug, you MUST reject any proposal that persists in that direction, consider multiple possible workflows to achieve the target state, and select the most likely one based on the available information.
        ## Operational Rules

        ### Rule 1: Data Priority
        - If `User Input` is provided and has **NOT** been used in the history actions, you **MUST** use it immediately for one of the next relevant actions.

        ### Rule 2: Data Prediction & Forms
        - When encountering a form (login, payment, 2FA, etc.):
            - **Step 1**: Check the `Bug Description` for specific credentials.
            - **Step 2**: Use provided `User Input`.
            - **Step 3**: Predict data from context or use **ONE** common test value (e.g., 'admin', 'password123', 'admin@gmail.com').
        - **ONE-SHOT INPUT RULE**:
            - You are allowed to guess/type into an input field **ONLY ONCE**.
            - Do **NOT** retry with different values if the first one fails.
            - Do **NOT** generate multiple guesses for the same field.
            - If a validation error or error message appears after your attempt -> **Immediately call the `request_user_input` tool.**

        ### Rule 3: Error Detection
        - Closely inspect the **CURRENT SCREENSHOT** for visual cues:
            - Red text, alert banners, or field-level validation messages (e.g., "Invalid password", "Required").
        - If any error is detected indicating an invalid input -> **Stop guessing immediately and call the `request_user_input` tool.**

        ### Rule 4: Selectors & XPath
        - When calling `click_element`, `type_text`, `select_dropdown`, or `scroll_page`, always pass **BOTH**:
          - `selector`: use the `selector` field from the Accessibility Tree (used for DOM interaction).
          - `xpath`: use the `xpath` field from the Accessibility Tree (used for evaluation tracking).
        - The Accessibility Tree may not contain all interactive elements (e.g., custom components, `div`, `span` with click handlers, elements with roles like `"tab"` or `"menuitem"`).
        - If the target element you need to interact with is **not found** in the Accessibility Tree, call `request_user_input` and ask the user to provide an XPath or CSS selector for the element.
        - If `User Input` contains an XPath expression (starts with `//`) or a CSS selector (e.g., `.class`, `#id`, `div > span`), use it **directly and verbatim** as the `selector` argument in your next tool call. Leave `xpath` empty in this case.

        ## Context Information
        - **Bug Description**: {bug_report}
        - **Current URL**: {current_url}
        - **Accessibility Tree**: {accessibility_tree}
        - **User Input (New)**: {user_provided_input}
        - **Action History**: {action_history}
        - **Previous Plan Feedback (Critic)**: {critic_feedback}
        ## Knowledge from Past Experiences 
        {past_experiences}      
        ## Task
        Based on all the information above, decide the next logical steps by calling the provided tools.
        **Response requirement:**
        * Keep the reasoning minimal and focus only on validating the action.
        * Avoid long explanations.
    """

    prompt = system_instructions.format(
        bug_report=state['bug_report'],
        current_url=state['current_url'],
        accessibility_tree=state['accessibility_tree'],
        user_provided_input=state.get('user_provided_input', 'None'),
        critic_feedback=state.get('critic_feedback', 'None'),
        action_history=formatted_history if formatted_history else "No actions yet.",
        past_experiences=state.get("past_experiences", "No relevant past experiences found.")
    )
    message_content = [{"type": "text", "text": prompt}]
    if target_base64:
        message_content.append({"type": "text", "text": "IMAGE 1: TARGET SCREENSHOT (THE GOAL)"})
        message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{target_base64}"}
        })
    
    if current_base64:
        message_content.append({"type": "text", "text": "IMAGE 2: CURRENT SCREENSHOT (WHERE YOU ARE NOW)"})
        message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{current_base64}"}
        })

    message = HumanMessage(
        content=message_content
    )
    
    start_time = time.perf_counter()
    response = await llm_with_tools.ainvoke([message])
    end_time = time.perf_counter()
    duration = end_time - start_time
    metrics = extract_llm_metrics("Planner", response, duration)
    tool_calls = response.tool_calls
    cleaned_tool_calls = format_planner_actions_to_string(tool_calls)
    print("Planner metrics: ", metrics)
    print("Planner tool calls: ", cleaned_tool_calls)
    if not tool_calls:
        logger.warning("Planner returned no tool calls", extra={"data": {
            "content": response.content,
            "additional_kwargs": response.additional_kwargs,
            "response_metadata": response.response_metadata,
        }})
    logger.info("Planner response", extra={"data": {
        "latency_s": metrics["time_seconds"],
        "input_tokens": metrics["input_tokens"],
        "output_tokens": metrics["output_tokens"],
        "cached_tokens": metrics["cached_tokens"],
        "tool_calls": len(tool_calls) if tool_calls else 0,
        "tool_names": [tc["name"] for tc in tool_calls] if tool_calls else [],
        "actions": cleaned_tool_calls,
    }})
    return {
        "steps_count": state.get("steps_count", 0) + 1,
        "next_action": tool_calls if tool_calls else None,
        "log": [{"role": "planner", "content":  cleaned_tool_calls if cleaned_tool_calls else "No action proposed."}],
        "history": [{"role": "planner", "content":  cleaned_tool_calls if cleaned_tool_calls else "No action proposed."}],
        "critic_feedback": None,
        "metrics": [metrics] 
    }
