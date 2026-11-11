#!/bin/bash
#SBATCH --job-name=energy_siting
#SBATCH --output=logs/run_all_%j.out
#SBATCH --error=logs/run_all_%j.err
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --partition=regular        # adjust to your cluster partition name

# ── Project root (edit this path) ────────────────────────────────────────────
export RSCRIPT_ROOT=/path/to/energySiting_analysis_Italy

mkdir -p "$RSCRIPT_ROOT/logs"
cd "$RSCRIPT_ROOT"

# ── Load R module (adjust version/name to your HPC module system) ─────────────
module load R/4.4.0          # check available versions with: module avail R

# ── Run pipeline ──────────────────────────────────────────────────────────────
echo "Job started: $(date)"
echo "Host: $(hostname)"
echo "CPUs: $SLURM_CPUS_PER_TASK"

R --no-save --no-restore -f run_all.R

echo "Job finished: $(date)"
