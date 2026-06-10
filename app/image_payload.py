"""H5 图片上传校验与公司加密文件解密预处理。"""

from __future__ import annotations

import logging
from pathlib import Path

from app.file_decrypt import decrypt_encrypted_file

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}


def incoming_upload_limit(raw: bytes, max_upload_bytes: int, max_encrypted_upload_bytes: int) -> int:
    """加密文件（无有效图片头）允许更大的入站体积，解密后再压缩。"""
    if has_image_magic_bytes(raw):
        return max_upload_bytes
    return max_encrypted_upload_bytes


def has_image_magic_bytes(raw: bytes) -> bool:
    if len(raw) >= 3 and raw[:3] == b"\xff\xd8\xff":
        return True
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if len(raw) >= 6 and raw[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return True
    if len(raw) >= 2 and raw[:2] == b"BM":
        return True
    return False


def looks_like_image_upload(raw: bytes, filename: str, content_type: str) -> bool:
    if has_image_magic_bytes(raw):
        return True

    ct = (content_type or "").lower().split(";", 1)[0].strip()
    if ct.startswith("image/") or ct == "application/octet-stream":
        return bool(raw)

    ext = Path(filename or "").suffix.lower()
    return ext in _IMAGE_EXTENSIONS and bool(raw)


def prepare_image_upload(
    raw: bytes,
    filename: str,
    content_type: str,
    userid: str,
) -> tuple[bytes, str]:
    """校验并在需要时解密，返回可用于存储的图片字节与文件名。"""
    if not raw:
        raise ValueError("图片内容为空")

    if has_image_magic_bytes(raw):
        return raw, filename or "upload.jpg"

    if not looks_like_image_upload(raw, filename, content_type):
        raise ValueError("仅支持 JPG/PNG/GIF/WebP/BMP/HEIC 图片")

    logger.info(
        "图片缺少有效文件头，尝试解密 userid=%s filename=%s size=%s",
        userid,
        filename,
        len(raw),
    )
    ok, result, output_name = decrypt_encrypted_file(userid, raw, filename or "upload.jpg")
    if not ok:
        message = str(result)
        if "未配置" in message:
            raise ValueError("图片可能已加密，但解密服务未配置，请联系管理员")
        raise ValueError(message or "图片解密失败")

    decrypted = result if isinstance(result, bytes) else b""
    if not has_image_magic_bytes(decrypted):
        raise ValueError("解密后仍不是有效图片，请确认您有权限查看该文件")

    return decrypted, output_name or filename or "upload.jpg"
