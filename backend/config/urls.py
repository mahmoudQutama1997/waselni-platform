import os
import posixpath

from django.http import HttpResponseNotFound
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from core.views import RegisterView, MeView, HealthView, CaptainDocumentView

CAPTAIN_DOCUMENTS_PREFIX = "captain_documents"


def _path_segments(path):
    # Backslashes separate directories on Windows and are not normalised by
    # every URL layer, so treat them identically before splitting.
    normalised = posixpath.normpath(str(path or "").replace("\\", "/"))
    return [segment for segment in normalised.split("/") if segment and segment not in (".", "..")]


def _is_private_segment(segment):
    # Windows ignores trailing dots and some APIs strip trailing spaces, so
    # "captain_documents." must be treated like "captain_documents" there.
    return segment.rstrip(" .").casefold() == CAPTAIN_DOCUMENTS_PREFIX


def _resolves_into_captain_documents(path):
    # Aliases such as the Windows 8.3 short name never appear in the textual
    # path, so resolve the location on disk and compare it with the private
    # folder as well.
    try:
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        private_root = os.path.realpath(os.path.join(media_root, CAPTAIN_DOCUMENTS_PREFIX))
        target = os.path.realpath(os.path.join(media_root, *str(path or "").replace("\\", "/").split("/")))
        return os.path.commonpath([target, private_root]) == private_root
    except (OSError, ValueError):
        return False


def is_captain_document_path(path):
    """Return True when a media path can reach the captain documents folder."""
    segments = _path_segments(path)
    if segments and _is_private_segment(segments[0]):
        return True
    return _resolves_into_captain_documents(path)


def serve_media(request, path):
    # SERVE_MEDIA still gates public media; checking it per request keeps the
    # route registered so its behaviour is exercised by the test suite.
    if not settings.SERVE_MEDIA:
        return HttpResponseNotFound()
    # Captain identity/licence/insurance documents are never public: an
    # authenticated, role-checked endpoint streams them instead.
    if is_captain_document_path(path):
        # Bare 404: never echo the attempted path or document name back.
        return HttpResponseNotFound()
    return serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path("api/health/", HealthView.as_view()),
    path("api/auth/register/", RegisterView.as_view()),
    path("api/auth/token/", TokenObtainPairView.as_view()),
    path("api/auth/token/refresh/", TokenRefreshView.as_view()),
    path("api/me/", MeView.as_view()),
    path("api/captain-documents/<int:profile_id>/<str:field>/", CaptainDocumentView.as_view()),
    path("api/", include("core.urls")),
    re_path(r"^media/(?P<path>.*)$", serve_media),
]
