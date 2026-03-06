import re
import os
import mimetypes
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils.html import strip_tags
from django.utils import timezone

# ---------------------------------------------------
# 🔒 GENERIC TEXT SANITIZER (Anti-XSS)
# ---------------------------------------------------

XSS_PATTERN = re.compile(
    r"(<\s*script.*?>.*?<\s*/\s*script\s*>|"
    r"javascript:|"
    r"on\w+\s*=)",
    re.IGNORECASE | re.DOTALL
)


def validate_no_xss(value: str):
    """
    Prevent stored XSS attacks in text fields.
    Removes tags and blocks script-based payloads.
    """
    if not value:
        return value

    if XSS_PATTERN.search(value):
        raise ValidationError("Malicious script content detected.")

    # Strip all HTML tags
    cleaned = strip_tags(value)

    return cleaned


# ---------------------------------------------------
# 📄 STRICT PDF VALIDATION (No XSS via File Upload)
# ---------------------------------------------------

ALLOWED_PDF_MIME = ["application/pdf"]
ALLOWED_PDF_EXT = [".pdf"]
MAX_PDF_SIZE_MB = 10


def validate_pdf_file(file):
    """
    Strict validation for PDF uploads.
    Prevents:
    - HTML renamed as .pdf
    - Script-injected files
    - Oversized files
    """

    if not file:
        return

    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_PDF_EXT:
        raise ValidationError("Only PDF files are allowed.")

    # Check MIME
    mime_type, _ = mimetypes.guess_type(file.name)
    if mime_type not in ALLOWED_PDF_MIME:
        raise ValidationError("Invalid file type. Must be a valid PDF.")

    # Check file size
    if file.size > MAX_PDF_SIZE_MB * 1024 * 1024:
        raise ValidationError("File size exceeds 10MB limit.")

    # Optional: check PDF header signature
    file.seek(0)
    header = file.read(4)
    file.seek(0)
    if header != b"%PDF":
        raise ValidationError("Corrupted or invalid PDF file.")


# ---------------------------------------------------
# 📅 DATE VALIDATION
# ---------------------------------------------------

def validate_not_future_date(value):
    if value and value > timezone.now().date():
        raise ValidationError("Date cannot be in the future.")
    return value


def validate_start_end_date(start_date, end_date):
    if start_date and end_date:
        if end_date < start_date:
            raise ValidationError("End date cannot be before start date.")


# ---------------------------------------------------
# 📱 MOBILE VALIDATION
# ---------------------------------------------------

MOBILE_PATTERN = re.compile(r"^[6-9]\d{9}$")


def validate_mobile(value):
    if value:
        if not MOBILE_PATTERN.match(value):
            raise ValidationError("Enter valid 10-digit Indian mobile number.")


# ---------------------------------------------------
# 🔢 POSITIVE NUMBER VALIDATION
# ---------------------------------------------------

def validate_positive_integer(value):
    if value is not None and value < 0:
        raise ValidationError("Value must be positive.")


def validate_decimal_amount(value):
    if value is not None:
        if value < Decimal("0"):
            raise ValidationError("Amount must be positive.")


# ---------------------------------------------------
# 📆 YEAR VALIDATION (YYYY)
# ---------------------------------------------------

YEAR_PATTERN = re.compile(r"^\d{4}$")


def validate_year(value):
    if value:
        if not YEAR_PATTERN.match(value):
            raise ValidationError("Year must be in YYYY format.")
        if int(value) > date.today().year:
            raise ValidationError("Year cannot be in the future.")


# ---------------------------------------------------
# 🏛 BUCKET APPROVAL VALIDATION
# ---------------------------------------------------

def validate_bucket_approval(status, rejection_reason):
    if status == "REJECTED" and not rejection_reason:
        raise ValidationError(
            "Rejection reason is required when status is REJECTED."
        )


# ---------------------------------------------------
# 🔐 SAFE CHAR VALIDATION (Optional Strict Mode)
# ---------------------------------------------------

SAFE_TEXT_PATTERN = re.compile(r"^[a-zA-Z0-9\s.,()\-_/&]+$")


def validate_safe_text(value):
    if value:
        if not SAFE_TEXT_PATTERN.match(value):
            raise ValidationError(
                "Invalid characters detected."
            )