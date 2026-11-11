#!/bin/bash
#BSUB -J energy_siting_py
#BSUB -o logs/run_all_py_%J.out
#BSUB -e logs/run_all_py_%J.err
#BSUB -q p_macro               # adjust to your queue name
#BSUB -n 16
#BSUB -P 0588                  # adjust to your project code
#BSUB -x
#BSUB -R "span[ptile=16]"
#BSUB -R "rusage[mem=64G]"
#BSUB -app macro               # remove if no application profile on your cluster

# Python / scikit-learn version of run_hpc.sh.
# One-time environment (login node):
#   python -m venv ~/venvs/energysiting && source ~/venvs/energysiting/bin/activate
#   pip install -r python/requirements.txt

export ES_ROOT=/path/to/energySiting_analysis_Italy
export ES_N_JOBS=${LSB_DJOB_NUMPROC:-16}
export OMP_NUM_THREADS=1        # parallelism comes from joblib workers

mkdir -p "$ES_ROOT/logs"
cd "$ES_ROOT"
source ~/venvs/energysiting/bin/activate

echo "Job started: $(date)  host: $(hostname)  CPUs: $ES_N_JOBS"
python python/run_all.py "$@"
echo "Job finished: $(date)"
