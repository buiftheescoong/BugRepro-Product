"""
evaluate.py — Compute M1-M6 metrics from result JSON files.

Usage:
    # Planner ablation
    python evaluate.py --phase planner_ablation

    # Critic ablation (needs baseline for ΔRSR)
    python evaluate.py --phase critic_ablation --no-critic-dir ../results/planner_ablation/gemini-2.5-flash

    # Full system
    python evaluate.py --phase full_system

Outputs:
    results/<phase>/summary.json        — per-model metrics dict
    results/<phase>/comparison_table.md — markdown table
    Console: formatted table
"""
import os
import sys
import json
import csv
import math
import argparse
import statistics
from pathlib import Path
from datetime import datetime, timezone

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# ── token pricing ($ per 1M tokens) ─────────────────────────────────────────
PRICING = {
    "gemini-2.5-flash":          {"in": 0.30,  "out": 2.50},
    "gemini-3.1-flash-lite":     {"in": 0.25,  "out": 1.50},
    "gemini-2.5-pro":            {"in": 1.25,  "out": 10.00},
    "gemini-2.5-flash-lite":     {"in": 0.10,  "out": 0.40},
    "claude-sonnet-4-6":         {"in": 3.00,  "out": 15.00},
    "claude-opus-4-7":           {"in": 15.00, "out": 75.00},
    "claude-haiku-4-5-20251001": {"in": 0.80,  "out": 4.00},
    "gpt-4.1":                   {"in": 2.00,  "out": 8.00},
    "gpt-4.1-mini":              {"in": 0.40,  "out": 1.60},
    "gpt-4o-mini":               {"in": 0.15,  "out": 0.60},
    "gpt-5.4-mini":              {"in": 0.75,  "out": 4.50},
    "gpt-5.4-nano":              {"in": 0.20,  "out": 1.25},
    "qwen3.5-9b":                {"in": 0.04,  "out": 0.15},
    "qwen3.5-397b-a17b":         {"in": 0.60,  "out": 3.60},
    "gemma-4-31b-it":            {"in": 0.20,  "out": 0.50},
    "qwen3-vl-32b-instruct":     {"in": 0.25,  "out": 1.50},
    "qwen2.5-vl-72b-instruct":   {"in": 0.25,  "out": 0.75},
    "qwen2.5-vl-7b":             {"in": 0.20,  "out": 0.20},
    "qwen/qwen3.5-9b":                       {"in": 0.04,  "out": 0.15},
    "Qwen/Qwen3.5-397B-A17B":                {"in": 0.60,  "out": 3.60},
    "google/gemma-4-31B-it":                 {"in": 0.20,  "out": 0.50},
    "qwen/qwen3-vl-32b-instruct":            {"in": 0.25,  "out": 1.50},
    "qwen/qwen2.5-vl-72b-instruct":          {"in": 0.25,  "out": 0.75},
    "qwen/qwen-2.5-vl-7b-instruct":          {"in": 0.20,  "out": 0.20},
    "openai/gpt-5.4-mini":       {"in": 0.75,  "out": 4.50},
    "openai/gpt-5.4-nano":       {"in": 0.20,  "out": 1.25},
}


