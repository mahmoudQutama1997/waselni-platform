"""Shared upload validation for profile images, store media and captain documents."""
import os

from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOCUMENT_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOCUMENT_CONTENT_TYPES = IMAGE_CONTENT_TYPES | {"application/pdf"}

IMAGE_ERROR = "Upload a JPG, PNG or WEBP image up to 5 MB."
DOCUMENT_ERROR = "Upload a PDF, JPG or PNG file up to 10 MB."


def _extension(upload):
    return os.path.splitext(upload.name or "")[1].lower()


def _reject(field, message):
    raise ValidationError({field: message} if field else message)


def validate_image_upload(upload, field=None):
    if upload is None:
        return upload
    if upload.size > MAX_IMAGE_BYTES:
        _reject(field, IMAGE_ERROR)
    if _extension(upload) not in IMAGE_EXTENSIONS:
        _reject(field, IMAGE_ERROR)
    content_type = getattr(upload, "content_type", "") or ""
    if content_type and content_type not in IMAGE_CONTENT_TYPES:
        _reject(field, IMAGE_ERROR)
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            image.verify()
        upload.seek(0)
        with Image.open(upload) as image:
            width, height = image.size
        upload.seek(0)
    except (UnidentifiedImageError, OSError, ValueError):
        _reject(field, "The uploaded file is not a valid image.")
    if width * height > MAX_IMAGE_PIXELS:
        _reject(field, "The image resolution is too large.")
    return upload


def validate_document_upload(upload, field=None):
    if upload is None:
        return upload
    if upload.size > MAX_DOCUMENT_BYTES:
        _reject(field, DOCUMENT_ERROR)
    if _extension(upload) not in DOCUMENT_EXTENSIONS:
        _reject(field, DOCUMENT_ERROR)
    content_type = getattr(upload, "content_type", "") or ""
    if content_type and content_type not in DOCUMENT_CONTENT_TYPES:
        _reject(field, DOCUMENT_ERROR)
    upload.seek(0)
    header = upload.read(5)
    upload.seek(0)
    if _extension(upload) == ".pdf":
        if header.startswith(b"%PDF-"):
            return upload
        _reject(field, "The uploaded file is not a valid PDF.")
    return validate_image_upload(upload, field)
