#!/usr/bin/env python3
"""
Test script for invoice extraction improvements.
This script processes one or more invoice PDFs and outputs extraction results
with confidence scores to validate the enhanced extraction pipeline.
"""

import os
import json
import argparse
from typing import Dict, List, Any
from invoice_processor import process_invoice

def test_extraction(invoice_paths: List[str], debug: bool = False) -> Dict[str, Any]:
    """
    Process multiple invoice PDFs and return a summary of extraction results.
    
    Args:
        invoice_paths: List of paths to invoice PDF files
        debug: Whether to include debug information in the output
        
    Returns:
        Dictionary containing summary statistics and individual results
    """
    results = []
    for path in invoice_paths:
        try:
            print(f"Processing {os.path.basename(path)}...")
            result = process_invoice(path, debug_mode=debug)
            results.append({
                "filename": os.path.basename(path),
                "result": result
            })
        except Exception as e:
            print(f"Error processing {path}: {str(e)}")
            results.append({
                "filename": os.path.basename(path),
                "error": str(e),
                "success": False
            })
    
    # Calculate summary statistics
    success_count = sum(1 for r in results if r.get("result", {}).get("success", False))
    templates_used = {}
    confidence_scores = {
        "company_name": [],
        "invoice_number": [],
        "fssai_number": [],
        "invoice_date": [],
        "products": [],
        "overall": []
    }
    
    for result in results:
        if "result" in result and result["result"].get("success", False):
            # Track templates used
            template = result["result"].get("pattern_used", "unknown")
            templates_used[template] = templates_used.get(template, 0) + 1
            
            # Track confidence scores
            scores = result["result"].get("confidence_scores", {})
            for field in confidence_scores.keys():
                if field in scores:
                    confidence_scores[field].append(scores[field])
    
    # Calculate average confidence scores
    avg_confidence = {}
    for field, scores in confidence_scores.items():
        avg_confidence[field] = sum(scores) / len(scores) if scores else 0
    
    summary = {
        "total_invoices": len(invoice_paths),
        "successful_extractions": success_count,
        "success_rate": round(success_count / len(invoice_paths) * 100, 2) if invoice_paths else 0,
        "templates_used": templates_used,
        "average_confidence": avg_confidence,
        "results": results
    }
    
    return summary

def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(description="Test invoice extraction")
    parser.add_argument("-d", "--directory", help="Directory containing invoice PDFs")
    parser.add_argument("-f", "--files", nargs="+", help="Specific invoice PDF files to process")
    parser.add_argument("--debug", action="store_true", help="Include debug information")
    parser.add_argument("-o", "--output", help="Output file for the results (JSON)")
    args = parser.parse_args()
    
    invoice_paths = []
    
    if args.directory:
        for file in os.listdir(args.directory):
            if file.lower().endswith(".pdf"):
                invoice_paths.append(os.path.join(args.directory, file))
    
    if args.files:
        invoice_paths.extend([f for f in args.files if os.path.exists(f)])
    
    if not invoice_paths:
        print("No invoice PDFs found. Specify files with -f or a directory with -d.")
        return
    
    print(f"Processing {len(invoice_paths)} invoice files...")
    summary = test_extraction(invoice_paths, args.debug)
    
    # Print summary
    print("\n=== EXTRACTION RESULTS ===")
    print(f"Processed {summary['total_invoices']} invoices")
    print(f"Success rate: {summary['success_rate']}% ({summary['successful_extractions']}/{summary['total_invoices']})")
    
    print("\nTemplates used:")
    for template, count in summary["templates_used"].items():
        print(f"  - {template}: {count}")
    
    print("\nAverage confidence scores:")
    for field, score in summary["average_confidence"].items():
        print(f"  - {field}: {score:.2f}")
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"\nDetailed results saved to {args.output}")
    
    # Print individual results if there are fewer than 5 invoices
    if len(invoice_paths) < 5:
        print("\nIndividual results:\n")
        for result in summary["results"]:
            if "result" in result and result["result"].get("success", False):
                r = result["result"]
                print(f"{result['filename']}:")
                print(f"  Template: {r.get('pattern_used', 'unknown')}")
                print(f"  Company: {r.get('company_name', 'N/A')}")
                print(f"  Invoice #: {r.get('invoice_number', 'N/A')}")
                print(f"  Date: {r.get('invoice_date', 'N/A')}")
                print(f"  Products: {len(r.get('products', []))}")
                print(f"  Overall confidence: {r.get('confidence_scores', {}).get('overall', 0):.2f}")
                print()
            else:
                print(f"{result['filename']}:")
                print(f"  Error: {result.get('error', 'N/A')}")
                print()

if __name__ == "__main__":
    main()
