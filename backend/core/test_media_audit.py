import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import User


class MediaAuditCommandTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._override = override_settings(MEDIA_ROOT=self.root)
        self._override.enable()
        self.addCleanup(self._override.disable)

    def test_reports_missing_and_present_files_without_changing_rows(self):
        with_image = User.objects.create_user(username="audit-with", password="x" * 12)
        with_image.profile_image = "profiles/present.png"
        with_image.save(update_fields=["profile_image"])
        (self.root / "profiles").mkdir(parents=True)
        (self.root / "profiles" / "present.png").write_bytes(b"png")

        without_image = User.objects.create_user(username="audit-without", password="x" * 12)
        without_image.profile_image = "profiles/missing.png"
        without_image.save(update_fields=["profile_image"])

        output = StringIO()
        call_command("media_audit", examples=5, stdout=output)
        text = output.getvalue()
        self.assertIn("core.User.profile_image: present=1 missing=1 empty=0", text)
        self.assertIn("stored=profiles/missing.png", text)

        without_image.refresh_from_db()
        self.assertEqual(without_image.profile_image.name, "profiles/missing.png")
