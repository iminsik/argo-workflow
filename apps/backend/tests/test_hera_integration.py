"""
Test script for Hera SDK integration with feature flag.

This script tests both the current implementation and Hera SDK implementation
to verify feature parity and correctness.

Usage:
    # Test with current implementation (feature flag disabled)
    python tests/test_hera_integration.py --hera-disabled

    # Test with Hera SDK (feature flag enabled)
    python tests/test_hera_integration.py --hera-enabled

    # Test both and compare
    python tests/test_hera_integration.py --compare
"""

import os
import sys
import time
import argparse
import requests
from typing import Dict, Any, Optional
from kubernetes.client import CustomObjectsApi
from kubernetes import config

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_workflow_from_k8s(workflow_id: str, namespace: str = "argo") -> Optional[Dict[str, Any]]:
    """Retrieve workflow from Kubernetes."""
    try:
        api_instance = CustomObjectsApi()
        workflow = api_instance.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            name=workflow_id
        )
        return workflow
    except Exception as e:
        print(f"Error retrieving workflow {workflow_id}: {e}")
        return None


def submit_task(api_url: str, python_code: str, dependencies: Optional[str] = None,
                requirements_file: Optional[str] = None) -> Dict[str, Any]:
    """Submit a task to the API."""
    payload = {
        "pythonCode": python_code,
    }
    if dependencies:
        payload["dependencies"] = dependencies
    if requirements_file:
        payload["requirementsFile"] = requirements_file
    
    response = requests.post(f"{api_url}/api/v1/tasks/submit", json=payload)
    response.raise_for_status()
    return response.json()


def test_simple_workflow(api_url: str, test_name: str) -> Dict[str, Any]:
    """Test a simple workflow without dependencies."""
    print(f"\n{'='*60}")
    print(f"Test: {test_name} - Simple Workflow")
    print(f"{'='*60}")
    
    python_code = "print('Hello from test workflow!')"
    
    try:
        result = submit_task(api_url, python_code)
        workflow_id = result.get("workflowId") or result.get("id")
        print(f"✅ Workflow created: {workflow_id}")
        return {"success": True, "workflow_id": workflow_id, "result": result}
    except Exception as e:
        print(f"❌ Failed: {e}")
        return {"success": False, "error": str(e)}


def test_workflow_with_dependencies(api_url: str, test_name: str) -> Dict[str, Any]:
    """Test a workflow with dependencies."""
    print(f"\n{'='*60}")
    print(f"Test: {test_name} - Workflow with Dependencies")
    print(f"{'='*60}")
    
    python_code = """
import numpy as np
arr = np.array([1, 2, 3, 4, 5])
print(f'Sum: {arr.sum()}, Mean: {arr.mean()}')
"""
    dependencies = "numpy"
    
    try:
        result = submit_task(api_url, python_code, dependencies=dependencies)
        workflow_id = result.get("workflowId") or result.get("id")
        print(f"✅ Workflow created: {workflow_id}")
        return {"success": True, "workflow_id": workflow_id, "result": result}
    except Exception as e:
        print(f"❌ Failed: {e}")
        return {"success": False, "error": str(e)}


def test_workflow_with_requirements_file(api_url: str, test_name: str) -> Dict[str, Any]:
    """Test a workflow with requirements file."""
    print(f"\n{'='*60}")
    print(f"Test: {test_name} - Workflow with Requirements File")
    print(f"{'='*60}")
    
    python_code = """
import pandas as pd
df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
print(df)
"""
    requirements_file = "pandas>=2.0.0\nnumpy>=1.24.0"
    
    try:
        result = submit_task(api_url, python_code, requirements_file=requirements_file)
        workflow_id = result.get("workflowId") or result.get("id")
        print(f"✅ Workflow created: {workflow_id}")
        return {"success": True, "workflow_id": workflow_id, "result": result}
    except Exception as e:
        print(f"❌ Failed: {e}")
        return {"success": False, "error": str(e)}


