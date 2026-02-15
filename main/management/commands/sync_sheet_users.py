import csv
import io
import time
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import User


@dataclass
class SheetUser:
    full_name: str
    gender: str = "UNKNOWN"
    club: str | None = None
    membership: str | None = None
    delegate_reg_id: str | None = None
    external_uuid: str | None = None


def normalize_name(name: str) -> str:
    return " ".join((name or "").strip().split())


def split_name(full_name: str) -> tuple[str, str]:
    normalized = normalize_name(full_name)
    if not normalized:
        return "", ""
    parts = normalized.split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def normalize_gender(raw_gender: str) -> str:
    value = (raw_gender or "").strip().upper()
    if value in {"F", "FEMALE"}:
        return "F"
    if value in {"M", "MALE"}:
        return "M"
    return "UNKNOWN"


def normalize_reg_id(raw_value: str) -> str | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    if value.endswith(".0"):
        value = value[:-2]
    return value or None


def get_sheet_rows(csv_url: str) -> list[dict]:
    response = requests.get(csv_url, timeout=30)
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    return list(reader)


def extract_user(row: dict) -> SheetUser | None:
    full_name = (
        row.get("FULLNAME")
        or row.get("Full Name")
        or row.get("Delegate Name")
        or row.get("Name")
        or row.get("FULL NAME")
        or ""
    )
    full_name = normalize_name(full_name)
    if not full_name:
        return None

    gender = normalize_gender(row.get("Gender") or row.get("GENDER") or "")
    club = (row.get("CLUB") or row.get("Club Name") or row.get("Club") or "").strip() or None
    membership = (row.get("Membership") or row.get("MEMBERSHIP") or "").strip() or None
    delegate_reg_id = normalize_reg_id(row.get("Delegate Reg ID") or row.get("Reg ID") or "")
    external_uuid = (row.get("UUID") or row.get("External UUID") or "").strip() or None

    return SheetUser(
        full_name=full_name,
        gender=gender,
        club=club,
        membership=membership,
        delegate_reg_id=delegate_reg_id,
        external_uuid=external_uuid,
    )


def find_existing_user(sheet_user: SheetUser) -> User | None:
    if sheet_user.external_uuid:
        user = User.objects.filter(external_uuid=sheet_user.external_uuid).first()
        if user:
            return user

    if sheet_user.delegate_reg_id:
        user = User.objects.filter(delegate_reg_id=sheet_user.delegate_reg_id).first()
        if user:
            return user

    first_name, last_name = split_name(sheet_user.full_name)
    if not first_name:
        return None

    users_by_name = User.objects.filter(
        first_name__iexact=first_name,
        last_name__iexact=last_name,
    )

    if sheet_user.gender in {"M", "F"}:
        return users_by_name.filter(gender=sheet_user.gender).first() or users_by_name.first()

    return users_by_name.first()


class Command(BaseCommand):
    help = "Sync users from a Google Sheet CSV into the database. Adds new users only by default."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-url",
            default=getattr(settings, "SHEET_CSV_URL", ""),
            help="CSV export URL for the sheet",
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
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update missing fields for matched users instead of create-only",
        )

    def handle(self, *args, **options):
        csv_url = options["csv_url"]
        loop = options["loop"]
        interval = options["interval"]
        update_existing = options["update_existing"]

        if not csv_url:
            self.stdout.write(self.style.ERROR("SHEET_CSV_URL is not configured."))
            return

        def run_once():
            try:
                rows = get_sheet_rows(csv_url)
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.ERROR(f"Failed to fetch CSV: {exc}"))
                return

            created = 0
            updated = 0

            for row in rows:
                sheet_user = extract_user(row)
                if not sheet_user:
                    continue

                existing = find_existing_user(sheet_user)
                if existing:
                    if update_existing:
                        changed = False
                        if existing.gender == "UNKNOWN" and sheet_user.gender in {"M", "F"}:
                            existing.gender = sheet_user.gender
                            changed = True
                        if not existing.rotary_club and sheet_user.club:
                            existing.rotary_club = sheet_user.club
                            changed = True
                        if not existing.membership and sheet_user.membership:
                            existing.membership = sheet_user.membership
                            changed = True
                        if not existing.delegate_reg_id and sheet_user.delegate_reg_id:
                            existing.delegate_reg_id = sheet_user.delegate_reg_id
                            changed = True
                        if not existing.external_uuid and sheet_user.external_uuid:
                            existing.external_uuid = sheet_user.external_uuid
                            changed = True
                        if changed:
                            existing.save()
                            updated += 1
                    continue

                first_name, last_name = split_name(sheet_user.full_name)
                if not first_name:
                    continue

                User.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    gender=sheet_user.gender,
                    rotary_club=sheet_user.club,
                    membership=sheet_user.membership,
                    delegate_reg_id=sheet_user.delegate_reg_id,
                    external_uuid=sheet_user.external_uuid,
                    lunches_remaining=User.WEEKLY_LUNCHES,
                    dinners_remaining=User.WEEKLY_DINNERS,
                    drinks_remaining=User.WEEKLY_DRINKS,
                    week_start=timezone.now(),
                )
                created += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"Sheet sync done. created={created}, updated={updated}, rows={len(rows)}"
                )
            )

        if loop:
            self.stdout.write(
                self.style.WARNING(
                    f"Starting sheet sync loop: interval={interval}s, url={csv_url}"
                )
            )
            while True:
                run_once()
                time.sleep(interval)
        else:
            run_once()
