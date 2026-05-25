"""
Tax Obligation Management System
Main Application Entry Point
"""

import os
import sys
import logging
from datetime import datetime

from flask import Flask, render_template, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from wtforms.csrf.session import SessionCSRF

from config import get_config
from models import db


def create_app(config_name: str = None) -> Flask:
    """Application Factory Pattern"""
    
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
        static_url_path='/static'
    )
    
    if config_name is None:
        config_name = os.environ.get('APP_ENV', 'production')
    
    config_class = get_config()
    app.config.from_object(config_class)
    config_class.init_app()
    
    setup_logging(app)
    init_extensions(app)
    register_blueprints(app)
    register_error_handlers(app)
    register_context_processors(app)
    
    with app.app_context():
        try:
            db.create_all()
            app.logger.info("Database tables created/verified successfully")
        except Exception as e:
            app.logger.warning(f"Could not create database tables: {str(e)}")
    
    app.logger.info(f"Application started in {config_name} mode")
    return app


def setup_logging(app: Flask) -> None:
    log_dir = os.path.join(app.root_path, '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d")}.log')
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


def init_extensions(app: Flask) -> None:
    """Initialize Flask extensions"""
    db.init_app(app)
    
    # Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Vui lòng đăng nhập để truy cập trang này.'
    login_manager.login_message_category = 'warning'
    login_manager.session_protection = 'strong'
    
    @login_manager.user_loader
    def load_user(user_id: str):
        from models.users import User
        try:
            return User.query.get(int(user_id))
        except (ValueError, TypeError):
            return None
    
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.is_json:
            return jsonify({'success': False, 'error': 'Unauthorized', 'message': 'Vui lòng đăng nhập.'}), 401
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))
    
    # CSRF Protection
    # CSRF Protection - temporarily disabled for debugging
    csrf = CSRFProtect()
    csrf.init_app(app)
    
    # Rate Limiter - more lenient limits for testing
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["1000 per day", "200 per hour", "50 per minute"],
        storage_uri="memory://"
    )
    limiter.init_app(app)
    
    # Store limiter in app extensions for later use
    app.extensions['limiter'] = limiter


