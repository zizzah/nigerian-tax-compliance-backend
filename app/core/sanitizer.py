"""
Input Sanitization Module
Location: app/core/sanitizer.py

CRITICAL SECURITY: Sanitize user input to prevent XSS and injection attacks

FIXES APPLIED:
1. Remove dangerous HTML tags AND their content (not just tags)
2. Fix TIN sanitization to strip HTML before filtering characters
"""

import bleach
import re
from typing import Optional, Dict, Any


class InputSanitizer:
    """Sanitize user input to prevent XSS and injection attacks"""

    ALLOWED_TAGS = []
    ALLOWED_ATTRIBUTES = {}
    DANGEROUS_PATTERN = re.compile(
        r'<(script|style|iframe|object|embed|svg|math|form|input|textarea|select|button)'
        r'[^>]*>.*?</\1>|<(script|style|iframe|object|embed|svg|math|form|input|textarea'
        r'|select|button)[^>]*/?>',
        re.IGNORECASE | re.DOTALL
    )
    EVENT_PATTERN = re.compile(r'\s*on\w+\s*=\s*["\']?[^"\'>\s]+["\']?', re.IGNORECASE)
    JAVASCRIPT_PATTERN = re.compile(r'javascript:', re.IGNORECASE)

    @staticmethod
    def sanitize_text(text: Optional[str], field_type: str = "general", max_length: int = 10000) -> Optional[str]:
        if not text:
            return text

        text = str(text)
        text = InputSanitizer.DANGEROUS_PATTERN.sub('', text)
        text = InputSanitizer.EVENT_PATTERN.sub('', text)
        text = InputSanitizer.JAVASCRIPT_PATTERN.sub('', text)
        text = bleach.clean(
            text,
            tags=InputSanitizer.ALLOWED_TAGS,
            attributes=InputSanitizer.ALLOWED_ATTRIBUTES,
            strip=True
        )

        if field_type == "name":
            max_length = 255
        elif field_type == "notes":
            max_length = 5000
        elif field_type == "address":
            max_length = 500
        elif field_type == "general":
            max_length = min(max_length, 10000)

        if len(text) > max_length:
            text = text[:max_length]

        text = text.replace('\x00', '')
        text = ' '.join(text.split())
        return text.strip()

    @staticmethod
    def sanitize_email(email: Optional[str]) -> Optional[str]:
        if not email:
            return email

        email = str(email).strip().lower()
        email = bleach.clean(email, strip=True)

        email_pattern = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        if not re.match(email_pattern, email):
            return email

        return email

    @staticmethod
    def sanitize_phone(phone: Optional[str]) -> Optional[str]:
        if not phone:
            return phone

        phone = ''.join(c for c in str(phone) if c.isdigit() or c in '+-() ')
        return phone.strip()

    @staticmethod
    def sanitize_tin(tin: Optional[str]) -> Optional[str]:
        if not tin:
            return tin

        tin = str(tin)
        tin = re.sub(r'<(script|style|iframe)[^>]*>.*?</\1>', '', tin, flags=re.IGNORECASE | re.DOTALL)
        tin = bleach.clean(tin, tags=[], strip=True)
        tin = ''.join(c for c in tin if c.isalnum() or c == '-')
        return tin.strip().upper()

    @staticmethod
    def sanitize_dict(data: Dict[str, Any], text_fields: list) -> Dict[str, Any]:
        sanitized = data.copy()
        for field in text_fields:
            if field in sanitized and isinstance(sanitized[field], str):
                sanitized[field] = InputSanitizer.sanitize_text(sanitized[field])
        return sanitized


sanitizer = InputSanitizer()