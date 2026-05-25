"""
User Routes
Handles regular user dashboard and profile management.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from flask import (
    Blueprint, render_template, request, jsonify,
    redirect, url_for, flash
)
from flask_login import login_required, current_user

from models import db
from models.nnt import NNT
from models.search_log import SearchLog
from services.tax_service import TaxService
from utils.security import mask_cccd

# Configure logging
logger = logging.getLogger(__name__)

# Create blueprint
user_bp = Blueprint('user', __name__, url_prefix='/user')


# =============================================================================
# USER DASHBOARD
# =============================================================================

@user_bp.route('/')
@user_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Regular user dashboard with read-only overview.
    
    Displays:
    - Basic statistics
    - Recent search activity
    - Quick search
    """
    try:
        # Get basic statistics
        total_nnt = db.session.query(NNT).count()
        
        # Get debt status
        co_no_count = db.session.query(NNT).filter(
            NNT.TRANG_THAI_NO == 'CO_NO'
        ).count()
        
        khong_no_count = db.session.query(NNT).filter(
            NNT.TRANG_THAI_NO == 'KHONG_NO'
        ).count()
        
        # Get recent searches (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_searches = SearchLog.query.filter(
            SearchLog.CREATED_AT >= week_ago
        ).order_by(SearchLog.CREATED_AT.desc()).limit(20).all()
        
        # Get user's last login info
        last_login = current_user.last_login
        
        return render_template(
            'user_dashboard.html',
            total_nnt=total_nnt,
            co_no_count=co_no_count,
            khong_no_count=khong_no_count,
            recent_searches=recent_searches,
            last_login=last_login
        )
        
    except Exception as e:
        logger.error(f"Error loading user dashboard: {str(e)}")
        flash('Đã xảy ra lỗi khi tải trang. Vui lòng thử lại.', 'error')
        return render_template('user_dashboard.html', 
                             total_nnt=0, co_no_count=0, khong_no_count=0,
                             recent_searches=[], last_login=None)


