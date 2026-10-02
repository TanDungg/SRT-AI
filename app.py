#!/usr/bin/env python3
"""
Entrypoint cho Hugging Face Spaces
Tự động chạy máy chủ Whiteboard Studio AI tại cổng 7860
"""
import os
import sys

# Hugging Face Spaces sử dụng cổng 7860 mặc định
os.environ["PORT"] = os.environ.get("PORT", "7860")

from server import main

if __name__ == "__main__":
    main()
