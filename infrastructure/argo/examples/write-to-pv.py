import json
import os
from datetime import datetime

# Create results directory if it doesn't exist
results_dir = "/mnt/results"
os.makedirs(results_dir, exist_ok=True)

# Generate some data to save
task_id = os.getenv("ARGO_WORKFLOW_NAME", "unknown-task")
result_data = {
    "task_id": task_id,
    "timestamp": datetime.now().isoformat(),
    "status": "completed",
    "result": "Task executed successfully!",
    "data": {
        "processed_items": 42,
        "computation_time": 1.23,
        "output": "Sample output data"
    }
}

# Write to file
output_file = os.path.join(results_dir, f"{task_id}_result.json")
with open(output_file, "w") as f:
    json.dump(result_data, f, indent=2)

print(f"Results saved to {output_file}")
print(f"Data: {json.dumps(result_data, indent=2)}")

