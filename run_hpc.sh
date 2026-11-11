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

# ── Load R module ─────────────────────────────────────────────────────────────
# Find the right name with:  module avail R
module load R-gcc/4.4.3

# Fail fast with a clear message if R is not on PATH after the module load
if ! command -v R &>/dev/null; then
  echo "ERROR: R not found after module load. Run 'module avail R' to find the correct module name." >&2
  exit 1
fi

# ── User R library (system library is read-only) ──────────────────────────────
export R_LIBS_USER="$HOME/R/x86_64-pc-linux-gnu-library/4.4"
mkdir -p "$R_LIBS_USER"

# Install librarian on first run (librarian then installs everything else)
R --no-save --no-restore -e "
  if (!requireNamespace('librarian', quietly = TRUE))
    install.packages('librarian', lib = Sys.getenv('R_LIBS_USER'),
                     repos = 'https://cloud.r-project.org')
"

# ── Run pipeline ──────────────────────────────────────────────────────────────
echo "Job started: $(date)"
echo "Host: $(hostname)"
echo "CPUs: $LSB_DJOB_NUMPROC"
echo "R:    $(R --version | head -1)"

R --no-save --no-restore -f run_all.R

echo "Job finished: $(date)"
