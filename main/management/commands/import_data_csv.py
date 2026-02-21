import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from main.models import User


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


class Command(BaseCommand):
    help = "Import users from data.csv with duplicate handling (matches by UUID, Reg ID, or name+gender)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(Path(settings.BASE_DIR) / "data.csv"),
            help="Path to data.csv file",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update missing fields for matched users instead of skipping",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv"]).expanduser().resolve()
        update_existing = options["update_existing"]

        if not csv_path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {csv_path}"))
            return

        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    full_name = normalize_name(row.get("Fullname", ""))
                    if not full_name:
                        skipped += 1
                        continue

                    first_name, last_name = split_name(full_name)
                    if not first_name:
                        skipped += 1
                        continue

                    # Extract fields
                    external_uuid = (row.get("UUID", "") or "").strip() or None
                    delegate_reg_id = normalize_reg_id(row.get("Reg ID", ""))
                    gender = normalize_gender(row.get("Gender", ""))
                    membership = (row.get("Membership", "") or "").strip() or None
                    club = (row.get("Club", "") or "").strip() or None
                    district = (row.get("District", "") or "").strip() or None
                    dietary = (row.get("Dietary Requirements", "") or "").strip() or None
                    if dietary and dietary.upper() == "NONE":
                        dietary = None

                    # Find existing user by UUID, Reg ID, or name+gender
                    existing = None
                    if external_uuid:
                        existing = User.objects.filter(external_uuid=external_uuid).first()

                    if not existing and delegate_reg_id:
                        existing = User.objects.filter(delegate_reg_id=delegate_reg_id).first()

                    if not existing:
                        users_by_name = User.objects.filter(
                            first_name__iexact=first_name,
                            last_name__iexact=last_name,
                        )
                        if gender in {"M", "F"}:
                            existing = users_by_name.filter(gender=gender).first() or users_by_name.first()
                        else:
                            existing = users_by_name.first()

                    if existing:
                        if update_existing:
                            changed = False
                            # Update only if current value is missing
                            if existing.gender == "UNKNOWN" and gender in {"M", "F"}:
                                existing.gender = gender
                                changed = True
                            if not existing.external_uuid and external_uuid:
                                existing.external_uuid = external_uuid
                                changed = True
                            if not existing.delegate_reg_id and delegate_reg_id:
                                existing.delegate_reg_id = delegate_reg_id
                                changed = True
                            if not existing.membership and membership:
                                existing.membership = membership
                                changed = True
                            if not existing.rotary_club and club:
                                existing.rotary_club = club
                                changed = True
                            if not existing.district and district:
                                existing.district = district
                                changed = True
                            if not existing.dietary_requirements and dietary:
                                existing.dietary_requirements = dietary
                                changed = True

                            if changed:
                                existing.save()
                                updated += 1
                            else:
                                skipped += 1
                        else:
                            skipped += 1
                        continue

                    # Create new user
                    User.objects.create(
                        first_name=first_name,
                        last_name=last_name,
                        gender=gender,
                        external_uuid=external_uuid,
                        delegate_reg_id=delegate_reg_id,
                        membership=membership,
                        rotary_club=club,
                        district=district,
                        dietary_requirements=dietary,
                        lunches_remaining=User.WEEKLY_LUNCHES,
                        dinners_remaining=User.WEEKLY_DINNERS,
                        drinks_remaining=User.WEEKLY_DRINKS,
                        week_start=timezone.now(),
                    )
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. created={created}, updated={updated}, skipped={skipped}"
            )
        )
