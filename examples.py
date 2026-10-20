#!/usr/bin/env python3
"""
Example usage of the Content Understanding Cost Estimator

This script demonstrates various ways to use the cu_cost_estimator.py tool
"""

import subprocess
import json
from pathlib import Path


def run_estimator(args):
    """Helper to run the estimator and return output"""
    cmd = ["python3", "cu_cost_estimator.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


def print_section(title):
    """Print a section header"""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")


def example_1_basic_estimate():
    """Example 1: Basic cost estimation for documents"""
    print_section("Example 1: Basic Document Processing Estimate")
    
    output = run_estimator([
        "estimate",
        "--file-type", "document",
        "--quantity", "1000",
        "--model", "gpt-4o"
    ])
    print(output)


def example_2_model_comparison():
    """Example 2: Compare different models"""
    print_section("Example 2: Model Comparison")
    
    print("Comparing gpt-4o vs gpt-4o-mini for 1000 pages:\n")
    
    print("--- GPT-4o (Regular Model) ---")
    output = run_estimator([
        "estimate",
        "--file-type", "document",
        "--quantity", "1000",
        "--model", "gpt-4o",
        "--json"
    ])
    data = json.loads(output)
    print(f"Total Cost: ${data['breakdown']['total_cost']:.2f}")
    print(f"Total Tokens: {data['breakdown']['total_tokens']:,}\n")
    
    print("--- GPT-4o-mini (Mini Model) ---")
    output = run_estimator([
        "estimate",
        "--file-type", "document",
        "--quantity", "1000",
        "--model", "gpt-4o-mini",
        "--json"
    ])
    data = json.loads(output)
    print(f"Total Cost: ${data['breakdown']['total_cost']:.2f}")
    print(f"Total Tokens: {data['breakdown']['total_tokens']:,}\n")
    
    savings = ((13.40 - data['breakdown']['total_cost']) / 13.40) * 100
    print(f"💰 Savings with mini model: ~{savings:.1f}%")


def example_3_file_types():
    """Example 3: Different file types"""
    print_section("Example 3: Different File Types")
    
    file_types = [
        ("document", "1000", "pages"),
        ("text", "3000000", "characters"),
        ("audio", "60", "minutes"),
        ("video", "30", "minutes"),
        ("image", "500", "images")
    ]
    
    for file_type, quantity, unit in file_types:
        output = run_estimator([
            "estimate",
            "--file-type", file_type,
            "--quantity", quantity,
            "--model", "gpt-4o-mini",
            "--json"
        ])
        data = json.loads(output)
        print(f"{file_type.capitalize():12} ({quantity:>10} {unit:12}): ${data['breakdown']['total_cost']:>8.4f}")


def example_4_with_features():
    """Example 4: All features enabled"""
    print_section("Example 4: Full-Featured Processing")
    
    output = run_estimator([
        "estimate",
        "--file-type", "document",
        "--quantity", "1000",
        "--model", "gpt-4o",
        "--deployment", "data_zone",
        "--embeddings",
        "--embeddings-model", "text-embedding-3-large"
    ])
    print(output)


def example_5_batch_analysis():
    """Example 5: Analyze batch results"""
    print_section("Example 5: Batch Processing Analysis")
    
    # Check if example file exists
    if not Path("example_batch_results.json").exists():
        print("⚠️  example_batch_results.json not found. Skipping this example.")
        return
    
    output = run_estimator([
        "analyze",
        "--results-file", "example_batch_results.json"
    ])
    print(output)


def example_6_cost_projections():
    """Example 6: Cost projections for different scales"""
    print_section("Example 6: Cost Projections")
    
    print("Cost projections using gpt-4o-mini for document processing:\n")
    
    scales = [100, 1000, 10000, 100000, 1000000]
    
    for scale in scales:
        output = run_estimator([
            "estimate",
            "--file-type", "document",
            "--quantity", str(scale),
            "--model", "gpt-4o-mini",
            "--json"
        ])
        data = json.loads(output)
        cost = data['breakdown']['total_cost']
        cost_per_page = cost / scale
        print(f"{scale:>10,} pages: ${cost:>10,.2f} (${cost_per_page:.4f}/page)")


def example_7_deployment_comparison():
    """Example 7: Compare deployment types"""
    print_section("Example 7: Deployment Type Comparison")
    
    print("Comparing deployment types for 1000 document pages:\n")
    
    deployments = ["global", "regional", "data_zone"]
    
    for deployment in deployments:
        output = run_estimator([
            "estimate",
            "--file-type", "document",
            "--quantity", "1000",
            "--model", "gpt-4o",
            "--deployment", deployment,
            "--json"
        ])
        data = json.loads(output)
        print(f"{deployment.capitalize():12}: ${data['breakdown']['total_cost']:.4f}")


def main():
    """Run all examples"""
    print("\n" + "=" * 80)
    print(" Azure AI Content Understanding Cost Estimator - Example Usage")
    print("=" * 80)
    
    examples = [
        example_1_basic_estimate,
        example_2_model_comparison,
        example_3_file_types,
        example_4_with_features,
        example_5_batch_analysis,
        example_6_cost_projections,
        example_7_deployment_comparison
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"Error running example: {e}")
    
    print("\n" + "=" * 80)
    print(" Examples Complete!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
