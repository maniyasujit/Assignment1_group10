#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

TOOLS_DIR="$ROOT_DIR/arcade_tools"
OUTPUT_DIR="$ROOT_DIR/output"
WEEK3_DIR="$OUTPUT_DIR/week3"

A2A_TOOL="$TOOLS_DIR/arcade_core_A2a.jar"
CVG_TOOL="$TOOLS_DIR/arcade_core_Cvg.jar"

ARC_RSF="$WEEK3_DIR/group10_week3_arc_clusters.rsf"
ACDC_RSF="$OUTPUT_DIR/acdc/hadoop_acdc_clusters.rsf"
LIMBO_RSF="$OUTPUT_DIR/limbo/hadoop-limbo-3.6.0-snapshot_IL_50_clusters.rsf"
WCA_RSF="$OUTPUT_DIR/wca/hadoop-wca-3.6.0-snapshot_UEM_50_clusters.rsf"

RESULTS_FILE="$OUTPUT_DIR/group10_week3_arc_a2a-cvg-results.txt"

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing required file: $1" >&2
    exit 1
  fi
}

run_metric() {
  local metric_name="$1"
  local tool="$2"
  local baseline_rsf="$3"
  local comparison_label="$4"

  {
    echo "============================================================"
    echo "$metric_name: ARC vs $comparison_label"
    echo "Command: java -jar $tool $ARC_RSF $baseline_rsf"
    echo "------------------------------------------------------------"
  } | tee -a "$RESULTS_FILE"

  java -jar "$tool" "$ARC_RSF" "$baseline_rsf" | tee -a "$RESULTS_FILE"
  echo | tee -a "$RESULTS_FILE"
}

command -v java >/dev/null 2>&1 || {
  echo "Java is required but was not found in PATH." >&2
  exit 1
}

require_file "$A2A_TOOL"
require_file "$CVG_TOOL"
require_file "$ARC_RSF"
require_file "$ACDC_RSF"
require_file "$LIMBO_RSF"
require_file "$WCA_RSF"

mkdir -p "$OUTPUT_DIR"
: > "$RESULTS_FILE"

echo "Running Week 3 ARC comparisons..."
echo "ARC RSF:     $ARC_RSF"
echo "Results:     $RESULTS_FILE"
echo

run_metric "A2a" "$A2A_TOOL" "$ACDC_RSF" "ACDC"
run_metric "Cvg" "$CVG_TOOL" "$ACDC_RSF" "ACDC"

run_metric "A2a" "$A2A_TOOL" "$LIMBO_RSF" "LIMBO"
run_metric "Cvg" "$CVG_TOOL" "$LIMBO_RSF" "LIMBO"

run_metric "A2a" "$A2A_TOOL" "$WCA_RSF" "WCA"
run_metric "Cvg" "$CVG_TOOL" "$WCA_RSF" "WCA"

echo "Done. Results saved to: $RESULTS_FILE"
