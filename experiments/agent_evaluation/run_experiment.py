"""
run_experiment.py — Orchestrator for running experiments across bugs x models.

Usage:
    # Planner ablation (all models, all configured bugs)
    python run_experiment.py --phase planner_ablation

    # Single model, single bug (for testing)
    python run_experiment.py --phase planner_ablation --model gemini-2.5-flash --bug-id 4

    # Critic ablation (planner fixed)
    python run_experiment.py --phase critic_ablation

    # Full system
    python run_experiment.py --phase full_system

    # Resume after crash — skips already-done bugs automatically
    python run_experiment.py --phase planner_ablation --model gemini-2.5-flash
"""
import os
import sys
import json
import time
import asyncio
import argparse
from pathlib import Path

# Add rebugger-agent and this directory to path
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REBUGGER_DIR = os.path.abspath(os.path.join(THIS_DIR, "../../rebugger-agent"))
if REBUGGER_DIR not in sys.path:
    sys.path.insert(0, REBUGGER_DIR)
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(REBUGGER_DIR, ".env"))

import yaml
from runner import (
    run_single_bug,
    load_config,
    load_bug_corpus,
    result_path,
)


def load_screenshot_map(smap_path: str) -> dict:
    with open(smap_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def print_header(phase: str, models: list, bug_ids: list):
    print(f"\n{'='*60}")
    print(f"  EXPERIMENT: {phase.upper()}")
    print(f"  Models : {', '.join(models)}")
    print(f"  Bugs   : {len(bug_ids)} bugs")
    print(f"{'='*60}\n")


def print_progress(current: int, total: int, bug_id: int, model: str):
    print(f"\n[{current}/{total}] Bug #{bug_id} | {model}")


def resolve_execution_options(cfg: dict, args) -> dict:
    execution_cfg = cfg.get("execution", {})
    unattended = bool(execution_cfg.get("unattended", False))
    if args.unattended:
        unattended = True
    elif args.interactive:
        unattended = False

    return {
        "unattended": unattended,
        "need_input_skip_log": execution_cfg.get("need_input_skip_log", "./need_input_skips.jsonl"),
        "remove_skipped_run_log": execution_cfg.get("remove_skipped_run_log", True),
    }


async def run_phase_planner_ablation(cfg: dict, args):
    common = cfg["common"]
    phase_cfg = cfg["planner_ablation"]
    execution_options = args.execution_options

    corpus = load_bug_corpus(os.path.abspath(os.path.join(THIS_DIR, common["bug_corpus"])))
    smap = load_screenshot_map(os.path.abspath(os.path.join(THIS_DIR, common["screenshot_map"])))
    screenshots_dir = os.path.abspath(os.path.join(THIS_DIR, common["screenshots_dir"]))
    results_dir = os.path.abspath(os.path.join(THIS_DIR, phase_cfg["results_dir"]))

    bug_ids = args.bug_id_list or phase_cfg.get("bug_ids") or sorted(corpus.keys())
    models = [args.model] if args.model else phase_cfg["models"]

    print_header("planner_ablation", models, bug_ids)

    total = len(models) * len(bug_ids)
    current = 0

    for model in models:
        print(f"\n--- Model: {model} ---")
        for bug_id in bug_ids:
            bug = corpus.get(int(bug_id))
            if not bug:
                print(f"  [WARN] Bug #{bug_id} not in corpus, skipping.")
                continue
            current += 1
            print_progress(current, total, bug_id, model)
            try:
                await run_single_bug(
                    bug=bug,
                    planner_model=model,
                    critic_model=None,
                    critic_enabled=False,
                    rag_enabled=False,
                    root_url=common["root_url"],
                    screenshots_dir=screenshots_dir,
                    screenshot_map=smap,
                    results_dir=results_dir,
                    model_label=model,
                    headless=args.headless,
                    temperature=common["temperature"],
                    max_steps=common["max_steps"],
                    model_registry=cfg.get("model_registry"),
                    phase="planner_ablation",
                    **execution_options,
                )
            except KeyboardInterrupt:
                print("\n[INTERRUPTED] Progress saved. Re-run to resume.")
                return
            except Exception as e:
                print(f"  [ERROR] Bug #{bug_id} / {model}: {e}")


async def run_phase_critic_ablation(cfg: dict, args):
    common = cfg["common"]
    phase_cfg = cfg["critic_ablation"]
    execution_options = args.execution_options

    planner_model = args.planner_model or phase_cfg.get("planner_model")
    if not planner_model:
        print("ERROR: Set planner_model in config.yaml [critic_ablation] or pass --planner-model")
        sys.exit(1)

    corpus = load_bug_corpus(os.path.abspath(os.path.join(THIS_DIR, common["bug_corpus"])))
    smap = load_screenshot_map(os.path.abspath(os.path.join(THIS_DIR, common["screenshot_map"])))
    screenshots_dir = os.path.abspath(os.path.join(THIS_DIR, common["screenshots_dir"]))
    results_dir = os.path.abspath(os.path.join(THIS_DIR, phase_cfg["results_dir"]))

    bug_ids = args.bug_id_list or phase_cfg.get("bug_ids") or sorted(corpus.keys())
    critic_models = [args.model] if args.model else phase_cfg["critic_models"]

    print_header("critic_ablation", [f"{planner_model}+{c}" for c in critic_models], bug_ids)

    total = len(critic_models) * len(bug_ids)
    current = 0

    for critic_model in critic_models:
        label = f"{planner_model}__{critic_model}"
        print(f"\n--- Critic: {critic_model} ---")
        for bug_id in bug_ids:
            bug = corpus.get(int(bug_id))
            if not bug:
                print(f"  [WARN] Bug #{bug_id} not in corpus, skipping.")
                continue
            current += 1
            print_progress(current, total, bug_id, label)
            try:
                await run_single_bug(
                    bug=bug,
                    planner_model=planner_model,
                    critic_model=critic_model,
                    critic_enabled=True,
                    rag_enabled=phase_cfg.get("rag_enabled", True),
                    root_url=common["root_url"],
                    screenshots_dir=screenshots_dir,
                    screenshot_map=smap,
                    results_dir=os.path.join(results_dir, planner_model),
                    model_label=critic_model,
                    headless=args.headless,
                    temperature=common["temperature"],
                    max_steps=common["max_steps"],
                    model_registry=cfg.get("model_registry"),
                    phase="critic_ablation",
                    **execution_options,
                )
            except KeyboardInterrupt:
                print("\n[INTERRUPTED] Progress saved. Re-run to resume.")
                return
            except Exception as e:
                print(f"  [ERROR] Bug #{bug_id} / critic={critic_model}: {e}")


async def run_phase_full_system(cfg: dict, args):
    common = cfg["common"]
    phase_cfg = cfg["full_system"]
    execution_options = args.execution_options

    planner_model = args.planner_model or phase_cfg.get("planner_model")
    critic_model = args.critic_model or phase_cfg.get("critic_model")
    if not planner_model:
        print("ERROR: Set planner_model in config.yaml [full_system] or pass --planner-model")
        sys.exit(1)
    if not critic_model:
        print("ERROR: Set critic_model in config.yaml [full_system] or pass --critic-model")
        sys.exit(1)

    corpus = load_bug_corpus(os.path.abspath(os.path.join(THIS_DIR, common["bug_corpus"])))
    smap = load_screenshot_map(os.path.abspath(os.path.join(THIS_DIR, common["screenshot_map"])))
    screenshots_dir = os.path.abspath(os.path.join(THIS_DIR, common["screenshots_dir"]))
    results_dir = os.path.abspath(os.path.join(THIS_DIR, phase_cfg["results_dir"]))

    bug_ids = args.bug_id_list or phase_cfg.get("bug_ids") or sorted(corpus.keys())
    configs_to_run = phase_cfg["configs"]

    # Filter to specific config name if provided
    if args.config_name:
        configs_to_run = [c for c in configs_to_run if c["name"] == args.config_name]
        if not configs_to_run:
            print(f"ERROR: Config '{args.config_name}' not found in full_system configs.")
            sys.exit(1)

    config_names = [c["name"] for c in configs_to_run]
    print_header("full_system", [f"{planner_model}+{critic_model} [{n}]" for n in config_names], bug_ids)

    total = len(configs_to_run) * len(bug_ids)
    current = 0

    for sys_cfg in configs_to_run:
        config_name = sys_cfg["name"]
        critic_en = sys_cfg.get("critic_enabled", True)
        rag_en = sys_cfg.get("rag_enabled", True)
        rag_memory_dir = sys_cfg.get("rag_memory_dir")
        rag_search_k = int(sys_cfg.get("rag_search_k", 3))
        rag_min_similarity = float(sys_cfg.get("rag_min_similarity", 0.72))
        rag_max_success_cases = int(sys_cfg.get("rag_max_success_cases", 1))
        print(
            f"\n--- Config: {config_name} "
            f"(critic={critic_en}, rag={rag_en}, rag_memory_dir={rag_memory_dir or 'default'}, "
            f"rag_search_k={rag_search_k}, rag_min_similarity={rag_min_similarity}, "
            f"rag_max_success_cases={rag_max_success_cases}) ---"
        )

        for bug_id in bug_ids:
            bug = corpus.get(int(bug_id))
            if not bug:
                print(f"  [WARN] Bug #{bug_id} not in corpus, skipping.")
                continue
            current += 1
            label = config_name
            print_progress(current, total, bug_id, f"{config_name}")
            try:
                await run_single_bug(
                    bug=bug,
                    planner_model=planner_model,
                    critic_model=critic_model if critic_en else None,
                    critic_enabled=critic_en,
                    rag_enabled=rag_en,
                    root_url=common["root_url"],
                    screenshots_dir=screenshots_dir,
                    screenshot_map=smap,
                    results_dir=os.path.join(results_dir, config_name),
                    model_label=label,
                    headless=args.headless,
                    temperature=common["temperature"],
                    max_steps=common["max_steps"],
                    model_registry=cfg.get("model_registry"),
                    phase="full_system",
                    rag_memory_dir=rag_memory_dir,
                    rag_search_k=rag_search_k,
                    rag_min_similarity=rag_min_similarity,
                    rag_max_success_cases=rag_max_success_cases,
                    **execution_options,
                )
            except KeyboardInterrupt:
                print("\n[INTERRUPTED] Progress saved. Re-run to resume.")
                return
            except Exception as e:
                print(f"  [ERROR] Bug #{bug_id} / {config_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="ReBugger experiment orchestrator")
    parser.add_argument("--phase", required=True,
                        choices=["planner_ablation", "critic_ablation", "full_system"])
    parser.add_argument("--model", type=str, default=None,
                        help="Run only this model (planner or critic depending on phase)")
    parser.add_argument("--planner-model", type=str, default=None,
                        help="Override planner model (for critic_ablation / full_system)")
    parser.add_argument("--critic-model", type=str, default=None,
                        help="Override critic model (for full_system)")
    parser.add_argument("--config-name", type=str, default=None,
                        help="Run only this config name in full_system (planner_only/planner_rag/planner_critic/full)")
    parser.add_argument("--bug-id", type=int, default=None,
                        help="Run only this specific bug ID")
    parser.add_argument("--headless", action="store_true",
                        help="Run browser in headless mode (default: visible)")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--unattended", action="store_true",
                            help="Skip runs that ask for user input and record them in the skip log")
    mode_group.add_argument("--interactive", action="store_true",
                            help="Force interactive user-input prompts even if config enables unattended mode")

    args = parser.parse_args()

    # Normalize bug_id to list
    args.bug_id_list = [args.bug_id] if args.bug_id else None

    cfg = load_config()
    args.execution_options = resolve_execution_options(cfg, args)

    if args.phase == "planner_ablation":
        asyncio.run(run_phase_planner_ablation(cfg, args))
    elif args.phase == "critic_ablation":
        asyncio.run(run_phase_critic_ablation(cfg, args))
    elif args.phase == "full_system":
        asyncio.run(run_phase_full_system(cfg, args))


if __name__ == "__main__":
    main()
