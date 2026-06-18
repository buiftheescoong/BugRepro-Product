"""
runner.py — Run a single bug through the ReBugger agent and save results.

Usage (via run_experiment.py, or directly for testing):
    python runner.py --bug-id 4 --model gemini-2.5-flash --phase planner_ablation
"""
import os
import sys
import json
import time
import base64
import logging
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
from llm_factory import setup_experiment_models
from dotenv import load_dotenv
load_dotenv(os.path.join(REBUGGER_DIR, ".env"))

import yaml
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.core.config import settings
from src.core.graph import create_experiment_graph
from src.tools.browsers import browser_manager
from src.utils.logger import get_logger
from db_reset import reset_before_bug
from src.utils.memory_manager import get_memory_manager


# Add rebugger-agent to path
REBUGGER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../rebugger-agent"))
if REBUGGER_DIR not in sys.path:
    sys.path.insert(0, REBUGGER_DIR)

logger = get_logger("experiment.runner")

THIS_DIR = Path(__file__).resolve().parent
CONFIG_PATH = THIS_DIR / "config.yaml"

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_bug_corpus(corpus_path: str) -> dict:
    with open(corpus_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {bug["bug_id"]: bug for bug in data["bugs"]}


def load_screenshot_b64(bug_id: int, screenshots_dir: str, screenshot_map: dict) -> str | None:
    key = str(bug_id)
    filename = screenshot_map.get(key)
    if not filename:
        return None
    filepath = os.path.join(screenshots_dir, filename)
    if not os.path.exists(filepath):
        logger.warning(f"Screenshot file not found: {filepath}")
        return None
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def safe_model_dir_name(model_label: str) -> str:
    return model_label.replace("/", "__").replace("\\", "__").replace(":", "_")


def result_path(results_dir: str, model_label: str, bug_id: int) -> Path:
    return Path(results_dir) / safe_model_dir_name(model_label) / f"bug_{bug_id:03d}.json"


def log_path(results_dir: str, model_label: str, bug_id: int) -> Path:
    return Path(results_dir) / safe_model_dir_name(model_label) / f"bug_{bug_id:03d}.log"


def resolve_agent_eval_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return THIS_DIR / path


def append_need_input_skip(skip_log_path: str | Path, record: dict) -> Path:
    resolved_path = resolve_agent_eval_path(skip_log_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return resolved_path


def remove_file_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.warning(f"Could not remove skipped run log: {exc}", extra={"data": {"path": str(path)}})


def _add_run_log_handler(log_file: Path) -> logging.FileHandler:
    """Attach a plain-text FileHandler to the rebugger root logger for this run."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] [%(name)s] %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(fmt)
    logging.getLogger("rebugger").addHandler(handler)
    return handler


def _remove_run_log_handler(handler: logging.FileHandler):
    logging.getLogger("rebugger").removeHandler(handler)
    handler.close()


def get_past_experiences(
    bug_description: str,
    root_url: str,
    rag_memory_dir: str | None = None,
    rag_search_k: int = 3,
    rag_min_similarity: float = 0.72,
    rag_max_success_cases: int = 1,
) -> str:

    memory_manager = get_memory_manager(rag_memory_dir)
    success_cases, _ = memory_manager.search_similar_experiences(
        bug_description,
        root_url,
        search_k=rag_search_k,
        min_similarity=rag_min_similarity,
        max_success_cases=rag_max_success_cases,
    )
    text = ""
    if success_cases:
        text += "\n### RELEVANT SUCCESSFUL PAST EXAMPLE:\n"
        for i, c in enumerate(success_cases):
            text += f"Example {i+1} similarity: {c.get('similarity', 0):.3f}\n"
            text += f"Bug: {c['desc']}\n"
            text += f"Reusable flow:\n{c['actions']}\n"
            if c.get("reusable_inputs"):
                text += f"Reusable inputs:\n{c['reusable_inputs']}\n"
    return text

async def run_single_bug(
    bug: dict,
    planner_model: str,
    critic_model: str | None,
    critic_enabled: bool,
    rag_enabled: bool,
    root_url: str,
    screenshots_dir: str,
    screenshot_map: dict,
    results_dir: str,
    model_label: str,
    headless: bool = False,
    temperature: float = 0.2,
    max_steps: int = 33,
    model_registry: dict = None,
    phase: str = "planner_ablation",
    rag_memory_dir: str | None = None,
    rag_search_k: int = 3,
    rag_min_similarity: float = 0.72,
    rag_max_success_cases: int = 1,
    unattended: bool = False,
    need_input_skip_log: str = "./need_input_skips.jsonl",
    remove_skipped_run_log: bool = True,
) -> dict:
    """
    Run one bug through the agent. Returns result dict.
    Saves result JSON + log file automatically.
    Skips if result file already exists (resume-safe).
    """
    bug_id = bug["bug_id"]
    out_path = result_path(results_dir, model_label, bug_id)
    log_file = log_path(results_dir, model_label, bug_id)

    if out_path.exists():
        print(f"  [SKIP] Bug #{bug_id} already done — {out_path}")
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Override root_url with bug's root_url if available
    actual_root_url = bug.get("root_url", root_url)
    run_handler = _add_run_log_handler(log_file)
    settings.MAX_STEPS = max_steps
    settings.HEADLESS = headless

    print(f"\n  Running Bug #{bug_id} | planner={planner_model} | critic={critic_model or 'none'} | rag={rag_enabled} | url={actual_root_url}")
    logger.info(f"Starting bug run", extra={"data": {
        "bug_id": bug_id, "planner": planner_model,
        "critic": critic_model, "rag": rag_enabled,
        "root_url": actual_root_url,
    }})

    reset_before_bug(
        actual_root_url,
        load_config(),
        logger=logger,
        context={
            "bug_id": bug_id,
            "model_label": model_label,
            "phase": phase,
            "root_url": actual_root_url,
        },
    )
    setup_experiment_models(
        planner_model=planner_model,
        critic_model=critic_model if critic_enabled else None,
        temperature=temperature,
        model_registry=model_registry,
    )

    # Load screenshot
    screenshot_b64 = load_screenshot_b64(bug_id, screenshots_dir, screenshot_map)
    if screenshot_b64 is None:
        logger.warning(f"No screenshot for bug #{bug_id} — using empty string")
        screenshot_b64 = ""

    # Build bug description
    bug_description = bug.get("desc_en") or bug.get("desc_full") or bug.get("desc_vi", "")

    # RAG
    past_experiences = ""
    if rag_enabled:
        past_experiences = get_past_experiences(
            bug_description,
            actual_root_url,
            rag_memory_dir,
            rag_search_k=rag_search_k,
            rag_min_similarity=rag_min_similarity,
            rag_max_success_cases=rag_max_success_cases,
        )

    # Build initial state
    initial_input = {
        "bug_report": bug_description,
        "target_screenshot": "",          # local run — no B2 URL needed
        "root_url": actual_root_url,
        "history": [],
        "log": [],
        "steps_count": 0,
        "is_reproduced": False,
        "wait_for_input": False,
        "user_provided_input": None,
        "target_screenshot_base64": screenshot_b64,
        "past_experiences": past_experiences,
        "metrics": [],
        "review_count": 0,
        "critic_feedback": None,
        "search_action": None,
        "next_action": None,
    }

    thread_id = f"exp_{phase}_{model_label}_bug{bug_id}_{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}}

    wall_start = time.time()
    final_state = dict(initial_input)
    all_logs = []
    all_metrics = []
    skipped_need_input = False

    checkpoint_db = os.path.join(REBUGGER_DIR, "data", "exp_checkpoints.db")
    os.makedirs(os.path.dirname(checkpoint_db), exist_ok=True)

    try:
        async with AsyncSqliteSaver.from_conn_string(checkpoint_db) as memory:
            agent_app = create_experiment_graph(memory, critic_enabled=critic_enabled)

            # Start initial stream
            stream_input = initial_input

            while True:
                async for event in agent_app.astream(stream_input, config=config):
                    for node_name, node_output in event.items():
                        if node_name == "__end__":
                            final_state = node_output
                            continue
                        new_logs = node_output.get("log", [])
                        if new_logs:
                            all_logs.extend(new_logs)
                        new_metrics = node_output.get("metrics", [])
                        if new_metrics:
                            all_metrics.extend(new_metrics)
                        final_state.update(node_output)

                # After stream ends, check termination conditions FIRST
                if final_state.get("is_reproduced") or final_state.get("steps_count", 0) >= settings.MAX_STEPS:
                    logger.info(f"Closing browser: is_reproduced={final_state.get('is_reproduced')}, steps={final_state.get('steps_count')}")
                    await browser_manager.close_session(thread_id)
                    logger.info(f"Browser session {thread_id} closed")
                    break

                if final_state.get("wait_for_input"):
                    msg = final_state.get("input_request_message", "Agent needs input:")
                    if unattended:
                        skipped_need_input = True
                        skip_record = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "phase": phase,
                            "bug_id": bug_id,
                            "planner_model": planner_model,
                            "critic_model": critic_model,
                            "model_label": model_label,
                            "root_url": actual_root_url,
                            "question": msg,
                            "steps_count": int(final_state.get("steps_count", 0)),
                            "thread_id": thread_id,
                            "result_path": str(out_path),
                        }
                        skip_log_path = append_need_input_skip(need_input_skip_log, skip_record)
                        logger.info("Skipped run requiring user input", extra={"data": {
                            **skip_record,
                            "skip_log_path": str(skip_log_path),
                        }})
                        print(f"\n  [SKIP NEED INPUT] Bug #{bug_id} | {model_label} | logged to {skip_log_path}")
                        return {
                            "status": "skipped_need_input",
                            "bug_id": bug_id,
                            "planner_model": planner_model,
                            "critic_model": critic_model,
                            "model_label": model_label,
                            "phase": phase,
                            "root_url": actual_root_url,
                            "question": msg,
                            "steps_count": int(final_state.get("steps_count", 0)),
                            "thread_id": thread_id,
                            "skip_log_path": str(skip_log_path),
                            "result_path": str(out_path),
                        }

                    print(f"\n  [INPUT NEEDED] {msg}")
                    user_input = input("  Your input > ").strip()
                    await agent_app.aupdate_state(config, {
                        "user_provided_input": user_input,
                        "wait_for_input": False,
                        "next_action": None,
                        "input_request_message": None,
                    })
                    stream_input = None
                    logger.info("User input received, resuming agent")
                    continue

                # Other termination
                logger.info("Stream ended, exiting")
                break

    except Exception as e:
        logger.error(f"Bug run failed: {e}", exc_info=True)
        final_state["run_error"] = str(e)
    finally:
        try:
            await browser_manager.close_session(thread_id)
        except Exception as cleanup_error:
            logger.warning(f"Browser cleanup error: {cleanup_error}")
        _remove_run_log_handler(run_handler)
        if skipped_need_input and remove_skipped_run_log:
            remove_file_if_exists(log_file)

    wall_time = time.time() - wall_start

    # Use accumulated metrics
    final_state["metrics"] = all_metrics
    final_state["log"] = all_logs
    final_state["history"] = all_logs

    result = {
        "bug_id": bug_id,
        "planner_model": planner_model,
        "critic_model": critic_model,
        "critic_enabled": critic_enabled,
        "rag_enabled": rag_enabled,
        "phase": phase,
        "model_label": model_label,
        "is_reproduced": bool(final_state.get("is_reproduced", False)),
        "steps_count": int(final_state.get("steps_count", 0)),
        "total_input_tokens": sum(m.get("input_tokens", 0) for m in all_metrics),
        "total_output_tokens": sum(m.get("output_tokens", 0) for m in all_metrics),
        "total_llm_time_seconds": round(sum(m.get("time_seconds", 0) for m in all_metrics), 3),
        "total_wall_time_seconds": round(wall_time, 3),
        "llm_calls": len(all_metrics),
        "run_error": final_state.get("run_error"),
        "rag_memory_dir": rag_memory_dir,
        "rag_search_k": rag_search_k,
        "rag_min_similarity": rag_min_similarity,
        "rag_max_success_cases": rag_max_success_cases,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics_detail": all_metrics,
        "history": all_logs,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    if rag_enabled and not result["run_error"]:
        try:
            from src.utils.memory_manager import get_memory_manager

            memory_state = dict(final_state)
            memory_state["bug_report"] = bug_description
            memory_state["root_url"] = actual_root_url
            memory_state["history"] = final_state.get("history") or all_logs
            memory_state["is_reproduced"] = result["is_reproduced"]
            memory_manager = get_memory_manager(rag_memory_dir)
            memory_manager.save_task_to_memory(memory_state)
        except Exception as memory_error:
            logger.warning(f"Could not save experience to RAG memory: {memory_error}", exc_info=True)

    status = "SUCCESS" if result["is_reproduced"] else ("ERROR" if result["run_error"] else "FAILED")
    print(f"  [{status}] Bug #{bug_id} | {result['steps_count']} steps | {wall_time:.1f}s")
    logger.info("Bug run completed", extra={"data": {
        "bug_id": bug_id, "status": status,
        "steps": result["steps_count"], "wall_time": round(wall_time, 1),
    }})

    return result


def main():
    parser = argparse.ArgumentParser(description="Run a single bug through ReBugger agent")
    parser.add_argument("--bug-id", type=int, required=True)
    parser.add_argument("--model", type=str, required=True, help="Planner model name")
    parser.add_argument("--critic-model", type=str, default=None)
    parser.add_argument("--phase", type=str, default="planner_ablation",
                        choices=["planner_ablation", "critic_ablation", "full_system"])
    parser.add_argument("--no-critic", action="store_true")
    parser.add_argument("--rag", action="store_true")
    parser.add_argument("--rag-memory-dir", type=str, default=None)
    parser.add_argument("--rag-search-k", type=int, default=3)
    parser.add_argument("--rag-min-similarity", type=float, default=0.72)
    parser.add_argument("--rag-max-success-cases", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--unattended", action="store_true",
                            help="Skip runs that ask for user input and record them in the skip log")
    mode_group.add_argument("--interactive", action="store_true",
                            help="Force interactive user-input prompts even if config enables unattended mode")
    args = parser.parse_args()

    cfg = load_config()
    common = cfg["common"]
    phase_cfg = cfg[args.phase]
    execution_cfg = cfg.get("execution", {})
    unattended = bool(execution_cfg.get("unattended", False))
    if args.unattended:
        unattended = True
    elif args.interactive:
        unattended = False

    results_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), phase_cfg["results_dir"]))
    screenshots_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), common["screenshots_dir"]))
    corpus_path = os.path.abspath(os.path.join(os.path.dirname(__file__), common["bug_corpus"]))
    smap_path = os.path.abspath(os.path.join(os.path.dirname(__file__), common["screenshot_map"]))

    corpus = load_bug_corpus(corpus_path)
    with open(smap_path, "r", encoding="utf-8") as f:
        raw_smap = json.load(f)
    screenshot_map = {k: v for k, v in raw_smap.items() if not k.startswith("_")}

    bug = corpus.get(args.bug_id)
    if not bug:
        print(f"Bug #{args.bug_id} not found in corpus.")
        sys.exit(1)

    critic_enabled = not args.no_critic
    model_label = args.model

    asyncio.run(run_single_bug(
        bug=bug,
        planner_model=args.model,
        critic_model=args.critic_model,
        critic_enabled=critic_enabled,
        rag_enabled=args.rag,
        root_url=common["root_url"],
        screenshots_dir=screenshots_dir,
        screenshot_map=screenshot_map,
        results_dir=results_dir,
        model_label=model_label,
        headless=args.headless,
        temperature=common["temperature"],
        max_steps=common["max_steps"],
        model_registry=cfg.get("model_registry"),
        phase=args.phase,
        rag_memory_dir=args.rag_memory_dir,
        rag_search_k=args.rag_search_k,
        rag_min_similarity=args.rag_min_similarity,
        rag_max_success_cases=args.rag_max_success_cases,
        unattended=unattended,
        need_input_skip_log=execution_cfg.get("need_input_skip_log", "./need_input_skips.jsonl"),
        remove_skipped_run_log=execution_cfg.get("remove_skipped_run_log", True),
    ))


if __name__ == "__main__":
    main()
