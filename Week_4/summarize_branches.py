import os
import subprocess
import sys

def run_summary_job(target_file, output_file, prompt):
    """
    Runs a SLURM job to summarize a given text file.
    """
    print(f"--- Starting summarization job for: {os.path.basename(target_file)} ---")
    
    env = os.environ.copy()
    env["SUMMARY_TARGET_FILE"] = target_file
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
            with open(output_file, "w") as f:
                f.write(summary_text)
            print(f"Successfully saved summary to {output_file}")
            return summary_text
        else:
            print(f"ERROR: Model output not found in stdout for {target_file}")
            print("Full log:", process.stdout)
            return None

    except subprocess.CalledProcessError as e:
        print(f"ERROR: SLURM job failed for {target_file} with exit code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred for {target_file}: {e}")
        return None

def main():
    base_dir = "/pc2/groups/hpc-prf-dssecs/group10"
    summaries_dir = os.path.join(base_dir, "summaries")
    branch_summaries_dir = os.path.join(base_dir, "branch_summaries")
    
    if not os.path.exists(branch_summaries_dir):
        os.makedirs(branch_summaries_dir)

    # --- 1. Process Branch Nodes ---
    print("--- Starting Branch Node Summarization ---")
    branch_summary_files = []
    
    # Also process files in the root of summaries_dir (the non-subdirectory ones)
    top_level_files = [f for f in os.listdir(summaries_dir) if os.path.isfile(os.path.join(summaries_dir, f)) and f.endswith('.txt')]
    if top_level_files:
        print(f"Found {len(top_level_files)} top-level summary files to process as a branch.")
        combined_branch_path = os.path.join(branch_summaries_dir, "temp_top_level_branch.txt")
        with open(combined_branch_path, 'w') as outfile:
            for filename in top_level_files:
                with open(os.path.join(summaries_dir, filename)) as infile:
                    outfile.write(f"--- Summary for {filename.replace('.java.txt', '.java')} ---\n")
                    outfile.write(infile.read())
                    outfile.write("\n\n")
        
        branch_output_file = os.path.join(branch_summaries_dir, "top_level_summary.txt")
        prompt = "Based on the following summaries of individual Java files, provide a concise summary of this group of components."
        if run_summary_job(combined_branch_path, branch_output_file, prompt):
            branch_summary_files.append(branch_output_file)
        os.remove(combined_branch_path) # Clean up temp file
        print("-" * 50)


    for branch_name in sorted([d for d in os.listdir(summaries_dir) if os.path.isdir(os.path.join(summaries_dir, d))]):
        branch_dir = os.path.join(summaries_dir, branch_name)
        print(f"--- Processing Branch: {branch_name} ---")
        
        leaf_summaries = [f for f in os.listdir(branch_dir) if f.endswith('.txt')]
        if not leaf_summaries:
            continue

        combined_branch_path = os.path.join(branch_summaries_dir, f"temp_{branch_name}_branch.txt")
        with open(combined_branch_path, 'w') as outfile:
            for filename in leaf_summaries:
                with open(os.path.join(branch_dir, filename)) as infile:
                    outfile.write(f"--- Summary for {filename.replace('.java.txt', '.java')} ---\n")
                    outfile.write(infile.read())
                    outfile.write("\n\n")
        
        branch_output_file = os.path.join(branch_summaries_dir, f"{branch_name}_summary.txt")
        prompt = f"You are summarizing the '{branch_name}' sub-module. Based on the following summaries of its files, provide a concise summary of this sub-module's role and functionality."
        if run_summary_job(combined_branch_path, branch_output_file, prompt):
            branch_summary_files.append(branch_output_file)
        
        os.remove(combined_branch_path) # Clean up temp file
        print("-" * 50)

    # --- 2. Process Root Node ---
    print("\n--- Starting Root Node Summarization ---")
    if not branch_summary_files:
        print("ERROR: No branch summaries were generated. Cannot create a root summary.")
        sys.exit(1)

    final_combined_path = os.path.join(base_dir, "final_combined_summaries.txt")
    with open(final_combined_path, 'w') as outfile:
        for branch_file in branch_summary_files:
            branch_name = os.path.basename(branch_file).replace('_summary.txt', '')
            outfile.write(f"--- High-Level Summary for Sub-Module: {branch_name} ---\n")
            with open(branch_file) as infile:
                outfile.write(infile.read())
            outfile.write("\n\n")
            
    final_output_file = os.path.join(base_dir, "final_architectural_summary.txt")
    prompt = "Based on the following high-level summaries of different sub-modules, generate a final, comprehensive architectural summary. Describe the overall purpose of the entire module, how the sub-modules interact, and the key responsibilities of each part."
    final_summary = run_summary_job(final_combined_path, final_output_file, prompt)

    if final_summary:
        print("\n--- !!! FINAL ARCHITECTURAL SUMMARY !!! ---")
        print(final_summary)
        print(f"\nSUCCESS: Final summary saved to {final_output_file}")
    else:
        print("ERROR: Failed to generate the final architectural summary.")
    
    os.remove(final_combined_path) # Clean up final temp file

if __name__ == "__main__":
    main()
