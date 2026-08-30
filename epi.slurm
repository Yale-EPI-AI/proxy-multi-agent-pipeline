#!/bin/bash

#SBATCH --output=logs/%x-%j_%A_%a.out
#SBATCH --error=logs/%x-%j_%A_%a.err
#SBATCH --mail-type=ALL

#SBATCH --job-name=epi-120b
#SBATCH --time=48:00:00
#SBATCH --mem=200G
#SBATCH --partition=gpu_h200
#SBATCH --gpus=h200:1
#SBATCH --cpus-per-task=5

ts_echo() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') | ${*}"
}

indicators_file=$(mktemp)
cat >"$indicators_file" <<'EOF'
BCA
BER
BTO
BTZ
CBP
CDA
CDF
CHA
COE
FCD
FCL
FGA
FLI
FSS
GHA
GHI
GHN
GHP
GTI
GTP
HFD
HFX
HPE
IFL
LED
LEX
LUF
MHP
MKP
MPE
NDA
NOD
NOE
NXA
OEB
OEC
OZD
OZE
PAE
PAR
PFL
PHL
PRS
PSU
RCY
RLI
RMS
SDA
SHI
SMW
SNM
SOE
SPI
TBN
TCG
TKP
USD
USX
UWD
UWX
VOE
WPC
WRR
WWC
WWG
WWR
WWT
EOF

# Variables exported here override values in the .env file.
# Edit these variables directly before submitting the job

# export USE_LOCAL_INFERENCE=true
# export LOCAL_MODEL_NAME="openai/gpt-oss-120b"
# export LOCAL_ENGINE_TYPE="vllm"
# export LOCAL_ENGINE_ARGS="--tool-call-parser openai --enable-auto-tool-choice --enable-chunked-prefill --enable-prefix-caching --async-scheduling"

export OUTPUTS_DIR="new-outputs"

mkdir -p logs "$OUTPUTS_DIR"

ts_echo "Processing indicators with model: $LOCAL_MODEL_NAME"
ts_echo "Outputs directory: $OUTPUTS_DIR"
uv run epi-proxy --indicators-file "$indicators_file"
rm -f "$indicators_file"
