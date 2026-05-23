#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TOOLS_DIR="arcade_tools"
OUTPUT_DIR="output"

A2A_TOOL="$TOOLS_DIR/arcade_core_A2a.jar"
CVG_TOOL="$TOOLS_DIR/arcade_core_Cvg.jar"

ACDC_RSF="$OUTPUT_DIR/acdc/hadoop_acdc_clusters.rsf"
LIMBO_RSF="$OUTPUT_DIR/limbo/hadoop-limbo-3.6.0-snapshot_IL_50_clusters.rsf"
WCA_RSF="$OUTPUT_DIR/wca/hadoop-wca-3.6.0-snapshot_UEM_50_clusters.rsf"

RESULTS_FILE="$OUTPUT_DIR/hadoop_a2a-cvg-results.txt"

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing required file: $1" >&2
    exit 1
  fi
}

run_metric() {
  local metric_name="$1"
  local tool="$2"
  local first_rsf="$3"
  local second_rsf="$4"
  local comparison_label="$5"

  {
    echo "============================================================"
    echo "$metric_name: $comparison_label"
    echo "Command: java -jar $tool $first_rsf $second_rsf"
    echo "------------------------------------------------------------"
  } | tee -a "$RESULTS_FILE"

  java -jar "$tool" "$first_rsf" "$second_rsf" | tee -a "$RESULTS_FILE"
  echo | tee -a "$RESULTS_FILE"
}

command -v java >/dev/null 2>&1 || {
  echo "Java is required but was not found in PATH." >&2
  exit 1
}

require_file "$A2A_TOOL"
require_file "$CVG_TOOL"
require_file "$ACDC_RSF"
require_file "$LIMBO_RSF"
require_file "$WCA_RSF"

: > "$RESULTS_FILE"

echo "Running A2a comparisons..."
run_metric "A2a" "$A2A_TOOL" "$ACDC_RSF" "$LIMBO_RSF" "ACDC vs LIMBO"
run_metric "A2a" "$A2A_TOOL" "$ACDC_RSF" "$WCA_RSF" "ACDC vs WCA"
run_metric "A2a" "$A2A_TOOL" "$LIMBO_RSF" "$WCA_RSF" "LIMBO vs WCA"

echo "Running Cvg comparisons..."
run_metric "Cvg" "$CVG_TOOL" "$ACDC_RSF" "$LIMBO_RSF" "ACDC vs LIMBO"
run_metric "Cvg" "$CVG_TOOL" "$ACDC_RSF" "$WCA_RSF" "ACDC vs WCA"
run_metric "Cvg" "$CVG_TOOL" "$LIMBO_RSF" "$WCA_RSF" "LIMBO vs WCA"

echo "Done. Results saved to: $RESULTS_FILE"
