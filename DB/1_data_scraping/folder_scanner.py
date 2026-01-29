"""
Folder Scanner
==============

Utility to scan and analyze folder structures for battery simulation data.
Helps identify what data is available before importing.
"""

from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict


def scan_folder_structure(root_path: str, max_depth: int = 3) -> Dict:
    """
    Scan a folder structure and report on what's found.
    
    Args:
        root_path: Root folder to scan
        max_depth: Maximum depth to traverse
        
    Returns:
        Dictionary with structure information
    """
    root = Path(root_path)
    if not root.exists():
        print(f"❌ Path not found: {root_path}")
        return {}
    
    result = {
        "root": str(root),
        "clients": [],
        "total_runs": 0,
        "total_configs": 0,
        "file_types": defaultdict(int),
    }
    
    print(f"\n{'='*70}")
    print(f"SCANNING: {root}")
    print(f"{'='*70}\n")
    
    for client_folder in sorted(root.iterdir()):
        if not client_folder.is_dir() or client_folder.name.startswith('.'):
            continue
        
        client_info = _scan_client_folder(client_folder, max_depth)
        if client_info["runs"]:
            result["clients"].append(client_info)
            result["total_runs"] += len(client_info["runs"])
            result["total_configs"] += client_info["total_configs"]
            
            # Count file types
            for file_type, count in client_info["file_types"].items():
                result["file_types"][file_type] += count
    
    _print_scan_summary(result)
    return result


def find_flex_cases(root_path: str, flex_subfolder: str = "02_Flex Offer Files") -> List[Dict]:
    """
    Find all client folders that contain flex offer files.
    
    Args:
        root_path: Root folder to scan
        flex_subfolder: Name of the subfolder containing runs
        
    Returns:
        List of dictionaries with client information
    """
    root = Path(root_path)
    if not root.exists():
        return []
    
    results = []
    
    for client_folder in sorted(root.iterdir()):
        if not client_folder.is_dir() or client_folder.name.startswith('.'):
            continue
        
        flex_path = client_folder / flex_subfolder
        if not flex_path.exists():
            continue
        
        runs = []
        for run_folder in flex_path.iterdir():
            if not run_folder.is_dir():
                continue
            
            output_folder = run_folder / "Output"
            if output_folder.exists():
                # Count output files
                kpi_files = list(output_folder.glob("kpi_summary*.csv")) + \
                           list(output_folder.glob("kpi_summary*.xlsx"))
                ts_files = list(output_folder.glob("flex_timeseries*.csv"))
                
                if kpi_files or ts_files:
                    runs.append({
                        "name": run_folder.name,
                        "path": str(run_folder),
                        "kpi_files": len(kpi_files),
                        "ts_files": len(ts_files),
                    })
        
        if runs:
            results.append({
                "client": client_folder.name,
                "path": str(client_folder),
                "flex_folder": str(flex_path),
                "runs": runs,
            })
    
    return results


def preview_import(root_path: str, flex_subfolder: str = "02_Flex Offer Files",
                   max_clients: int = 10):
    """
    Preview what would be imported from a folder.
    
    Args:
        root_path: Root folder to scan
        flex_subfolder: Name of the subfolder containing runs
        max_clients: Maximum number of clients to show
    """
    cases = find_flex_cases(root_path, flex_subfolder)
    
    print(f"\n{'='*70}")
    print(f"IMPORT PREVIEW: {root_path}")
    print(f"{'='*70}\n")
    
    if not cases:
        print("❌ No flex cases found")
        return
    
    print(f"Found {len(cases)} clients with data\n")
    
    for i, case in enumerate(cases[:max_clients]):
        print(f"📁 {case['client']}")
        print(f"   Runs: {len(case['runs'])}")
        for run in case['runs']:
            print(f"      └── {run['name']}")
            print(f"          KPI files: {run['kpi_files']}, Timeseries: {run['ts_files']}")
        print()
    
    if len(cases) > max_clients:
        print(f"... and {len(cases) - max_clients} more clients\n")
    
    total_runs = sum(len(c['runs']) for c in cases)
    print(f"{'='*70}")
    print(f"Total: {len(cases)} clients, {total_runs} runs")
    print(f"{'='*70}\n")


def _scan_client_folder(client_folder: Path, max_depth: int) -> Dict:
    """Scan a single client folder."""
    info = {
        "name": client_folder.name,
        "path": str(client_folder),
        "runs": [],
        "total_configs": 0,
        "file_types": defaultdict(int),
    }
    
    # Look for run folders
    for item in client_folder.rglob("*"):
        if item.is_file():
            info["file_types"][item.suffix] += 1
        
        # Check if this looks like a run folder
        if item.is_dir() and item.name == "Output":
            run_folder = item.parent
            run_info = _scan_run_folder(run_folder)
            if run_info["configs"]:
                info["runs"].append(run_info)
                info["total_configs"] += len(run_info["configs"])
    
    return info


def _scan_run_folder(run_folder: Path) -> Dict:
    """Scan a single run folder."""
    info = {
        "name": run_folder.name,
        "path": str(run_folder),
        "configs": [],
        "has_input": False,
    }
    
    input_folder = run_folder / "Input"
    output_folder = run_folder / "Output"
    
    info["has_input"] = input_folder.exists()
    
    if output_folder.exists():
        # Find configs by output files
        configs = set()
        
        for kpi_file in output_folder.glob("kpi_summary*"):
            config_name = _extract_config_from_filename(kpi_file.name)
            configs.add(config_name)
        
        for ts_file in output_folder.glob("flex_timeseries*"):
            config_name = _extract_config_from_filename(ts_file.name)
            configs.add(config_name)
        
        info["configs"] = sorted(configs)
    
    return info


def _extract_config_from_filename(filename: str) -> str:
    """Extract config name from a filename."""
    import re
    
    name = Path(filename).stem
    
    # Pattern with timestamp
    match = re.search(r'_\d{8}_\d{6}_(.+)$', name)
    if match:
        return match.group(1)
    
    # Remove known prefixes
    for prefix in ["kpi_summary_", "flex_timeseries_outputs_", "flex_timeseries_"]:
        if name.startswith(prefix):
            return name[len(prefix):]
    
    return name


def _print_scan_summary(result: Dict):
    """Print summary of scan results."""
    print(f"\n{'='*70}")
    print("SCAN SUMMARY")
    print(f"{'='*70}")
    print(f"Total clients:  {len(result['clients'])}")
    print(f"Total runs:     {result['total_runs']}")
    print(f"Total configs:  {result['total_configs']}")
    
    if result["file_types"]:
        print("\nFile types found:")
        for ext, count in sorted(result["file_types"].items(), key=lambda x: -x[1])[:10]:
            print(f"  {ext or '(no extension)'}: {count}")
    
    print(f"{'='*70}\n")


# Convenience function for command-line usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python folder_scanner.py <path>")
        sys.exit(1)
    
    path = sys.argv[1]
    scan_folder_structure(path)

