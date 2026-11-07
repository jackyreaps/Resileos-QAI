#!/usr/bin/env python3
"""Resileos Chat entry. Same portable surface as Studio.

  streamlit run ui_chat.py --server.port 8502
"""
import os
os.environ.setdefault("RESILEOS_UI_MODE", "chat")
from resileos.ui.studio_app import main

if __name__ == "__main__":
    main()
