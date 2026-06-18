from src.core.state import AgentState
from src.core.llm import critic_llm_with_tools
from src.tools.critic_tools import critic_tools
from langchain_core.messages import HumanMessage
import json
import base64
import os
import re
import time
from src.utils.metrics import extract_llm_metrics
from src.utils.parser import clean_actions_for_critic
from src.utils.logger import get_logger

logger = get_logger("critic")

async def critic_node(state: AgentState):
    proposed_action = state.get("next_action")
    cleaned_data = clean_actions_for_critic(proposed_action)
    logger.info("Entering critic node", extra={"data": {
        "review_count": state.get("review_count", 0),
        "action_count": len(proposed_action) if proposed_action else 0,
    }})

    if not cleaned_data:
        print("Critic No action")
        return {
            "critic_feedback": None,
            "history": [{"role": "critic", "content": "No proposed action"}],
            "log": [{"role": "critic", "content": "No proposed action, assuming approval."}]
        }
    else:
        if len(cleaned_data) > 1:
            for action in cleaned_data:
                if (action["name"] in ["request_user_input", "bug_reproduced_successfully", "search_web_info"]):
                    logger.warning("Invalid batch: exclusive tool cannot be combined", extra={"data": {
                        "tool": action["name"],
                        "batch_size": len(cleaned_data),
                    }})
                    print("Critic Invalid batch")
                    return {
                        "critic_feedback": f"Invalid batch: {action['name']} cannot be combined with other tools.",
                        "history": [{"role": "critic", "content": f"Invalid batch: {action['name']} cannot be combined with other tools."}],
                        "log": [{"role": "critic", "content": f"Invalid batch: {action['name']} cannot be combined with other tools."}]
                    }
    target_base64 = state.get('target_screenshot_base64')
    current_base64 = state.get('current_screenshot_base64')

    
    recent_history = state.get("history", [])[-10:]
    formatted_history = "\n".join([f"- {h['role'].upper()}: {h['content']}" for h in recent_history])

    system_instructions  = """
        # SYSTEM PROMPT: SENIOR QA AUTOMATION ENGINEER 
        ## Role & Mission
        You are a **Senior QA Automation Engineer** acting as a **Critic Node**. Your mission is to audit the **PROPOSED ACTION SEQUENCE** (one or more steps). You must ensure the bug reproduction path is logical, efficient, and strictly adheres to the bug report conditions. Additionally, you will be provided with the Goal Context, including **Bug Description** and **Target Screenshot**, along with the current state, which includes **Current URL**, **Accessibility Tree**, **Action History**, **User Input** (if available), and **Proposed Action** for context.
        ## Visual Guidance
        * **TARGET SCREENSHOT:** The goal state. It shows the bug and the UI state that must be reached.
        * **CURRENT SCREENSHOT:** The live state of the browser at this moment.
        ---
       
        ## Critical Audit Rules

        ### 1. Logical Alignment & Pre-conditions
        * Does the action align with the reproduction flow? 
        * Are there any conditions mentioned in the bug description that must be satisfied before performing this sequence?
        * **Mandatory Check:** Verify specific conditions and actions mentioned in the **Bug Description**. 
            * *Example:* If the bug triggers when "selecting an aircraft with 0 seats," but the Planner selects a random aircraft, you must **REJECT**.

        ### 2. Redundancy & Loop Detection
        * Analyze the current sequence of actions against the **Action History** to see if the proposed actions repeat failed or ineffective steps; or the current flow mimics a previously attempted pattern that failed to reproduce the bug, you must **REJECT** and demand a different approach (e.g., try different data, explore alternative paths, request user for more information, etc).

        ### 3. Essential vs. Cosmetic Actions
        * Focus only on the **functional path** to trigger the bug.
        * **Constraint:** Do not waste actions trying to match UI elements that are irrelevant to the bug (e.g., matching the value of the current aircraft number element when it is unrelated to the bug about the incorrect display of the current flight numbe a footer text or a side banner or etc) just to make the UI look identical to the Target Screenshot.

        ### 4. Element & Selector Validation if the **Proposed Action** is a sequence of web interaction actions or a single web interaction action
        * Chain Reaction: Does the order of actions make sense?
        * Navigation Alert: If an action triggers navigation (e.g., clicking a link/submit), ensure it is the **LAST** action in the sequence. You cannot interact with elements of the current page after a navigation-triggering action.
        * **Selector Source Check**:
            * If the selector is a `[data-agent-id="..."]` selector, verify it exists in the **Accessibility Tree**.
            * If the selector is an XPath (starts with `//` or `..`) or a custom CSS selector (e.g., `.class`, `#id`, `div > span`) that was provided by the user via **User Input**, **trust it and do NOT reject it** just because it is absent from the Accessibility Tree. The user provided it precisely because the element is not captured by the tree.
        * Check whether the target element is being covered by any popup or modal. If a popup or modal is open and the target element is not inside it, the popup or modal must be closed before interacting with the target element.
        * If the **Proposed Action** includes "type_text", should the data mentioned in the bug description be used (if available), or should the data provided by the user in **User Input** be used instead (if available) or ensure the data is valid and satisfies any conditions specified in the bug description?
        
        ### 5. Final Success Verification
        * When the Planner claims "Success":    
            * **Logic over Visuals:** Do not approve just because the UI "looks" similar to the Target Screenshot. 
            * Ensure all mandatory logical steps and edge-case conditions from the **Bug Description** were actually executed.

        ---

        ## Current Context
        * **Bug Description:** {bug_report}
        * **Current URL:** {current_url}
        * **Accessibility Tree:** {accessibility_tree}
        * **User Input:** {user_provided_input}
        * **Action History:** {action_history}
        * **Proposed Action:** {proposed_action}
        ---

        ### Instructions:
        1. Provide a concise, step-by-step reasoning for the whole sequence.
        2. If the sequence is logical, call `approve_action` tool.
        3. If ANY step in the sequence is flawed, call `reject_action` tool with specific feedback.
        4. If you cannot validate the action due to dynamic data (gold prices, dates, exchange rates, etc.), call `search_web_info` tool to gather necessary info before making a decision.
        **Strict Requirement:** Minimal reasoning. Focus on validation. No long preambles.
    """
    prompt = system_instructions.format(
        bug_report=state['bug_report'],
        current_url=state['current_url'],
        accessibility_tree=state['accessibility_tree'],
        user_provided_input=state.get('user_provided_input', 'None'),
        action_history=formatted_history if formatted_history else "No actions yet.",
        proposed_action=json.dumps(cleaned_data, indent=2)
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
    response = await critic_llm_with_tools.ainvoke([message])
    end_time = time.perf_counter()
    
    duration = end_time - start_time
    metrics = extract_llm_metrics("Critic", response, duration)
    logger.info("Critic response", extra={"data": {
        "latency_s": metrics["time_seconds"],
        "input_tokens": metrics["input_tokens"],
        "output_tokens": metrics["output_tokens"],
        "cached_tokens": metrics["cached_tokens"],
    }})

    tool_calls = response.tool_calls
    print("Critic metrics: ", metrics)
    print("Critic tool calls: ", tool_calls)
    if not tool_calls:
        logger.warning("Critic returned no tool calls, assuming approval")
        return {"critic_feedback": None, 
                "history": [{"role": "critic", "content": "No response."}],
                "log": [{"role": "critic", "content": "No response, assuming approval."}],
                "metrics": [metrics],
                "steps_count": state.get("steps_count", 0) + 1
        }

    
    tool_call = tool_calls[0]
    name = tool_call["name"]
    args = tool_call["args"]

    if name == "reject_action":
        feedback = args.get("feedback", "Invalid action.")
        logger.info("Critic: REJECTED", extra={"data": {"feedback": feedback}})
        return {
            "critic_feedback": feedback,
            "review_count": state.get("review_count", 0) + 1,
            "history": [{"role": "critic", "content": f"REJECTED: {feedback}"}],
            "log": [{"role": "critic", "content": f"REJECTED: {feedback}"}],
            "metrics": [metrics],
            "steps_count": state.get("steps_count", 0) + 1
        }
    
    elif name == "approve_action":
        logger.info("Critic: APPROVED", extra={"data": {"reason": args.get("reason")}})
        return {
            "critic_feedback": None, 
            "review_count": 0,
            "history": [{"role": "critic", "content": f"APPROVED"}],
            "log": [{"role": "critic", "content": f"APPROVED: {args.get('reason')}"}],
            "metrics": [metrics],
            "steps_count": state.get("steps_count", 0) + 1,
            "user_provided_input": None
        }
    else:
        logger.info("Critic: SEARCH", extra={"data": {"query": args.get("query")}})
        return {
            "search_action": tool_call, 
            "history": [{"role": "critic", "content": f"Searching: {args['query']}"}],
            "log": [{"role": "critic", "content": f"Searching: {args['query']}"}],
            "metrics": [metrics],
            "steps_count": state.get("steps_count", 0) + 1
        }
 