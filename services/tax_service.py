"""
Tax Service
Business logic layer for tax-related operations including search, statistics, and reporting.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import func, text, and_, or_
from sqlalchemy.orm import joinedload

from models import db
from models.nnt import NNT, LOAI_NO, TT_NO
from models.no_history import NO_HISTORY
from models.search_log import SearchLog
from utils.security import mask_cccd

logger = logging.getLogger(__name__)


class TaxService:
    """
    Tax Service
    
    Central business logic for tax obligation management:
    - Public search with masking
    - Admin statistics and reporting
    - Debt analysis
    - Audit trail queries
    
    All methods are designed for optimized database queries to minimize
    data transfer from Supabase Cloud.
    """
    
    @staticmethod
    def search_by_mst(mst: str, include_raw_data: bool = False) -> Optional[Dict[str, Any]]:
        """
        Search taxpayer by MST (Tax Identification Number).
        
        Args:
            mst: Tax Identification Number
            include_raw_data: If True, return unmasked CCCD/CMT (admin only)
        
        Returns:
            Taxpayer data dictionary or None if not found
        """
        try:
            nnt = NNT.query.options(
                joinedload(NNT.tax_obligations).joinedload(TT_NO.loai_no)
            ).filter(NNT.MST == mst).first()
            
            if not nnt:
                return None
            
            result = nnt.to_dict(masked=not include_raw_data)
            result['obligations'] = [
                obligation.to_dict() for obligation in nnt.tax_obligations
            ]
            
            return result
            
        except Exception as e:
            logger.error(f"Error searching by MST {mst}: {str(e)}")
            return None
    
    @staticmethod
    def search_by_cccd(cccd: str, include_raw_data: bool = False) -> List[Dict[str, Any]]:
        """
        Search taxpayers by CCCD (Citizen ID).
        
        Args:
            cccd: Citizen ID Number
            include_raw_data: If True, return unmasked CCCD (admin only)
        
        Returns:
            List of matching taxpayer dictionaries
        """
        try:
            # Normalize CCCD (remove spaces, dashes)
            cccd_normalized = ''.join(c for c in str(cccd) if c.isalnum())
            
            nnts = NNT.query.filter(NNT.CCCD == cccd_normalized).options(
                joinedload(NNT.tax_obligations).joinedload(TT_NO.loai_no)
            ).all()
            
            results = []
            for nnt in nnts:
                result = nnt.to_dict(masked=not include_raw_data)
                result['obligations'] = [
                    obligation.to_dict() for obligation in nnt.tax_obligations
                ]
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching by CCCD {cccd}: {str(e)}")
            return []
    
    @staticmethod
    def search_nnt(query: str, search_type: str = 'mst', 
                  include_raw_data: bool = False) -> Tuple[List[Dict[str, Any]], str]:
        """
        Generic search for taxpayers.
        
        Args:
            query: Search query
            search_type: Type of search ('mst', 'cccd', 'name')
            include_raw_data: If True, return unmasked data
        
        Returns:
            Tuple of (results list, status message)
        """
        try:
            # Normalize query
            query_normalized = str(query).strip()
            
            if search_type == 'mst':
                result = TaxService.search_by_mst(query_normalized, include_raw_data)
                if result:
                    return [result], 'FOUND'
                return [], 'NOT_FOUND'
            
            elif search_type == 'cccd':
                results = TaxService.search_by_cccd(query_normalized, include_raw_data)
                if results:
                    return results, 'FOUND'
                return [], 'NOT_FOUND'
            
            elif search_type == 'name':
                nnts = NNT.query.filter(
                    NNT.HO_TEN.ilike(f'%{query_normalized}%')
                ).limit(50).all()
                
                results = []
                for nnt in nnts:
                    result = nnt.to_dict(masked=not include_raw_data)
                    results.append(result)
                
                if results:
                    return results, 'FOUND'
                return [], 'NOT_FOUND'
            
            return [], 'INVALID_SEARCH_TYPE'
            
        except Exception as e:
            logger.error(f"Error in generic search: {str(e)}")
            return [], 'ERROR'
    
    @staticmethod
    def get_dashboard_stats() -> Dict[str, Any]:
        """
        Get dashboard statistics for admin view.
        Uses optimized SQL aggregation to minimize data transfer.
        
        Returns:
            Dictionary with dashboard statistics
        """
        try:
            stats = {}
            
            # 1. Total NNT count
            stats['total_nnt'] = db.session.query(func.count(NNT.MST)).scalar() or 0
            
            # 2. Total debt amount (SUM)
            total_debt = db.session.query(func.sum(TT_NO.NO_TAM_TINH)).scalar() or 0.0
            stats['total_debt'] = float(total_debt)
            
            # 3. Debt status breakdown (CO_NO vs KHONG_NO)
            status_counts = db.session.query(
                NNT.TRANG_THAI_NO,
                func.count(NNT.MST)
            ).group_by(NNT.TRANG_THAI_NO).all()
            
            stats['status_breakdown'] = {
                'CO_NO': 0,
                'KHONG_NO': 0
            }
            for status, count in status_counts:
                if status in stats['status_breakdown']:
                    stats['status_breakdown'][status] = count
            
            # 4. Active vs Inactive count
            active_counts = db.session.query(
                NNT.TRANG_THAI_HD,
                func.count(NNT.MST)
            ).group_by(NNT.TRANG_THAI_HD).all()
            
            stats['active_breakdown'] = {}
            for status, count in active_counts:
                stats['active_breakdown'][status] = count
            
            # 5. New NNTs today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            stats['new_nnt_today'] = db.session.query(
                func.count(NNT.MST)
            ).filter(NNT.NGAY_TAO >= today_start).scalar() or 0
            
            # 6. New NNTs this month
            month_start = today_start.replace(day=1)
            stats['new_nnt_month'] = db.session.query(
                func.count(NNT.MST)
            ).filter(NNT.NGAY_TAO >= month_start).scalar() or 0
            
            # 7. Total obligation count
            stats['total_obligations'] = db.session.query(func.count(TT_NO.ID)).scalar() or 0
            
            # 8. Debt types distribution
            debt_type_stats = db.session.query(
                LOAI_NO.TEN_NO,
                func.count(TT_NO.ID),
                func.sum(TT_NO.NO_TAM_TINH)
            ).join(TT_NO, TT_NO.ID_NO == LOAI_NO.ID_NO)\
             .group_by(LOAI_NO.TEN_NO).all()
            
            stats['debt_types'] = [
                {
                    'name': name,
                    'count': count,
                    'total': float(total or 0)
                }
                for name, count, total in debt_type_stats
            ]
            
            # 9. Recent imports count (last 7 days)
            week_ago = datetime.utcnow() - timedelta(days=7)
            from models.import_history import ImportHistory
            stats['recent_imports'] = db.session.query(
                func.count(ImportHistory.id)
            ).filter(ImportHistory.created_at >= week_ago).scalar() or 0
            
            # 10. Search activity (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            stats['searches_today'] = db.session.query(
                func.count(SearchLog.id)
            ).filter(SearchLog.CREATED_AT >= yesterday).scalar() or 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {str(e)}")
            return {
                'error': str(e),
                'total_nnt': 0,
                'total_debt': 0,
                'status_breakdown': {'CO_NO': 0, 'KHONG_NO': 0},
                'new_nnt_today': 0
            }
    
    @staticmethod
    def get_top_debtors(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top taxpayers with largest outstanding obligations.
        
        Args:
            limit: Number of top debtors to return
        
        Returns:
            List of taxpayer dictionaries with total debt
        """
        try:
            # Subquery to get total debt per NNT
            subquery = db.session.query(
                TT_NO.ID_NNT,
                func.sum(TT_NO.NO_TAM_TINH).label('total_debt')
            ).group_by(TT_NO.ID_NNT).subquery()
            
            # Main query joining with NNT
            results = db.session.query(
                NNT.MST,
                NNT.HO_TEN,
                NNT.TRANG_THAI_NO,
                NNT.TRANG_THAI_HD,
                subquery.c.total_debt
            ).join(
                subquery, NNT.MST == subquery.c.ID_NNT
            ).order_by(
                subquery.c.total_debt.desc()
            ).limit(limit).all()
            
            return [
                {
                    'MST': r.MST,
                    'HO_TEN': r.HO_TEN,
                    'TRANG_THAI_NO': r.TRANG_THAI_NO,
                    'TRANG_THAI_HD': r.TRANG_THAI_HD,
                    'total_debt': float(r.total_debt or 0)
                }
                for r in results
            ]
            
        except Exception as e:
            logger.error(f"Error getting top debtors: {str(e)}")
            return []
    
    @staticmethod
    def get_monthly_debt_trend(months: int = 12) -> List[Dict[str, Any]]:
        """
        Get monthly debt trend for charting.
        
        Args:
            months: Number of months to look back
        
        Returns:
            List of monthly debt statistics
        """
        try:
            from datetime import date
            
            results = []
            today = datetime.utcnow()
            
            for i in range(months):
                # Calculate month range
                month_date = today.replace(day=1) - timedelta(days=i * 30)
                month_start = month_date.replace(day=1)
                if month_date.month == 12:
                    month_end = month_date.replace(year=month_date.year + 1, month=1, day=1)
                else:
                    month_end = month_date.replace(month=month_date.month + 1, day=1)
                
                # Get count and sum for the month
                count = db.session.query(func.count(NO_HISTORY.id)).filter(
                    and_(
                        NO_HISTORY.UPDATED_AT >= month_start,
                        NO_HISTORY.UPDATED_AT < month_end
                    )
                ).scalar() or 0
                
                total_change = db.session.query(
                    func.sum(NO_HISTORY.NO_MOI - NO_HISTORY.NO_CU)
                ).filter(
                    and_(
                        NO_HISTORY.UPDATED_AT >= month_start,
                        NO_HISTORY.UPDATED_AT < month_end
                    )
                ).scalar() or 0.0
                
                results.insert(0, {
                    'month': month_start.strftime('%Y-%m'),
                    'label': month_start.strftime('%b %Y'),
                    'changes': int(count),
                    'total_change': float(total_change)
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting monthly debt trend: {str(e)}")
            return []
    
    @staticmethod
    def get_recent_changes(limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent obligation changes for audit trail.
        
        Args:
            limit: Number of recent changes to return
        
        Returns:
            List of NO_HISTORY records
        """
        try:
            changes = NO_HISTORY.query.order_by(
                NO_HISTORY.UPDATED_AT.desc()
            ).limit(limit).all()
            
            return [change.to_dict() for change in changes]
            
        except Exception as e:
            logger.error(f"Error getting recent changes: {str(e)}")
            return []
    
    @staticmethod
    def get_nnt_list(page: int = 1, per_page: int = 50,
                     status_filter: Optional[str] = None,
                     search_query: Optional[str] = None,
                     sort_by: str = 'MST',
                     sort_order: str = 'asc') -> Dict[str, Any]:
        """
        Get paginated list of taxpayers.
        
        Args:
            page: Page number
            per_page: Items per page
            status_filter: Filter by debt status
            search_query: Search in MST or name
            sort_by: Field to sort by
            sort_order: Sort order (asc/desc)
        
        Returns:
            Dictionary with paginated results
        """
        try:
            query = NNT.query
            
            # Apply filters
            if status_filter:
                query = query.filter(NNT.TRANG_THAI_NO == status_filter)
            
            if search_query:
                search = f'%{search_query}%'
                query = query.filter(
                    or_(
                        NNT.MST.ilike(search),
                        NNT.HO_TEN.ilike(search)
                    )
                )
            
            # Apply sorting
            sort_column = getattr(NNT, sort_by, NNT.MST)
            if sort_order.lower() == 'desc':
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            return {
                'items': [nnt.to_dict() for nnt in pagination.items],
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page,
                'per_page': per_page,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
            
        except Exception as e:
            logger.error(f"Error getting NNT list: {str(e)}")
            return {
                'items': [],
                'total': 0,
                'pages': 0,
                'current_page': page,
                'error': str(e)
            }
    
    @staticmethod
    def get_debt_types() -> List[Dict[str, Any]]:
        """
        Get all debt types.
        
        Returns:
            List of debt type dictionaries
        """
        try:
            debt_types = LOAI_NO.query.all()
            return [dt.to_dict() for dt in debt_types]
        except Exception as e:
            logger.error(f"Error getting debt types: {str(e)}")
            return []
    
    @staticmethod
    def create_debt_type(loai_no: str, ten_no: str, mo_ta: Optional[str] = None) -> Optional[LOAI_NO]:
        """
        Create a new debt type.
        
        Args:
            loai_no: Debt type code
            ten_no: Debt type name
            mo_ta: Description
        
        Returns:
            Created LOAI_NO instance or None
        """
        try:
            # Check if exists
            existing = LOAI_NO.query.filter(
                db.or_(
                    LOAI_NO.LOAI_NO == loai_no,
                    LOAI_NO.TEN_NO == ten_no
                )
            ).first()
            
            if existing:
                return existing
            
            debt_type = LOAI_NO(
                LOAI_NO=loai_no,
                TEN_NO=ten_no,
                MO_TA=mo_ta
            )
            db.session.add(debt_type)
            db.session.commit()
            
            return debt_type
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating debt type: {str(e)}")
            return None
    
    @staticmethod
    def initialize_default_debt_types() -> None:
        """
        Initialize default debt types if they don't exist.
        """
        default_types = [
            ('THUÊ', 'Thuế', 'Các loại thuế phải nộp'),
            ('PHÍ', 'Phí', 'Các loại phí'),
            ('LỆ PHÍ', 'Lệ phí', 'Các loại lệ phí'),
            ('TIỀN THUÊ ĐẤT', 'Tiền thuê đất', 'Tiền thuê đất hàng năm'),
            ('KHÁC', 'Khác', 'Các nghĩa vụ tài chính khác')
        ]
        
        for loai_no, ten_no, mo_ta in default_types:
            TaxService.create_debt_type(loai_no, ten_no, mo_ta)
