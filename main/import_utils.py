from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.utils import timezone

from .models import User

DEFAULT_IMPORT_FILES = (
    "data_one.csv",
    "data_two.csv",
    "data_three.csv",
)

CSV_IMPORT_ENCODINGS = (
    "utf-8-sig",
    "cp1252",
    "latin-1",
)


@dataclass(slots=True)
class ImportedUserRecord:
    first_name: str
    last_name: str
    registration_id: str | None = None
    external_uuid: str | None = None
    membership: str | None = None
    club: str | None = None


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
    if value.endswith(".0"):
        value = value[:-2]
    return value or None


def normalize_membership(raw_value: str) -> str | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    return value.upper()


def normalize_club(raw_value: str) -> str | None:
    value = normalize_name(raw_value)
    return value or None


def extract_user_record(row: dict) -> ImportedUserRecord | None:
    full_name = normalize_name(row.get("Fullname") or row.get("FULLNAME") or "")
    if not full_name:
        return None

    first_name, last_name = split_name(full_name)
    if not first_name:
        return None

    return ImportedUserRecord(
        first_name=first_name,
        last_name=last_name,
        registration_id=normalize_reg_id(row.get("Reg ID") or row.get("REG ID") or ""),
        external_uuid=(row.get("UUID") or "").strip() or None,
        membership=normalize_membership(row.get("Membership") or row.get("MEMBERSHIP") or ""),
        club=normalize_club(row.get("Club") or row.get("CLUB") or ""),
    )


def find_existing_user(record: ImportedUserRecord) -> User | None:
    if record.external_uuid:
        user = User.objects.filter(external_uuid=record.external_uuid).first()
        if user:
            return user

    if record.registration_id:
        user = User.objects.filter(registration_id=record.registration_id).first()
        if user:
            return user

    return (
        User.objects.filter(
            first_name__iexact=record.first_name,
            last_name__iexact=record.last_name,
        )
        .order_by("-updated_at", "-id")
        .first()
    )


def sync_user_record(record: ImportedUserRecord, update_existing: bool = True) -> str:
    user = find_existing_user(record)
    if user:
        if not update_existing:
            return "skipped"

        changed_fields: list[str] = []
        for field_name, value in {
            "first_name": record.first_name,
            "last_name": record.last_name,
            "registration_id": record.registration_id,
            "external_uuid": record.external_uuid,
            "membership": record.membership,
            "club": record.club,
        }.items():
            if value is not None and getattr(user, field_name) != value:
                setattr(user, field_name, value)
                changed_fields.append(field_name)

        if changed_fields:
            user.save(update_fields=changed_fields + ["updated_at"])
            return "updated"

        return "skipped"

    User.objects.create(
        first_name=record.first_name,
        last_name=record.last_name,
        registration_id=record.registration_id,
        external_uuid=record.external_uuid,
        membership=record.membership,
        club=record.club,
        lunches_remaining=User.WEEKLY_LUNCHES,
        dinners_remaining=User.WEEKLY_DINNERS,
        drinks_remaining=User.WEEKLY_DRINKS,
        week_start=timezone.now(),
    )
    return "created"


def import_user_rows(rows: Iterable[dict], update_existing: bool = True) -> dict[str, int]:
    created = 0
    updated = 0
    skipped = 0

    for row in rows:
        record = extract_user_record(row)
        if not record:
            skipped += 1
            continue

        result = sync_user_record(record, update_existing=update_existing)
        if result == "created":
            created += 1
        elif result == "updated":
            updated += 1
        else:
            skipped += 1

    return {"created": created, "updated": updated, "skipped": skipped}


def read_csv_rows(csv_paths: Iterable[str | Path]) -> list[dict]:
    rows: list[dict] = []
    for csv_path in csv_paths:
        path = Path(csv_path).expanduser().resolve()
        last_error: UnicodeDecodeError | None = None
        for encoding in CSV_IMPORT_ENCODINGS:
            try:
                with path.open(mode="r", encoding=encoding, newline="") as file_handle:
                    rows.extend(csv.DictReader(file_handle))
                last_error = None
                break
            except UnicodeDecodeError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
    return rows
