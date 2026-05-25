"""
Database Seeder
Automatically initializes the database with tables, default data, and admin user.
Run this on first startup or when database needs to be reset.
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import db
from models.nnt import NNT, LOAI_NO, TT_NO
from models.users import User
from models.import_history import ImportHistory
from models.no_history import NO_HISTORY
from models.search_log import SearchLog
from services.tax_service import TaxService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseSeeder:
    """
    Database Seeder
    
    Automatically checks and initializes the database if needed:
    - Creates all tables
    - Inserts default debt types
    - Creates admin user
    - Inserts sample NNT data for testing
    """
    
    def __init__(self, app=None):
        """
        Initialize seeder.
        
        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        self.results = {
            'tables_created': False,
            'admin_created': False,
            'debt_types_created': 0,
            'sample_nnt_created': 0,
            'errors': []
        }
    
    def init_app(self, app):
        """
        Initialize with Flask app.
        
        Args:
            app: Flask application instance
        """
        self.app = app
    
    def seed(self) -> bool:
        """
        Main seeding function.
        Runs all seeding steps in order.
        
        Returns:
            True if seeding completed successfully
        """
        if not self.app:
            logger.error("Flask app not initialized")
            return False
        
        with self.app.app_context():
            try:
                logger.info("=" * 50)
                logger.info("Starting database seeding...")
                logger.info("=" * 50)
                
                # Step 1: Create tables
                self._create_tables()
                
                # Step 2: Create debt types
                self._create_debt_types()
                
                # Step 3: Create admin user
                self._create_admin_user()
                
                # Step 4: Create sample NNT data
                self._create_sample_nnt()
                
                # Step 5: Verify data
                self._verify_data()
                
                logger.info("=" * 50)
                logger.info("Database seeding completed!")
                logger.info("=" * 50)
                self._print_results()
                
                return True
                
            except Exception as e:
                logger.error(f"Seeding failed: {str(e)}")
                self.results['errors'].append(str(e))
                return False
    
    def _create_tables(self) -> None:
        """
        Create all database tables.
        Uses SQLAlchemy create_all() method.
        """
        try:
            logger.info("Step 1: Creating database tables...")
            
            # Import all models to ensure they're registered
            from models import NNT, LOAI_NO, TT_NO, User, ImportHistory, NO_HISTORY, SearchLog
            
            # Create all tables
            db.create_all()
            
            self.results['tables_created'] = True
            logger.info("✓ All tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create tables: {str(e)}")
            self.results['errors'].append(f"Tables: {str(e)}")
            raise
    
    def _create_debt_types(self) -> None:
        """
        Create default debt types if they don't exist.
        """
        try:
            logger.info("Step 2: Creating default debt types...")
            
            default_types = [
                ('THUÊ', 'Thuế', 'Các loại thuế phải nộp theo quy định'),
                ('PHÍ', 'Phí', 'Các loại phí hành chính và dịch vụ'),
                ('LỆ PHÍ', 'Lệ phí', 'Các loại lệ phí ngân sách'),
                ('TIỀN THUÊ ĐẤT', 'Tiền thuê đất', 'Tiền thuê đất hàng năm theo hợp đồng'),
                ('KHÁC', 'Khác', 'Các nghĩa vụ tài chính khác')
            ]
            
            created_count = 0
            for loai_no, ten_no, mo_ta in default_types:
                # Check if exists
                existing = LOAI_NO.query.filter(
                    db.or_(
                        LOAI_NO.LOAI_NO == loai_no,
                        LOAI_NO.TEN_NO == ten_no
                    )
                ).first()
                
                if not existing:
                    debt_type = LOAI_NO(
                        LOAI_NO=loai_no,
                        TEN_NO=ten_no,
                        MO_TA=mo_ta
                    )
                    db.session.add(debt_type)
                    created_count += 1
                    logger.info(f"  - Created: {loai_no} - {ten_no}")
                else:
                    logger.info(f"  - Exists: {loai_no} - {ten_no}")
            
            db.session.commit()
            self.results['debt_types_created'] = created_count
            logger.info(f"✓ Created {created_count} new debt types")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create debt types: {str(e)}")
            self.results['errors'].append(f"Debt types: {str(e)}")
    
    def _create_admin_user(self) -> None:
        """
        Create admin user if it doesn't exist.
        Default credentials: admin / admin123
        """
        try:
            logger.info("Step 3: Creating admin user...")
            
            # Check if admin exists
            admin = User.find_by_username('admin')
            
            if not admin:
                # Get default password from config
                admin_password = self.app.config.get('ADMIN_PASSWORD', 'admin123')
                
                admin = User(
                    username='admin',
                    email='admin@taxsystem.local',
                    full_name='Quản trị viên hệ thống',
                    role='ADMIN',
                    is_active=True
                )
                admin.set_password(admin_password)
                
                db.session.add(admin)
                db.session.commit()
                
                self.results['admin_created'] = True
                logger.info("✓ Admin user created:")
                logger.info("  - Username: admin")
                logger.info("  - Password: admin123")
                logger.info("  - Email: admin@taxsystem.local")
                logger.info("  ⚠️  Please change the default password after first login!")
            else:
                logger.info("✓ Admin user already exists")
                self.results['admin_created'] = True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create admin user: {str(e)}")
            self.results['errors'].append(f"Admin: {str(e)}")
    
    def _create_sample_nnt(self) -> None:
        """
        Create sample NNT data for testing (only if database is empty).
        """
        try:
            logger.info("Step 4: Creating sample NNT data...")
            
            # Check if NNT table is empty
            nnt_count = NNT.query.count()
            
            if nnt_count > 0:
                logger.info(f"✓ NNT table already has {nnt_count} records, skipping sample data")
                return
            
            # Sample NNT data
            sample_data = [
                {
                    'MST': '0123456789',
                    'HO_TEN': 'Nguyễn Văn An',
                    'CCCD': '040193001234',
                    'DIA_CHI': '123 Đường Lê Lợi, Quận 1, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456790',
                    'HO_TEN': 'Trần Thị Bình',
                    'CCCD': '040294005678',
                    'DIA_CHI': '456 Đường Nguyễn Huệ, Quận 1, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 15000000
                },
                {
                    'MST': '0123456791',
                    'HO_TEN': 'Lê Văn Cường',
                    'CCCD': '040395008901',
                    'DIA_CHI': '789 Đường Đồng Khởi, Quận 1, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 25000000
                },
                {
                    'MST': '0123456792',
                    'HO_TEN': 'Phạm Thị Dung',
                    'CCCD': '040496002345',
                    'DIA_CHI': '321 Đường Hai Bà Trưng, Quận 3, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456793',
                    'HO_TEN': 'Hoàng Văn Em',
                    'CCCD': '040597006789',
                    'DIA_CHI': '654 Đường Pasteur, Quận 3, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 5000000
                },
                {
                    'MST': '0123456794',
                    'HO_TEN': 'Ngô Thị Phương',
                    'CCCD': '040698001112',
                    'DIA_CHI': '987 Đường Võ Văn Tần, Quận 3, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456795',
                    'HO_TEN': 'Vũ Văn Giang',
                    'CCCD': '040799003334',
                    'DIA_CHI': '147 Đường Nguyễn Đình Chiểu, Quận 1, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 35000000
                },
                {
                    'MST': '0123456796',
                    'HO_TEN': 'Đặng Thị Hà',
                    'CCCD': '040800004445',
                    'DIA_CHI': '258 Đường Điện Biên Phủ, Quận Bình Thạnh, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456797',
                    'HO_TEN': 'Bùi Văn Hùng',
                    'CCCD': '040901005556',
                    'DIA_CHI': '369 Đường Phạm Văn Đồng, Quận Gò Vấp, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 18000000
                },
                {
                    'MST': '0123456798',
                    'HO_TEN': 'Trương Thị Mai',
                    'CCCD': '041002006667',
                    'DIA_CHI': '741 Đường Lê Văn Việt, Quận 9, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 22000000
                },
                {
                    'MST': '0123456799',
                    'HO_TEN': 'Đỗ Văn Khoa',
                    'CCCD': '041103007778',
                    'DIA_CHI': '852 Đường Nguyễn Oanh, Quận Gò Vấp, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456800',
                    'HO_TEN': 'Lý Thị Ngọc',
                    'CCCD': '041204008889',
                    'DIA_CHI': '963 Đường Phan Văn Trị, Quận Bình Thạnh, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 12000000
                },
                {
                    'MST': '0123456801',
                    'HO_TEN': 'Nguyễn Thị Lan',
                    'CCCD': '041305009990',
                    'DIA_CHI': '159 Đường Phạm Hùng, Quận 8, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456802',
                    'HO_TEN': 'Chu Văn Nam',
                    'CCCD': '041406001111',
                    'DIA_CHI': '357 Đường Tạ Quang Bửu, Quận 8, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 8500000
                },
                {
                    'MST': '0123456803',
                    'HO_TEN': 'Hà Thị Oanh',
                    'CCCD': '041507002222',
                    'DIA_CHI': '468 Đường Bùi Minh Trực, Quận 8, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456804',
                    'HO_TEN': 'Trịnh Văn Phong',
                    'CCCD': '041608003333',
                    'DIA_CHI': '579 Đường Hùng Vương, Quận 5, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 45000000
                },
                {
                    'MST': '0123456805',
                    'HO_TEN': 'Phan Thị Quỳnh',
                    'CCCD': '041709004444',
                    'DIA_CHI': '680 Đường Trần Hưng Đạo, Quận 5, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456806',
                    'HO_TEN': 'Đinh Văn Rừng',
                    'CCCD': '041810005555',
                    'DIA_CHI': '791 Đường Nguyễn Trãi, Quận 5, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 7500000
                },
                {
                    'MST': '0123456807',
                    'HO_TEN': 'Hứa Thị Thanh',
                    'CCCD': '041911006666',
                    'DIA_CHI': '802 Đường Lý Thường Kiệt, Quận 10, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'KHONG_NO',
                    'NO_TAM_TINH': 0
                },
                {
                    'MST': '0123456808',
                    'HO_TEN': 'Mạc Văn Sơn',
                    'CCCD': '042012007777',
                    'DIA_CHI': '913 Đường 3 Tháng 2, Quận 10, TP. Hồ Chí Minh',
                    'TRANG_THAI_HD': 'Active',
                    'TRANG_THAI_NO': 'CO_NO',
                    'NO_TAM_TINH': 28000000
                }
            ]
            
            # Get default debt type
            default_debt_type = LOAI_NO.query.first()
            debt_type_id = default_debt_type.ID_NO if default_debt_type else 1
            
            # Insert sample data
            for data in sample_data:
                nnt = NNT(
                    MST=data['MST'],
                    HO_TEN=data['HO_TEN'],
                    CCCD=data['CCCD'],
                    DIA_CHI=data['DIA_CHI'],
                    TRANG_THAI_HD=data['TRANG_THAI_HD'],
                    TRANG_THAI_NO=data['TRANG_THAI_NO'],
                    NGAY_TAO=datetime.utcnow() - timedelta(days=30)
                )
                db.session.add(nnt)
                
                # Add obligation record
                obligation = TT_NO(
                    ID_NNT=data['MST'],
                    ID_NO=debt_type_id,
                    NO_TAM_TINH=data['NO_TAM_TINH'],
                    CREATED_AT=datetime.utcnow() - timedelta(days=30),
                    UPDATED_AT=datetime.utcnow()
                )
                db.session.add(obligation)
                
                logger.info(f"  - Created: {data['MST']} - {data['HO_TEN']}")
            
            db.session.commit()
            self.results['sample_nnt_created'] = len(sample_data)
            logger.info(f"✓ Created {len(sample_data)} sample NNT records")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create sample NNT: {str(e)}")
            self.results['errors'].append(f"Sample NNT: {str(e)}")
    
    def _verify_data(self) -> None:
        """
        Verify seeded data.
        """
        try:
            logger.info("Step 5: Verifying data...")
            
            nnt_count = NNT.query.count()
            user_count = User.query.count()
            debt_type_count = LOAI_NO.query.count()
            
            logger.info(f"✓ NNT records: {nnt_count}")
            logger.info(f"✓ User records: {user_count}")
            logger.info(f"✓ Debt type records: {debt_type_count}")
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            self.results['errors'].append(f"Verification: {str(e)}")
    
    def _print_results(self) -> None:
        """
        Print seeding results summary.
        """
        logger.info("\n" + "=" * 50)
        logger.info("SEEDING RESULTS SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Tables Created: {'✓ Yes' if self.results['tables_created'] else '✗ No'}")
        logger.info(f"Admin Created: {'✓ Yes' if self.results['admin_created'] else '✗ No'}")
        logger.info(f"Debt Types Created: {self.results['debt_types_created']}")
        logger.info(f"Sample NNT Created: {self.results['sample_nnt_created']}")
        
        if self.results['errors']:
            logger.warning("\nErrors encountered:")
            for error in self.results['errors']:
                logger.warning(f"  - {error}")
        
        logger.info("=" * 50)
        logger.info("\n📋 Default Login Credentials:")
        logger.info("   Username: admin")
        logger.info("   Password: admin123")
        logger.info("\n⚠️  IMPORTANT: Change the default password after first login!")
        logger.info("=" * 50)


def run_seeder(app=None):
    """
    Run the database seeder.
    
    Args:
        app: Flask application instance
    
    Returns:
        DatabaseSeeder instance
    """
    seeder = DatabaseSeeder(app)
    success = seeder.seed()
    return seeder


if __name__ == '__main__':
    """
    Run seeder standalone for testing or manual initialization.
    """
    from app import create_app
    
    logger.info("Starting standalone database seeder...")
    
    app = create_app()
    seeder = run_seeder(app)
    
    if seeder:
        logger.info("Seeding completed successfully!")
        sys.exit(0)
    else:
        logger.error("Seeding failed!")
        sys.exit(1)
