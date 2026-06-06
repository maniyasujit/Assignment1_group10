from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


CAPACITY_PREFIX = (
    "org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity."
)

FILE_PROMPT = """You are an expert software architect.

Analyze the provided Java source file and produce a concise file-level semantic summary.

Your summary must include:
1. Key Functionality: What this file/class mainly does.
2. Core Logic: The important algorithm, control flow, or business logic.
3. Inputs/Outputs: Main inputs, outputs, state changes, or side effects.
4. Dependencies: Important classes, interfaces, libraries, frameworks, or Hadoop/YARN APIs used.

Keep the summary concise but specific.
Return only the summary text.
"""

CLUSTER_PROMPT = """You are a software architect.

You are given file-level summaries for files belonging to one recovered software cluster.
Do not describe every file separately. Instead, synthesize an architectural cluster-level result.

Generate:
1. A short architectural title.
2. A concise architectural description under 150 words.

The description must explicitly include:
- Main components in the cluster.
- How the components interact.
- Relevant quality attributes such as maintainability, scalability, reliability,
  configurability, performance, or security.
- Technologies, frameworks, languages, or libraries used.
- The overall architectural role of the cluster.

Return only:

Title:
<generated title>

Description:
<generated description>
"""


@dataclass(frozen=True)
class Layout:
    base_dir: Path
    artifact_dir: Path
    sample_sh: Path
    source_root: Path


@dataclass(frozen=True)
class AlgorithmConfig:
    name: str
    rsf_path: Path


def detect_layout() -> Layout:
    script_dir = Path(__file__).resolve().parent

    if (script_dir / "hadoop").exists() and (script_dir / "output").exists():
        base_dir = script_dir
        artifact_dir = script_dir
    elif (script_dir.parent / "hadoop").exists() and (script_dir.parent / "output").exists():
        base_dir = script_dir.parent
        artifact_dir = script_dir
    else:
        base_dir = Path(os.environ.get("GROUP10_BASE_DIR", "/pc2/groups/hpc-prf-dssecs/group10"))
        artifact_dir = base_dir

    sample_sh = script_dir / "sample.sh"
    if not sample_sh.exists():
        sample_sh = base_dir / "sample.sh"

    source_root = (
        base_dir
        / "hadoop"
        / "hadoop-yarn-project"
        / "hadoop-yarn"
        / "hadoop-yarn-server"
        / "hadoop-yarn-server-resourcemanager"
        / "src"
        / "main"
        / "java"
        / "org"
        / "apache"
        / "hadoop"
        / "yarn"
        / "server"
        / "resourcemanager"
        / "scheduler"
        / "capacity"
    )

    if not source_root.exists() and (base_dir / "capacity").exists():
        source_root = base_dir / "capacity"

    return Layout(
        base_dir=base_dir,
        artifact_dir=artifact_dir,
        sample_sh=sample_sh,
        source_root=source_root,
    )


def algorithm_configs(base_dir: Path) -> list[AlgorithmConfig]:
    return [
        AlgorithmConfig("ARC", base_dir / "output" / "week3" / "group10_week3_arc_clusters.rsf"),
        AlgorithmConfig("ACDC", base_dir / "output" / "acdc" / "hadoop_acdc_clusters.rsf"),
        AlgorithmConfig(
            "LIMBO",
            base_dir / "output" / "limbo" / "hadoop-limbo-3.6.0-snapshot_IL_50_clusters.rsf",
        ),
    ]


def natural_sort_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(value))]


def safe_file_id(relative_java_path: str) -> str:
    return relative_java_path.replace("/", "__").replace("\\", "__").replace(".java", "")


def read_rsf(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"RSF file not found: {path}")

    clusters: dict[str, list[str]] = defaultdict(list)
    with path.open() as handle:
        for line in handle:
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] == "contain":
                clusters[parts[1]].append(parts[2])
    return dict(clusters)


