import time

def extract_llm_metrics(node_name, response, duration):
    usage = getattr(response, "usage_metadata", {})
    
    return {
        "node": node_name,
        "time_seconds": round(duration, 2),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "cached_tokens": usage.get("cache_creation_input_token_count", 0) + usage.get("cached_content_input_token_count", 0)
    }