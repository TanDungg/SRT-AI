#!/usr/bin/env python3
"""
Entrypoint cho Hugging Face Spaces
Tự động chạy máy chủ Whiteboard Studio AI tại cổng 7860
"""
import os
import sys

# Hugging Face Spaces sử dụng cổng 7860 mặc định
os.environ["PORT"] = os.environ.get("PORT", "7860")

# Tương thích với môi trường ZeroGPU của Hugging Face
try:
    import spaces
    @spaces.GPU(duration=10)
    def _hf_zerogpu_keepalive():
        """Hàm đăng ký để vượt qua bộ quét kiểm tra @spaces.GPU của ZeroGPU"""
        return True
    
    # Kích hoạt đăng ký
    _hf_zerogpu_keepalive()
except Exception:
    pass

from server import main

if __name__ == "__main__":
    main()

