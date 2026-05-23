#!/bin/bash
#SBATCH --job-name=group10_GLM5
#SBATCH --partition=gpu
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:a100:5
#SBATCH --mem=300G
#SBATCH --output=sample_out_%j.log
#SBATCH --error=sample_err_%j.log

set -x
echo "=================================================="
echo "Job started on \$(date)"
echo "Running on node: \$(hostname)"
echo "Working directory: \$(pwd)"
echo "=================================================="

cd /pc2/groups/hpc-prf-dssecs/group10 || exit 1

module purge
module load lang/Python/3.10.4-GCCcore-11.3.0
module load system/CUDA/12.4.0

source /pc2/groups/hpc-prf-dssecs/group10/venv/bin/activate

export HF_HOME=/scratch/hpc-prf-dssecs/jenish_hf_cache
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export HF_TOKEN="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"
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

python sample.py
