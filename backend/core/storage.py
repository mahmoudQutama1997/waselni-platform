"""Media storage that keeps private captain documents local and sends public
images to ImageKit.

Existing files are never moved: a name that resolves to a file under
MEDIA_ROOT keeps its /media/ URL, and only names that are not present locally
are served from the ImageKit endpoint. If ImageKit is unconfigured or an upload
fails, the file is stored locally and the failure is logged.
"""
import base64
import json
import logging
import posixpath
import uuid
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage, Storage

logger = logging.getLogger("waselni.storage")

CAPTAIN_DOCUMENTS_FOLDER = "captain_documents"
DEFAULT_UPLOAD_API = "https://upload.imagekit.io/api/v1/files/upload"
DEFAULT_MEDIA_API = "https://api.imagekit.io/v1"


class ImageKitError(Exception):
    """Raised when ImageKit rejects or fails an upload/delete request."""


def is_captain_document(name):
    """True when any path segment is the private captain documents folder."""
    normalised = str(name or "").replace("\\", "/")
    segments = [segment for segment in posixpath.normpath(normalised).split("/") if segment and segment != "."]
    return any(segment.rstrip(" .").casefold() == CAPTAIN_DOCUMENTS_FOLDER for segment in segments)


def imagekit_config():
    private_key = (getattr(settings, "IMAGEKIT_PRIVATE_KEY", "") or "").strip()
    endpoint = (getattr(settings, "IMAGEKIT_URL_ENDPOINT", "") or "").strip().rstrip("/")
    if not private_key or not endpoint:
        return None
    return {
        "private_key": private_key,
        "endpoint": endpoint,
        "upload_api": getattr(settings, "IMAGEKIT_UPLOAD_API", DEFAULT_UPLOAD_API),
        "media_api": getattr(settings, "IMAGEKIT_MEDIA_API", DEFAULT_MEDIA_API),
        "prefix": (getattr(settings, "IMAGEKIT_UPLOAD_FOLDER_PREFIX", "") or "").strip().strip("/"),
    }


def _authorization(config):
    token = base64.b64encode(f"{config['private_key']}:".encode()).decode()
    return f"Basic {token}"


