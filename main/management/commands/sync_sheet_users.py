import csv
import io
import time
from urllib.request import urlopen

from django.conf import settings
from django.core.management.base import BaseCommand

from main.import_utils import extract_user_record, sync_user_record


def get_sheet_rows(csv_url: str) -> list[dict]:
    with urlopen(csv_url, timeout=30) as response:
        content = response.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


class Command(BaseCommand):
    help = "Sync users from one or more CSV export URLs using the new sheet format."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-url",
            action="append",
            dest="csv_urls",
            default=None,
            help="CSV export URL for a sheet. Repeat for multiple sheets.",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep running and poll at a fixed interval",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=int(getattr(settings, "POLL_INTERVAL", "60")),
            help="Polling interval in seconds when using --loop",
        )

    def handle(self, *args, **options):
        csv_urls = options["csv_urls"] or []
        loop = options["loop"]
        interval = options["interval"]

        if not csv_urls:
            default_url = getattr(settings, "SHEET_CSV_URL", "")
            if default_url:
                csv_urls = [default_url]

        if not csv_urls:
            self.stdout.write(self.style.ERROR("Provide at least one --csv-url or configure SHEET_CSV_URL."))
            return

        def run_once():
            try:
                rows = []
                for csv_url in csv_urls:
                    rows.extend(get_sheet_rows(csv_url))
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.ERROR(f"Failed to fetch CSV: {exc}"))
                return

            created = 0
            updated = 0
            skipped = 0

            for row in rows:
                record = extract_user_record(row)
                if not record:
                    continue

                result = sync_user_record(record, update_existing=True)
                if result == "created":
                    created += 1
                elif result == "updated":
                    updated += 1
                else:
                    skipped += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Sheet sync done. created={created}, updated={updated}, skipped={skipped}, rows={len(rows)}"
                )
            )

        if loop:
            self.stdout.write(
                self.style.WARNING(
                    f"Starting sheet sync loop: interval={interval}s, urls={', '.join(csv_urls)}"
                )
            )
            while True:
                run_once()
                time.sleep(interval)
        else:
            run_once()
