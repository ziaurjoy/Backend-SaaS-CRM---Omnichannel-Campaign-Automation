import re
import logging
from typing import Optional, Dict, Any, Tuple
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

logger = logging.getLogger(__name__)

def validate_and_normalize_phone(
    raw_phone: Optional[str],
    default_region: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates and normalizes any input phone number into international E.164 format.
    
    :param raw_phone: Raw phone string (e.g., '+880 1771-833614', '(017) 718-33614', '01771833614', '+1 (555) 019-9992')
    :param default_region: 2-letter ISO country code (e.g. 'BD', 'US') to resolve national numbers.
    :return: Dict containing validation status, formatted E.164, country code, and error detail.
    """
    if not raw_phone:
        return {
            'is_valid': False,
            'e164': None,
            'national_format': None,
            'country_code': None,
            'region_code': None,
            'error': 'Phone number is empty or not provided.'
        }

    phone_str = str(raw_phone).strip()
    # Strip common extension markers or trailing garbage
    phone_str = re.sub(r'[\r\n\t]', '', phone_str)

    # Attempt parsing:
    # 1. Direct parse if starts with '+'
    # 2. If no '+' and default_region provided, parse with default_region
    # 3. Fallback: try parsing with '+' prepended if starts with country code like 880, 1, 44, etc.
    candidate_regions = []
    if default_region and len(default_region) == 2:
        candidate_regions.append(default_region.upper())
    # Common default fallbacks if none specified
    candidate_regions.extend([None, 'BD', 'US', 'GB'])

    parsed_number = None
    last_error = None

    if phone_str.startswith('+'):
        try:
            parsed = phonenumbers.parse(phone_str, None)
            if phonenumbers.is_valid_number(parsed):
                parsed_number = parsed
        except NumberParseException as e:
            last_error = str(e)
    else:
        # Try candidate regions
        for region in candidate_regions:
            try:
                parsed = phonenumbers.parse(phone_str, region)
                if phonenumbers.is_valid_number(parsed):
                    parsed_number = parsed
                    break
            except NumberParseException as e:
                last_error = str(e)
                continue

        # If still not parsed, try prepending '+' if it consists of digits
        if not parsed_number:
            digits_only = re.sub(r'[^0-9]', '', phone_str)
            if len(digits_only) >= 10:
                try:
                    parsed = phonenumbers.parse(f"+{digits_only}", None)
                    if phonenumbers.is_valid_number(parsed):
                        parsed_number = parsed
                except NumberParseException:
                    pass

    if parsed_number and phonenumbers.is_valid_number(parsed_number):
        e164_str = phonenumbers.format_number(parsed_number, PhoneNumberFormat.E164)
        national_str = phonenumbers.format_number(parsed_number, PhoneNumberFormat.NATIONAL)
        region = phonenumbers.region_code_for_number(parsed_number)
        
        return {
            'is_valid': True,
            'e164': e164_str,
            'national_format': national_str,
            'country_code': parsed_number.country_code,
            'region_code': region,
            'error': None
        }

    return {
        'is_valid': False,
        'e164': None,
        'national_format': None,
        'country_code': None,
        'region_code': None,
        'error': f"Invalid phone number format: '{raw_phone}'. {last_error or ''}".strip()
    }

def normalize_phone_e164(
    raw_phone: Optional[str],
    default_region: Optional[str] = None
) -> Optional[str]:
    """
    Convenience helper to quickly normalize a phone number to E.164 or return None if invalid.
    """
    res = validate_and_normalize_phone(raw_phone, default_region)
    return res['e164'] if res['is_valid'] else None
