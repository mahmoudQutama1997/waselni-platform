"""Map storage failures to a retryable API response instead of a 500."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .storage import ImageKitError

UNAVAILABLE = {
    "detail": "Media storage is temporarily unavailable. Please try again.",
    "code": "media_storage_unavailable",
}


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ImageKitError):
        return Response(UNAVAILABLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return None
