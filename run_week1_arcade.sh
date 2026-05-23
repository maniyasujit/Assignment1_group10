#!/usr/bin/env bash
set -euo pipefail

# Recreates the Week 1 ARCADE pipeline:
# input Hadoop jar -> master RSF -> focused RSF -> WCA/Limbo/ACDC clusters.

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INPUT_DIR="$ROOT_DIR/input"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/output}"
ARCADE_DIR="${ARCADE_DIR:-$ROOT_DIR/arcade_tools}"

JAVAPARSER_JAR="$ARCADE_DIR/arcade_core_JavaParser.jar"
CLUSTERER_JAR="$ARCADE_DIR/arcade_core_clusterer.jar"
ACDC_JAR="$ARCADE_DIR/arcade_core-ACDC.jar"

MASTER_PREFIX="${MASTER_PREFIX:-org.apache.hadoop}"
FOCUS_PACKAGE="${FOCUS_PACKAGE:-org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity}"

PROJECT_VERSION="${PROJECT_VERSION:-3.6.0-snapshot}"
WCA_PROJECT="${WCA_PROJECT:-hadoop-wca}"
LIMBO_PROJECT="${LIMBO_PROJECT:-hadoop-limbo}"
WCA_MEASURE="${WCA_MEASURE:-uem}"
LIMBO_MEASURE="${LIMBO_MEASURE:-il}"

MASTER_RSF="$OUTPUT_DIR/facts/hadoop_resourcemanager_master.rsf"
MASTER_FF="$OUTPUT_DIR/facts/hadoop_resourcemanager_master.ff"
FOCUSED_RSF="$OUTPUT_DIR/facts/hadoop_yarn_capacity.rsf"
ACDC_RSF="$OUTPUT_DIR/acdc/hadoop_acdc_clusters.rsf"

if [[ -n "${INPUT_TARGET:-}" ]]; then
  TARGET="$INPUT_TARGET"
else
  TARGET="$(find "$INPUT_DIR" -maxdepth 1 -type f -name "*.jar" | sort | sed -n '1p')"
  if [[ -z "$TARGET" ]]; then
    echo "No jar found in: $INPUT_DIR" >&2
    echo "Put your generated Hadoop jar in input/ or run with INPUT_TARGET=/path/to/file.jar" >&2
    exit 1
  fi
fi

for required in "$JAVAPARSER_JAR" "$CLUSTERER_JAR" "$ACDC_JAR" "$TARGET"; do
  if [[ ! -e "$required" ]]; then
    echo "Missing required file: $required" >&2
    exit 1
  fi
done

mkdir -p "$OUTPUT_DIR/facts" "$OUTPUT_DIR/wca" "$OUTPUT_DIR/limbo" "$OUTPUT_DIR/acdc"

echo "Input target: $TARGET"
echo "Output dir:   $OUTPUT_DIR"
echo "Focus:        $FOCUS_PACKAGE"
echo "WCA measure:  $WCA_MEASURE"
echo "Limbo measure: $LIMBO_MEASURE"
echo

echo "1/4 Extracting master dependencies..."
java -jar "$JAVAPARSER_JAR" \
  "$TARGET" \
  "$MASTER_RSF" \
  "$MASTER_FF" \
  "$MASTER_PREFIX"

echo
echo "2/4 Filtering dependencies for focused package..."
awk -v p="$FOCUS_PACKAGE" \
  '$1=="depends" && ($2 ~ "^"p || $3 ~ "^"p)' \
  "$MASTER_RSF" > "$FOCUSED_RSF"

MASTER_LINES="$(wc -l < "$MASTER_RSF" | tr -d ' ')"
FOCUSED_LINES="$(wc -l < "$FOCUSED_RSF" | tr -d ' ')"
echo "Master RSF lines:  $MASTER_LINES"
echo "Focused RSF lines: $FOCUSED_LINES"

if [[ "$FOCUSED_LINES" -eq 0 ]]; then
  echo "Focused RSF is empty. Check FOCUS_PACKAGE." >&2
  exit 1
fi

echo
echo "3/4 Running WCA and Limbo clustering..."
java -jar "$CLUSTERER_JAR" \
  algo=wca \
  measure="$WCA_MEASURE" \
  projname="$WCA_PROJECT" \
  projversion="$PROJECT_VERSION" \
  projpath="$OUTPUT_DIR/wca" \
  deps="$FOCUSED_RSF" \
  language=java

java -jar "$CLUSTERER_JAR" \
  algo=limbo \
  measure="$LIMBO_MEASURE" \
  projname="$LIMBO_PROJECT" \
  projversion="$PROJECT_VERSION" \
  projpath="$OUTPUT_DIR/limbo" \
  deps="$FOCUSED_RSF" \
  language=java

echo
echo "4/4 Running ACDC clustering..."
java -jar "$ACDC_JAR" "$FOCUSED_RSF" "$ACDC_RSF"

echo
echo "Generated files:"
find "$OUTPUT_DIR" -type f | sort
