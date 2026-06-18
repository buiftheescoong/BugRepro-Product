"""
analyze.py — Generate charts from experiment summary.json files.

Usage:
    python analyze.py --phase planner_ablation
    python analyze.py --phase critic_ablation
    python analyze.py --phase full_system
    python analyze.py --all

Outputs saved to results/<phase>/plots/
"""
import os
import sys
import json
import argparse
from pathlib import Path

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[WARN] matplotlib not installed — charts will be skipped. Run: pip install matplotlib")


def load_config():
    import yaml
    with open(os.path.join(THIS_DIR, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_summary(summary_path: Path) -> list[dict]:
    if not summary_path.exists():
        print(f"[WARN] No summary found at {summary_path}. Run evaluate.py first.")
        return []
    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("models", [])


def save_fig(fig, path: Path):
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")



def bar_rsr(models: list[dict], title: str, out_path: Path):
    if not HAS_MPL:
        return
    labels = [m["model_label"] for m in models]
    values = [m["rsr1_pct"] for m in models]
    colors = ["#2196F3" if v == max(values) else "#90CAF9" for v in values]

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 5))
    bars = ax.bar(labels, values, color=colors, edgecolor="white")
    ax.set_ylim(0, 110)
    ax.set_ylabel("RSR@1 (%)")
    ax.set_title(title)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=9)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    save_fig(fig, out_path)


def scatter_pareto(models: list[dict], title: str, out_path: Path):
    """RSR@1 vs Cost per bug scatter plot."""
    if not HAS_MPL:
        return
    labels = [m["model_label"] for m in models]
    x = [m["cost_per_bug_usd"] for m in models]
    y = [m["rsr1_pct"] for m in models]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(x, y, s=80, color="#2196F3", zorder=3)
    for lbl, xi, yi in zip(labels, x, y):
        ax.annotate(lbl, (xi, yi), textcoords="offset points", xytext=(5, 4), fontsize=8)
    ax.set_xlabel("Cost per bug (USD)")
    ax.set_ylabel("RSR@1 (%)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    save_fig(fig, out_path)


def bar_delta_rsr(models: list[dict], title: str, out_path: Path):
    """ΔRSR@1 bar chart for critic ablation."""
    if not HAS_MPL:
        return
    labels = [m["model_label"] for m in models]
    values = [m.get("delta_rsr1_pct", 0) for m in models]
    colors = ["#4CAF50" if v > 0 else ("#F44336" if v < 0 else "#9E9E9E") for v in values]

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 5))
    bars = ax.bar(labels, values, color=colors, edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("ΔRSR@1 (percentage points)")
    ax.set_title(title)
    for bar, val in zip(bars, values):
        offset = 0.5 if val >= 0 else -1.5
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + offset,
                f"{val:+.1f}pp", ha="center", va="bottom" if val >= 0 else "top", fontsize=9)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    save_fig(fig, out_path)


def bar_steps(models: list[dict], title: str, out_path: Path):
    """Mean steps per model."""
    if not HAS_MPL:
        return
    labels = [m["model_label"] for m in models]
    values = [m.get("mean_steps_all", 0) for m in models]

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 5))
    ax.bar(labels, values, color="#FF9800", edgecolor="white")
    ax.set_ylabel("Mean steps")
    ax.set_title(title)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    save_fig(fig, out_path)


def analyze_planner_ablation(cfg: dict):
    phase_cfg = cfg["planner_ablation"]
    results_dir = Path(THIS_DIR) / phase_cfg["results_dir"]
    models = load_summary(results_dir / "summary.json")
    if not models:
        return
    plots_dir = results_dir / "plots"

    print("\n--- Planner Ablation Charts ---")
    bar_rsr(models, "RSR@1 per Planner Model", plots_dir / "rsr1_planner.png")
    scatter_pareto(models, "RSR@1 vs Cost per Bug (Planner)", plots_dir / "pareto_planner.png")
    bar_steps(models, "Mean Steps per Planner Model", plots_dir / "steps_planner.png")


def analyze_critic_ablation(cfg: dict):
    phase_cfg = cfg["critic_ablation"]
    results_dir = Path(THIS_DIR) / phase_cfg["results_dir"]
    models = load_summary(results_dir / "summary.json")
    if not models:
        return
    plots_dir = results_dir / "plots"

    print("\n--- Critic Ablation Charts ---")
    bar_rsr(models, "RSR@1 per Critic Model", plots_dir / "rsr1_critic.png")
    bar_delta_rsr(models, "ΔRSR@1 vs No-Critic", plots_dir / "delta_rsr1_critic.png")
    scatter_pareto(models, "RSR@1 vs Cost per Bug (Critic)", plots_dir / "pareto_critic.png")


def analyze_full_system(cfg: dict):
    phase_cfg = cfg["full_system"]
    results_dir = Path(THIS_DIR) / phase_cfg["results_dir"]
    models = load_summary(results_dir / "summary.json")
    if not models:
        return
    plots_dir = results_dir / "plots"

    print("\n--- Full System Charts ---")
    bar_rsr(models, "RSR@1: Full vs Ablations", plots_dir / "rsr1_full.png")
    bar_steps(models, "Mean Steps: Full vs Ablations", plots_dir / "steps_full.png")


def main():
    parser = argparse.ArgumentParser(description="Generate experiment charts")
    parser.add_argument("--phase", choices=["planner_ablation", "critic_ablation", "full_system"])
    parser.add_argument("--all", action="store_true", help="Run all phases")
    args = parser.parse_args()

    if not args.phase and not args.all:
        parser.print_help()
        sys.exit(1)

    cfg = load_config()

    phases = ["planner_ablation", "critic_ablation", "full_system"] if args.all else [args.phase]
    for phase in phases:
        if phase == "planner_ablation":
            analyze_planner_ablation(cfg)
        elif phase == "critic_ablation":
            analyze_critic_ablation(cfg)
        elif phase == "full_system":
            analyze_full_system(cfg)


if __name__ == "__main__":
    main()
