#!/bin/bash
# ═════════════════════════════════════════════════════════════════════════════
#  run_all.sh — Python / scikit-learn pipeline on a Linux cluster (LSF or SLURM)
#
#  Rebuilds EVERYTHING from the raw sources: base raster, all covariate layers,
#  the 108-layer stack, presence/absence data, models, CV and figures.
#  Nothing from derived/ or data/processed_data/ needs to be copied over.
#
#  From the repository root, on the LOGIN node (needs internet):
#
#      bash python/run_all.sh            # env + downloads + submit the job
#      bash python/run_all.sh prepare    # env + downloads only
#      bash python/run_all.sh submit     # submit only (inputs already fetched)
#      bash python/run_all.sh check      # list missing raw inputs
#      bash python/run_all.sh local      # run the pipeline in this shell, no scheduler
#
#  Settings (edit the defaults below or export them before running):
#      PY_MODULE      module to load for Python ≥ 3.11 (e.g. "python/3.11"), empty = none
#      CONDA_ENV      use this conda env instead of a venv (name or path), empty = venv
#      ENV_DIR        venv location                     (default ~/venvs/energysiting)
#      PIPELINE_ARGS  arguments for python/run_all.py   (default --force-setup)
#
#  Natura 2000 is the only manual download (see `bash python/run_all.sh check`).
# ═════════════════════════════════════════════════════════════════════════════

# ── LSF directives (read by `bsub < run_all.sh`; ignored by SLURM) ────────────
#BSUB -J energy_siting_py
#BSUB -o logs/energy_siting_py_%J.out
#BSUB -e logs/energy_siting_py_%J.err
#BSUB -q p_macro
#BSUB -n 16
#BSUB -P 0588
#BSUB -x
#BSUB -R "span[ptile=16]"
#BSUB -R "rusage[mem=64G]"
#BSUB -app macro
#BSUB -W 12:00

# ── SLURM directives (read by `sbatch`; ignored by LSF) ──────────────────────
#SBATCH --job-name=energy_siting_py
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/energy_siting_py_%j.out

set -eo pipefail

PY_MODULE="${PY_MODULE:-}"
CONDA_ENV="${CONDA_ENV:-}"
ENV_DIR="${ENV_DIR:-$HOME/venvs/energysiting}"
PIPELINE_ARGS="${PIPELINE_ARGS:---force-setup}"

# ── where is the repository? ─────────────────────────────────────────────────
# Inside a batch job the scheduler runs a copy of this file, so the root is
# passed through ES_ROOT (exported automatically by the submit step below).
if [[ -n "${LSB_JOBID:-}" || -n "${SLURM_JOB_ID:-}" ]]; then
    IN_JOB=1
    ES_ROOT="${ES_ROOT:?ES_ROOT not set inside the job — submit with: bash python/run_all.sh submit}"
else
    IN_JOB=0
    ES_ROOT="${ES_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
fi
export ES_ROOT
cd "$ES_ROOT"
export PYTHONPATH="$ES_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"

log() { echo "[$(date +%H:%M:%S)] $*"; }

load_python() {
    if [[ -n "$PY_MODULE" ]]; then
        if ! type module &>/dev/null; then
            for f in /etc/profile.d/modules.sh /usr/share/lmod/lmod/init/bash /etc/profile.d/lmod.sh; do
                [[ -f "$f" ]] && source "$f" && break
            done
        fi
        module load "$PY_MODULE"
    fi
}

activate_env() {
    load_python
    if [[ -n "$CONDA_ENV" ]]; then
        eval "$(conda shell.bash hook)"
        conda activate "$CONDA_ENV"
    else
        # shellcheck disable=SC1091
        source "$ENV_DIR/bin/activate"
    fi
}

