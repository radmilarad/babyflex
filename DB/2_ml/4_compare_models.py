#!/usr/bin/env python3
"""
Step 3b: Compare – Übersicht aller Modelle (Performance, Features, Kategorien)
=============================================================================

Zeigt Performance-Tabelle, Feature-Importance-Vergleich und Kategorien-Analyse.

Aus Projektroot:  python 2_ml/4_compare_models.py
"""
import sys
from pathlib import Path
from importlib import import_module

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

_compare = import_module("2_ml.training.compare_models")
compare_models = _compare.compare_models


def main():
    compare_models()
    print("\n✅ Step 3b done.")


if __name__ == "__main__":
    main()