def register_blueprints(app: Flask) -> None:
    """Register Flask blueprints"""
    
    from flask import Blueprint
    limiter = app.extensions.get('limiter')
    
    # Create blueprints
    public_bp = Blueprint('public', __name__)
    auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
    admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
    user_bp = Blueprint('user', __name__, url_prefix='/user')
    
    # =============================================================================
    # PUBLIC ROUTES
    # =============================================================================
    
    @public_bp.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('public.search'))
    
    @public_bp.route('/tra-cuu')
    def search():
        return render_template('public_search.html')
    
    @public_bp.route('/captcha')
    def captcha():
        from utils.captcha import CaptchaGenerator
        generator = CaptchaGenerator()
        return generator.get_image_response()
    
    @public_bp.route('/api/public/search')
    def api_public_search():
        from flask import jsonify
        from models.search_log import SearchLog
        from services.tax_service import TaxService
        import time
        
        start_time = time.time()
        client_ip = request.remote_addr or '0.0.0.0'
        user_agent = request.headers.get('User-Agent', '')[:500]
        
        try:
            mst_raw = request.args.get('mst', '')
            cccd_raw = request.args.get('cccd', '')
            
            search_type = None
            search_value = None
            
            if mst_raw and mst_raw.strip():
                search_type = 'mst'
                search_value = ''.join(c for c in mst_raw if c.isdigit())
                if len(search_value) not in [10, 13]:
                    return jsonify({
                        'success': False, 
                        'error': 'Invalid MST',
                        'message': f'MST phai co 10 hoac 13 chu so (ban nhap {len(search_value)} chu so)'
                    }), 400
            
            elif cccd_raw and cccd_raw.strip():
                search_type = 'cccd'
                search_value = ''.join(c for c in cccd_raw if c.isdigit())
                if len(search_value) not in [9, 12]:
                    return jsonify({
                        'success': False, 
                        'error': 'Invalid CCCD',
                        'message': f'CCCD phai co 9 hoac 12 chu so (ban nhap {len(search_value)} chu so)'
                    }), 400
            
            else:
                return jsonify({
                    'success': False, 
                    'error': 'Missing params', 
                    'message': 'Vui long nhap MST hoac CCCD'
                }), 400
            
            # Perform search
            results, status = TaxService.search_nnt(search_value, search_type, include_raw_data=False)
            
            # Log search (ignore errors)
            try:
                SearchLog.log_search(
                    ip_address=client_ip,
                    search_type=search_type.upper(),
                    search_value=search_value if search_type == 'mst' else '***',
                    user_agent=user_agent,
                    result_count=len(results),
                    response_time=(time.time() - start_time) * 1000,
                    status='SUCCESS' if results else 'NOT_FOUND'
                )
            except:
                pass
            
            if results:
                return jsonify({
                    'success': True,
                    'found': True,
                    'count': len(results),
                    'data': [_mask_nnt_data(r) for r in results],
                    'search_type': search_type.upper()
                }), 200
            else:
                return jsonify({
                    'success': True,
                    'found': False,
                    'count': 0,
                    'message': 'Khong tim thay thong tin nguoi nop thue.',
                    'search_type': search_type.upper()
                }), 200
                
        except Exception as e:
            import traceback
            return jsonify({
                'success': False,
                'error': 'Server error',
                'message': f'Da xay ra loi: {str(e)}'
            }), 500
    
    def _mask_nnt_data(data):
        from utils.security import mask_cccd
        masked = data.copy()
        if 'CCCD' in masked and masked['CCCD']:
            masked['CCCD'] = mask_cccd(masked['CCCD'])
        if 'CMT' in masked:
            masked['CMT'] = None
        return masked
    
    @public_bp.route('/health')
    def health_check():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'status': 'healthy', 'database': 'connected'}), 200
        except:
            return jsonify({'status': 'unhealthy', 'database': 'disconnected'}), 503
    
    @public_bp.route('/simple-login')
    def simple_login():
        return render_template('simple_login.html')
    
    @public_bp.route('/test-login')
    def test_login_page():
        return render_template('test_login.html')
    
    @public_bp.route('/huong-dan')
    def guide():
        return render_template('guide.html')
    
    @public_bp.route('/gioi-thieu')
    def about():
        return render_template('about.html')
    
    @public_bp.route('/lien-he')
    def contact():
        return render_template('contact.html')
    
    # =============================================================================
    # AUTH ROUTES
    # =============================================================================
    
    @auth_bp.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            from flask import redirect, url_for
            if current_user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('user.dashboard'))
        
        if request.method == 'POST':
            from flask import flash
            from models.users import User
            
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            remember_me = request.form.get('remember_me', False)
            
            if not username or not password:
                flash('Vui lòng nhập tên đăng nhập và mật khẩu.', 'error')
                return render_template('login.html'), 400
            
            user = User.find_by_username(username)
            
            if not user or not user.check_password(password):
                flash('Tên đăng nhập hoặc mật khẩu không đúng.', 'error')
                return render_template('login.html'), 401
            
            if not user.is_active:
                flash('Tài khoản đã bị vô hiệu hóa.', 'error')
                return render_template('login.html'), 403
            
            login_user(user, remember=remember_me)
            user.update_last_login()
            flash('Đăng nhập thành công!', 'success')
            
            from flask import redirect, url_for
            if user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('user.dashboard'))
        
        return render_template('login.html')
    
    @auth_bp.route('/logout', methods=['GET', 'POST'])
    def logout():
        logout_user()
        from flask import flash, redirect, url_for
        flash('Đã đăng xuất thành công.', 'success')
        return redirect(url_for('public.search'))
    
    @auth_bp.route('/reset-password', methods=['GET', 'POST'])
    def reset_password_request():
        if request.method == 'POST':
            from flask import flash, redirect, url_for
            email = request.form.get('email', '').strip()
            if email:
                flash('Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi.', 'success')
            return redirect(url_for('auth.login'))
        return render_template('reset_password_request.html')
    
    @auth_bp.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            from flask import flash, redirect, url_for
            from models.users import User
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            email = request.form.get('email', '').strip()
            full_name = request.form.get('full_name', '').strip()
            
            if not username or not password:
                flash('Vui lòng điền đầy đủ thông tin bắt buộc.', 'error')
                return render_template('register.html'), 400
            
            if User.find_by_username(username):
                flash('Tên đăng nhập đã tồn tại.', 'error')
                return render_template('register.html'), 400
            
            user = User(username=username, email=email or None, full_name=full_name or None, role='USER')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f'Đã tạo tài khoản "{username}" thành công.', 'success')
            return redirect(url_for('auth.login'))
        return render_template('register.html')
    
    # =============================================================================
    # ADMIN ROUTES
    # =============================================================================
    
    @admin_bp.route('/')
    @admin_bp.route('/dashboard')
    @login_required
    def dashboard():
        from services.tax_service import TaxService
        from models.import_history import ImportHistory
        
        stats = TaxService.get_dashboard_stats()
        top_debtors = TaxService.get_top_debtors(limit=10)
        recent_imports = ImportHistory.query.order_by(ImportHistory.created_at.desc()).limit(5).all()
        recent_changes = TaxService.get_recent_changes(limit=10)
        
        return render_template('admin_dashboard.html', 
            stats=stats, top_debtors=top_debtors,
            recent_imports=[imp.to_dict() for imp in recent_imports],
            recent_changes=recent_changes)
    
    @admin_bp.route('/import')
    @login_required
    def import_page():
        from services.tax_service import TaxService
        from models.import_history import ImportHistory
        
        from models.nnt import LOAI_NO
        debt_types = LOAI_NO.query.order_by(LOAI_NO.LOAI_NO).all()
        import_history = ImportHistory.query.order_by(ImportHistory.created_at.desc()).limit(20).all()
        
        return render_template('admin_import.html',
            debt_types=debt_types,
            import_history=import_history)
    
    @admin_bp.route('/api/import', methods=['POST'])
    @login_required
    def api_import():
        import traceback
        from flask import jsonify
        from services.excel_service import ExcelService
        from models.import_history import ImportHistory
        from utils.security import allowed_file, sanitize_filename
        
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'No file provided'}), 400
            
            file = request.files['file']
            if not file.filename or not allowed_file(file.filename):
                return jsonify({'success': False, 'error': 'Invalid file type'}), 400
            
            import_record = ImportHistory(
                file_name=sanitize_filename(file.filename),
                file_size=0,
                status='PENDING',
                import_by=current_user.id
            )
            db.session.add(import_record)
            db.session.commit()
            
            file_bytes = file.read()
            import_record.file_size = len(file_bytes)
            db.session.commit()
            
            excel_service = ExcelService(import_history_id=import_record.id, user_id=current_user.id)
            start_time = datetime.utcnow()
            results = excel_service.import_from_bytes(file_bytes, file.filename)
            end_time = datetime.utcnow()
            
            import_time = (end_time - start_time).total_seconds()
            import_record.import_time = import_time
            import_record.total_rows = results['stats']['total_rows']
            import_record.success_rows = results['stats']['success_rows']
            import_record.failed_rows = results['stats']['failed_rows']
            import_record.status = 'COMPLETED' if results['success'] else 'PARTIAL'
            import_record.completed_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Đã nhập {results["stats"]["success_rows"]} bản ghi.',
                'results': results
            }), 200
            
        except Exception as e:
            app.logger.error(f"Import error: {str(e)}\n{traceback.format_exc()}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @admin_bp.route('/nnt')
    @login_required
    def nnt_list():
        from services.tax_service import TaxService
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        status_filter = request.args.get('status')
        search_query = request.args.get('q', '').strip()
        
        from models.nnt import NNT
        from sqlalchemy import or_
        query = NNT.query
        if status_filter:
            query = query.filter(NNT.TRANG_THAI_NO == status_filter)
        if search_query:
            s = f'%{search_query}%'
            query = query.filter(or_(NNT.MST.ilike(s), NNT.HO_TEN.ilike(s)))
        query = query.order_by(NNT.MST.asc())
        pag = query.paginate(page=page, per_page=per_page, error_out=False)
        pagination = {
            'items': pag.items, 'total': pag.total, 'pages': pag.pages,
            'current_page': page, 'per_page': per_page,
            'has_next': pag.has_next, 'has_prev': pag.has_prev
        }
        return render_template('admin_nnt_list.html',
            nnt_list=pag.items,
            pagination=pagination,
            filters={'status': status_filter, 'search': search_query, 'sort': 'MST', 'order': 'asc'})
    
    @admin_bp.route('/users')
    @login_required
    def user_list():
        from models.users import User
        users = User.query.order_by(User.created_at.desc()).all()
        users_json = [u.to_dict() for u in users]
        return render_template('admin_user_list.html', users=users, users_json=users_json)
    
    @admin_bp.route('/search-logs')
    @login_required
    def search_logs():
        from models.search_log import SearchLog
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        logs = SearchLog.query.order_by(SearchLog.CREATED_AT.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
        
        return render_template('admin_search_logs.html', logs=logs.items, pagination=logs)
    

    @admin_bp.route('/api/debt-types', methods=['POST'])
    @login_required
    def api_create_debt_type():
        from flask import jsonify
        from models.nnt import LOAI_NO
        data = request.get_json() or {}
        loai_no = (data.get('loai_no') or '').strip().upper()
        ten_no = (data.get('ten_no') or '').strip()
        if not loai_no or not ten_no:
            return jsonify({'success': False, 'error': 'Thiếu thông tin loại nợ'}), 400
        if LOAI_NO.query.filter_by(LOAI_NO=loai_no).first():
            return jsonify({'success': False, 'error': 'Loại nợ đã tồn tại'}), 400
        dt = LOAI_NO(LOAI_NO=loai_no, TEN_NO=ten_no)
        db.session.add(dt)
        db.session.commit()
        return jsonify({'success': True, 'debt_type': dt.to_dict()}), 201
    
    @admin_bp.route('/api/nnt/<mst>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def api_nnt(mst):
        from flask import jsonify
        from models.nnt import NNT
        
        nnt = NNT.query.get(mst)
        
        if request.method == 'GET':
            if not nnt:
                return jsonify({'success': False, 'error': 'Not found'}), 404
            return jsonify({'success': True, 'nnt': nnt.to_dict(masked=False)}), 200
        
        elif request.method == 'PUT':
            if not nnt:
                return jsonify({'success': False, 'error': 'Not found'}), 404
            
            data = request.get_json()
            for field in ['HO_TEN', 'DIA_CHI', 'CCCD', 'CMT', 'TRANG_THAI_HD', 'TRANG_THAI_NO']:
                if field in data:
                    setattr(nnt, field, data[field])
            
            nnt.LAST_SYNC = datetime.utcnow()
            db.session.commit()
            return jsonify({'success': True, 'message': 'Updated', 'nnt': nnt.to_dict()}), 200
        
        elif request.method == 'DELETE':
            if not nnt:
                return jsonify({'success': False, 'error': 'Not found'}), 404
            db.session.delete(nnt)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Deleted'}), 200
    
    @admin_bp.route('/api/users', methods=['POST'])
    @login_required
    def api_create_user():
        from flask import jsonify
        from models.users import User
        
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        if User.find_by_username(username):
            return jsonify({'success': False, 'error': 'Username exists'}), 400
        
        user = User(
            username=username,
            email=data.get('email', '').strip() or None,
            full_name=data.get('full_name', '').strip() or None,
            role=data.get('role', 'USER')
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'success': True, 'user': user.to_dict()}), 201
    
    @admin_bp.route('/api/users/<int:user_id>', methods=['PUT', 'DELETE'])
    @login_required
    def api_user(user_id):
        from flask import jsonify
        from models.users import User
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        
        if request.method == 'PUT':
            data = request.get_json()
            for field in ['email', 'full_name', 'role', 'is_active']:
                if field in data:
                    setattr(user, field, data[field])
            if 'password' in data and data['password']:
                user.set_password(data['password'])
            db.session.commit()
            return jsonify({'success': True, 'user': user.to_dict()}), 200
        
        elif request.method == 'DELETE':
            if user_id == current_user.id:
                return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 400
            db.session.delete(user)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Deleted'}), 200
    
    # =============================================================================
    # USER ROUTES
    # =============================================================================
    
    @user_bp.route('/')
    @user_bp.route('/dashboard')
    @login_required
    def dashboard():
        from models.nnt import NNT
        from models.search_log import SearchLog
        from datetime import timedelta
        
        total_nnt = NNT.query.count()
        co_no_count = NNT.query.filter(NNT.TRANG_THAI_NO == 'CO_NO').count()
        khong_no_count = NNT.query.filter(NNT.TRANG_THAI_NO == 'KHONG_NO').count()
        
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_searches = SearchLog.query.filter(
            SearchLog.CREATED_AT >= week_ago
        ).order_by(SearchLog.CREATED_AT.desc()).limit(20).all()
        
        return render_template('user_dashboard.html',
            total_nnt=total_nnt,
            co_no_count=co_no_count,
            khong_no_count=khong_no_count,
            recent_searches=recent_searches,
            last_login=current_user.last_login)
    
    @user_bp.route('/nnt')
    @login_required
    def nnt_list():
        from services.tax_service import TaxService
        from utils.security import mask_cccd
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100)
        status_filter = request.args.get('status')
        search_query = request.args.get('q', '').strip()
        
        result = TaxService.get_nnt_list(page, per_page, status_filter,
            search_query if search_query else None, 'MST', 'asc')
        
        for item in result['items']:
            if 'CCCD' in item and item['CCCD']:
                item['CCCD'] = mask_cccd(item['CCCD'])
        
        return render_template('user_nnt_list.html',
            nnt_list=result['items'],
            pagination=result,
            filters={'status': status_filter, 'search': search_query})
    
    @user_bp.route('/search-history')
    @login_required
    def search_history():
        from models.search_log import SearchLog
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        logs = SearchLog.query.order_by(
            SearchLog.CREATED_AT.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return render_template('user_search_history.html', logs=logs.items, pagination=logs)
    
    @user_bp.route('/profile')
    @login_required
    def profile():
        return render_template('user_profile.html')
    
    @user_bp.route('/api/profile', methods=['PUT'])
    @login_required
    def api_profile():
        from flask import jsonify
        data = request.get_json()
        if 'email' in data:
            current_user.email = data['email']
        if 'full_name' in data:
            current_user.full_name = data['full_name']
        db.session.commit()
        return jsonify({'success': True, 'user': current_user.to_dict()}), 200
    
    @user_bp.route('/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        if request.method == 'POST':
            from flask import jsonify
            data = request.get_json() if request.is_json else request.form
            
            current_password = data.get('current_password', '')
            new_password = data.get('new_password', '')
            confirm_password = data.get('confirm_password', '')
            
            if not current_user.check_password(current_password):
                return jsonify({'success': False, 'error': 'Mật khẩu hiện tại không đúng.'}), 400
            
            if new_password != confirm_password:
                return jsonify({'success': False, 'error': 'Mật khẩu xác nhận không khớp.'}), 400
            
            if len(new_password) < 8:
                return jsonify({'success': False, 'error': 'Mật khẩu mới phải có ít nhất 8 ký tự.'}), 400
            
            current_user.set_password(new_password)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Đã đổi mật khẩu thành công.'}), 200
        
        return render_template('user_change_password.html')
    
    @user_bp.route('/api/nnt/<mst>')
    @login_required
    def api_nnt(mst):
        from flask import jsonify
        from services.tax_service import TaxService
        from utils.security import mask_cccd
        
        result = TaxService.search_by_mst(mst, include_raw_data=False)
        if not result:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        
        if result.get('CCCD'):
            result['CCCD'] = mask_cccd(result['CCCD'])
        result['CMT'] = None
        
        return jsonify({'success': True, 'nnt': result}), 200
    
    # Register blueprints
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    
    app.logger.info("Blueprints registered successfully")


def register_error_handlers(app: Flask) -> None:
    """Register error handlers"""
    
    @app.errorhandler(400)
    def bad_request(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Bad Request', 'message': str(error.description)}), 400
        return render_template('errors/400.html', error=error), 400
    
    @app.errorhandler(404)
    def not_found(error):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Not Found', 'message': 'Trang không tồn tại.'}), 404
        return render_template('errors/404.html', error=error), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal server error: {str(error)}")
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Internal Server Error', 'message': 'Đã xảy ra lỗi nội bộ. Vui lòng thử lại.'}), 500
        return render_template('errors/500.html', error=error), 500


def register_context_processors(app: Flask) -> None:
    """Register template context processors and filters"""
    
    @app.context_processor
    def inject_now():
        return {'year': datetime.now().year}
    
    @app.template_filter('format_currency')
    def format_currency(value):
        if value:
            try:
                return "{:,.0f} VND".format(float(value)).replace(",", ".")
            except:
                return "0 VND"
        return "0 VND"


# CLI Commands
def init_cli_commands(app: Flask) -> None:
    import click
    
    @app.cli.command('init-db')
    def init_db_command():
        from database_seeder import run_seeder
        seeder = run_seeder(app)
        if seeder.results.get('tables_created'):
            click.echo('Database initialized successfully!')
        else:
            click.echo('Database initialization failed.')
    
    @app.cli.command('seed-db')
    def seed_db_command():
        from database_seeder import run_seeder
        seeder = run_seeder(app)
        click.echo(f'Created {seeder.results.get("sample_nnt_created", 0)} sample records.')


# Create application instance
app = create_app()
init_cli_commands(app)


if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    app.run(host=host, port=port, debug=debug, threaded=True)
