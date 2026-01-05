import json
import os
from datetime import datetime

# Read from results directory
results_dir = "/mnt/results"

if not os.path.exists(results_dir):
    print(f"Error: Results directory {results_dir} does not exist")
    exit(1)

# List all result files (read all JSON files, not just _result.json)
result_files = [f for f in os.listdir(results_dir) if f.endswith(".json")]

if not result_files:
    print("No result files found in /mnt/results")
    print(f"Directory contents: {os.listdir(results_dir)}")
    exit(0)

print(f"Found {len(result_files)} result file(s):")
print("-" * 50)

# Read and display each result file
for result_file in sorted(result_files):
    file_path = os.path.join(results_dir, result_file)
    print(f"\nReading: {result_file}")
    print("-" * 50)
    
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error reading {result_file}: {e}")

print("\n" + "=" * 50)
print(f"Successfully read {len(result_files)} result file(s)")

