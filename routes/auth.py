"""
Authentication Routes
Handles user login, logout, and session management.
"""
import logging
from datetime import datetime
from functools import wraps
from typing import Optional

from flask import (
    render_template, redirect, url_for, request, flash,
    jsonify, session, current_app
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required,
    current_user
)

from models import db
from models.users import User
from utils.security import validate_password_strength

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Flask-Login
login_manager = LoginManager()


def init_login_manager(app):
    """
    Initialize Flask-Login with the application.
    
    Args:
        app: Flask application instance
    """
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Vui lòng đăng nhập để truy cập trang này.'
    login_manager.login_message_category = 'warning'
    login_manager.session_protection = 'strong'


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """
    Load user by ID for Flask-Login session management.
    
    Args:
        user_id: User ID string from session
    
    Returns:
        User instance or None
    """
    try:
        return User.query.get(int(user_id))
    except (ValueError, TypeError):
        return None


@login_manager.unauthorized_handler
def unauthorized():
    """
    Handle unauthorized access attempts.
    
    Returns:
        JSON response or redirect to login
    """
    if request.is_json:
        return jsonify({
            'success': False,
            'error': 'Unauthorized',
            'message': 'Vui lòng đăng nhập để truy cập trang này.'
        }), 401
    
    flash('Vui lòng đăng nhập để truy cập trang này.', 'warning')
    return redirect(url_for('auth.login'))


# =============================================================================
# LOGIN ROUTE
# =============================================================================



# This is handled by the import in routes/__init__.py
# The actual routes are registered in auth_bp below

def login():
    """
    Handle user login.
    
    Methods: GET, POST
    
    GET: Display login form
    POST: Process login credentials
    """
    # Redirect if already logged in
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        try:
            # Get form data
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            remember_me = request.form.get('remember_me', False)
            
            # Validate input
            if not username or not password:
                flash('Vui lòng nhập tên đăng nhập và mật khẩu.', 'error')
                return render_template('login.html')
            
            # Find user
            user = User.find_by_username(username)
            
            if not user:
                logger.warning(f"Login attempt with unknown username: {username}")
                flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'error')
                return render_template('login.html'), 401
            
            # Check if user is active
            if not user.is_active:
                logger.warning(f"Login attempt for inactive user: {username}")
                flash('Tài khoản đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên.', 'error')
                return render_template('login.html'), 403
            
            # Verify password
            if not user.check_password(password):
                logger.warning(f"Failed login attempt for user: {username}")
                flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'error')
                return render_template('login.html'), 401
            
            # Check if this is JSON request
            if request.is_json:
                # Login successful
                login_user(user, remember=remember_me)
                user.update_last_login()
                
                logger.info(f"User logged in: {username}")
                
                # Determine redirect URL
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    redirect_url = next_page
                elif user.is_admin:
                    redirect_url = url_for('admin.dashboard')
                else:
                    redirect_url = url_for('user.dashboard')
                
                return jsonify({
                    'success': True,
                    'message': 'Đăng nhập thành công.',
                    'redirect': redirect_url,
                    'user': user.to_dict()
                }), 200
            
            # HTML form login
            login_user(user, remember=remember_me)
            user.update_last_login()
            
            logger.info(f"User logged in: {username}")
            flash('Đăng nhập thành công!', 'success')
            
            # Redirect to next page or dashboard
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('user.dashboard'))
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            flash('Đã xảy ra lỗi trong quá trình đăng nhập. Vui lòng thử lại.', 'error')
            return render_template('login.html'), 500
    
    # GET request - show login form
    return render_template('login.html')


def logout():
    """
    Handle user logout.
    
    Methods: GET, POST
    """
    if current_user.is_authenticated:
        username = current_user.username
        logger.info(f"User logging out: {username}")
    
    logout_user()
    flash('Đã đăng xuất thành công.', 'success')
    
    if request.is_json:
        return jsonify({
            'success': True,
            'message': 'Đăng xuất thành công.'
        }), 200
    
    return redirect(url_for('public.search'))


