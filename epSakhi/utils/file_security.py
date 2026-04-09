import os
import uuid
from django.core.exceptions import ValidationError

# VUN-4 Fixes: File Upload Security Enhancements

# Allowed extensions (whitelist)
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.pdf', '.docx', '.doc'}

# Max file size (e.g., 30MB)
MAX_FILE_SIZE = 30 * 1024 * 1024

def validate_and_rename(file):
    if not file:
        return file

    # No filename Validation
    if not file.name:
        raise ValidationError("Invalid file: missing filename.")

    filename = file.name

    # Double extension (file.php.png) Validation
    # parts = filename.split('.')
    # if len(parts) > 2:
    #     raise ValidationError("Invalid file: multiple extensions detected.")

    # Extension check
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported file type: {ext}")

    # Size check
    if file.size > MAX_FILE_SIZE:
        raise ValidationError("File too large (max 30MB).")

    # Renaming file to a uuid as  Suggested
    new_name = f"{uuid.uuid4().hex}{ext}"
    file.name = new_name

    return file