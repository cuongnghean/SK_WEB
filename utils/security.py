"""
Security Utilities
Provides data masking, IP detection, and file security functions.
"""
import re
import os
from functools import wraps
from typing import Optional, Callable, Any
from flask import request, jsonify, current_app


def mask_cccd(cccd_str: str) -> str:
    """
    Mask CCCD (Citizen ID) number for public display.
    Only shows last 4 characters, masks the rest.
    
    Args:
        cccd_str: Full CCCD number
    
    Returns:
        Masked CCCD string (e.g., '********1234')
    
    Examples:
        >>> mask_cccd('040093001234')
        '********1234'
        >>> mask_cccd('123456789')
        '*****6789'
    """
    if not cccd_str or not isinstance(cccd_str, str):
        return ''
    
    # Normalize: remove spaces, dashes, and non-alphanumeric
    cccd_clean = ''.join(c for c in str(cccd_str).strip() if c.isalnum())
    
    if len(cccd_clean) <= 4:
        return '*' * len(cccd_clean)
    
    # Keep only last 4 characters, mask the rest
    visible_count = 4
    masked_length = len(cccd_clean) - visible_count
    
    return '*' * masked_length + cccd_clean[-visible_count:]


def mask_cmt(cmt_str: str) -> str:
    """
    Mask CMT (Old ID) number for public display.
    Same logic as CCCD but returns empty for public safety.
    
    Args:
        cmt_str: Full CMT number
    
    Returns:
        Masked CMT string (always masked for security)
    """
    if not cmt_str or not isinstance(cmt_str, str):
        return ''
    
    # CMT is never shown in public views
    cmt_clean = ''.join(c for c in str(cmt_str).strip() if c.isalnum())
    
    if len(cmt_clean) <= 4:
        return '*' * len(cmt_clean)
    
    visible_count = 4
    masked_length = len(cmt_clean) - visible_count
    
    return '*' * masked_length + cmt_clean[-visible_count:]


def mask_phone(phone_str: str) -> str:
    """
    Mask phone number for public display.
    
    Args:
        phone_str: Full phone number
    
    Returns:
        Masked phone string
    """
    if not phone_str or not isinstance(phone_str, str):
        return ''
    
    phone_clean = ''.join(c for c in str(phone_str).strip() if c.isalnum())
    
    if len(phone_clean) <= 4:
        return '*' * len(phone_clean)
    
    visible_count = 4
    masked_length = len(phone_clean) - visible_count
    
    return '*' * masked_length + phone_clean[-visible_count:]


def mask_email(email: str) -> str:
    """
    Mask email address for public display.
    
    Args:
        email: Full email address
    
    Returns:
        Masked email string
    """
    if not email or '@' not in str(email):
        return ''
    
    parts = str(email).split('@')
    if len(parts) != 2:
        return ''
    
    username = parts[0]
    domain = parts[1]
    
    if len(username) <= 2:
        masked_username = '*' * len(username)
    else:
        masked_username = username[0] + '*' * (len(username) - 2) + username[-1]
    
    return f"{masked_username}@{domain}"


def get_client_ip() -> str:
    """
    Get client IP address from request, handling proxy headers.
    
    Returns:
        Client IP address string
    """
    # Check for forwarded headers (when behind proxy/load balancer)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(',')[0].strip()
    
    # Check other common proxy headers
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()
    
    # Fall back to remote_addr
    return request.remote_addr or '0.0.0.0'


def validate_mst_format(mst: str) -> bool:
    """
    Validate Vietnamese Tax Identification Number format.
    
    Args:
        mst: MST string to validate
    
    Returns:
        True if valid format
    """
    if not mst or not isinstance(mst, str):
        return False
    
    # MST should be 10 or 13 digits (common formats)
    # Remove any non-digit characters
    mst_clean = ''.join(c for c in mst.strip() if c.isdigit())
    
    # Valid MST lengths: 10 (simple) or 13 (formatted with dashes)
    return len(mst_clean) == 10 or len(mst_clean) == 13