@user_bp.route('/api/dashboard')
@login_required
def api_dashboard():
    """
    API endpoint for dashboard data (AJAX).
    
    Returns:
        JSON with dashboard statistics
    """
    try:
        # Get basic stats
        total_nnt = db.session.query(NNT).count()
        
        co_no = db.session.query(NNT).filter(
            NNT.TRANG_THAI_NO == 'CO_NO'
        ).count()
        
        khong_no = db.session.query(NNT).filter(
            NNT.TRANG_THAI_NO == 'KHONG_NO'
        ).count()
        
        # Get total debt
        from models.nnt import TT_NO
        from sqlalchemy import func
        
        total_debt = db.session.query(
            func.sum(TT_NO.NO_TAM_TINH)
        ).scalar() or 0.0
        
        # Get top debtors
        top_debtors = TaxService.get_top_debtors(limit=5)
        
        # Format for display
        for debtor in top_debtors:
            debtor['CCCD_masked'] = mask_cccd(
                debtor.get('CCCD', '')
            ) if debtor.get('CCCD') else 'N/A'
        
        return jsonify({
            'success': True,
            'stats': {
                'total_nnt': total_nnt,
                'co_no': co_no,
                'khong_no': khong_no,
                'total_debt': float(total_debt),
                'total_debt_formatted': f"{int(total_debt):,}".replace(',', '.') + ' VND'
            },
            'top_debtors': top_debtors[:5]
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting dashboard API: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# PROFILE MANAGEMENT
# =============================================================================

@user_bp.route('/profile')
@login_required
def profile():
    """
    Display user profile page.
    """
    return render_template('user_profile.html')


@user_bp.route('/api/profile')
@login_required
def api_profile():
    """
    Get current user's profile data.
    
    Returns:
        JSON with user profile
    """
    try:
        return jsonify({
            'success': True,
            'user': current_user.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting profile: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@user_bp.route('/api/profile', methods=['PUT'])
@login_required
def api_update_profile():
    """
    Update current user's profile.
    
    Returns:
        JSON with update result
    """
    try:
        data = request.get_json()
        
        # Update allowed fields
        if 'email' in data:
            current_user.email = data['email']
        if 'full_name' in data:
            current_user.full_name = data['full_name']
        
        db.session.commit()
        
        logger.info(f"Profile updated for user: {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Đã cập nhật thông tin cá nhân.',
            'user': current_user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating profile: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# PASSWORD CHANGE
# =============================================================================

@user_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    Display and process password change form.
    """
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            current_password = data.get('current_password', '')
            new_password = data.get('new_password', '')
            confirm_password = data.get('confirm_password', '')
            
            # Verify current password
            if not current_user.check_password(current_password):
                return jsonify({
                    'success': False,
                    'error': 'Mật khẩu hiện tại không đúng.'
                }), 400
            
            # Validate new password
            if len(new_password) < 8:
                return jsonify({
                    'success': False,
                    'error': 'Mật khẩu mới phải có ít nhất 8 ký tự.'
                }), 400
            
            if new_password != confirm_password:
                return jsonify({
                    'success': False,
                    'error': 'Mật khẩu xác nhận không khớp.'
                }), 400
            
            # Update password
            current_user.set_password(new_password)
            db.session.commit()
            
            logger.info(f"Password changed for user: {current_user.username}")
            
            return jsonify({
                'success': True,
                'message': 'Đã đổi mật khẩu thành công.'
            }), 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error changing password: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    return render_template('user_change_password.html')


# =============================================================================
# SEARCH HISTORY
# =============================================================================

@user_bp.route('/search-history')
@login_required
def search_history():
    """
    Display user's search history.
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        logs = SearchLog.query\
            .filter(SearchLog.IP_ADDRESS == request.remote_addr)\
            .order_by(SearchLog.CREATED_AT.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        return render_template(
            'user_search_history.html',
            logs=logs.items,
            pagination=logs
        )
        
    except Exception as e:
        logger.error(f"Error loading search history: {str(e)}")
        flash('Đã xảy ra lỗi khi tải lịch sử tra cứu.', 'error')
        return redirect(url_for('user.dashboard'))


# =============================================================================
# NNT LIST (READ-ONLY FOR REGULAR USERS)
# =============================================================================

@user_bp.route('/nnt')
@login_required
def nnt_list():
    """
    Display paginated list of taxpayers (read-only).
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        status_filter = request.args.get('status')
        search_query = request.args.get('q', '').strip()
        
        per_page = min(per_page, 100)
        
        result = TaxService.get_nnt_list(
            page=page,
            per_page=per_page,
            status_filter=status_filter,
            search_query=search_query if search_query else None,
            sort_by='MST',
            sort_order='asc'
        )
        
        # Mask CCCD for regular users
        for item in result['items']:
            if 'CCCD' in item and item['CCCD']:
                item['CCCD'] = mask_cccd(item['CCCD'])
        
        return render_template(
            'user_nnt_list.html',
            nnt_list=result['items'],
            pagination=result,
            filters={
                'status': status_filter,
                'search': search_query
            }
        )
        
    except Exception as e:
        logger.error(f"Error loading NNT list: {str(e)}")
        flash('Đã xảy ra lỗi khi tải danh sách.', 'error')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/api/nnt/<mst>')
@login_required
def api_nnt_detail(mst):
    """
    Get taxpayer details (masked for regular users).
    
    Args:
        mst: Taxpayer MST
    
    Returns:
        JSON with masked taxpayer data
    """
    try:
        result = TaxService.search_by_mst(mst, include_raw_data=False)
        
        if not result:
            return jsonify({
                'success': False,
                'error': 'Không tìm thấy người nộp thuế.'
            }), 404
        
        # Ensure CCCD is masked
        if 'CCCD' in result and result['CCCD']:
            result['CCCD'] = mask_cccd(result['CCCD'])
        if 'CMT' in result:
            result['CMT'] = None
        
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


# =============================================================================
# QUICK SEARCH (FOR USER DASHBOARD)
# =============================================================================

@user_bp.route('/api/quick-search')
@login_required
def api_quick_search():
    """
    Quick search API for user dashboard.
    
    Query Parameters:
    - mst: Tax Identification Number (optional)
    - cccd: Citizen ID (optional)
    
    Returns:
        JSON with search results (masked)
    """
    try:
        mst = request.args.get('mst', '').strip()
        cccd = request.args.get('cccd', '').strip()
        
        if not mst and not cccd:
            return jsonify({
                'success': False,
                'error': 'Vui lòng nhập MST hoặc CCCD.'
            }), 400
        
        search_type = 'mst' if mst else 'cccd'
        query = mst if mst else cccd
        
        results, status = TaxService.search_nnt(
            query=query,
            search_type=search_type,
            include_raw_data=False
        )
        
        if status == 'FOUND' and results:
            # Mask data
            masked_results = []
            for r in results:
                if 'CCCD' in r and r['CCCD']:
                    r['CCCD'] = mask_cccd(r['CCCD'])
                if 'CMT' in r:
                    r['CMT'] = None
                masked_results.append(r)
            
            return jsonify({
                'success': True,
                'found': True,
                'count': len(masked_results),
                'data': masked_results
            }), 200
        
        return jsonify({
            'success': True,
            'found': False,
            'count': 0,
            'message': 'Không tìm thấy thông tin.'
        }), 200
        
    except Exception as e:
        logger.error(f"Error in quick search: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
