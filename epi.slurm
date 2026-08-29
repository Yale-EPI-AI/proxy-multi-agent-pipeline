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

export OUTPUTS_DIR=new-outputs

ts_echo "Processing all indicators with shared inference engine"
uv run epi-proxy --indicators-file "$indicators_file"
rm -f "$indicators_file"
