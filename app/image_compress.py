"""服务端图片压缩，使解密/上传后的图片符合大小限制。"""

from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def compress_image_to_limit(raw: bytes, max_bytes: int) -> bytes:
    """将图片压缩到不超过 max_bytes，优先降 JPEG 质量，仍超限则缩小尺寸。"""
    if len(raw) <= max_bytes:
        return raw

    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError(
            f"图片大小 {len(raw) // 1024}KB 超过限制 {max_bytes // (1024 * 1024)}MB，"
            "且服务端未安装 Pillow，无法自动压缩"
        ) from exc

    with Image.open(BytesIO(raw)) as img:
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            alpha = img.split()[-1] if img.mode in ("RGBA", "LA") else None
            background.paste(img, mask=alpha)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        quality = 85
        while quality >= 55:
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                logger.info(
                    "图片已压缩至 %sKB (quality=%s)",
                    len(data) // 1024,
                    quality,
                )
                return data
            quality -= 7

        scale = 0.85
        working = img
        data = raw
        while scale >= 0.35:
            width = max(1, int(working.width * scale))
            height = max(1, int(working.height * scale))
            resized = working.resize((width, height), Image.Resampling.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="JPEG", quality=82, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                logger.info(
                    "图片已缩放压缩至 %sKB (scale=%.2f)",
                    len(data) // 1024,
                    scale,
                )
                return data
            scale -= 0.1

        if len(data) <= max_bytes * 1.1:
            return data

    raise ValueError(
        f"图片压缩后仍超过 {max_bytes // (1024 * 1024)}MB，请换一张更小的截图"
    )


def ensure_image_within_limit(
    raw: bytes,
    filename: str,
    max_bytes: int,
) -> tuple[bytes, str]:
    if len(raw) <= max_bytes:
        return raw, filename

    compressed = compress_image_to_limit(raw, max_bytes)
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    return compressed, f"{base}.jpg"
