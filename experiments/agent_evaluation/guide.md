# Experiment Guide

This guide records the commands for running and analyzing the experiment phases from the repo root.

```powershell
cd D:\KLTN\AutomatedBugReproduction
$env:PYTHONIOENCODING='utf-8'
```

Use the project venv:

```powershell
.\experiments\venv\Scripts\python.exe
```

## Full System Factorial Ablation

The full-system phase uses 4 configs in `experiments\agent_evaluation\config.yaml`:

| Config | Planner | RAG | Critic |
|---|---:|---:|---:|
| `planner_only` | on | off | off |
| `planner_rag` | on | on | off |
| `planner_critic` | on | off | on |
| `full` | on | on | on |

Current selected models:

```yaml
full_system:
  planner_model: gemini-2.5-flash
  critic_model: gemini-2.5-flash
  bug_ids: []
```

`bug_ids: []` means run all bugs from `experiments\data\bug_corpus_full.json`.

For RAG configs, the memory uses ChromaDB with `BAAI/bge-m3` embeddings. Each RAG config has its own memory directory:

```text
planner_rag -> rebugger-agent\data\chroma_db_planner_rag
full        -> rebugger-agent\data\chroma_db_planner_rag_critic
```

In the online-memory protocol, start from an empty memory before each RAG config, then each completed RAG-enabled run is saved for later bugs in that same config.

Backup and clear old memory before starting `planner_rag`:

```powershell
if (Test-Path -LiteralPath .\rebugger-agent\data\chroma_db_planner_rag) {
  Copy-Item `
    -LiteralPath .\rebugger-agent\data\chroma_db_planner_rag `
    -Destination .\rebugger-agent\data\chroma_db_backup_before_planner_rag `
    -Recurse

  Remove-Item `
    -LiteralPath .\rebugger-agent\data\chroma_db_planner_rag `
    -Recurse `
    -Force
}
```

For the full config (`planner + rag + critic`), use `chroma_db_planner_rag_critic` instead:

```powershell
if (Test-Path -LiteralPath .\rebugger-agent\data\chroma_db_planner_rag_critic) {
  Copy-Item `
    -LiteralPath .\rebugger-agent\data\chroma_db_planner_rag_critic `
    -Destination .\rebugger-agent\data\chroma_db_backup_before_planner_rag_critic `
    -Recurse

  Remove-Item `
    -LiteralPath .\rebugger-agent\data\chroma_db_planner_rag_critic `
    -Recurse `
    -Force
}
```

Run all 4 configs:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\run_experiment.py `
  --phase full_system `
  --headless `
  --unattended
```

Run one config only:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\run_experiment.py `
  --phase full_system `
  --config-name planner_only `
  --headless `
  --unattended
```

Replace `planner_only` with one of:

```text
planner_only
planner_rag
planner_critic
full
```

Test one bug before running the full set:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\run_experiment.py `
  --phase full_system `
  --config-name full `
  --bug-id 1 `
  --headless `
  --unattended
```

Results are saved under:

```text
experiments\results\full_system\planner_only\planner_only\bug_XXX.json
experiments\results\full_system\planner_rag\planner_rag\bug_XXX.json
experiments\results\full_system\planner_critic\planner_critic\bug_XXX.json
experiments\results\full_system\full\full\bug_XXX.json
```

The runner is resume-safe: if a `bug_XXX.json` already exists, that run is skipped.

## Evaluate And Analyze Full System

Run evaluation:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\evaluate.py --phase full_system
```

Run chart generation:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\analyze.py --phase full_system
```

Main outputs:

```text
experiments\results\full_system\summary.json
experiments\results\full_system\comparison_table.md
experiments\results\full_system\plots\rsr1_full.png
experiments\results\full_system\plots\steps_full.png
```

Read `comparison_table.md` first for the compact table. Use `summary.json` for exact metric values and plotting/custom analysis.

## Critic Ablation

Run critic ablation with planner fixed to `gemini-2.5-flash`:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\run_experiment.py `
  --phase critic_ablation `
  --planner-model gemini-2.5-flash `
  --headless `
  --unattended
```

