#!/bin/bash
#BSUB -J energy_siting
#BSUB -o logs/run_all_%J.out
#BSUB -e logs/run_all_%J.err
#BSUB -q p_macro               # adjust to your queue name
#BSUB -n 16
#BSUB -P 0588                  # adjust to your project code
#BSUB -x
#BSUB -R "span[ptile=16]"
#BSUB -R "rusage[mem=64G]"
#BSUB -app macro               # remove if no application profile on your cluster

export OMP_NUM_THREADS=$LSB_DJOB_NUMPROC

# ── Project root (edit this path) ────────────────────────────────────────────
export RSCRIPT_ROOT=/path/to/energySiting_analysis_Italy

mkdir -p "$RSCRIPT_ROOT/logs"
cd "$RSCRIPT_ROOT"

# ── Load R module (adjust version/name to your HPC module system) ─────────────
module load R/4.4.0          # check available versions with: module avail R

# ── Run pipeline ──────────────────────────────────────────────────────────────
echo "Job started: $(date)"
echo "Host: $(hostname)"
echo "CPUs: $LSB_DJOB_NUMPROC"

R --no-save --no-restore -f run_all.R

echo "Job finished: $(date)"
