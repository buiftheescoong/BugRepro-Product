import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


def _float_env(name: str, default: float) -> float:
    value = _env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}.") from exc


class Settings:
    OPENAI_API_KEY = _env("OPENAI_API_KEY")
    TOGETHER_API_KEY = _env("TOGETHER_API_KEY")
    OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
    GEMINI_API_KEY = _env("GEMINI_API_KEY")
    TAVILY_API_KEY = _env("TAVILY_API_KEY")

    OPENAI_BASE_URL = _env("OPENAI_BASE_URL")
    TOGETHER_BASE_URL = _env("TOGETHER_BASE_URL", _env("BASE_URL", "https://api.together.ai/v1"))
    OPENROUTER_BASE_URL = _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_SITE_URL = _env("OPENROUTER_SITE_URL", "http://localhost")
    OPENROUTER_APP_NAME = _env("OPENROUTER_APP_NAME", "ReBugger Agent")
    BASE_URL = TOGETHER_BASE_URL

    PLANNER_PROVIDER = _env("PLANNER_PROVIDER")
    CRITIC_PROVIDER = _env("CRITIC_PROVIDER")
    PLANNER_MODEL_NAME = _env("PLANNER_MODEL_NAME")
    CRITIC_MODEL_NAME = _env("CRITIC_MODEL_NAME")
    TEMPERATURE = _float_env("TEMPERATURE", 0.5)
    
    HEADLESS = False
    BROWSER_TIMEOUT = 30000 
    SCREENSHOT_QUALITY = 50
    
    B2_KEY_ID = _env("B2_KEY_ID")
    B2_APPLICATION_KEY = _env("B2_APPLICATION_KEY")
    B2_BUCKET_NAME = _env("B2_BUCKET_NAME")
    B2_ENDPOINT = _env("B2_ENDPOINT")
    
   
    MAX_STEPS = 32
    SCREENSHOT_DIR = "././data/screenshots"
    LOG_DIR = "././data/logs"

settings = Settings()
