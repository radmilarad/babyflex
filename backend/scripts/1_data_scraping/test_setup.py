#!/usr/bin/env python3
"""
Quick Test: Verify Data Scraping Setup
=======================================

Run this script to verify everything is set up correctly.
"""

import sys
from pathlib import Path

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from data_scraping import GDriveImporter, scan_folder_structure, GDRIVE_CONFIG
        from data_scraping import find_flex_cases, get_gdrive_path
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_paths():
    """Test that paths are configured."""
    print("\nTesting paths...")
    try:
        from data_scraping import get_gdrive_path, get_flex_cases_path
        
        base = get_gdrive_path()
        flex = get_flex_cases_path()
        
        print(f"   Base path: {base}")
        print(f"   Exists: {'✅' if base.exists() else '❌'}")
        
        print(f"   Flex cases path: {flex}")
        print(f"   Exists: {'✅' if flex.exists() else '❌'}")
        
        if flex.exists():
            client_count = sum(1 for f in flex.iterdir() 
                             if f.is_dir() and not f.name.startswith('.'))
            print(f"   Client folders found: {client_count}")
            return True
        else:
            print("   ⚠️  Path doesn't exist - you may need to update config.py")
            return False
            
    except Exception as e:
        print(f"❌ Path error: {e}")
        return False

def test_database():
    """Test database connection."""
    print("\nTesting database...")
    try:
        from battery_db import BatteryDatabase
        
        db = BatteryDatabase()
        clients = db.conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        configs = db.conn.execute("SELECT COUNT(*) FROM battery_configs").fetchone()[0]
        db.close()
        
        print(f"✅ Database connected")
        print(f"   Current clients: {clients}")
        print(f"   Current configs: {configs}")
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_dependencies():
    """Test required dependencies."""
    print("\nTesting dependencies...")
    deps = {
        "pandas": "pandas",
        "duckdb": "duckdb",
        "yaml": "pyyaml",
        "openpyxl": "openpyxl",
    }
    
    all_ok = True
    for module, package in deps.items():
        try:
            __import__(module)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - install with: pip install {package}")
            all_ok = False
    
    return all_ok

def main():
    print("=" * 70)
    print("DATA SCRAPING MODULE - SETUP VERIFICATION")
    print("=" * 70)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Dependencies", test_dependencies()))
    results.append(("Paths", test_paths()))
    results.append(("Database", test_database()))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✅ All tests passed! You're ready to import data.")
        print("\nNext steps:")
        print("  1. Preview: python -m data_scraping.cli preview")
        print("  2. Import:  python -m data_scraping.cli import-all")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()

