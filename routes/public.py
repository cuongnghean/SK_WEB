"""
Public Routes
Handles public taxpayer search with rate limiting, captcha, and data masking.
"""
import logging
import time
from datetime import datetime
from functools import wraps
from typing import Optional, Tuple

from flask import (
    Blueprint, render_template, request, jsonify, 
    redirect, url_for, flash, current_app
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from models import db
from models.search_log import SearchLog
from services.tax_service import TaxService
from utils.security import get_client_ip, mask_cccd, validate_mst_format, validate_cccd_format
from utils.captcha import validate_captcha, CaptchaGenerator

# Configure logging
logger = logging.getLogger(__name__)

# Create blueprint
public_bp = Blueprint('public', __name__)

# Initialize limiter (will be configured in app.py)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


def configure_limiter(app):
    """
    Configure rate limiter with the Flask app.
    
    Args:
        app: Flask application instance
    """
    limiter.init_app(app)


# =============================================================================
# PUBLIC SEARCH PAGE
# =============================================================================

@public_bp.route('/')
def index():
    """Redirect to public search page"""
    return redirect(url_for('public.search'))


@public_bp.route('/tra-cuu')
def search():
    """
    Public taxpayer search page.
    
    Displays search form with MST and CCCD search options.
    """
    return render_template('public_search.html')


@public_bp.route('/captcha')
def captcha():
    """
    Generate and return captcha image.
    
    Returns:
        PNG image response
    """
    generator = CaptchaGenerator()
    return generator.get_image_response()


# =============================================================================
# PUBLIC SEARCH API
# =============================================================================

@public_bp.route('/api/public/search')
@limiter.limit("20 per minute")  # Strict rate limit for public API
def api_public_search():
    """
    Public API for taxpayer search.
    
    Query Parameters:
    - mst: Tax Identification Number
    - cccd: Citizen ID
    - captcha: Captcha code
    
    Returns:
        JSON with search results (masked data)
    """
    start_time = time.time()
    client_ip = get_client_ip()
    user_agent = request.headers.get('User-Agent', '')[:500]
    
    try:
        # Get search parameters
        mst = request.args.get('mst', '').strip()
        cccd = request.args.get('cccd', '').strip()
        captcha_input = request.args.get('captcha', '').strip()
        
        # Determine search type
        search_type = None
        search_value = None
        
        if mst:
            search_type = 'mst'
            search_value = mst
            
            # Validate MST format
            if not validate_mst_format(mst):
                _log_search(client_ip, search_type, search_value, user_agent, 
                           response_time=time.time() - start_time, status='ERROR',
                           error_message='Invalid MST format')
                return jsonify({
                    'success': False,
                    'error': 'Mã số thuế không hợp lệ',
                    'message': 'Mã số thuế phải có 10 hoặc 13 chữ số.'
                }), 400
        
        elif cccd:
            search_type = 'cccd'
            search_value = cccd
            
            # Validate CCCD format
            if not validate_cccd_format(cccd):
                _log_search(client_ip, search_type, search_value, user_agent,
                           response_time=time.time() - start_time, status='ERROR',
                           error_message='Invalid CCCD format')
                return jsonify({
                    'success': False,
                    'error': 'Số định danh không hợp lệ',
                    'message': 'Số CCCD phải có 9 hoặc 12 chữ số.'
                }), 400
        
        else:
            _log_search(client_ip, 'UNKNOWN', '', user_agent,
                       response_time=time.time() - start_time, status='ERROR',
                       error_message='No search criteria provided')
            return jsonify({
                'success': False,
                'error': 'Thiếu thông tin tìm kiếm',
                'message': 'Vui lòng nhập Mã số thuế hoặc Số CCCD.'
            }), 400
        
        # Validate captcha
        is_captcha_valid, captcha_error = validate_captcha(captcha_input)
        if not is_captcha_valid:
            _log_search(client_ip, search_type, search_value, user_agent,
                       response_time=time.time() - start_time, status='ERROR',
                       error_message=f'Captcha failed: {captcha_error}')
            return jsonify({
                'success': False,
                'error': 'Mã xác thực không hợp lệ',
                'message': captcha_error or 'Vui lòng nhập đúng mã xác thực.'
            }), 400
        
        # Perform search
        results, status = TaxService.search_nnt(
            query=search_value,
            search_type=search_type,
            include_raw_data=False  # Always mask for public
        )
        
        response_time = time.time() - start_time
        
        if status == 'FOUND' and results:
            # Log successful search
            _log_search(client_ip, search_type, search_value, user_agent,
                       result_count=len(results), response_time=response_time,
                       status='SUCCESS')
            
            # Return masked results
            masked_results = [_mask_nnt_data(r) for r in results]
            
            return jsonify({
                'success': True,
                'found': True,
                'count': len(masked_results),
                'data': masked_results,
                'search_type': search_type.upper()
            }), 200
        
        else:
            # Log not found
            _log_search(client_ip, search_type, search_value, user_agent,
                       result_count=0, response_time=response_time,
                       status='NOT_FOUND')
            
            return jsonify({
                'success': True,
                'found': False,
                'count': 0,
                'message': 'Không tìm thấy thông tin người nộp thuế.',
                'search_type': search_type.upper()
            }), 200
    
    except Exception as e:
        logger.error(f"Public search error: {str(e)}")
        response_time = time.time() - start_time
        
        _log_search(client_ip, search_type or 'UNKNOWN', search_value or '', user_agent,
                   response_time=response_time, status='ERROR',
                   error_message=str(e))
        
        return jsonify({
            'success': False,
            'error': 'Lỗi hệ thống',
            'message': 'Đã xảy ra lỗi trong quá trình tra cứu. Vui lòng thử lại sau.'
        }), 500


def _mask_nnt_data(data: dict) -> dict:
    """
    Mask sensitive fields in NNT data for public display.
    
    Args:
        data: Full NNT data dictionary
    
    Returns:
        Masked data dictionary
    """
    # Create a copy to avoid modifying original
    masked = data.copy()
    
    # Always mask CCCD
    if 'CCCD' in masked and masked['CCCD']:
        masked['CCCD'] = mask_cccd(masked['CCCD'])
    
    # Never expose CMT in public
    if 'CMT' in masked:
        masked['CMT'] = None
    
    # Remove any other sensitive fields if present
    sensitive_fields = ['cmt', 'chung_minh_thu', 'so_cmnd']
    for field in sensitive_fields:
        if field in masked:
            masked[field] = None
    
    # Mask obligations
    if 'obligations' in masked and masked['obligations']:
        masked['obligations'] = [
            {
                'LOAI_NO': obl.get('LOAI_NO'),
                'NO_TAM_TINH': obl.get('NO_TAM_TINH'),
                'UPDATED_AT': obl.get('UPDATED_AT')
            }
            for obl in masked['obligations']
        ]
    
    return masked


def _log_search(ip_address: str, search_type: str, search_value: str,
                user_agent: str, result_count: int = 0,
                response_time: float = 0, status: str = 'SUCCESS',
                error_message: Optional[str] = None) -> None:
    """
    Log search query to database.
    
    Args:
        ip_address: Client IP
        search_type: Type of search (MST, CCCD)
        search_value: Searched value (masked for CCCD)
        user_agent: Browser user agent
        result_count: Number of results
        response_time: Response time in seconds
        status: Search status
        error_message: Error details if failed
    """
    try:
        # Mask CCCD in log
        logged_value = search_value
        if search_type == 'cccd' and search_value:
            logged_value = mask_cccd(search_value)
        
        SearchLog.log_search(
            ip_address=ip_address,
            search_type=search_type,
            search_value=logged_value,
            user_agent=user_agent,
            result_count=result_count,
            response_time=response_time * 1000,  # Convert to ms
            status=status,
            error_message=error_message
        )
    except Exception as e:
        # Silently fail - don't disrupt user experience
        logger.warning(f"Failed to log search: {str(e)}")


# =============================================================================
# RATE LIMIT EXCEEDED HANDLER
# =============================================================================

@public_bp.errorhandler(429)
def ratelimit_handler(e):
    """
    Handle rate limit exceeded error.
    
    Args:
        e: Rate limit exception
    
    Returns:
        JSON error response
    """
    logger.warning(f"Rate limit exceeded for IP {get_client_ip()}")
    
    return jsonify({
        'success': False,
        'error': 'Quá nhiều yêu cầu',
        'message': 'Bạn đã thực hiện quá nhiều yêu cầu. Vui lòng chờ và thử lại sau.',
        'retry_after': 60
    }), 429


# =============================================================================
# HEALTH CHECK
# =============================================================================

@public_bp.route('/health')
def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        JSON with health status
    """
    try:
        # Check database connection
        db.session.execute(db.text('SELECT 1'))
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503


# =============================================================================
# STATIC PAGES
# =============================================================================

@public_bp.route('/huong-dan')
def guide():
    """
    Display user guide page.
    """
    return render_template('guide.html')


@public_bp.route('/gioi-thieu')
def about():
    """
    Display about page.
    """
    return render_template('about.html')


@public_bp.route('/lien-he')
def contact():
    """
    Display contact page.
    """
    return render_template('contact.html')