Run only one critic model:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\run_experiment.py `
  --phase critic_ablation `
  --planner-model gemini-2.5-flash `
  --model qwen3.5-9b `
  --headless `
  --unattended
```

Evaluate critic ablation:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\evaluate.py `
  --phase critic_ablation `
  --planner-model gemini-2.5-flash `
  --no-critic-dir .\experiments\results\planner_ablation\gemini-2.5-flash
```

Generate critic charts:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\analyze.py --phase critic_ablation
```

Critic outputs:

```text
experiments\results\critic_ablation\summary.json
experiments\results\critic_ablation\comparison_table.md
experiments\results\critic_ablation\plots\rsr1_critic.png
experiments\results\critic_ablation\plots\delta_rsr1_critic.png
experiments\results\critic_ablation\plots\pareto_critic.png
```

## Planner Ablation

Run planner ablation:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\run_experiment.py `
  --phase planner_ablation `
  --headless `
  --unattended
```

Run only one planner model:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\run_experiment.py `
  --phase planner_ablation `
  --model gemini-2.5-flash `
  --headless `
  --unattended
```

Evaluate and analyze:

```powershell
.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\evaluate.py --phase planner_ablation

.\experiments\venv\Scripts\python.exe .\experiments\agent_evaluation\analyze.py --phase planner_ablation
```

Planner outputs:

```text
experiments\results\planner_ablation\summary.json
experiments\results\planner_ablation\comparison_table.md
experiments\results\planner_ablation\plots\rsr1_planner.png
experiments\results\planner_ablation\plots\pareto_planner.png
experiments\results\planner_ablation\plots\steps_planner.png
```

## How To Read Results

Use these files in order:

1. `comparison_table.md`: quick ranking table.
2. `summary.json`: exact values for metrics and custom analysis.
3. `plots\*.png`: figures for report/thesis.
4. Individual `bug_XXX.json`: debug one bug/run in detail.

Key metrics:

| Metric | Meaning |
|---|---|
| `RSR@1` | Human-verified reproduction success rate. Higher is better. |
| `Precision` | Among claimed successes, how many were human-verified true. Higher means fewer false positives. |
| `Cost/bug` | Estimated LLM cost per bug. Lower is cheaper. |
| `Wall Mean` | Average end-to-end wall-clock runtime per bug. Lower is faster. |
| `Wall P50` | Median wall-clock runtime. Lower is faster. |
| `Steps` | Average number of agent steps. Lower usually means more efficient. |
| `Error %` | Run-level error rate from `run_error`. Lower is better. |

For full-system factorial ablation, compare:

```text
planner_only    = baseline
planner_rag     = effect of RAG without critic
planner_critic  = effect of critic without RAG
full            = combined system
```

Useful effects:

```text
RAG effect without critic     = RSR(planner_rag) - RSR(planner_only)
Critic effect without RAG     = RSR(planner_critic) - RSR(planner_only)
RAG effect with critic        = RSR(full) - RSR(planner_critic)
Critic effect with RAG        = RSR(full) - RSR(planner_rag)
Interaction effect            = RSR(full) - RSR(planner_rag) - RSR(planner_critic) + RSR(planner_only)
```

If interaction is positive, RAG and Critic help each other. If negative, the combined system may introduce redundancy or noise.

## Notes

- Prefer running commands from the repo root: `D:\KLTN\AutomatedBugReproduction`.
- Use `--unattended` for long experiment runs so prompts for user input are skipped and logged.
- Use `--bug-id N` to test one bug before launching a large run.
- If a run is skipped unexpectedly, check whether its result JSON already exists.
- For full-system evaluation, make sure `experiments\results\reviews\full_system.csv` contains human verification labels for the configs you want to report.
