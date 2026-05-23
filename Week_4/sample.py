# ==========================================
# 0. IMPORT THE REQUIRED DEPENDENCIES
# ==========================================
import torch
import sys
from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer

# ==========================================
# 1. ENVIRONMENT & MODEL SETUP
# ==========================================
model_name = "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF" 

import os
hf_token = os.environ.get('HF_TOKEN')
if not hf_token:
    print("WARNING: HF_TOKEN not found. Proceeding with open-weights model download.")

# ==========================================
# 2. LOAD THE TOKENIZER
# ==========================================
print(f"Loading Tokenizer for {model_name}...")
tokenizer = AutoTokenizer.from_pretrained(
    model_name, 
    token=hf_token, 
    trust_remote_code=True 
)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "left" 

# ==========================================
# 3. LOAD THE MODEL
# ==========================================
print("Checking for CUDA GPUs...")
if torch.cuda.is_available():
    print(f"Found {torch.cuda.device_count()} GPU(s).")
    device = "cuda"
else:
    print("WARNING: No GPU found! Running on CPU will be extremely slow.")
    device = "cpu"

print(f"Loading Model to {device}...")
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    token=hf_token,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16 if device == "cuda" else torch.float16,             
    device_map="auto" if device == "cuda" else None                   
)
if device == "cpu":
    model.to(device)

# ==========================================
# 4. INFERENCE PIPELINE
# ==========================================
# Get the system prompt and file path from environment variables
system_prompt = os.environ.get(
    "SUMMARY_PROMPT",
    """You are an expert software architect. Your task is to analyze the code and provide:

1. **Key Functionality:** A concise, high-level overview of what this code does.
2. **Core Logic:** A step-by-step explanation of the main algorithm or business logic.
3. **Inputs/Outputs:** A description of the primary inputs the code takes and the outputs it produces.
4. **Dependencies:** A list of key classes, interfaces, or external libraries that this code depends on."""
)
file_to_summarize = os.environ.get('SUMMARY_TARGET_FILE')

if not file_to_summarize:
    print("ERROR: SUMMARY_TARGET_FILE environment variable not set.")
    sys.exit(1)

try:
    with open(file_to_summarize, 'r') as f:
        source_code = f.read()
    print(f"Successfully read source code from {file_to_summarize}")
except FileNotFoundError:
    print(f"ERROR: File not found at {file_to_summarize}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Could not read file at {file_to_summarize}: {e}")
    sys.exit(1)

messages = [
    {
        "role": "system", 
        "content": system_prompt
    },
    {
        "role": "user", 
        "content": f"""Please analyze the following source code:
        
<source_code>
{source_code}
</source_code>
"""
    }
]

inputs = tokenizer.apply_chat_template(
    messages, 
    add_generation_prompt=True, 
    return_dict=True, 
    return_tensors="pt"
)
inputs = {k: v.to(model.device) for k, v in inputs.items()}

print("\nGenerating response...\n--- Model Output ---")
streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

outputs = model.generate(
    **inputs,
    max_new_tokens=512,      
    temperature=0.5,
    top_p=0.8,                
    do_sample=True,           
    pad_token_id=tokenizer.eos_token_id,
    streamer=streamer
)

print("\n--- Generation Complete ---")