def compare_workflows(workflow1: Dict[str, Any], workflow2: Dict[str, Any], 
                     name1: str, name2: str) -> None:
    """Compare two workflows and print differences."""
    print(f"\n{'='*60}")
    print(f"Comparing Workflows: {name1} vs {name2}")
    print(f"{'='*60}")
    
    spec1 = workflow1.get("spec", {})
    spec2 = workflow2.get("spec", {})
    
    # Compare entrypoint
    entrypoint1 = spec1.get("entrypoint")
    entrypoint2 = spec2.get("entrypoint")
    if entrypoint1 == entrypoint2:
        print(f"✅ Entrypoint: {entrypoint1}")
    else:
        print(f"❌ Entrypoint differs: {entrypoint1} vs {entrypoint2}")
    
    # Compare volumes
    volumes1 = spec1.get("volumes", [])
    volumes2 = spec2.get("volumes", [])
    if len(volumes1) == len(volumes2):
        print(f"✅ Volumes count: {len(volumes1)}")
    else:
        print(f"❌ Volumes count differs: {len(volumes1)} vs {len(volumes2)}")
    
    # Compare templates
    templates1 = spec1.get("templates", [])
    templates2 = spec2.get("templates", [])
    if len(templates1) == len(templates2):
        print(f"✅ Templates count: {len(templates1)}")
        
        # Compare first template
        if templates1 and templates2:
            template1 = templates1[0]
            template2 = templates2[0]
            
            # Compare template type
            has_container1 = "container" in template1
            has_container2 = "container" in template2
            has_script1 = "script" in template1
            has_script2 = "script" in template2
            
            if has_container1 == has_container2 and has_script1 == has_script2:
                template_type = "container" if has_container1 else "script"
                print(f"✅ Template type: {template_type}")
            else:
                print(f"❌ Template type differs")
            
            # Compare image
            if has_container1:
                image1 = template1["container"].get("image")
                image2 = template2["container"].get("image")
            elif has_script1:
                image1 = template1["script"].get("image")
                image2 = template2["script"].get("image")
            else:
                image1 = image2 = None
            
            if image1 == image2:
                print(f"✅ Image: {image1}")
            else:
                print(f"❌ Image differs: {image1} vs {image2}")
    else:
        print(f"❌ Templates count differs: {len(templates1)} vs {len(templates2)}")
    
    print(f"\n{'='*60}")


def run_tests(api_url: str, use_hera: bool, test_name: str) -> Dict[str, Any]:
    """Run all tests with specified implementation."""
    print(f"\n{'#'*60}")
    print(f"Testing with: {test_name}")
    print(f"Feature Flag (USE_HERA_SDK): {use_hera}")
    print(f"{'#'*60}")
    
    results = {
        "test_name": test_name,
        "use_hera": use_hera,
        "tests": {}
    }
    
    # Test 1: Simple workflow
    result1 = test_simple_workflow(api_url, test_name)
    results["tests"]["simple"] = result1
    
    # Test 2: Workflow with dependencies
    result2 = test_workflow_with_dependencies(api_url, test_name)
    results["tests"]["with_dependencies"] = result2
    
    # Test 3: Workflow with requirements file
    result3 = test_workflow_with_requirements_file(api_url, test_name)
    results["tests"]["with_requirements"] = result3
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Test Summary for {test_name}")
    print(f"{'='*60}")
    passed = sum(1 for t in results["tests"].values() if t.get("success"))
    total = len(results["tests"])
    print(f"Passed: {passed}/{total}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Test Hera SDK integration")
    parser.add_argument("--api-url", default="http://localhost:8000",
                       help="API URL (default: http://localhost:8000)")
    parser.add_argument("--hera-disabled", action="store_true",
                       help="Test with current implementation (Hera disabled)")
    parser.add_argument("--hera-enabled", action="store_true",
                       help="Test with Hera SDK (Hera enabled)")
    parser.add_argument("--compare", action="store_true",
                       help="Test both and compare workflows")
    parser.add_argument("--namespace", default="argo",
                       help="Kubernetes namespace (default: argo)")
    
    args = parser.parse_args()
    
    # Initialize Kubernetes config
    try:
        config.load_incluster_config()
    except:
        try:
            config.load_kube_config()
        except:
            print("Warning: Could not load Kubernetes config. Workflow comparison may fail.")
    
    if args.compare:
        # Test both implementations and compare
        print("\n" + "="*60)
        print("COMPARISON MODE: Testing both implementations")
        print("="*60)
        
        # Test with current implementation
        print("\n⚠️  Make sure USE_HERA_SDK=false in your environment")
        input("Press Enter to continue with current implementation test...")
        results_current = run_tests(args.api_url, False, "Current Implementation")
        
        # Wait a bit
        time.sleep(2)
        
        # Test with Hera SDK
        print("\n⚠️  Make sure USE_HERA_SDK=true in your environment")
        input("Press Enter to continue with Hera SDK test...")
        results_hera = run_tests(args.api_url, True, "Hera SDK")
        
        # Compare workflows
        print("\n" + "="*60)
        print("COMPARING WORKFLOWS")
        print("="*60)
        
        for test_type in ["simple", "with_dependencies", "with_requirements"]:
            current_result = results_current["tests"].get(test_type)
            hera_result = results_hera["tests"].get(test_type)
            
            if current_result.get("success") and hera_result.get("success"):
                workflow1_id = current_result.get("workflow_id")
                workflow2_id = hera_result.get("workflow_id")
                
                if workflow1_id and workflow2_id:
                    workflow1 = get_workflow_from_k8s(workflow1_id, args.namespace)
                    workflow2 = get_workflow_from_k8s(workflow2_id, args.namespace)
                    
                    if workflow1 and workflow2:
                        compare_workflows(
                            workflow1, workflow2,
                            f"Current ({workflow1_id[:20]}...)",
                            f"Hera ({workflow2_id[:20]}...)"
                        )
        
    elif args.hera_disabled:
        run_tests(args.api_url, False, "Current Implementation")
    elif args.hera_enabled:
        run_tests(args.api_url, True, "Hera SDK")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