def build_source_index(source_root: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    if not source_root.exists():
        raise FileNotFoundError(f"Source root not found: {source_root}")

    by_relative: dict[str, Path] = {}
    basename_candidates: dict[str, list[Path]] = defaultdict(list)

    for source_path in sorted(source_root.rglob("*.java")):
        relative_key = source_path.relative_to(source_root).as_posix()
        by_relative[relative_key] = source_path
        basename_candidates[source_path.name].append(source_path)

    by_basename = {
        basename: paths[0]
        for basename, paths in basename_candidates.items()
        if len(paths) == 1
    }
    return by_relative, by_basename


def object_to_java_file(
    algorithm: str,
    raw_object: str,
    source_root: Path,
    source_by_relative: dict[str, Path],
    source_by_basename: dict[str, Path],
) -> str | None:
    # Converts inner-class objects such as X$Inner to the outer Java file X.java.
    class_name = raw_object.split("$", 1)[0]

    if class_name.startswith(CAPACITY_PREFIX):
        relative_java = class_name[len(CAPACITY_PREFIX):].replace(".", "/") + ".java"
        return relative_java if relative_java in source_by_relative else None

    simple_name = class_name.rsplit(".", 1)[-1]
    if not simple_name.endswith(".java"):
        simple_name = f"{simple_name}.java"

    # ARC output often already has file/class names without the full package.
    if algorithm == "ARC" and simple_name in source_by_basename:
        return source_by_basename[simple_name].relative_to(source_root).as_posix()

    return None


def normalise_clusters(
    algorithm: str,
    raw_clusters: dict[str, list[str]],
    source_root: Path,
    source_by_relative: dict[str, Path],
    source_by_basename: dict[str, Path],
) -> tuple[list[dict[str, object]], int]:
    rows: list[dict[str, object]] = []
    skipped = 0
    sorted_cluster_ids = sorted(raw_clusters, key=natural_sort_key)
    raw_cluster_order = {cluster_id: index for index, cluster_id in enumerate(sorted_cluster_ids)}

    file_cluster_counts: dict[str, Counter[str]] = defaultdict(Counter)
    file_outer_clusters: dict[str, set[str]] = defaultdict(set)

    for original_cluster_id in sorted_cluster_ids:
        for raw_object in raw_clusters[original_cluster_id]:
            java_file = object_to_java_file(
                algorithm,
                raw_object,
                source_root,
                source_by_relative,
                source_by_basename,
            )
            if java_file is None:
                skipped += 1
                continue

            file_cluster_counts[java_file][original_cluster_id] += 1
            if "$" not in raw_object:
                file_outer_clusters[java_file].add(original_cluster_id)

    chosen_clusters: dict[str, list[str]] = defaultdict(list)
    for java_file, cluster_counts in file_cluster_counts.items():
        chosen_cluster = max(
            cluster_counts,
            key=lambda cluster_id: (
                cluster_id in file_outer_clusters[java_file],
                cluster_counts[cluster_id],
                -raw_cluster_order[cluster_id],
            ),
        )
        chosen_clusters[chosen_cluster].append(java_file)

    display_index = 1
    for original_cluster_id in sorted_cluster_ids:
        files = sorted(set(chosen_clusters[original_cluster_id]), key=natural_sort_key)
        if files:
            rows.append(
                {
                    "cluster_ID": f"{algorithm}_{display_index:02d}",
                    "original_cluster_ID": original_cluster_id,
                    "files": files,
                }
            )
            display_index += 1

    return rows, skipped


def parse_model_output(stdout: str) -> str | None:
    output_lines = stdout.splitlines()
    summary_started = False
    summary: list[str] = []

    for line in output_lines:
        if "--- Model Output ---" in line:
            summary_started = True
            continue
        if "--- Generation Complete ---" in line:
            break
        if summary_started:
            summary.append(line)

    summary_text = "\n".join(summary).strip()
    return summary_text or None


def run_llm(
    layout: Layout,
    target_file: Path,
    prompt: str,
    raw_output_file: Path,
    overwrite: bool,
    label: str,
) -> str | None:
    if raw_output_file.exists() and not overwrite:
        print(f"--- Existing LLM output found for {label}. Skipping. ---")
        return raw_output_file.read_text(errors="replace").strip()

    if shutil.which("srun") is None:
        print(f"WARNING: srun not found. Cannot call LLM for {label}.")
        return None

    raw_output_file.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["SUMMARY_TARGET_FILE"] = str(target_file)
    env["SUMMARY_PROMPT"] = prompt

    srun_command = [
        "srun",
        "--partition=dgx",
        "--qos=devel",
        "--nodes=1",
        "--ntasks=1",
        "--cpus-per-task=16",
        "--gres=gpu:a100:5",
        "--mem=300G",
        "--time=01:00:00",
        "bash",
        str(layout.sample_sh),
    ]

    print(f"--- Starting LLM call for {label} ---")
    try:
        process = subprocess.run(
            srun_command,
            capture_output=True,
            text=True,
            check=True,
            env=env,
            cwd=layout.base_dir,
        )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: SLURM/LLM call failed for {label} with exit code {exc.returncode}")
        print("STDOUT:", exc.stdout)
        print("STDERR:", exc.stderr)
        return None

    model_output = parse_model_output(process.stdout)
    if not model_output:
        print(f"ERROR: Could not parse model output for {label}.")
        print("Full STDOUT:", process.stdout)
        print("Full STDERR:", process.stderr)
        return None

    raw_output_file.write_text(model_output, encoding="utf-8")
    print(f"Saved LLM output to {raw_output_file}")
    return model_output


def collect_unique_files(rows_by_algorithm: dict[str, list[dict[str, object]]]) -> list[str]:
    files: set[str] = set()
    for rows in rows_by_algorithm.values():
        for row in rows:
            files.update(row["files"])
    return sorted(files, key=natural_sort_key)


def summarize_files(
    layout: Layout,
    files: list[str],
    source_by_relative: dict[str, Path],
    overwrite: bool,
) -> dict[str, str]:
    file_summary_dir = layout.artifact_dir / "hierarchical_outputs" / "file_summaries"
    file_summary_dir.mkdir(parents=True, exist_ok=True)

    summaries: dict[str, str] = {}
    for relative_file in files:
        source_path = source_by_relative[relative_file]
        summary_path = file_summary_dir / f"{safe_file_id(relative_file)}.txt"

        summary = run_llm(
            layout=layout,
            target_file=source_path,
            prompt=FILE_PROMPT,
            raw_output_file=summary_path,
            overwrite=overwrite,
            label=f"file {relative_file}",
        )
        if summary:
            summaries[relative_file] = summary

    return summaries


def read_existing_file_summaries(artifact_dir: Path, files: list[str]) -> dict[str, str]:
    file_summary_dir = artifact_dir / "hierarchical_outputs" / "file_summaries"
    summaries: dict[str, str] = {}
    for relative_file in files:
        summary_path = file_summary_dir / f"{safe_file_id(relative_file)}.txt"
        if summary_path.exists():
            summaries[relative_file] = summary_path.read_text(errors="replace").strip()
    return summaries


def write_converted_clusters(artifact_dir: Path, algorithm: str, rows: list[dict[str, object]]) -> None:
    converted_dir = artifact_dir / "hierarchical_outputs" / "converted_clusters"
    converted_dir.mkdir(parents=True, exist_ok=True)
    output_path = converted_dir / f"{algorithm}_file_clusters.csv"

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["cluster_ID", "original_cluster_ID", "files"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "cluster_ID": row["cluster_ID"],
                    "original_cluster_ID": row["original_cluster_ID"],
                    "files": "; ".join(row["files"]),
                }
            )


