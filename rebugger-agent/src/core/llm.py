from src.core.config import settings
from src.core.llm_factory import bind_tools_for_provider, create_llm
from src.tools.web_tools import web_tools
from src.tools.critic_tools import critic_tools


planner_llm = create_llm(
    settings.PLANNER_MODEL_NAME,
    provider=settings.PLANNER_PROVIDER,
    temperature=settings.TEMPERATURE,
)

critic_llm = create_llm(
    settings.CRITIC_MODEL_NAME,
    provider=settings.CRITIC_PROVIDER,
    temperature=settings.TEMPERATURE,
)

llm_with_tools = bind_tools_for_provider(planner_llm, web_tools, role="planner")
critic_llm_with_tools = bind_tools_for_provider(critic_llm, critic_tools, role="critic")
