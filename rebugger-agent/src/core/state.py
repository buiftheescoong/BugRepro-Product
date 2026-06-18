from typing import TypedDict, List, Annotated, Optional
from operator import add

class AgentState(TypedDict):
    root_url: str
    bug_report: str           
    target_screenshot: str    
    history: Annotated[List[dict], add]
    log: Annotated[List[dict], add]
    current_url: str
    current_screenshot: Optional[str]
    accessibility_tree: Optional[str]
    is_reproduced: bool       
    steps_count: int       
    next_action: Optional[List[dict]]
    wait_for_input: bool
    input_request_message: Optional[str]
    user_provided_input: Optional[str]
    critic_feedback: Optional[str]
    review_count: int
    metrics: Annotated[List[dict], add]
    search_action: Optional[dict]
    target_screenshot_base64: str
    current_screenshot_base64: Optional[str]
    past_experiences: Optional[str]