def write_cluster_summary_input(
    artifact_dir: Path,
    algorithm: str,
    row: dict[str, object],
    file_summaries: dict[str, str],
) -> Path:
    input_dir = artifact_dir / "hierarchical_outputs" / "cluster_summary_inputs" / algorithm
    input_dir.mkdir(parents=True, exist_ok=True)

    cluster_id = str(row["cluster_ID"])
    output_path = input_dir / f"{cluster_id}.txt"

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(f"Algorithm: {algorithm}\n")
        handle.write(f"Cluster ID: {cluster_id}\n")
        handle.write(f"Original cluster ID: {row['original_cluster_ID']}\n")
        handle.write("Files:\n")
        for file_name in row["files"]:
            handle.write(f"- {file_name}\n")

        handle.write("\nFile-level summaries:\n")
        for file_name in row["files"]:
            handle.write(f"\n===== FILE SUMMARY: {file_name} =====\n")
            summary = file_summaries.get(file_name, "").strip()
            if summary:
                handle.write(summary)
            else:
                handle.write("[MISSING FILE SUMMARY]")
            handle.write("\n")

    return output_path


def parse_title_description(model_output: str) -> tuple[str, str]:
    match = re.search(
        r"\*{0,2}Title:\*{0,2}\s*(.*?)\s*\*{0,2}Description:\*{0,2}\s*(.*)",
        model_output,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        title = match.group(1).strip()
        description = match.group(2).strip()
    else:
        lines = [line.strip() for line in model_output.splitlines() if line.strip()]
        title = lines[0] if lines else ""
        description = " ".join(lines[1:]).strip()

    # Enforce tutor requirement.
    words = description.split()
    if len(words) > 149:
        description = " ".join(words[:149]).rstrip(".,;") + "."

    return title, description


def write_algorithm_llm_outputs(
    artifact_dir: Path,
    algorithm: str,
    outputs: dict[str, dict[str, str]],
) -> None:
    output_dir = artifact_dir / "hierarchical_outputs" / "cluster_llm_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{algorithm}_llm_outputs.csv"

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["cluster_ID", "title", "description"])
        writer.writeheader()
        for cluster_id in sorted(outputs, key=natural_sort_key):
            writer.writerow(
                {
                    "cluster_ID": cluster_id,
                    "title": outputs[cluster_id]["title"],
                    "description": outputs[cluster_id]["description"],
                }
            )


