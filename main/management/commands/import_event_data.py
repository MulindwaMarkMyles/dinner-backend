import csv
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from main.models import User


@dataclass
class PersonData:
    full_name: str
    delegate_reg_id: str | None = None
    external_uuid: str | None = None
    membership: str | None = None
    club_name: str | None = None
    inferred_gender: str = "UNKNOWN"
    has_friday_lunch: bool = False
    has_saturday_lunch: bool = False
    has_bbq: bool = False
    lunch_slots: int = 0
    dinner_slots: int = 0
    seen_sources: set[str] = field(default_factory=set)


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


def normalize_reg_id(raw_value: str) -> str | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    # Some rows come as "7406.0"
    if value.endswith(".0"):
        value = value[:-2]

    return value or None


def normalize_gender(raw_gender: str) -> str:
    value = (raw_gender or "").strip().upper()
    if value in {"F", "FEMALE"}:
        return "F"
    if value in {"M", "MALE"}:
        return "M"
    return "UNKNOWN"


def infer_gender_from_extra(extra_name: str) -> str:
    value = (extra_name or "").strip().lower()

    if "female bag" in value or "blouse" in value:
        return "F"
    if "male bag" in value or "shirt" in value:
        return "M"

    return "UNKNOWN"


def choose_gender(current: str, incoming: str) -> str:
    if current == "UNKNOWN" and incoming in {"M", "F"}:
        return incoming
    if incoming == "UNKNOWN":
        return current
    if current == incoming:
        return current
    # Conflicting source hints: keep UNKNOWN to avoid wrong assignment
    return "UNKNOWN"


class Command(BaseCommand):
    help = "Import event delegates from local CSV files into the DB (no Google Sheets)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lunch-csv",
            default=str(Path(settings.BASE_DIR) / "lunch_bbq_data.csv"),
            help="Path to lunch/bbq CSV",
        )
        parser.add_argument(
            "--other-csv",
            default=str(Path(settings.BASE_DIR) / "other_data.csv"),
            help="Path to other registrations CSV",
        )
        parser.add_argument(
            "--reset-users",
            action="store_true",
            help="Delete all existing users before import",
        )

    def handle(self, *args, **options):
        lunch_csv = Path(options["lunch_csv"]).expanduser().resolve()
        other_csv = Path(options["other_csv"]).expanduser().resolve()
        reset_users = options["reset_users"]

        if not lunch_csv.exists():
            self.stdout.write(self.style.ERROR(f"Missing file: {lunch_csv}"))
            return

        if not other_csv.exists():
            self.stdout.write(self.style.ERROR(f"Missing file: {other_csv}"))
            return

        people: dict[str, PersonData] = {}

        def upsert_person(row: dict, source: str) -> PersonData | None:
            full_name = normalize_name(row.get("Delegate Name", ""))
            if not full_name:
                return None

            delegate_reg_id = normalize_reg_id(row.get("Delegate Reg ID", ""))
            external_uuid = (row.get("UUID", "") or "").strip() or None

            key = external_uuid or delegate_reg_id or full_name.lower()

            person = people.get(key)
            if not person:
                person = PersonData(full_name=full_name)
                people[key] = person

            person.delegate_reg_id = person.delegate_reg_id or delegate_reg_id
            person.external_uuid = person.external_uuid or external_uuid
            person.membership = person.membership or (row.get("Membership", "") or "").strip() or None
            person.club_name = person.club_name or (row.get("Club Name", "") or "").strip() or None
            person.seen_sources.add(source)

            inferred = infer_gender_from_extra(row.get("Extra Name", ""))
            person.inferred_gender = choose_gender(person.inferred_gender, inferred)

            return person

        with lunch_csv.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                person = upsert_person(row, "lunch")
                if not person:
                    continue

                extra_name = (row.get("Extra Name", "") or "").strip().lower()
                if extra_name == "friday lunch":
                    person.has_friday_lunch = True
                    person.lunch_slots += 1
                elif extra_name == "saturday lunch":
                    person.has_saturday_lunch = True
                    person.lunch_slots += 1
                elif extra_name == "meat & greet bbq":
                    person.has_bbq = True
                    person.dinner_slots += 1

        with other_csv.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                upsert_person(row, "other")

        if not people:
            self.stdout.write(self.style.WARNING("No rows imported from source CSV files."))
            return

        created = 0
        updated = 0

        with transaction.atomic():
            if reset_users:
                User.objects.all().delete()

            for person in people.values():
                first_name, last_name = split_name(person.full_name)
                if not first_name:
                    continue

                target_gender = normalize_gender(person.inferred_gender)

                # Prefer stable IDs for matching, fallback to names
                user = None
                if person.external_uuid:
                    user = User.objects.filter(external_uuid=person.external_uuid).first()

                if not user and person.delegate_reg_id:
                    user = User.objects.filter(delegate_reg_id=person.delegate_reg_id).first()

                if not user:
                    users_by_name = User.objects.filter(
                        first_name__iexact=first_name,
                        last_name__iexact=last_name,
                    )
                    user = users_by_name.filter(gender=target_gender).first() or users_by_name.first()

                defaults = {
                    "gender": target_gender,
                    "rotary_club": person.club_name,
                    "delegate_reg_id": person.delegate_reg_id,
                    "external_uuid": person.external_uuid,
                    "membership": person.membership,
                    "has_friday_lunch": person.has_friday_lunch,
                    "has_saturday_lunch": person.has_saturday_lunch,
                    "has_bbq": person.has_bbq,
                    "lunches_remaining": person.lunch_slots,
                    "dinners_remaining": person.dinner_slots,
                    "drinks_remaining": User.WEEKLY_DRINKS,
                    "week_start": timezone.now(),
                }

                if user:
                    # Only replace UNKNOWN with concrete gender
                    if user.gender == "UNKNOWN" and target_gender in {"M", "F"}:
                        user.gender = target_gender

                    for field_name, value in defaults.items():
                        if field_name == "gender":
                            continue
                        setattr(user, field_name, value)

                    user.first_name = first_name
                    user.last_name = last_name
                    user.save()
                    updated += 1
                else:
                    User.objects.create(
                        first_name=first_name,
                        last_name=last_name,
                        **defaults,
                    )
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. created={created}, updated={updated}, total_source_people={len(people)}"
            )
        )
