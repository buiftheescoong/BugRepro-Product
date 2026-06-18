from __future__ import annotations
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from src.core.config import settings


SUPPORTED_PROVIDERS = {"gemini", "google", "openai", "openrouter", "together"}

MODEL_REGISTRY: dict[str, dict[str, str]] = {
    "gemini-2.5-flash": {
        "provider": "gemini",
        "model_id": "gemini-2.5-flash",
    },
    "openrouter/gemini-2.5-flash": {
        "provider": "openrouter",
        "model_id": "google/gemini-2.5-flash",
        "base_url": settings.OPENROUTER_BASE_URL,
    },
    "gpt-5.4-mini": {
        "provider": "openai",
        "model_id": "gpt-5.4-mini",
    },
    "gemma-4-31b-it": {
        "provider": "together",
        "model_id": "google/gemma-4-31B-it",
        "base_url": settings.TOGETHER_BASE_URL,
    }
}


def create_llm(model_name: str | None, provider: str | None = None, temperature: float | None = None):
    resolved_provider, model_id, base_url = resolve_model(model_name, provider)
    temperature = settings.TEMPERATURE if temperature is None else temperature

    if resolved_provider in ("gemini", "google"):
        api_key = _required_key(settings.GEMINI_API_KEY, "GEMINI_API_KEY", resolved_provider)
        llm = ChatGoogleGenerativeAI(
            model=model_id,
            temperature=temperature,
            google_api_key=api_key,
        )
    elif resolved_provider == "openai":
        api_key = _required_key(settings.OPENAI_API_KEY, "OPENAI_API_KEY", resolved_provider)
        kwargs: dict[str, Any] = {
            "model": model_id,
            "temperature": temperature,
            "api_key": api_key,
        }
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        llm = ChatOpenAI(**kwargs)
    elif resolved_provider == "openrouter":
        api_key = _required_key(settings.OPENROUTER_API_KEY, "OPENROUTER_API_KEY", resolved_provider)
        llm = ChatOpenAI(
            model=model_id,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url or settings.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": settings.OPENROUTER_SITE_URL,
                "X-OpenRouter-Title": settings.OPENROUTER_APP_NAME,
            },
        )
    elif resolved_provider == "together":
        api_key = _required_key(settings.TOGETHER_API_KEY, "TOGETHER_API_KEY", resolved_provider)
        llm = ChatOpenAI(
            model=model_id,
            temperature=temperature,
            api_key=api_key,
            base_url=base_url or settings.TOGETHER_BASE_URL,
            extra_body={"reasoning": {"enabled": False}},
        )
    else:
        raise ValueError(f"Unsupported provider '{resolved_provider}'. Supported providers: {sorted(SUPPORTED_PROVIDERS)}")

    llm._rebugger_provider = resolved_provider
    llm._rebugger_model_id = model_id
    return llm


def resolve_model(model_name: str | None, provider: str | None = None) -> tuple[str, str, str | None]:
    if not provider:
        raise ValueError(
            "Provider is required. Set PLANNER_PROVIDER and CRITIC_PROVIDER "
            "to one of: gemini, openai, openrouter, together."
        )
    if not model_name:
        raise ValueError("Model name is required. Set PLANNER_MODEL_NAME and CRITIC_MODEL_NAME.")

    resolved_provider = _normalize_provider(provider)
    if resolved_provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider '{provider}'. Supported providers: {SUPPORTED_PROVIDERS}")
    if model_name in MODEL_REGISTRY:
        cfg = MODEL_REGISTRY[model_name]
        registry_provider = _normalize_provider(cfg["provider"])
        if registry_provider != resolved_provider:
            raise ValueError(
                f"Model registry entry '{model_name}' is configured for provider "
                f"'{registry_provider}', but provider '{resolved_provider}' was requested."
            )
        return resolved_provider, cfg["model_id"], cfg.get("base_url")

    if model_name.lower().startswith(("claude", "anthropic/")) or resolved_provider == "anthropic":
        raise ValueError("Anthropic models are not supported in the main ReBugger LLM interface.")

    return resolved_provider, _strip_provider_prefix(model_name, resolved_provider), _default_base_url(resolved_provider)


def bind_tools_for_provider(llm, tools, role: str):
    provider = getattr(llm, "_rebugger_provider", None)
    if provider in ("openrouter", "together"):
        return llm.bind_tools(tools, tool_choice="required")
    return llm.bind_tools(tools, tool_choice="any")


def _normalize_provider(provider: str) -> str:
    provider = provider.lower().strip()
    if provider == "google":
        return "gemini"
    if provider == "anthropic":
        raise ValueError("Anthropic provider is not supported in the main ReBugger LLM interface.")
    return provider


def _strip_provider_prefix(model_name: str, provider: str) -> str:
    prefixes = {
        "gemini": "gemini/",
        "google": "google/",
        "openai": "openai/",
        "openrouter": "openrouter/",
        "together": "together/",
    }
    prefix = prefixes.get(provider)
    if prefix and model_name.lower().startswith(prefix):
        return model_name.split("/", 1)[1]
    return MODEL_REGISTRY.get(model_name, {}).get("model_id", model_name)


def _default_base_url(provider: str) -> str | None:
    if provider == "openrouter":
        return settings.OPENROUTER_BASE_URL
    if provider == "together":
        return settings.TOGETHER_BASE_URL
    if provider == "openai":
        return settings.OPENAI_BASE_URL
    return None


def _required_key(value: str | None, env_name: str, provider: str) -> str:
    if not value:
        raise ValueError(f"{env_name} is required for provider '{provider}'.")
    return value