def read_algorithm_llm_outputs(artifact_dir: Path, algorithm: str) -> dict[str, dict[str, str]]:
    output_path = artifact_dir / "hierarchical_outputs" / "cluster_llm_outputs" / f"{algorithm}_llm_outputs.csv"
    if not output_path.exists():
        return {}

    outputs: dict[str, dict[str, str]] = {}
    with output_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            outputs[row["cluster_ID"].strip()] = {
                "title": row.get("title", "").strip(),
                "description": row.get("description", "").strip(),
            }
    return outputs


def summarize_clusters(
    layout: Layout,
    algorithm: str,
    rows: list[dict[str, object]],
    file_summaries: dict[str, str],
    overwrite: bool,
) -> dict[str, dict[str, str]]:
    outputs = read_algorithm_llm_outputs(layout.artifact_dir, algorithm)

    for row in rows:
        cluster_id = str(row["cluster_ID"])
        target_file = write_cluster_summary_input(
            artifact_dir=layout.artifact_dir,
            algorithm=algorithm,
            row=row,
            file_summaries=file_summaries,
        )

        raw_output_file = (
            layout.artifact_dir
            / "hierarchical_outputs"
            / "cluster_llm_outputs"
            / "raw"
            / algorithm
            / f"{cluster_id}.txt"
        )

        model_output = run_llm(
            layout=layout,
            target_file=target_file,
            prompt=CLUSTER_PROMPT,
            raw_output_file=raw_output_file,
            overwrite=overwrite,
            label=f"cluster {cluster_id}",
        )

        if model_output:
            title, description = parse_title_description(model_output)
            outputs[cluster_id] = {"title": title, "description": description}

    write_algorithm_llm_outputs(layout.artifact_dir, algorithm, outputs)
    return outputs


def write_results_csv(
    artifact_dir: Path,
    algorithm: str,
    rows: list[dict[str, object]],
    llm_outputs: dict[str, dict[str, str]],
) -> None:
    # This is the exact final format requested by the tutor.
    output_path = artifact_dir / f"{algorithm}_results.csv"

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["cluster_ID", "files", "title", "description"])
        writer.writeheader()

        for row in rows:
            cluster_id = str(row["cluster_ID"])
            llm_row = llm_outputs.get(cluster_id, {})
            writer.writerow(
                {
                    "cluster_ID": cluster_id,
                    "files": "; ".join(row["files"]),
                    "title": llm_row.get("title", ""),
                    "description": llm_row.get("description", ""),
                }
            )


def write_prompt_files(artifact_dir: Path) -> None:
    output_dir = artifact_dir / "hierarchical_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "file_level_prompt.txt").write_text(FILE_PROMPT, encoding="utf-8")
    (output_dir / "cluster_level_prompt.txt").write_text(CLUSTER_PROMPT, encoding="utf-8")


