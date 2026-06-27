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

source .venv/bin/activate

indicators=(
    OEB
    OEC
    NXA
    SDA
    SNM
    PSU
    PRS
    RCY
    MKP
    MHP
    MPE
    PAR
    BER
    SHI
    SPI
    PAE
    PHL
    TBN
    TKP
    RLI
    PFL
    IFL
    FCL
    TCG
    FLI
    FSS
    FCD
    BTZ
    BTO
    RMS
    WWG
    WWC
    WWT
    WWR
    COE
    HFD
    HFX
    NOD
    NOE
    OZD
    OZE
    HPE
    SOE
    VOE
    LED
    LEX
    WPC
    WRR
    SMW
    USD
    UWD
    USX
    UWX
    CDA
    CDF
    CHA
    FGA
    NDA
    BCA
    GHN
    GHI
    GHP
    GHA
    LUF
    GTI
    GTP
    CBP
)

export OUTPUTS_DIR=new-outputs

ts_echo "Processing ${#indicators[@]} indicators"

for ind in "${indicators[@]}"; do
    ts_echo "Start processing indicator: ${ind}"
    python -m src -i "${ind}"
    ts_echo "End processing indicator: ${ind}"
done