# ── helpers ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    import yaml
    with open(os.path.join(THIS_DIR, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_results(results_dir: Path) -> list[dict]:
    """Load all bug_XXX.json files from a model directory."""
    results = []
    for f in sorted(results_dir.glob("bug_*.json")):
        with open(f, "r", encoding="utf-8") as fh:
            results.append(json.load(fh))
    return results


def safe_model_dir_name(model_label: str) -> str:
    return model_label.replace("/", "__").replace("\\", "__").replace(":", "_")


def load_review_csv(review_path: Path) -> dict:
    """
    Load human review CSV. Returns dict keyed by (bug_id, model_label).
    CSV columns: bug_id, model_label, human_verified (true/false), notes
    """
    review = {}
    if not review_path.exists():
        return review
    with open(review_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (int(row["bug_id"]), row["model_label"])
            review[key] = row.get("human_verified", "").lower() in ("true", "yes", "1")
    return review


def compute_cost(result: dict) -> float:
    """Estimate cost in USD from token counts and planner model pricing."""
    model = result.get("planner_model", "")
    price = PRICING.get(model, {"in": 0.0, "out": 0.0})
    in_tok = result.get("total_input_tokens", 0)
    out_tok = result.get("total_output_tokens", 0)
    return (in_tok * price["in"] + out_tok * price["out"]) / 1_000_000


def compute_metrics_for_model(results: list[dict], review: dict, model_label: str) -> dict:
    """Compute all metrics for one model config."""
    n = len(results)
    if n == 0:
        return {}

    # RSR@1 uses human review as ground truth.
    successes = [r for r in results if review.get((r["bug_id"], model_label), False)]
    c = len(successes)
    rsr1 = c / n
    claimed_success = [r for r in results if r.get("is_reproduced")]
    claimed_true_positives = [
        r for r in claimed_success
        if review.get((r["bug_id"], model_label), False)
    ]
    claimed_success_count = len(claimed_success)
    claimed_true_positive_count = len(claimed_true_positives)
    claimed_precision = (
        claimed_true_positive_count / claimed_success_count
        if claimed_success_count > 0 else None
    )

    costs = [compute_cost(r) for r in results]
    cost_per_bug = sum(costs) / n
    wall_times = [r.get("total_wall_time_seconds", 0) for r in results]
    llm_times = [r.get("total_llm_time_seconds", 0) for r in results]
    lat_mean = statistics.mean(wall_times) if wall_times else 0
    lat_p50 = statistics.median(wall_times) if wall_times else 0
    lat_p95 = _percentile(wall_times, 95) if wall_times else 0
    llm_lat_mean = statistics.mean(llm_times) if llm_times else 0
    llm_lat_p50 = statistics.median(llm_times) if llm_times else 0
    llm_lat_p95 = _percentile(llm_times, 95) if llm_times else 0

    # Raw steps (on all runs, not just successful)
    all_steps = [r.get("steps_count", 0) for r in results]
    success_steps = [r.get("steps_count", 0) for r in successes]
    mean_steps = statistics.mean(all_steps) if all_steps else 0
    mean_steps_success = statistics.mean(success_steps) if success_steps else None

    # LLM calls: Planner/Critic calls only, not perception/executor graph steps.
    all_llm_calls = [r.get("llm_calls", 0) for r in results]
    success_llm_calls = [r.get("llm_calls", 0) for r in successes]
    mean_llm_calls = statistics.mean(all_llm_calls) if all_llm_calls else 0
    mean_llm_calls_success = statistics.mean(success_llm_calls) if success_llm_calls else None

    # Error rate
    errors = [r for r in results if r.get("run_error")]
    error_rate = len(errors) / n

    return {
        "model_label": model_label,
        "n_bugs": n,
        "n_success": c,
        "rsr1": round(rsr1, 4),
        "rsr1_pct": round(rsr1 * 100, 1),
        "claimed_precision": round(claimed_precision, 4) if claimed_precision is not None else None,
        "claimed_precision_pct": round(claimed_precision * 100, 1) if claimed_precision is not None else None,
        "claimed_success_count": claimed_success_count,
        "claimed_true_positive_count": claimed_true_positive_count,
        "claim_reviewed_count": claimed_success_count,
        "cost_per_bug_usd": round(cost_per_bug, 4),
        "total_cost_usd": round(sum(costs), 4),
        "lat_wall_mean_s": round(lat_mean, 1),
        "lat_wall_p50_s": round(lat_p50, 1),
        "lat_wall_p95_s": round(lat_p95, 1),
        "lat_llm_mean_s": round(llm_lat_mean, 1),
        "lat_llm_p50_s": round(llm_lat_p50, 1),
        "lat_llm_p95_s": round(llm_lat_p95, 1),
        "mean_steps_all": round(mean_steps, 1),
        "mean_steps_success": round(mean_steps_success, 1) if mean_steps_success is not None else None,
        "total_llm_calls": sum(all_llm_calls),
        "mean_llm_calls_all": round(mean_llm_calls, 1),
        "mean_llm_calls_success": round(mean_llm_calls_success, 1) if mean_llm_calls_success is not None else None,
        "error_rate": round(error_rate, 4),
    }


def _percentile(data: list, p: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = math.ceil((p * len(sorted_data)) / 100) - 1
    return sorted_data[max(0, idx)]



def compute_delta_rsr(model_metrics: dict, baseline_metrics: dict) -> dict:
    """Compute ΔRSR and Δclaimed precision vs baseline (No-Critic)."""
    delta = dict(model_metrics)
    base_rsr1 = baseline_metrics.get("rsr1", 0)
    delta["delta_rsr1"] = round(model_metrics["rsr1"] - base_rsr1, 4)
    delta["delta_rsr1_pct"] = round(delta["delta_rsr1"] * 100, 1)
    if (
        model_metrics["claimed_precision"] is not None
        and baseline_metrics.get("claimed_precision") is not None
    ):
        delta["delta_claimed_precision"] = round(
            model_metrics["claimed_precision"] - baseline_metrics["claimed_precision"], 4
        )
        delta["delta_claimed_precision_pct"] = round(delta["delta_claimed_precision"] * 100, 1)
    return delta


def format_markdown_table(all_metrics: list[dict], phase: str) -> str:
    if phase == "planner_ablation":
        headers = ["Model", "RSR@1 %", "n_success/n", "Cost/bug $", "LLM P50 s", "Wall P50 s", "Wall Mean s", "LLM P95 s", "Wall P95 s", "Steps (all)", "LLM Calls", "Precision %", "Error %"]
        rows = []
        for m in sorted(all_metrics, key=lambda x: -x["rsr1"]):
            claimed_precision_str = f"{m['claimed_precision_pct']:.1f}" if m["claimed_precision_pct"] is not None else "—"
            rows.append([
                m["model_label"],
                f"{m['rsr1_pct']:.1f}",
                f"{m['n_success']}/{m['n_bugs']}",
                f"{m['cost_per_bug_usd']:.4f}",
                f"{m['lat_llm_p50_s']:.1f}",
                f"{m['lat_wall_p50_s']:.1f}",
                f"{m['lat_wall_mean_s']:.1f}",
                f"{m['lat_llm_p95_s']:.1f}",
                f"{m['lat_wall_p95_s']:.1f}",
                f"{m['mean_steps_all']:.1f}",
                f"{m['mean_llm_calls_all']:.1f}",
                claimed_precision_str,
                f"{m['error_rate']*100:.1f}",
            ])
    elif phase == "critic_ablation":
        headers = ["Critic Model", "RSR@1 %", "Delta RSR@1 %", "Cost/bug $", "Precision %", "Delta Precision %", "Wall P50 s", "Wall Mean s", "Steps"]
        rows = []
        for m in sorted(all_metrics, key=lambda x: -x["rsr1"]):
            claimed_precision_str = f"{m['claimed_precision_pct']:.1f}" if m["claimed_precision_pct"] is not None else "—"
            delta_claimed_precision_str = f"{m.get('delta_claimed_precision_pct', 0):.1f}" if m.get("delta_claimed_precision_pct") is not None else "—"
            rows.append([
                m["model_label"],
                f"{m['rsr1_pct']:.1f}",
                f"{m.get('delta_rsr1_pct', 0):+.1f}",
                f"{m['cost_per_bug_usd']:.4f}",
                claimed_precision_str,
                delta_claimed_precision_str,
                f"{m['lat_wall_p50_s']:.1f}",
                f"{m['lat_wall_mean_s']:.1f}",
                f"{m['mean_steps_all']:.1f}",
            ])
    else:  # full_system
        headers = ["Config", "RSR@1 %", "n_success/n", "Cost/bug $", "Wall P50 s", "Wall Mean s", "Steps", "Precision %"]
        rows = []
        for m in sorted(all_metrics, key=lambda x: -x["rsr1"]):
            claimed_precision_str = f"{m['claimed_precision_pct']:.1f}" if m["claimed_precision_pct"] is not None else "—"
            rows.append([
                m["model_label"],
                f"{m['rsr1_pct']:.1f}",
                f"{m['n_success']}/{m['n_bugs']}",
                f"{m['cost_per_bug_usd']:.4f}",
                f"{m['lat_wall_p50_s']:.1f}",
                f"{m['lat_wall_mean_s']:.1f}",
                f"{m['mean_steps_all']:.1f}",
                claimed_precision_str,
            ])

    if phase in ("critic_ablation", "full_system"):
        headers.append("LLM Calls")
        sorted_metrics = sorted(all_metrics, key=lambda x: -x["rsr1"])
        for row, m in zip(rows, sorted_metrics):
            row.append(f"{m['mean_llm_calls_all']:.1f}")

    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    header_row = "| " + " | ".join(headers) + " |"
    data_rows = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([header_row, sep] + data_rows)


def evaluate_planner_ablation(cfg: dict, args):
    phase_cfg = cfg["planner_ablation"]
    results_dir = Path(THIS_DIR) / phase_cfg["results_dir"]
    review_path = Path(THIS_DIR) / "../results/reviews/planner_ablation.csv"
    review = load_review_csv(review_path)

    models = [args.model] if args.model else phase_cfg["models"]
    all_metrics = []

    for model in models:
        model_dir = results_dir / safe_model_dir_name(model)
        if not model_dir.exists():
            print(f"[WARN] No results for {model} at {model_dir}")
            continue
        results = load_results(model_dir)
        if not results:
            print(f"[WARN] No result files in {model_dir}")
            continue
        m = compute_metrics_for_model(results, review, model_label=model)
        all_metrics.append(m)
        print(f"  {model:30s} RSR@1={m['rsr1_pct']:.1f}%  cost=${m['cost_per_bug_usd']:.4f}/bug  steps={m['mean_steps_all']:.1f}")

    _save_and_print(all_metrics, results_dir, "planner_ablation")


def evaluate_critic_ablation(cfg: dict, args):
    phase_cfg = cfg["critic_ablation"]
    planner_model = args.planner_model or phase_cfg.get("planner_model")
    if not planner_model:
        print("ERROR: Specify --planner-model or set in config.yaml")
        sys.exit(1)

    results_dir = Path(THIS_DIR) / phase_cfg["results_dir"] / planner_model
    review_path = Path(THIS_DIR) / "../results/reviews/critic_ablation.csv"
    review = load_review_csv(review_path)

    critic_models = [args.model] if args.model else phase_cfg["critic_models"]
    all_metrics = []
    baseline_metrics = None

    # Load No-Critic baseline from planner_ablation results
    if args.no_critic_dir:
        no_critic_dir = Path(args.no_critic_dir)
        if no_critic_dir.exists():
            no_critic_results = load_results(no_critic_dir)
            baseline_review_path = Path(THIS_DIR) / "../results/reviews/planner_ablation.csv"
            baseline_review = load_review_csv(baseline_review_path)
            baseline_metrics = compute_metrics_for_model(
                no_critic_results,
                baseline_review,
                model_label=planner_model,
            )
            baseline_metrics["model_label"] = "no-critic"
            baseline_metrics["delta_rsr1"] = 0.0
            baseline_metrics["delta_rsr1_pct"] = 0.0
            all_metrics.append(baseline_metrics)
            print(f"  {'no-critic':30s} RSR@1={baseline_metrics['rsr1_pct']:.1f}% (baseline)")

    for critic_model in critic_models:
        model_dir = results_dir / safe_model_dir_name(critic_model)
        if not model_dir.exists():
            print(f"[WARN] No results for critic={critic_model}")
            continue
        results = load_results(model_dir)
        if not results:
            continue
        m = compute_metrics_for_model(results, review, model_label=critic_model)
        if baseline_metrics:
            m = compute_delta_rsr(m, baseline_metrics)
        all_metrics.append(m)
        delta_str = f"  Delta RSR={m.get('delta_rsr1_pct', 0):+.1f}%" if baseline_metrics else ""
        print(f"  {critic_model:30s} RSR@1={m['rsr1_pct']:.1f}%{delta_str}")

    out_dir = Path(THIS_DIR) / phase_cfg["results_dir"]
    _save_and_print(all_metrics, out_dir, "critic_ablation")


def evaluate_full_system(cfg: dict, args):
    phase_cfg = cfg["full_system"]
    results_dir = Path(THIS_DIR) / phase_cfg["results_dir"]
    review_path = Path(THIS_DIR) / "../results/reviews/full_system.csv"
    review = load_review_csv(review_path)

    config_names = [c["name"] for c in phase_cfg["configs"]]
    all_metrics = []

    for config_name in config_names:
        config_dir = results_dir / config_name
        if not config_dir.exists():
            print(f"[WARN] No results for config={config_name}")
            continue
        label_dirs = [d for d in config_dir.iterdir() if d.is_dir()]
        if not label_dirs:
            results = load_results(config_dir)
            m = compute_metrics_for_model(results, review, model_label=config_name)
        else:
            all_r = []
            for ld in label_dirs:
                all_r.extend(load_results(ld))
            m = compute_metrics_for_model(all_r, review, model_label=config_name)
        all_metrics.append(m)
        print(f"  {config_name:20s} RSR@1={m['rsr1_pct']:.1f}%  n={m['n_success']}/{m['n_bugs']}")

    _save_and_print(all_metrics, results_dir, "full_system")


def _save_and_print(all_metrics: list[dict], results_dir: Path, phase: str):
    results_dir = results_dir.resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    summary_path = results_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "phase": phase,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models": all_metrics,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved: {summary_path}")

    table = format_markdown_table(all_metrics, phase)
    table_path = results_dir / "comparison_table.md"
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(f"# {phase} — Comparison Table\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(table)
        f.write("\n")
    print(f"Saved: {table_path}")
    print(f"\n{table}\n")



def main():
    parser = argparse.ArgumentParser(description="Evaluate experiment results")
    parser.add_argument("--phase", required=True,
                        choices=["planner_ablation", "critic_ablation", "full_system"])
    parser.add_argument("--model", type=str, default=None, help="Evaluate only this model")
    parser.add_argument("--planner-model", type=str, default=None)
    parser.add_argument("--no-critic-dir", type=str, default=None,
                        help="Path to no-critic baseline results dir (for ΔRSR in critic ablation)")
    args = parser.parse_args()

    cfg = load_config()

    print(f"\n=== Evaluate: {args.phase} ===\n")
    if args.phase == "planner_ablation":
        evaluate_planner_ablation(cfg, args)
    elif args.phase == "critic_ablation":
        evaluate_critic_ablation(cfg, args)
    elif args.phase == "full_system":
        evaluate_full_system(cfg, args)


if __name__ == "__main__":
    main()
