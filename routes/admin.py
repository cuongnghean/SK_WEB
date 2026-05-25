"""
Admin Routes
Handles administrative functions including dashboard, import, and user management.
"""
import os
import logging
import traceback
from datetime import datetime
from typing import Optional

from flask import (
    Blueprint, render_template, request, jsonify, 
    redirect, url_for, flash, send_file, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import db
from models.nnt import NNT, LOAI_NO, TT_NO
from models.users import User
from models.import_history import ImportHistory
from models.no_history import NO_HISTORY
from models.search_log import SearchLog
from services.excel_service import ExcelService
from services.tax_service import TaxService
from utils.security import (
    admin_required, get_client_ip, allowed_file, 
    sanitize_filename, format_currency
)
from utils.captcha import CaptchaGenerator

# Configure logging
logger = logging.getLogger(__name__)

# Create blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# =============================================================================
# DASHBOARD ROUTES
# =============================================================================

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """
    Admin dashboard with system overview.
    
    Displays:
    - Total NNT count
    - Total debt amount
    - Recent imports
    - Search statistics
    """
    try:
        # Get dashboard statistics
        stats = TaxService.get_dashboard_stats()
        
        # Get top debtors
        top_debtors = TaxService.get_top_debtors(limit=10)
        
        # Get recent imports
        recent_imports = ImportHistory.query\
            .order_by(ImportHistory.created_at.desc())\
            .limit(5)\
            .all()
        
        # Get recent changes
        recent_changes = TaxService.get_recent_changes(limit=10)
        
        return render_template(
            'admin_dashboard.html',
            stats=stats,
            top_debtors=top_debtors,
            recent_imports=[imp.to_dict() for imp in recent_imports],
            recent_changes=recent_changes
        )
        
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {str(e)}")
        flash('Đã xảy ra lỗi khi tải trang. Vui lòng thử lại.', 'error')
        return render_template('admin_dashboard.html', stats={}, top_debtors=[], recent_imports=[])


@admin_bp.route('/api/dashboard')
@login_required
@admin_required
def api_dashboard():
    """
    API endpoint for dashboard data (AJAX).
    
    Returns:
        JSON with dashboard statistics
    """
    try:
        stats = TaxService.get_dashboard_stats()
        
        # Format currency for JSON
        stats['total_debt_formatted'] = format_currency(stats.get('total_debt', 0))
        
        # Get chart data
        chart_data = {
            'debt_status': stats.get('status_breakdown', {'CO_NO': 0, 'KHONG_NO': 0}),
            'active_status': stats.get('active_breakdown', {}),
            'debt_types': stats.get('debt_types', [])
        }
        
        return jsonify({
            'success': True,
            'stats': stats,
            'chart_data': chart_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting dashboard API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# IMPORT ROUTES
# =============================================================================

@admin_bp.route('/import')
@login_required
@admin_required
def import_page():
    """
    Display import page for Excel file uploads.
    """
    try:
        # Get debt types for dropdown
        debt_types = TaxService.get_debt_types()
        
        # Get import history
        import_history = ImportHistory.query\
            .order_by(ImportHistory.created_at.desc())\
            .limit(20)\
            .all()
        
        return render_template(
            'admin_import.html',
            debt_types=debt_types,
            import_history=[imp.to_dict() for imp in import_history]
        )
        
    except Exception as e:
        logger.error(f"Error loading import page: {str(e)}")
        flash('Đã xảy ra lỗi khi tải trang. Vui lòng thử lại.', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/api/import', methods=['POST'])
@login_required
@admin_required
def api_import():
    """
    Handle Excel file import.
    
    Accepts:
    - multipart/form-data with 'file' field
    
    Returns:
        JSON with import results
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy tệp tin.'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'Vui lòng chọn tệp tin.'
            }), 400
        
        # Validate file extension
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'Định dạng tệp tin không được hỗ trợ. Vui lòng sử dụng .xlsx hoặc .xls'
            }), 400
        
        # Create import history record
        import_record = ImportHistory(
            file_name=sanitize_filename(file.filename),
            file_size=0,  # Will update after reading
            status='PENDING',
            import_by=current_user.id
        )
        db.session.add(import_record)
        db.session.commit()
        
        # Read file and process
        file_bytes = file.read()
        import_record.file_size = len(file_bytes)
        db.session.commit()
        
        # Initialize Excel service
        excel_service = ExcelService(
            import_history_id=import_record.id,
            user_id=current_user.id
        )
        
        # Start import
        start_time = datetime.utcnow()
        results = excel_service.import_from_bytes(file_bytes, file.filename)
        end_time = datetime.utcnow()
        
        # Update import record
        import_time = (end_time - start_time).total_seconds()
        import_record.import_time = import_time
        import_record.total_rows = results['stats']['total_rows']
        import_record.success_rows = results['stats']['success_rows']
        import_record.failed_rows = results['stats']['failed_rows']
        
        if results['errors']:
            import_record.error_details = str(results['errors'][:50])  # Limit size
        
        import_record.status = 'COMPLETED' if results['success'] else 'PARTIAL'
        import_record.completed_at = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"Import completed: {results['stats']}")
        
        return jsonify({
            'success': True,
            'message': f'Đã nhập {results["stats"]["success_rows"]} bản ghi.',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Import error: {str(e)}\n{traceback.format_exc()}")
        
        # Update import record if exists
        if 'import_record' in locals():
            import_record.status = 'FAILED'
            import_record.error_details = str(e)
            import_record.completed_at = datetime.utcnow()
            db.session.commit()
        
        return jsonify({
            'success': False,
            'error': f'Đã xảy ra lỗi khi nhập dữ liệu: {str(e)}'
        }), 500


@admin_bp.route('/api/import/<int:import_id>')
@login_required
@admin_required
def api_import_status(import_id):
    """
    Get status of a specific import.
    
    Args:
        import_id: Import history record ID
    
    Returns:
        JSON with import details
    """
    try:
        import_record = ImportHistory.query.get(import_id)
        
        if not import_record:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy bản ghi import.'
            }), 404
        
        return jsonify({
            'success': True,
            'import': import_record.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting import status: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/import/<int:import_id>/delete', methods=['DELETE'])
@login_required
@admin_required
def api_import_delete(import_id):
    """
    Delete an import history record.
    
    Args:
        import_id: Import history record ID
    
    Returns:
        JSON with deletion result
    """
    try:
        import_record = ImportHistory.query.get(import_id)
        
        if not import_record:
            return jsonify({
                'success': False,
                'error': 'Không tìm thạy bản ghi.'
            }), 404
        
        db.session.delete(import_record)
        db.session.commit()
        
        logger.info(f"Import record {import_id} deleted by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Đã xóa bản ghi import.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting import: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# NNT MANAGEMENT ROUTES
# =============================================================================

@admin_bp.route('/nnt')
@login_required
@admin_required
def nnt_list():
    """
    Display paginated list of taxpayers.
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        status_filter = request.args.get('status')
        search_query = request.args.get('q', '').strip()
        sort_by = request.args.get('sort', 'MST')
        sort_order = request.args.get('order', 'asc')
        
        # Validate pagination
        per_page = min(per_page, 100)  # Max 100 per page
        
        result = TaxService.get_nnt_list(
            page=page,
            per_page=per_page,
            status_filter=status_filter,
            search_query=search_query if search_query else None,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return render_template(
            'admin_nnt_list.html',
            nnt_list=result['items'],
            pagination=result,
            filters={
                'status': status_filter,
                'search': search_query,
                'sort': sort_by,
                'order': sort_order
            }
        )
        
    except Exception as e:
        logger.error(f"Error loading NNT list: {str(e)}")
        flash('Đã xảy ra lỗi khi tải danh sách. Vui lòng thử lại.', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/api/nnt/<mst>')
@login_required
@admin_required
def api_nnt_detail(mst):
    """
    Get detailed taxpayer information (admin view - raw data).
    
    Args:
        mst: Taxpayer MST
    
    Returns:
        JSON with full taxpayer data
    """
    try:
        result = TaxService.search_by_mst(mst, include_raw_data=True)
        
        if not result:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy người nộp thuế.'
            }), 404
        
        return jsonify({
            'success': True,
            'nnt': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting NNT detail: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/nnt/<mst>', methods=['PUT'])
@login_required
@admin_required
def api_nnt_update(mst):
    """
    Update taxpayer information.
    
    Args:
        mst: Taxpayer MST
    
    Returns:
        JSON with update result
    """
    try:
        nnt = NNT.query.get(mst)
        
        if not nnt:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy người nộp thuế.'
            }), 404
        
        data = request.get_json()
        
        # Update fields
        if 'HO_TEN' in data:
            nnt.HO_TEN = data['HO_TEN']
        if 'DIA_CHI' in data:
            nnt.DIA_CHI = data['DIA_CHI']
        if 'CCCD' in data:
            nnt.CCCD = data['CCCD']
        if 'CMT' in data:
            nnt.CMT = data['CMT']
        if 'TRANG_THAI_HD' in data:
            nnt.TRANG_THAI_HD = data['TRANG_THAI_HD']
        if 'TRANG_THAI_NO' in data:
            nnt.TRANG_THAI_NO = data['TRANG_THAI_NO']
        
        nnt.LAST_SYNC = datetime.utcnow()
        db.session.commit()
        
        logger.info(f"NNT {mst} updated by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Đã cập nhật thông tin.',
            'nnt': nnt.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating NNT: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/nnt/<mst>', methods=['DELETE'])
@login_required
@admin_required
def api_nnt_delete(mst):
    """
    Delete taxpayer (admin only).
    
    Args:
        mst: Taxpayer MST
    
    Returns:
        JSON with deletion result
    """
    try:
        nnt = NNT.query.get(mst)
        
        if not nnt:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy người nộp thuế.'
            }), 404
        
        # Store for logging
        ho_ten = nnt.HO_TEN
        
        db.session.delete(nnt)
        db.session.commit()
        
        logger.info(f"NNT {mst} ({ho_ten}) deleted by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'Đã xóa người nộp thuế {mst}.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting NNT: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# USER MANAGEMENT ROUTES
# =============================================================================

@admin_bp.route('/users')
@login_required
@admin_required
def user_list():
    """
    Display list of all users.
    """
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin_user_list.html', users=users)
        
    except Exception as e:
        logger.error(f"Error loading user list: {str(e)}")
        flash('Đã xảy ra lỗi khi tải danh sách người dùng.', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/api/users', methods=['POST'])
@login_required
@admin_required
def api_create_user():
    """
    Create a new user (admin only).
    
    Returns:
        JSON with creation result
    """
    try:
        data = request.get_json()
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        full_name = data.get('full_name', '').strip()
        role = data.get('role', 'USER')
        
        # Validate input
        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Tên đăng nhập và mật khẩu là bắt buộc.'
            }), 400
        
        # Check if username exists
        if User.find_by_username(username):
            return jsonify({
                'success': False,
                'error': 'Tên đăng nhập đã tồn tại.'
            }), 400
        
        # Check if email exists
        if email and User.find_by_email(email):
            return jsonify({
                'success': False,
                'error': 'Email đã được sử dụng.'
            }), 400
        
        # Create user
        user = User(
            username=username,
            email=email if email else None,
            full_name=full_name if full_name else None,
            role=role if role in ['ADMIN', 'USER'] else 'USER'
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"User {username} created by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'Đã tạo tài khoản "{username}".',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def api_update_user(user_id):
    """
    Update user information.
    
    Args:
        user_id: User ID
    
    Returns:
        JSON with update result
    """
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy người dùng.'
            }), 404
        
        data = request.get_json()
        
        if 'email' in data:
            user.email = data['email']
        if 'full_name' in data:
            user.full_name = data['full_name']
        if 'role' in data:
            if data['role'] in ['ADMIN', 'USER']:
                user.role = data['role']
        if 'is_active' in data:
            user.is_active = bool(data['is_active'])
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        
        db.session.commit()
        
        logger.info(f"User {user.username} updated by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Đã cập nhật thông tin người dùng.',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def api_delete_user(user_id):
    """
    Delete a user (cannot delete self).
    
    Args:
        user_id: User ID
    
    Returns:
        JSON with deletion result
    """
    try:
        # Cannot delete self
        if user_id == current_user.id:
            return jsonify({
                'success': False,
                'error': 'Bạn không thể xóa tài khoản của chính mình.'
            }), 400
        
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy người dùng.'
            }), 404
        
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        logger.info(f"User {username} deleted by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'Đã xóa tài khoản "{username}".'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# DEBT TYPE MANAGEMENT
# =============================================================================

@admin_bp.route('/api/debt-types', methods=['GET'])
@login_required
@admin_required
def api_get_debt_types():
    """
    Get all debt types.
    
    Returns:
        JSON with debt types list
    """
    try:
        debt_types = TaxService.get_debt_types()
        return jsonify({
            'success': True,
            'debt_types': debt_types
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting debt types: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/debt-types', methods=['POST'])
@login_required
@admin_required
def api_create_debt_type():
    """
    Create a new debt type.
    
    Returns:
        JSON with creation result
    """
    try:
        data = request.get_json()
        
        loai_no = data.get('loai_no', '').strip()
        ten_no = data.get('ten_no', '').strip()
        mo_ta = data.get('mo_ta', '').strip()
        
        if not loai_no or not ten_no:
            return jsonify({
                'success': False,
                'error': 'Mã loại nợ và tên loại nợ là bắt buộc.'
            }), 400
        
        debt_type = TaxService.create_debt_type(loai_no, ten_no, mo_ta if mo_ta else None)
        
        if debt_type:
            logger.info(f"Debt type {loai_no} created by {current_user.username}")
            return jsonify({
                'success': True,
                'message': 'Đã tạo loại nợ mới.',
                'debt_type': debt_type.to_dict()
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Không thể tạo loại nợ.'
            }), 500
            
    except Exception as e:
        logger.error(f"Error creating debt type: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# STATISTICS & REPORTS
# =============================================================================

@admin_bp.route('/api/top-debtors')
@login_required
@admin_required
def api_top_debtors():
    """
    Get top debtors for charts/tables.
    
    Query params:
    - limit: Number of results (default 10)
    
    Returns:
        JSON with top debtors list
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = min(limit, 100)
        
        top_debtors = TaxService.get_top_debtors(limit=limit)
        
        return jsonify({
            'success': True,
            'top_debtors': top_debtors
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting top debtors: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/monthly-trend')
@login_required
@admin_required
def api_monthly_trend():
    """
    Get monthly debt trend data.
    
    Query params:
    - months: Number of months (default 12)
    
    Returns:
        JSON with trend data
    """
    try:
        months = request.args.get('months', 12, type=int)
        months = min(months, 24)
        
        trend = TaxService.get_monthly_debt_trend(months=months)
        
        return jsonify({
            'success': True,
            'trend': trend
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting monthly trend: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/api/recent-changes')
@login_required
@admin_required
def api_recent_changes():
    """
    Get recent obligation changes.
    
    Query params:
    - limit: Number of results (default 20)
    
    Returns:
        JSON with changes list
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        limit = min(limit, 100)
        
        changes = TaxService.get_recent_changes(limit=limit)
        
        return jsonify({
            'success': True,
            'changes': changes
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting recent changes: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# SEARCH LOGS
# =============================================================================

@admin_bp.route('/search-logs')
@login_required
@admin_required
def search_logs():
    """
    Display search logs.
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        logs = SearchLog.query\
            .order_by(SearchLog.CREATED_AT.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        return render_template(
            'admin_search_logs.html',
            logs=logs.items,
            pagination=logs
        )
        
    except Exception as e:
        logger.error(f"Error loading search logs: {str(e)}")
        flash('Đã xảy ra lỗi khi tải nhật ký tra cứu.', 'error')
        return redirect(url_for('admin.dashboard'))