def validate_cccd_format(cccd: str) -> bool:
    """
    Validate Vietnamese Citizen ID (CCCD) format.
    
    Args:
        cccd: CCCD string to validate
    
    Returns:
        True if valid format
    """
    if not cccd or not isinstance(cccd, str):
        return False
    
    # Remove spaces and dashes
    cccd_clean = ''.join(c for c in cccd.strip() if c.isdigit())
    
    # CCCD should be 9 or 12 digits
    return len(cccd_clean) == 9 or len(cccd_clean) == 12


def validate_password_strength(password: str) -> tuple:
    """
    Validate password strength.
    
    Args:
        password: Password string to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if len(password) > 128:
        return False, "Password is too long (max 128 characters)"
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    
    if not (has_upper and has_lower and has_digit):
        return False, "Password must contain uppercase, lowercase, and digit"
    
    return True, ""


def allowed_file(filename: str, allowed_extensions: Optional[set] = None) -> bool:
    """
    Check if file extension is allowed.
    
    Args:
        filename: Original filename
        allowed_extensions: Set of allowed extensions (defaults to config)
    
    Returns:
        True if file extension is allowed
    """
    if not filename:
        return False
    
    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'xlsx', 'xls'})
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    
    Args:
        filename: Original filename
    
    Returns:
        Sanitized filename
    """
    if not filename:
        return 'unnamed_file'
    
    # Remove path separators
    filename = os.path.basename(filename)
    
    # Replace potentially dangerous characters
    filename = re.sub(r'[^\w\s\-\.]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    
    return filename


def require_role(*allowed_roles: str) -> Callable:
    """
    Decorator to require specific roles for a route.
    
    Args:
        allowed_roles: Variable number of allowed role strings
    
    Returns:
        Decorator function
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            from flask_login import current_user
            
            # Check if user is authenticated
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'error': 'Authentication required'}), 401
                from flask import redirect, url_for
                return redirect(url_for('auth.login'))
            
            # Check if user has required role
            if current_user.role not in allowed_roles:
                if request.is_json:
                    return jsonify({'error': 'Insufficient permissions'}), 403
                from flask import abort
                return abort(403)
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def admin_required(f: Callable) -> Callable:
    """
    Decorator to require admin role for a route.
    
    Args:
        f: Function to decorate
    
    Returns:
        Decorated function
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        from flask_login import current_user
        
        if not current_user.is_authenticated:
            if request.is_json:
                return jsonify({'error': 'Authentication required'}), 401
            from flask import redirect, url_for
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            if request.is_json:
                return jsonify({'error': 'Admin access required'}), 403
            from flask import abort
            return abort(403)
        
        return f(*args, **kwargs)
    
    return decorated_function


def rate_limit_message(limit_name: str) -> dict:
    """
    Generate a rate limit exceeded response message.
    
    Args:
        limit_name: Name of the rate limit
    
    Returns:
        JSON response dictionary
    """
    return {
        'error': 'Rate limit exceeded',
        'message': f'Too many requests. Please try again later.',
        'limit': limit_name
    }


def format_currency(amount: float, currency: str = 'VND') -> str:
    """
    Format amount as currency string.
    
    Args:
        amount: Numeric amount
        currency: Currency code
    
    Returns:
        Formatted currency string (e.g., '1,234,567 VND')
    """
    if amount is None:
        return '0 VND'
    
    if currency == 'VND':
        return f"{int(amount):,}".replace(',', '.') + ' VND'
    
    return f"{amount:,.2f} {currency}"


def parse_currency(currency_str: str) -> float:
    """
    Parse currency string to float.
    
    Args:
        currency_str: Currency string (e.g., '1,234,567 VND')
    
    Returns:
        Parsed float value
    """
    if not currency_str:
        return 0.0
    
    # Remove currency symbols and thousand separators
    cleaned = currency_str.replace('VND', '').replace('₫', '').replace('.', '').replace(',', '').strip()
    
    try:
        return float(cleaned)
    except ValueError:
        return 0.0
