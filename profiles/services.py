import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils.crypto import get_random_string

from accounts.models import User, UserRole
from profiles.models import StudentProfile


def import_students_from_csv(file_obj, institution) -> tuple[int, list[dict[str, Any]]]:
    """
    Import students from a CSV file into the given institution.
    Required CSV headers (case-insensitive):
      roll_no, name, email, programme, batch, cgpa

    Returns:
      (success_count, error_records)
    """
    # Read file content safely
    try:
        content = file_obj.read()
        if isinstance(content, bytes):
            try:
                decoded_file = io.StringIO(content.decode('utf-8'))
            except UnicodeDecodeError:
                decoded_file = io.StringIO(content.decode('latin-1'))
        else:
            decoded_file = io.StringIO(content)
    except Exception as exc:
        return 0, [{'row': '-', 'roll_no': '-', 'name': '-', 'email': '-', 'programme': '-', 'batch': '-', 'cgpa': '-', 'reason': f"Could not read CSV file: {exc}"}]

    reader = csv.reader(decoded_file)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return 0, [{'row': '1', 'roll_no': '-', 'name': '-', 'email': '-', 'programme': '-', 'batch': '-', 'cgpa': '-', 'reason': "CSV file is completely empty."}]

    # Normalize headers
    headers = [h.strip().lower() for h in raw_headers]
    required_fields = ['roll_no', 'name', 'email', 'programme', 'batch', 'cgpa']
    missing = [f for f in required_fields if f not in headers]
    if missing:
        return 0, [{
            'row': '1',
            'roll_no': '-',
            'name': '-',
            'email': '-',
            'programme': '-',
            'batch': '-',
            'cgpa': '-',
            'reason': f"Missing required column headers: {', '.join(missing)}. Expected columns: {', '.join(required_fields)}",
        }]

    col_map = {name: headers.index(name) for name in required_fields}

    success_count = 0
    errors: list[dict[str, Any]] = []

    seen_emails_in_batch = set()
    seen_rolls_in_batch = set()

    row_num = 1
    for row in reader:
        row_num += 1
        if not row or not any(field.strip() for field in row):
            continue  # skip blank lines

        # Extract values
        def get_val(col_name):
            idx = col_map[col_name]
            return row[idx].strip() if idx < len(row) else ''

        roll_no = get_val('roll_no')
        name = get_val('name')
        email = get_val('email').lower()
        programme = get_val('programme')
        batch = get_val('batch')
        cgpa_str = get_val('cgpa')

        error_reason = None

        # Validation rules
        if not roll_no:
            error_reason = "Missing roll number."
        elif roll_no in seen_rolls_in_batch or StudentProfile.objects.filter(institution=institution, roll_no=roll_no).exists():
            error_reason = f"Duplicate roll number '{roll_no}' in this institution."
        elif not name:
            error_reason = "Missing student name."
        elif not email:
            error_reason = "Missing email address."
        else:
            try:
                validate_email(email)
            except ValidationError:
                error_reason = f"Invalid email format: '{email}'."

        if not error_reason:
            if email in seen_emails_in_batch or User.objects.filter(email=email).exists():
                error_reason = f"Email '{email}' is already registered in the system."

        if not error_reason and not programme:
            error_reason = "Missing programme/degree."

        if not error_reason and not batch:
            error_reason = "Missing batch/graduation year."

        cgpa_decimal = None
        if not error_reason and cgpa_str:
            try:
                cgpa_val = Decimal(cgpa_str)
                if not (Decimal('0.00') <= cgpa_val <= Decimal('10.00')):
                    error_reason = f"CGPA '{cgpa_str}' out of range. Must be between 0.00 and 10.00."
                else:
                    cgpa_decimal = cgpa_val
            except (InvalidOperation, ValueError):
                error_reason = f"CGPA '{cgpa_str}' is not a valid number."

        # If any validation failed, record error and skip row
        if error_reason:
            errors.append({
                'row': str(row_num),
                'roll_no': roll_no or '—',
                'name': name or '—',
                'email': email or '—',
                'programme': programme or '—',
                'batch': batch or '—',
                'cgpa': cgpa_str or '—',
                'reason': error_reason,
            })
            continue

        # Valid row -> Atomic creation
        try:
            with transaction.atomic():
                # Split name into first and last
                name_parts = name.split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''

                temp_password = f"Nuv@{get_random_string(8)}1"

                user = User.objects.create_user(
                    email=email,
                    password=temp_password,
                    first_name=first_name,
                    last_name=last_name,
                    role=UserRole.STUDENT,
                    institution=institution,
                    is_verified=True,  # Institutional import is pre-verified
                )

                StudentProfile.objects.create(
                    user=user,
                    institution=institution,
                    roll_no=roll_no,
                    programme=programme,
                    batch=batch,
                    cgpa=cgpa_decimal,
                )

                seen_rolls_in_batch.add(roll_no)
                seen_emails_in_batch.add(email)
                success_count += 1
        except Exception as exc:
            errors.append({
                'row': str(row_num),
                'roll_no': roll_no,
                'name': name,
                'email': email,
                'programme': programme,
                'batch': batch,
                'cgpa': cgpa_str,
                'reason': f"Database creation error: {exc}",
            })

    return success_count, errors
