from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from main.import_utils import DEFAULT_IMPORT_FILES, import_user_rows, read_csv_rows
from main.models import User


class Command(BaseCommand):
    help = "Compatibility importer for the new sheet CSV exports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-files",
            nargs="+",
            default=[str(Path(settings.BASE_DIR) / file_name) for file_name in DEFAULT_IMPORT_FILES],
            help="One or more CSV files in the new sheet format",
        )
        parser.add_argument(
            "--reset-users",
            action="store_true",
            help="Delete all existing users before import",
        )

    def handle(self, *args, **options):
        csv_paths = [Path(path).expanduser().resolve() for path in options["csv_files"]]
        reset_users = options["reset_users"]

        missing_files = [path for path in csv_paths if not path.exists()]
        if missing_files:
            missing = ", ".join(str(path) for path in missing_files)
            self.stdout.write(self.style.ERROR(f"Missing file(s): {missing}"))
            return

        with transaction.atomic():
            if reset_users:
                User.objects.all().delete()

            result = import_user_rows(read_csv_rows(csv_paths), update_existing=True)

        self.stdout.write(
            self.style.SUCCESS(
                "Import complete. "
                f"created={result['created']}, updated={result['updated']}, skipped={result['skipped']}"
            )
        )