def selected_algorithms(configs: list[AlgorithmConfig], selected: set[str] | None) -> list[AlgorithmConfig]:
    if not selected:
        return configs
    return [config for config in configs if config.name in selected]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="True hierarchical summarization: Java file summaries -> cluster summaries -> final CSVs."
    )
    parser.add_argument(
        "--algorithm",
        choices=["ARC", "ACDC", "LIMBO"],
        action="append",
        help="Run only one algorithm. Can be used multiple times.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Do not call the LLM. Rebuild converted clusters and final CSVs from existing summaries.",
    )
    parser.add_argument(
        "--skip-file-summaries",
        action="store_true",
        help="Reuse existing file summaries and only run cluster summarization.",
    )
    parser.add_argument(
        "--skip-cluster-summaries",
        action="store_true",
        help="Only create/reuse file summaries and converted clusters; do not summarize clusters.",
    )
    parser.add_argument(
        "--overwrite-file-summaries",
        action="store_true",
        help="Regenerate file-level summaries even if they already exist.",
    )
    parser.add_argument(
        "--overwrite-cluster-summaries",
        action="store_true",
        help="Regenerate cluster-level summaries even if they already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    layout = detect_layout()
    write_prompt_files(layout.artifact_dir)

    print(f"Base directory: {layout.base_dir}")
    print(f"Artifact directory: {layout.artifact_dir}")
    print(f"Source root: {layout.source_root}")
    print(f"sample.sh: {layout.sample_sh}")

    source_by_relative, source_by_basename = build_source_index(layout.source_root)
    print(f"Loaded {len(source_by_relative)} Java source files.")

    configs = selected_algorithms(
        algorithm_configs(layout.base_dir),
        set(args.algorithm) if args.algorithm else None,
    )

    rows_by_algorithm: dict[str, list[dict[str, object]]] = {}

    for config in configs:
        raw_clusters = read_rsf(config.rsf_path)
        rows, skipped = normalise_clusters(
            algorithm=config.name,
            raw_clusters=raw_clusters,
            source_root=layout.source_root,
            source_by_relative=source_by_relative,
            source_by_basename=source_by_basename,
        )
        rows_by_algorithm[config.name] = rows
        write_converted_clusters(layout.artifact_dir, config.name, rows)

        file_count = sum(len(row["files"]) for row in rows)
        print(
            f"{config.name}: {len(raw_clusters)} raw clusters -> "
            f"{len(rows)} file-level clusters, {file_count} file assignments, "
            f"{skipped} skipped entries."
        )

    unique_files = collect_unique_files(rows_by_algorithm)
    print(f"Unique Java files requiring file-level summaries: {len(unique_files)}")

    if args.no_llm or args.skip_file_summaries:
        file_summaries = read_existing_file_summaries(layout.artifact_dir, unique_files)
        print(f"Loaded {len(file_summaries)} existing file summaries.")
    else:
        file_summaries = summarize_files(
            layout=layout,
            files=unique_files,
            source_by_relative=source_by_relative,
            overwrite=args.overwrite_file_summaries,
        )

    missing_file_summaries = [file for file in unique_files if file not in file_summaries]
    if missing_file_summaries:
        print("WARNING: Some file summaries are missing:")
        for file_name in missing_file_summaries[:30]:
            print(f"  - {file_name}")
        if len(missing_file_summaries) > 30:
            print(f"  ... and {len(missing_file_summaries) - 30} more")

    for algorithm, rows in rows_by_algorithm.items():
        if args.no_llm or args.skip_cluster_summaries:
            cluster_outputs = read_algorithm_llm_outputs(layout.artifact_dir, algorithm)
        else:
            cluster_outputs = summarize_clusters(
                layout=layout,
                algorithm=algorithm,
                rows=rows,
                file_summaries=file_summaries,
                overwrite=args.overwrite_cluster_summaries,
            )

        write_results_csv(layout.artifact_dir, algorithm, rows, cluster_outputs)
        filled_count = sum(1 for row in rows if str(row["cluster_ID"]) in cluster_outputs)
        print(f"{algorithm}: wrote final CSV with {filled_count}/{len(rows)} LLM-filled rows.")

    print("\nDone.")
    print(f"Prompts: {layout.artifact_dir / 'hierarchical_outputs'}")
    print(f"File summaries: {layout.artifact_dir / 'hierarchical_outputs' / 'file_summaries'}")
    print(f"Cluster inputs: {layout.artifact_dir / 'hierarchical_outputs' / 'cluster_summary_inputs'}")
    print(f"Cluster LLM outputs: {layout.artifact_dir / 'hierarchical_outputs' / 'cluster_llm_outputs'}")
    print(f"Final CSV files: {layout.artifact_dir / 'ARC_results.csv'}, ACDC_results.csv, LIMBO_results.csv")


if __name__ == "__main__":
    main()
