#!/usr/bin/env python3
"""
Data Scraping CLI
=================

Command-line interface for data scraping operations.

Usage:
    python -m data_scraping.cli preview [--max-clients N]
    python -m data_scraping.cli import-all [--dry-run]
    python -m data_scraping.cli import-client <name>
    python -m data_scraping.cli scan <path>
"""

import argparse
import sys
from pathlib import Path

from .gdrive_importer import GDriveImporter
from .folder_scanner import scan_folder_structure, preview_import
from .config import get_flex_cases_path


def cmd_preview(args):
    """Preview what will be imported from Google Drive."""
    with GDriveImporter() as importer:
        importer.preview(max_clients=args.max_clients)


def cmd_import_all(args):
    """Import all data from Google Drive."""
    with GDriveImporter() as importer:
        stats = importer.import_all(dry_run=args.dry_run)
        
        if not args.dry_run:
            print(f"\n✅ Successfully imported:")
            print(f"   {stats['clients_imported']} clients")
            print(f"   {stats['runs_imported']} runs")
            print(f"   {stats['configs_imported']} configurations")
            print(f"   {stats['kpis_imported']} KPIs")


def cmd_import_client(args):
    """Import a specific client."""
    with GDriveImporter() as importer:
        success = importer.import_client(args.client_name)
        if success:
            print(f"✅ Successfully imported {args.client_name}")
        else:
            print(f"❌ Failed to import {args.client_name}")
            sys.exit(1)


def cmd_scan(args):
    """Scan a folder structure."""
    if args.preview_mode:
        preview_import(args.path, max_clients=args.max_clients)
    else:
        scan_folder_structure(args.path, max_depth=args.max_depth)


def cmd_show_path(args):
    """Show the configured Google Drive path."""
    path = get_flex_cases_path()
    print(f"Google Drive Flex Cases Path:")
    print(f"  {path}")
    print(f"\nExists: {'✅ Yes' if path.exists() else '❌ No'}")
    
    if path.exists():
        client_count = sum(1 for f in path.iterdir() if f.is_dir() and not f.name.startswith('.'))
        print(f"Client folders: {client_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Data Scraping CLI for Battery Database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Preview command
    preview_parser = subparsers.add_parser("preview", help="Preview import")
    preview_parser.add_argument(
        "--max-clients", 
        type=int, 
        default=10,
        help="Maximum number of clients to preview (default: 10)"
    )
    preview_parser.set_defaults(func=cmd_preview)
    
    # Import all command
    import_parser = subparsers.add_parser("import-all", help="Import all data")
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't actually import"
    )
    import_parser.set_defaults(func=cmd_import_all)
    
    # Import client command
    client_parser = subparsers.add_parser("import-client", help="Import specific client")
    client_parser.add_argument("client_name", help="Name of the client to import")
    client_parser.set_defaults(func=cmd_import_client)
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan folder structure")
    scan_parser.add_argument("path", help="Path to scan")
    scan_parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum depth to traverse (default: 3)"
    )
    scan_parser.add_argument(
        "--preview-mode",
        action="store_true",
        help="Use preview mode (shows import-ready structure)"
    )
    scan_parser.add_argument(
        "--max-clients",
        type=int,
        default=10,
        help="Maximum clients to show in preview mode (default: 10)"
    )
    scan_parser.set_defaults(func=cmd_scan)
    
    # Show path command
    path_parser = subparsers.add_parser("show-path", help="Show configured Google Drive path")
    path_parser.set_defaults(func=cmd_show_path)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if "--debug" in sys.argv:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
