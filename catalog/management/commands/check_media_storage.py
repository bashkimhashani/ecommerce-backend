from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Show active media storage configuration and optionally verify writes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verify-write",
            action="store_true",
            help="Write and delete a small media file to verify storage access.",
        )

    def handle(self, *args, **options):
        storage_class = (
            f"{default_storage.__class__.__module__}."
            f"{default_storage.__class__.__name__}"
        )

        self.stdout.write(f"MEDIA_URL={settings.MEDIA_URL}")
        self.stdout.write(f"DEFAULT_STORAGE={storage_class}")
        self.stdout.write(
            f"AWS_STORAGE_BUCKET_NAME={settings.AWS_STORAGE_BUCKET_NAME or ''}"
        )
        self.stdout.write(f"AWS_S3_REGION_NAME={settings.AWS_S3_REGION_NAME or ''}")

        if settings.AWS_STORAGE_BUCKET_NAME:
            self.stdout.write(self.style.SUCCESS("S3 media storage is configured."))
        else:
            self.stdout.write(
                self.style.WARNING("Local filesystem media storage is active.")
            )

        if options["verify_write"]:
            self.verify_write_access()

    def verify_write_access(self):
        path = "health-check/media-storage.txt"
        content = ContentFile(b"Vendora media storage health check.\n")

        try:
            saved_path = default_storage.save(path, content)
            if not default_storage.exists(saved_path):
                raise CommandError(
                    "Storage write verification failed: file was not found "
                    "after save."
                )
            default_storage.delete(saved_path)
        except Exception as error:
            raise CommandError(
                f"Storage write verification failed: {error}"
            ) from error

        self.stdout.write(self.style.SUCCESS("Storage write verification succeeded."))
