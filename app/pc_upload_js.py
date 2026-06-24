"""H5 页面共用的 PC 端粘贴/截图上传脚本。"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import Response

_PC_JS_PATH = Path(__file__).resolve().parent.parent / "static" / "upload_pc_image.js"


def serve_upload_pc_image_js() -> Response:
    if not _PC_JS_PATH.is_file():
        raise HTTPException(status_code=500, detail="PC 上传脚本缺失")
    return Response(
        content=_PC_JS_PATH.read_bytes(),
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )
