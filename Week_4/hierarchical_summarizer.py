import os
import subprocess

def run_inference_for_file(java_file_path, base_output_dir, root_dir):
    """
    Runs the SLURM job for a single Java file to generate its summary, skipping if it already exists.
    """
    # Determine the relative path and create a corresponding output directory
    relative_path = os.path.relpath(os.path.dirname(java_file_path), root_dir)
    output_dir = os.path.join(base_output_dir, relative_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Check if the summary file already exists
    output_filename = os.path.join(output_dir, os.path.basename(java_file_path) + ".txt")
    if os.path.exists(output_filename):
        print(f"--- Summary for {os.path.relpath(java_file_path, root_dir)} already exists. Skipping. ---")
        return

    print(f"--- Starting summarization for: {os.path.relpath(java_file_path, root_dir)} ---")
    
    # Set environment variables for the child process
    env = os.environ.copy()
    env["SUMMARY_TARGET_FILE"] = java_file_path
    
    # Define the srun command
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
        "./sample.sh"
    ]

    try:
        process = subprocess.run(
            srun_command,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        
        output_lines = process.stdout.splitlines()
        summary_started = False
        summary = []
        # Find the model output from the captured stdout
        # This requires sample.py to have clear start/end markers for the output
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
            output_filename = os.path.join(output_dir, os.path.basename(java_file_path) + ".txt")
            with open(output_filename, "w") as f:
                f.write(summary_text)
            print(f"Successfully saved summary to {output_filename}")
        else:
            print(f"ERROR: Model output not found in stdout for {java_file_path}")
            print("Full log:", process.stdout)

    except subprocess.CalledProcessError as e:
        print(f"ERROR: SLURM job failed for {java_file_path} with exit code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
    except Exception as e:
        print(f"An unexpected error occurred for {java_file_path}: {e}")


def main():
    """
    Main function to find all Java files in a directory tree and process them.
    """
    base_dir = "/pc2/groups/hpc-prf-dssecs/group10"
    capacity_dir = os.path.join(base_dir, "capacity")
    output_dir = os.path.join(base_dir, "summaries")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    java_files = []
    for root, _, files in os.walk(capacity_dir):
        for file in files:
            if file.endswith(".java"):
                java_files.append(os.path.join(root, file))
    
    print(f"Found {len(java_files)} Java files to summarize in the '{capacity_dir}' directory tree.")

    for java_file in sorted(java_files):
        run_inference_for_file(java_file, output_dir, capacity_dir)
        print("-" * 50)

if __name__ == "__main__":
    main()