def _multipart_body(boundary, fields, file_field):
    parts = []
    for key, value in fields.items():
        if value in (None, ""):
            continue
        parts.append(f"--{boundary}")
        parts.append(f'Content-Disposition: form-data; name="{key}"')
        parts.append("")
        parts.append(str(value))
    field_name, file_name, data = file_field
    parts.append(f"--{boundary}")
    parts.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"')
    parts.append("Content-Type: application/octet-stream")
    parts.append("")
    head = ("\r\n".join(parts) + "\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + data + tail


def upload_to_imagekit(name, data, config):
    """Upload bytes to ImageKit and return the stored remote path."""
    folder = posixpath.dirname(name)
    if config["prefix"]:
        folder = posixpath.join(config["prefix"], folder) if folder else config["prefix"]
    file_name = posixpath.basename(name)
    boundary = f"----waselni{uuid.uuid4().hex}"
    body = _multipart_body(
        boundary,
        {"fileName": file_name, "folder": f"/{folder}" if folder else "", "useUniqueFileName": "false"},
        ("file", file_name, data),
    )
    request = Request(
        config["upload_api"],
        data=body,
        method="POST",
        headers={
            "Authorization": _authorization(config),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode() or "{}")
    except (HTTPError, URLError, ValueError, OSError) as exc:
        raise ImageKitError(f"ImageKit upload failed for {file_name}: {exc}") from exc
    remote_path = str(payload.get("filePath") or "").lstrip("/")
    if not remote_path:
        raise ImageKitError(f"ImageKit upload returned no filePath for {file_name}.")
    return remote_path


def delete_from_imagekit(name, config):
    """Delete a remote file by path. Raises ImageKitError on any failure."""
    query = urlencode({"searchQuery": f'path="{name if name.startswith("/") else "/" + name}"'})
    request = Request(
        f"{config['media_api']}/files?{query}",
        headers={"Authorization": _authorization(config)},
    )
    try:
        with urlopen(request, timeout=20) as response:
            files = json.loads(response.read().decode() or "[]")
    except (HTTPError, URLError, ValueError, OSError) as exc:
        raise ImageKitError(f"ImageKit lookup failed for {name}: {exc}") from exc
    for item in files or []:
        if str(item.get("filePath", "")).lstrip("/") != name.lstrip("/"):
            continue
        file_id = item.get("fileId")
        if not file_id:
            continue
        delete_request = Request(
            f"{config['media_api']}/files/{quote(str(file_id))}",
            method="DELETE",
            headers={"Authorization": _authorization(config)},
        )
        try:
            with urlopen(delete_request, timeout=20) as response:
                response.read()
        except (HTTPError, URLError, OSError) as exc:
            raise ImageKitError(f"ImageKit delete failed for {name}: {exc}") from exc
        return
    raise ImageKitError(f"ImageKit has no file at {name}.")


def _unique_name(name):
    folder, file_name = posixpath.split(str(name))
    stem, extension = posixpath.splitext(file_name)
    unique = f"{stem[:40]}-{uuid.uuid4().hex}{extension.lower()}"
    return posixpath.join(folder, unique) if folder else unique


class WaselniMediaStorage(Storage):
    """Route private documents to local disk and public images to ImageKit."""

    def __init__(self):
        self._local = FileSystemStorage()

    def _config(self):
        return imagekit_config()

    def _is_remote(self, name):
        """A name is remote when ImageKit is ready, the path is public and no
        legacy local file already exists under MEDIA_ROOT."""
        return bool(self._config()) and not is_captain_document(name) and not self._local.exists(name)

    def get_available_name(self, name, max_length=None):
        if not is_captain_document(name) and self._config():
            # _save() adds a UUID; that makes collisions impossible without a
            # filesystem round trip on every upload.
            return name
        return self._local.get_available_name(name, max_length)

    def _save(self, name, content):
        data = content.read()
        if is_captain_document(name):
            return self._local._save(name, ContentFile(data, name=name))
        config = self._config()
        if not config:
            return self._local._save(name, ContentFile(data, name=name))
        unique = _unique_name(name)
        try:
            return upload_to_imagekit(unique, data, config)
        except ImageKitError:
            logger.exception("ImageKit upload failed; saved %s to local media instead.", unique)
            return self._local._save(unique, ContentFile(data, name=unique))

    def url(self, name):
        if self._is_remote(name):
            endpoint = self._config()["endpoint"]
            path = "/".join(quote(segment) for segment in str(name).lstrip("/").split("/"))
            return f"{endpoint}/{path}"
        return self._local.url(name)

    def exists(self, name):
        if self._local.exists(name):
            return True
        return self._is_remote(name)

    def delete(self, name):
        if not name:
            return
        if self._local.exists(name):
            self._local.delete(name)
            return
        config = self._config()
        if not config or is_captain_document(name):
            return
        try:
            delete_from_imagekit(str(name), config)
        except ImageKitError:
            logger.warning("ImageKit delete failed; remote file left in place: %s", name, exc_info=True)

    def size(self, name):
        if self._local.exists(name) or not self._is_remote(name):
            return self._local.size(name)
        request = Request(self.url(name), method="HEAD")
        try:
            with urlopen(request, timeout=20) as response:
                length = response.headers.get("Content-Length")
                if length is not None:
                    return int(length)
        except (HTTPError, URLError, OSError, ValueError) as exc:
            raise OSError(f"Could not read remote file size for {name}: {exc}") from exc
        return len(self._open(name).read())

    def _open(self, name, mode="rb"):
        if self._local.exists(name) or not self._is_remote(name):
            return self._local._open(name, mode)
        request = Request(self.url(name))
        try:
            with urlopen(request, timeout=25) as response:
                return File(BytesIO(response.read()), name=str(name))
        except (HTTPError, URLError, OSError) as exc:
            raise FileNotFoundError(f"Could not open remote file {name}: {exc}") from exc

    def path(self, name):
        if self._local.exists(name) or not self._is_remote(name):
            return self._local.path(name)
        raise NotImplementedError("Remote ImageKit files have no local path.")
