import os
import re
from pathlib import Path
from urllib.parse import urlparse
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from src.utils.logger import get_logger
logger = get_logger("memory")
AGENT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAG_SEARCH_K = 3
DEFAULT_RAG_MIN_SIMILARITY = 0.72
DEFAULT_RAG_MAX_SUCCESS_CASES = 1
DEFAULT_ACTION_SUMMARY_CHARS = 1800
DEFAULT_ACTION_SENTENCE_CHARS = 300
DEFAULT_INPUT_VALUE_CHARS = 200
DEFAULT_MAX_ACTION_STEPS = 20
ALLOWED_REUSABLE_INPUT_LABELS = {"email", "password", "username", "selector_hint"}


class BgeM3Embeddings(Embeddings):
    """LangChain-compatible wrapper for the BAAI/bge-m3 sentence-transformer."""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name, trust_remote_code=True)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]


def resolve_persist_dir(persist_dir: str | None = None) -> str:
    raw_dir = persist_dir or os.getenv("REBUGGER_CHROMA_DIR", "./data/chroma_db_planner_rag_critic")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = AGENT_ROOT / path
    return str(path.resolve())


class MemoryManager:
    def __init__(self, persist_dir: str | None = None):
        persist_dir = resolve_persist_dir(persist_dir)
        os.makedirs(persist_dir, exist_ok=True)
        embedding_model = os.getenv("REBUGGER_EMBEDDING_MODEL", "BAAI/bge-m3")
        self.persist_dir = persist_dir
        self.vector_db = Chroma(
            persist_directory=persist_dir,
            embedding_function=BgeM3Embeddings(model_name=embedding_model),
            collection_metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Memory manager initialized",
            extra={"data": {"persist_dir": persist_dir, "embedding_model": embedding_model}},
        )

    def get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def save_task_to_memory(self, state: dict):
        """Save a completed bug reproduction attempt for future RAG retrieval."""
        history = state.get("history") or []
        if not history:
            logger.warning("Skipping memory save: missing history")
            return
        if not state.get("bug_report") or not state.get("root_url"):
            logger.warning("Skipping memory save: missing bug_report or root_url")
            return

        bug_desc = state["bug_report"]
        domain = self.get_domain(state["root_url"])
        status = "success" if state.get("is_reproduced") else "failed"
        action_summary = self._build_action_summary(history)
        reusable_inputs = self._extract_reusable_inputs(history)

        self.vector_db.add_texts(
            texts=[bug_desc],
            metadatas=[{
                "domain": domain,
                "status": status,
                "actions": action_summary,
                "action_summary": action_summary,
                "reusable_inputs": reusable_inputs,
                "url": state["root_url"],
            }],
        )
        logger.info(
            "Experience saved to memory",
            extra={"data": {"domain": domain, "status": status, "bug_desc": bug_desc[:100]}},
        )

    def search_similar_experiences(
        self,
        bug_desc: str,
        root_url: str,
        search_k: int = DEFAULT_RAG_SEARCH_K,
        min_similarity: float = DEFAULT_RAG_MIN_SIMILARITY,
        max_success_cases: int = DEFAULT_RAG_MAX_SUCCESS_CASES,
    ):
        domain = self.get_domain(root_url)

        try:
            results = self.vector_db.similarity_search_with_score(
                bug_desc,
                k=max(search_k, max_success_cases),
                filter={"$and": [{"domain": domain}, {"status": "success"}]},
            )
        except Exception:
            logger.warning("Falling back to domain-only memory filter", exc_info=True)
            results = self.vector_db.similarity_search_with_score(
                bug_desc,
                k=max(search_k, max_success_cases),
                filter={"domain": domain},
            )

        success_cases = []
        for res, distance in results:
            if res.metadata.get("status") != "success":
                continue
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            if similarity < min_similarity:
                continue
            case = {
                "desc": res.page_content,
                "actions": res.metadata.get("action_summary") or res.metadata.get("actions", ""),
                "reusable_inputs": res.metadata.get("reusable_inputs", ""),
                "similarity": similarity,
            }
            success_cases.append(case)
            print("SUCCESS CASES: \n", case["desc"], "\nACTIONS: ", case["actions"], "\nREUSABLE INPUTS: ", case["reusable_inputs"], "\nSIMILARITY: ", case["similarity"])
            if len(success_cases) >= max_success_cases:
                break

        logger.info("Memory search completed", extra={"data": {
            "domain": domain,
            "success_cases": len(success_cases),
            "search_k": search_k,
            "min_similarity": min_similarity,
            "max_success_cases": max_success_cases,
        }})
        print("SUCCESS CASES COUNT: ", len(success_cases))
        return success_cases, []

    def _build_action_summary(self, history: list[dict]) -> str:
        steps = []
        for item in history:
            if not isinstance(item, dict) or item.get("role") != "planner":
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            for sentence in self._split_sentences(content):
                normalized = self._normalize_action_sentence(sentence)
                if normalized and normalized not in steps:
                    steps.append(normalized)
                if len(steps) >= DEFAULT_MAX_ACTION_STEPS:
                    break
            if len(steps) >= DEFAULT_MAX_ACTION_STEPS:
                break

        if not steps:
            return ""

        summary = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
        return self._truncate(summary, DEFAULT_ACTION_SUMMARY_CHARS)

    def _extract_reusable_inputs(self, history: list[dict]) -> str:
        inputs = []
        seen = set()
        patterns = [
            re.compile(r"with value:\s*'([^']+)'", re.IGNORECASE),
            re.compile(r'with value:\s*"([^"]+)"', re.IGNORECASE),
            re.compile(r"with target URL:\s*'([^']+)'", re.IGNORECASE),
            re.compile(r'with target URL:\s*"([^"]+)"', re.IGNORECASE),
        ]

        for item in history:
            if not isinstance(item, dict) or item.get("role") != "planner":
                continue
            content = str(item.get("content", ""))
            for sentence in self._split_sentences(content):
                for pattern in patterns:
                    for match in pattern.finditer(sentence):
                        value = match.group(1).strip()
                        if not self._is_reusable_value(value, sentence):
                            continue
                        label = self._label_reusable_value(sentence, value)
                        if label not in ALLOWED_REUSABLE_INPUT_LABELS:
                            continue
                        key = (label, value)
                        if key in seen:
                            continue
                        seen.add(key)
                        inputs.append(f"- {label}: {value}")
                        if len(inputs) >= 10:
                            return "\n".join(inputs)

                if "selector" in sentence.lower() or "xpath" in sentence.lower():
                    for value in self._extract_selector_hints(sentence):
                        if not self._is_reusable_value(value, sentence):
                            continue
                        key = ("selector_hint", value)
                        if key in seen:
                            continue
                        seen.add(key)
                        inputs.append(f"- selector_hint: {value}")
                        if len(inputs) >= 10:
                            return "\n".join(inputs)

        return "\n".join(inputs)

    def _extract_selector_hints(self, sentence: str) -> list[str]:
        selectors = []
        selector_patterns = [
            re.compile(r"(//[^\s,.;]+)"),
            re.compile(r"((?:#[A-Za-z][\w-]*|\.[A-Za-z][\w-]*)(?:[ >.#:\[\]\w='\"-]*)?)"),
        ]
        for pattern in selector_patterns:
            for match in pattern.finditer(sentence):
                value = match.group(1).strip().strip("'\"")
                if value:
                    selectors.append(value)
        return selectors

    def _split_sentences(self, content: str) -> list[str]:
        content = re.sub(r"\s+", " ", content).strip()
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if s.strip()]

    def _normalize_action_sentence(self, sentence: str) -> str:
        sentence = re.sub(r"\s+with value:\s*'[^']*'", "", sentence, flags=re.IGNORECASE)
        sentence = re.sub(r'\s+with value:\s*"[^"]*"', "", sentence, flags=re.IGNORECASE)
        sentence = re.sub(r"\s+with target URL:\s*'[^']*'", "", sentence, flags=re.IGNORECASE)
        sentence = re.sub(r'\s+with target URL:\s*"[^"]*"', "", sentence, flags=re.IGNORECASE)
        sentence = sentence.strip(" .")
        if not sentence:
            return ""
        return self._truncate(sentence[0].upper() + sentence[1:] + ".", DEFAULT_ACTION_SENTENCE_CHARS)

    def _is_reusable_value(self, value: str, context: str) -> bool:
        if not value or len(value) > DEFAULT_INPUT_VALUE_CHARS:
            return False
        lowered_context = context.lower()
        lowered_value = value.lower()
        blocked_context_terms = [
            "api_key", "api key", "token", "cookie", "session",
            "authorization", "bearer", "jwt", "otp", "2fa",
            "verification code", "reset code", "secret",
        ]
        if any(term in lowered_context for term in blocked_context_terms):
            return False
        if lowered_value.startswith("data:image") or "base64," in lowered_value:
            return False
        if value.startswith("eyJ") and value.count(".") >= 2:
            return False
        if len(value) >= 48 and re.fullmatch(r"[A-Za-z0-9_\-+/=]+", value):
            return False
        return True

    def _label_reusable_value(self, context: str, value: str) -> str:
        text = context.lower()
        if "password" in text:
            return "password"
        if "username" in text or "user name" in text:
            return "username"
        if "email" in text or "@" in value:
            return "email"
        if "selector" in text or "xpath" in text or value.startswith(("//", "#", ".")):
            return "selector_hint"
        return "value"

    def _truncate(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."


_memory_managers: dict[str, MemoryManager] = {}


def get_memory_manager(persist_dir: str | None = None) -> MemoryManager:
    resolved_dir = resolve_persist_dir(persist_dir)
    if resolved_dir not in _memory_managers:
        _memory_managers[resolved_dir] = MemoryManager(resolved_dir)
    return _memory_managers[resolved_dir]

memory_manager = get_memory_manager()
