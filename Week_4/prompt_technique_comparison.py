import os
import subprocess
import sys

# --- 1. DEFINE THE PROMPTING TECHNIQUES ---

PROMPTS = {
    "zero_shot": "Summarize the following code.",
    
    "one_shot": """Here is an example of how to summarize a Java file.

**Example Input (AbstractCSQueue.java):**
```java
/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,

 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
 package org.apache.hadoop.yarn.server.resourcemanager.scheduler.capacity;
 // ... (code for AbstractCSQueue.java)
```

**Example Output:**
1.  **Key Functionality:** An abstract base class for queues in the Capacity Scheduler, providing common functionalities like resource management and application handling.
2.  **Core Logic:** Implements core queue operations such as submitting applications, completing applications, and updating queue resources.
3.  **Inputs/Outputs:** Inputs are applications and resource objects; Outputs are state changes to the queue and scheduler.
4.  **Dependencies:** Depends on `CSQueue`, `Resource`, and `SchedulerApplicationAttempt`.

---
Now, using the exact same format, summarize the following code:
""",

    "chain_of_thought": """Analyze the following code and provide a summary. First, think step-by-step about the code's purpose. Identify the main classes and their roles. Trace the logic for how it enforces limits. Then, based on your reasoning, provide a final summary structured with sections for Key Functionality, Core Logic, Inputs/Outputs, and Dependencies.
"""
}

def run_inference_for_file(java_file_path, technique, prompt, base_output_dir, root_dir):
    """
    Runs the SLURM job for a single Java file using a specific prompting technique.
    """
    # Determine the relative path and create a corresponding output directory for the technique
    relative_path = os.path.relpath(os.path.dirname(java_file_path), root_dir)
    output_dir = os.path.join(base_output_dir, technique, relative_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Check if the summary file already exists
    output_filename = os.path.join(output_dir, os.path.basename(java_file_path) + ".txt")
    if os.path.exists(output_filename):
        print(f"--- [{technique}] Summary for {os.path.basename(java_file_path)} already exists. Skipping. ---")
        return

    print(f"--- [{technique}] Starting summarization for: {os.path.basename(java_file_path)} ---")
    
    env = os.environ.copy()
    env["SUMMARY_TARGET_FILE"] = java_file_path
    env["SUMMARY_PROMPT"] = prompt
    
    srun_command = [
        "srun", "--partition=dgx", "--qos=devel", "--nodes=1", "--ntasks=1",
        "--cpus-per-task=16", "--gres=gpu:a100:5", "--mem=300G", "--time=01:00:00",
        "bash", "./sample.sh"
    ]

    try:
        process = subprocess.run(
            srun_command, capture_output=True, text=True, check=True, env=env
        )
        
        output_lines = process.stdout.splitlines()
        summary_started = False
        summary = []
        for line in output_lines:
            if "--- Model Output ---" in line:
                summary_started = True
                continue
            if "--- Generation Complete ---" in line:
                break
            if summary_started:
                summary.append(line)

        if summary:
            summary_text = "\n".join(summary).strip()
            with open(output_filename, "w") as f:
                f.write(summary_text)
            print(f"Successfully saved summary to {output_filename}")
        else:
            print(f"ERROR: Model output not found for {java_file_path}")

    except subprocess.CalledProcessError as e:
        print(f"ERROR: SLURM job failed for {java_file_path} with exit code {e.returncode}")
        print("STDERR:", e.stderr)

def main():
    """
    Main function to run a comparison of different prompting techniques on a subset of files.
    """
    base_dir = "/pc2/groups/hpc-prf-dssecs/group10"
    capacity_dir = os.path.join(base_dir, "capacity")
    comparison_output_dir = os.path.join(base_dir, "prompt_comparison_results")
    
    # --- 2. SELECT A SUBSET OF FILES FOR COMPARISON ---
    files_to_test = [
        os.path.join(capacity_dir, "AbsoluteResourceCapacityCalculator.java"),
        os.path.join(capacity_dir, "CSMaxRunningAppsEnforcer.java")
    ]

    print(f"Starting prompt technique comparison for {len(files_to_test)} files.")
    
    # --- 3. LOOP THROUGH FILES AND PROMPTING TECHNIQUES ---
    for java_file in files_to_test:
        if not os.path.exists(java_file):
            print(f"WARNING: Test file not found: {java_file}. Skipping.")
            continue
            
        print(f"\n{'='*20} Processing File: {os.path.basename(java_file)} {'='*20}")
        for technique, prompt in PROMPTS.items():
            run_inference_for_file(java_file, technique, prompt, comparison_output_dir, capacity_dir)
            print("-" * 50)

    print("\nPrompt technique comparison complete.")
    print(f"Results saved in: {comparison_output_dir}")

if __name__ == "__main__":
    main()
