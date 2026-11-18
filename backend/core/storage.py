"""Media storage that sends every new upload to ImageKit.

Public images (profiles, stores, products) are uploaded as normal ImageKit
files. Captain documents are uploaded with ``isPrivateFile`` and are only
readable through a short-lived signed URL generated server-side, so they never
have a public link. When ImageKit is not configured (local development and
tests) both kinds stay on local disk.

Existing files are never moved: a name that resolves to a file under
MEDIA_ROOT keeps its /media/ URL, and only names that are not present locally
are served from the ImageKit endpoint. A failed ImageKit upload raises
``ImageKitError`` instead of silently writing to the host's ephemeral disk.
"""
import base64
import hashlib
import hmac
import json
import logging
import posixpath
import time
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
ORDER_PROOFS_FOLDER = "order_proofs"
DEFAULT_UPLOAD_API = "https://upload.imagekit.io/api/v1/files/upload"
DEFAULT_MEDIA_API = "https://api.imagekit.io/v1"
DEFAULT_PRIVATE_URL_TTL = 300


class ImageKitError(Exception):
    """Raised when ImageKit rejects or fails an upload/delete request."""


def _posix(name):
    """Normalise separators: Django joins upload_to with the native separator."""
    return str(name or "").replace("\\", "/")


def is_captain_document(name):
    """True when any path segment is the private captain documents folder."""
    normalised = _posix(name)
    segments = [segment for segment in posixpath.normpath(normalised).split("/") if segment and segment != "."]
    return any(segment.rstrip(" .").casefold() == CAPTAIN_DOCUMENTS_FOLDER for segment in segments)


def is_order_proof(name):
    """True when any path segment is the private order proof folder."""
    normalised = _posix(name)
    segments = [segment for segment in posixpath.normpath(normalised).split("/") if segment and segment != "."]
    return any(segment.rstrip(" .").casefold() == ORDER_PROOFS_FOLDER for segment in segments)


def is_private_document(name):
    """Documents the platform may only serve through an authorised endpoint."""
    return is_captain_document(name) or is_order_proof(name)


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


