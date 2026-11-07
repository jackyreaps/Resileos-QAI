#!/usr/bin/env python3
"""Resileos Studio entry. Portable surface for memory, media, diagnostics.

  streamlit run ui_studio.py --server.port 8501
"""
from resileos.ui.studio_app import main

if __name__ == "__main__":
    main()