make_env() {
    load_python
    if [[ -n "$CONDA_ENV" ]]; then
        eval "$(conda shell.bash hook)"
        if ! conda env list | awk '{print $1, $NF}' | grep -qw "$CONDA_ENV"; then
            log "Creating conda env $CONDA_ENV (conda-forge)"
            conda create -y -n "$CONDA_ENV" -c conda-forge python=3.11 \
                numpy pandas scipy "scikit-learn>=1.8" joblib matplotlib tifffile openpyxl \
                rasterio geopandas pyogrio shapely pyproj xarray netcdf4 requests pip \
                cdsapi cfgrib eccodes
        fi
        conda activate "$CONDA_ENV"
        pip install -q remotezip
    else
        if [[ ! -x "$ENV_DIR/bin/python" ]]; then
            log "Creating venv at $ENV_DIR with $(python3 --version)"
            python3 -m venv "$ENV_DIR"
        fi
        source "$ENV_DIR/bin/activate"
        pip install -q --upgrade pip
        pip install -q -r python/requirements.txt
    fi
    if [[ "${ES_EMBEDDINGS-unset}" != "" ]]; then         # NN embeddings (optional; ES_EMBEDDINGS="" to skip)
        log "Installing the geospatial embeddings wrapper (CPU torch)"
        use_certifi
        python -c "import torch, torchvision" 2>/dev/null \
            || pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
        pip install -q -r python/requirements-embeddings.txt \
            || log "WARNING: embeddings wrapper not installed — the NN-embeddings step will be skipped"
        # torch and torchvision must be built for each other; a torchvision pulled from
        # PyPI for a different torch fails with "operator torchvision::nms does not exist"
        if ! python -c "import torch, torchvision; torchvision.ops.nms" 2>/dev/null; then
            log "torch/torchvision mismatch — reinstalling a matching CPU pair"
            pip install -q --force-reinstall --no-deps torch torchvision \
                --index-url https://download.pytorch.org/whl/cpu
        fi
        python -c "import torch, torchvision; torchvision.ops.nms; print(f'torch {torch.__version__}  torchvision {torchvision.__version__}')" \
            || log "WARNING: torch/torchvision still broken — the NN-embeddings step will be skipped"
    fi
    python - <<'EOF'
import sys
import sklearn, rasterio, geopandas, pyogrio, xarray, cdsapi, cfgrib  # noqa: F401
v = tuple(int(x) for x in sklearn.__version__.split(".")[:2])
assert v >= (1, 8), f"scikit-learn {sklearn.__version__} < 1.8 (Lasso would silently become ridge)"
drivers = pyogrio.list_drivers()
if "OSM" not in drivers:
    sys.exit("This GDAL build has no OSM driver (needed to read the .osm.pbf). "
             "Re-run with CONDA_ENV=energysiting to use conda-forge GDAL.")
print(f"python {sys.version.split()[0]}  scikit-learn {sklearn.__version__}  "
      f"rasterio {rasterio.__version__}  geopandas {geopandas.__version__}  GDAL OSM driver: yes")
EOF
}

use_certifi() {
    # Some clusters' git has no CA bundle ("SSL certificate problem: unable to get
    # local issuer certificate") while Python's certifi works: point git and
    # requests at certifi (RANGE+ clones its code with git at first use).
    local ca
    ca="$(python -m certifi 2>/dev/null)" || return 0
    [[ -n "${GIT_SSL_CAINFO:-}" ]] || export GIT_SSL_CAINFO="$ca"
}

prepare() {
    log "1/2  Python environment"
    make_env
    log "2/2  Downloading raw inputs (resumable; skips files already present)"
    use_certifi
    python -m energysiting.setup.fetch
}

submit() {
    mkdir -p logs
    if command -v bsub &>/dev/null; then
        log "Submitting to LSF"
        ES_ROOT="$ES_ROOT" PY_MODULE="$PY_MODULE" CONDA_ENV="$CONDA_ENV" ENV_DIR="$ENV_DIR" \
            PIPELINE_ARGS="$PIPELINE_ARGS" bsub < "$ES_ROOT/python/run_all.sh"
    elif command -v sbatch &>/dev/null; then
        log "Submitting to SLURM"
        sbatch --export=ALL,ES_ROOT="$ES_ROOT",PY_MODULE="$PY_MODULE",CONDA_ENV="$CONDA_ENV",ENV_DIR="$ENV_DIR",PIPELINE_ARGS="$PIPELINE_ARGS" \
            "$ES_ROOT/python/run_all.sh"
    else
        echo "Neither bsub nor sbatch found — use: bash python/run_all.sh local" >&2
        exit 1
    fi
    log "Logs will appear in $ES_ROOT/logs/"
}

run_pipeline() {
    activate_env
    export ES_N_JOBS="${LSB_DJOB_NUMPROC:-${SLURM_CPUS_PER_TASK:-$(nproc)}}"
    export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1   # parallelism = joblib workers
    export OSM_MAX_TMPFILE_SIZE=4096                                    # MB of RAM for GDAL's OSM reader
    export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1                      # embeddings: weights cached by prepare
    log "Host $(hostname)  CPUs $ES_N_JOBS  root $ES_ROOT"
    log "Checking raw inputs"
    python -m energysiting.setup.fetch --check
    log "python python/run_all.py $PIPELINE_ARGS"
    # shellcheck disable=SC2086
    python python/run_all.py $PIPELINE_ARGS
    log "Done. Outputs: derived/ (stacks), derived/py/ (results), fig/python/ (figures)"
}

if [[ "$IN_JOB" == 1 ]]; then
    run_pipeline
    exit 0
fi

case "${1:-all}" in
    all)     prepare && submit ;;
    prepare) prepare ;;
    submit)  submit ;;
    check)   activate_env && python -m energysiting.setup.fetch --check ;;
    local)   prepare && run_pipeline ;;
    *)       sed -n '2,25p' "$0"; exit 1 ;;
esac
