"""
LLM factory for experiment runner.
Creates LLM instances for different providers based on model name.
"""
import os
import sys
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
import src.agents.planner as planner_mod
import src.agents.critic as critic_mod
import src.core.llm as llm_mod
from src.tools.web_tools import web_tools



REBUGGER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../rebugger-agent"))
if REBUGGER_DIR not in sys.path:
    sys.path.insert(0, REBUGGER_DIR)

def create_llm(model_name: str, temperature: float = 0.0, model_registry: dict = None):
    """
    Create a raw LLM instance (no tools bound) for the given model name.
    model_registry: dict from config.yaml model_registry section.
    """
    if model_registry and model_name in model_registry:
        cfg = model_registry[model_name]
        provider = cfg["provider"]
        model_id = cfg["model_id"]
        base_url = cfg.get("base_url")
    else:
        provider, model_id, base_url = _infer_provider(model_name)

    if provider == "google":
        llm = ChatGoogleGenerativeAI(
            model=model_id,
            temperature=temperature,
            google_api_key=os.environ.get("GEMINI_API_KEY"),
        )
    elif provider == "anthropic":
        llm = ChatAnthropic(
            model=model_id,
            temperature=temperature,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
    elif provider in ("openai", "together", "openrouter"):
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
        elif provider == "together":
            api_key = os.environ.get("TOGETHER_API_KEY")
        else:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            base_url = base_url or "https://openrouter.ai/api/v1"

        kwargs = dict(
            model=model_id,
            temperature=temperature,
            api_key=api_key,
        )
        if base_url:
            kwargs["base_url"] = base_url
        if provider == "together":
            kwargs["extra_body"] = {"reasoning": {"enabled": False}}
        if provider == "openrouter":
            kwargs["default_headers"] = {
                "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "http://localhost"),
                "X-Title": os.environ.get("OPENROUTER_APP_NAME", "ReBugger Agent Evaluation"),
            }
        llm = ChatOpenAI(**kwargs)
    else:
        raise ValueError(f"Unknown provider '{provider}' for model '{model_name}'")

    llm._rebugger_provider = provider
    llm._rebugger_model_id = model_id
    return llm


def _infer_provider(model_name: str):
    """Infer (provider, model_id, base_url) from model name prefix."""
    name = model_name.lower()
    if name.startswith("openrouter/"):
        return "openrouter", model_name.split("/", 1)[1], "https://openrouter.ai/api/v1"
    elif "/" in model_name:
        return "openrouter", model_name, "https://openrouter.ai/api/v1"
    elif name.startswith("or-"):
        return "openrouter", model_name[3:], "https://openrouter.ai/api/v1"
    if name.startswith("gemini"):
        return "google", model_name, None
    elif name.startswith("claude"):
        return "anthropic", model_name, None
    elif name.startswith("gpt") or name.startswith("o1") or name.startswith("o3"):
        return "openai", model_name, None
    elif name.startswith("qwen"):
        return "together", model_name, "https://api.together.xyz/v1"
    else:
        raise ValueError(
            f"Cannot infer provider for model '{model_name}'. "
            "Add it to model_registry in config.yaml."
        )


def bind_tools_for_planner(llm):
    """Bind web_tools to an LLM for use as planner."""
    provider = getattr(llm, "_rebugger_provider", None)
    if provider == "openrouter":
        return llm.bind_tools(web_tools, tool_choice="required")
    if provider == "together":
        return llm.bind_tools(web_tools, tool_choice="required")
    return llm.bind_tools(web_tools, tool_choice="any")


def bind_tools_for_critic(llm):
    """Bind critic_tools to an LLM for use as critic."""
    from src.tools.critic_tools import critic_tools
    provider = getattr(llm, "_rebugger_provider", None)
    if provider == "openrouter":
        return llm.bind_tools(critic_tools, tool_choice="required")
    if provider == "together":
        return llm.bind_tools(critic_tools, tool_choice="required")
    return llm.bind_tools(critic_tools, tool_choice="any")


def setup_experiment_models(planner_model: str, critic_model: str = None, temperature: float = 0.0, model_registry: dict = None):
    """
    Create and monkey-patch planner/critic LLMs into the agent modules.
    Must be called before running the graph.

    Returns (planner_llm_with_tools, critic_llm_with_tools_or_None)
    """
    planner_llm = create_llm(planner_model, temperature=temperature, model_registry=model_registry)
    planner_with_tools = bind_tools_for_planner(planner_llm)
    llm_mod.llm_with_tools = planner_with_tools
    planner_mod.llm_with_tools = planner_with_tools
    critic_with_tools = None
    if critic_model:
        critic_llm = create_llm(critic_model, temperature=temperature, model_registry=model_registry)
        critic_with_tools = bind_tools_for_critic(critic_llm)
        llm_mod.critic_llm_with_tools = critic_with_tools
        critic_mod.critic_llm_with_tools = critic_with_tools

    return planner_with_tools, critic_with_tools