def upload_to_imagekit(name, data, config, private=False):
    """Upload bytes to ImageKit and return the stored remote path.

    ``private=True`` marks captain documents as private on ImageKit, which
    makes them readable only through a signed URL.
    """
    name = _posix(name)
    folder = posixpath.dirname(name)
    if config["prefix"]:
        folder = posixpath.join(config["prefix"], folder) if folder else config["prefix"]
    file_name = posixpath.basename(name)
    boundary = f"----waselni{uuid.uuid4().hex}"
    fields = {"fileName": file_name, "folder": f"/{folder}" if folder else "", "useUniqueFileName": "false"}
    if private:
        fields["isPrivateFile"] = "true"
    body = _multipart_body(
        boundary,
        fields,
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


def _search_remote_file_id(name, config):
    """Look a file up through the search API; None when it is not indexed yet."""
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
        if str(item.get("filePath", "")).lstrip("/") == name.lstrip("/"):
            return item.get("fileId")
    return None


def _folder_remote_file_id(name, config, limit=1000, max_pages=20):
    """Find a file by listing its folder, which does not depend on the search index."""
    folder = posixpath.dirname(name)
    skip = 0
    for _ in range(max_pages):
        query = urlencode({
            "path": f"/{folder}/" if folder else "/",
            "limit": limit,
            "skip": skip,
            "type": "file",
        })
        request = Request(
            f"{config['media_api']}/files?{query}",
            headers={"Authorization": _authorization(config)},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode() or "[]")
        except (HTTPError, URLError, ValueError, OSError) as exc:
            raise ImageKitError(f"ImageKit folder listing failed for {name}: {exc}") from exc
        items = payload if isinstance(payload, list) else payload.get("items") or payload.get("files") or []
        for item in items:
            if str(item.get("filePath", "")).lstrip("/") == name.lstrip("/"):
                return item.get("fileId")
        if len(items) < limit:
            break
        skip += limit
    return None


def delete_from_imagekit(name, config):
    """Delete a remote file by path. Raises ImageKitError on any failure."""
    name = _posix(name)
    try:
        file_id = _search_remote_file_id(name, config)
    except ImageKitError:
        file_id = None
    if not file_id:
        # Search is eventually consistent; listing the folder still finds a
        # file that was uploaded moments ago.
        file_id = _folder_remote_file_id(name, config)
    if not file_id:
        raise ImageKitError(f"ImageKit has no file at {name}.")
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


def purge_imagekit_url(name, config):
    """Purge the CDN and internal cache for a public ImageKit file.

    ImageKit keeps serving deleted files from its cache until the URL is
    purged, so a replaced avatar would otherwise stay reachable for a year.
    """
    name = _posix(name)
    path = "/".join(quote(segment) for segment in name.lstrip("/").split("/"))
    request = Request(
        f"{config['media_api']}/files/purge",
        data=json.dumps({"url": f"{config['endpoint']}/{path}"}).encode(),
        method="POST",
        headers={
            "Authorization": _authorization(config),
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            response.read()
    except (HTTPError, URLError, ValueError, OSError) as exc:
        raise ImageKitError(f"ImageKit cache purge failed for {name}: {exc}") from exc


def signed_private_url(name, config, expires_in=None):
    """Build a short-lived signed URL for a private ImageKit file.

    ImageKit expects HMAC-SHA1(private_key, path + expiry) in ``ik-s`` and the
    unix expiry in ``ik-t``. The URL is generated on the server and is never
    stored; callers must not log it because the signature grants access.
    """
    ttl = int(expires_in or getattr(settings, "IMAGEKIT_PRIVATE_URL_TTL", DEFAULT_PRIVATE_URL_TTL))
    expiry = int(time.time()) + max(30, ttl)
    path = "/" + _posix(name).lstrip("/")
    signature = hmac.new(
        config["private_key"].encode(), f"{path}{expiry}".encode(), hashlib.sha1
    ).hexdigest()
    encoded = "/".join(quote(segment) for segment in path.strip("/").split("/"))
    return f"{config['endpoint']}/{encoded}?ik-t={expiry}&ik-s={signature}"


def _unique_name(name):
    folder, file_name = posixpath.split(_posix(name))
    stem, extension = posixpath.splitext(file_name)
    unique = f"{stem[:40]}-{uuid.uuid4().hex}{extension.lower()}"
    return posixpath.join(folder, unique) if folder else unique


class WaselniMediaStorage(Storage):
    """Send public images and private captain documents to ImageKit.

    Local disk is only used when ImageKit is not configured, which is limited
    to development and tests.
    """

    def __init__(self):
        self._local = FileSystemStorage()

    def _config(self):
        return imagekit_config()

    def _is_remote(self, name):
        """A name is remote when ImageKit is ready, the path is public and no
        legacy local file already exists under MEDIA_ROOT."""
        return bool(self._config()) and not is_private_document(name) and not self._local.exists(name)

    def is_remote_captain_document(self, name):
        """True when a captain document lives on ImageKit rather than disk."""
        return bool(self._config()) and is_captain_document(name) and not self._local.exists(name)

    def is_remote_private_document(self, name):
        """True when any private document (captain file or proof) is remote."""
        return bool(self._config()) and is_private_document(name) and not self._local.exists(name)

    def get_available_name(self, name, max_length=None):
        if self._config():
            # _save() adds a UUID; that makes collisions impossible without a
            # filesystem round trip on every upload.
            return name
        return self._local.get_available_name(name, max_length)

    def _save(self, name, content):
        data = content.read()
        config = self._config()
        if not config:
            return self._local._save(name, ContentFile(data, name=name))
        unique = _unique_name(name)
        private = is_private_document(unique)
        try:
            return upload_to_imagekit(unique, data, config, private=private)
        except ImageKitError:
            # Never fall back to the host's ephemeral disk: the image would
            # disappear on the next restart and its owner would never know.
            logger.exception(
                "ImageKit upload failed for %s; the file was not stored locally.", unique
            )
            raise

    def url(self, name):
        if self._is_remote(name):
            endpoint = self._config()["endpoint"]
            path = "/".join(quote(segment) for segment in _posix(name).lstrip("/").split("/"))
            return f"{endpoint}/{path}"
        return self._local.url(name)

    def private_document_handle(self, name, expires_in=None):
        """Read a private remote document through a fresh signed URL.

        The signed URL is created here and never returned to the caller, so it
        cannot leak through the API response or browser history.
        """
        config = self._config()
        if not config or not is_private_document(name):
            raise FileNotFoundError("No private remote document is available.")
        request = Request(signed_private_url(name, config, expires_in))
        try:
            with urlopen(request, timeout=25) as response:
                data = response.read()
        except (HTTPError, URLError, OSError) as exc:
            raise FileNotFoundError(f"Could not read private document {name}.") from exc
        return File(BytesIO(data), name=str(name))

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
        if not config:
            return
        try:
            delete_from_imagekit(str(name), config)
        except ImageKitError:
            logger.warning("ImageKit delete failed; remote file left in place: %s", name, exc_info=True)
            return
        if not is_private_document(name):
            try:
                purge_imagekit_url(str(name), config)
            except ImageKitError:
                logger.warning(
                    "ImageKit cache purge failed; the old URL may stay cached: %s", name, exc_info=True
                )

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
