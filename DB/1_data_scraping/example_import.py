#!/usr/bin/env python3
"""
Example: Import Data from Google Drive
=======================================

This script shows how to use the data scraping module to import
battery simulation data from Google Drive into the DuckDB database.
"""

from data_scraping import GDriveImporter

def main():
    print("Battery Database - Google Drive Import Example")
    print("=" * 70)
    
    # Create importer
    importer = GDriveImporter()
    
    # Option 1: Preview first (recommended)
    print("\n1. Previewing what will be imported...\n")
    preview_data = importer.preview(max_clients=5)
    
    # Ask user to confirm
    print("\nDo you want to proceed with the import? (y/n): ", end="")
    response = input().strip().lower()
    
    if response != 'y':
        print("Import cancelled.")
        importer.close()
        return
    
    # Option 2: Import all data
    print("\n2. Starting import...\n")
    stats = importer.import_all()
    
    # Print results
    print("\n" + "=" * 70)
    print("IMPORT COMPLETE")
    print("=" * 70)
    print(f"✅ Imported {stats['configs_imported']} battery configurations")
    print(f"✅ Imported {stats['kpis_imported']} KPI records")
    print(f"✅ From {stats['clients_imported']} clients")
    
    if stats['errors']:
        print(f"\n⚠️  {len(stats['errors'])} errors occurred (see details above)")
    
    # Close connection
    importer.close()
    
    # Show database summary
    print("\n3. Database Summary:")
    print("-" * 70)
    from battery_db import BatteryDatabase
    db = BatteryDatabase()
    db.summary()
    db.close()


if __name__ == "__main__":
    main()