def register():
    """
    Handle user registration (admin only can create users).
    
    Methods: GET, POST
    """
    # Only admins can register new users
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('Bạn không có quyền thực hiện chức năng này.', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            # Get form data
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            full_name = request.form.get('full_name', '').strip()
            role = request.form.get('role', 'USER')
            
            # Validate input
            if not username or not password:
                flash('Vui lòng điền đầy đủ thông tin bắt buộc.', 'error')
                return render_template('register.html'), 400
            
            # Validate password strength
            is_valid, error_msg = validate_password_strength(password)
            if not is_valid:
                flash(error_msg, 'error')
                return render_template('register.html'), 400
            
            # Check password confirmation
            if password != confirm_password:
                flash('Mật khẩu xác nhận không khớp.', 'error')
                return render_template('register.html'), 400
            
            # Check if username exists
            if User.find_by_username(username):
                flash('Tên đăng nhập đã tồn tại.', 'error')
                return render_template('register.html'), 400
            
            # Check if email exists
            if email and User.find_by_email(email):
                flash('Email đã được sử dụng.', 'error')
                return render_template('register.html'), 400
            
            # Validate role
            if role not in ['ADMIN', 'USER']:
                role = 'USER'
            
            # Create user
            user = User(
                username=username,
                email=email if email else None,
                full_name=full_name if full_name else None,
                role=role
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            logger.info(f"New user registered: {username} by {current_user.username}")
            flash(f'Đã tạo tài khoản "{username}" thành công.', 'success')
            
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {str(e)}")
            flash('Đã xảy ra lỗi khi tạo tài khoản. Vui lòng thử lại.', 'error')
            return render_template('register.html'), 500
    
    # GET request - show registration form
    return render_template('register.html')


def change_password():
    """
    Handle password change for logged-in users.
    
    Methods: GET, POST
    """
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        try:
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Validate current password
            if not current_user.check_password(current_password):
                flash('Mật khẩu hiện tại không đúng.', 'error')
                return render_template('change_password.html'), 400
            
            # Validate new password
            is_valid, error_msg = validate_password_strength(new_password)
            if not is_valid:
                flash(error_msg, 'error')
                return render_template('change_password.html'), 400
            
            # Check confirmation
            if new_password != confirm_password:
                flash('Mật khẩu xác nhận không khớp.', 'error')
                return render_template('change_password.html'), 400
            
            # Check if same as current
            if current_user.check_password(new_password):
                flash('Mật khẩu mới phải khác mật khẩu hiện tại.', 'error')
                return render_template('change_password.html'), 400
            
            # Update password
            current_user.set_password(new_password)
            db.session.commit()
            
            logger.info(f"Password changed for user: {current_user.username}")
            flash('Đã đổi mật khẩu thành công.', 'success')
            
            return redirect(url_for('user.profile'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Password change error: {str(e)}")
            flash('Đã xảy ra lỗi. Vui lòng thử lại.', 'error')
            return render_template('change_password.html'), 500
    
    # GET request - show form
    return render_template('change_password.html')


def reset_password_request():
    """
    Handle password reset request (send email).
    Note: In production, implement email sending functionality.
    
    Methods: GET, POST
    """
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip()
            
            if not email:
                flash('Vui lòng nhập địa chỉ email.', 'error')
                return render_template('reset_password_request.html'), 400
            
            user = User.find_by_email(email)
            
            if user and user.is_active:
                # In production, send password reset email
                # For now, just log and show success message
                logger.info(f"Password reset requested for email: {email}")
                flash('Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi.', 'success')
            else:
                # Don't reveal if email exists for security
                flash('Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi.', 'success')
            
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            logger.error(f"Password reset request error: {str(e)}")
            flash('Đã xảy ra lỗi. Vui lòng thử lại.', 'error')
            return render_template('reset_password_request.html'), 500
    
    return render_template('reset_password_request.html')


# =============================================================================
# ROUTE REGISTRATION
# =============================================================================

def register_auth_routes(auth_bp):
    """
    Register all authentication routes with the blueprint.
    
    Args:
        auth_bp: Auth Blueprint instance
    """
    auth_bp.add_url_rule('/login', 'login', login, methods=['GET', 'POST'])
    auth_bp.add_url_rule('/logout', 'logout', logout, methods=['GET', 'POST'])
    auth_bp.add_url_rule('/register', 'register', register, methods=['GET', 'POST'])
    auth_bp.add_url_rule('/change-password', 'change_password', change_password, methods=['GET', 'POST'])
    auth_bp.add_url_rule('/reset-password', 'reset_password_request', reset_password_request, methods=['GET', 'POST'])
