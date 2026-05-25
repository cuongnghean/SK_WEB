"""
Search Log Model
Tracks public search queries for analytics, DDoS protection, and audit compliance
"""
from datetime import datetime
from typing import Optional

from models import db


class SearchLog(db.Model):
    """
    Search Log Model
    """
    __tablename__ = 'search_log'
    
    id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    IP_ADDRESS: str = db.Column(
        db.String(45),
        nullable=False,
        index=True
    )
    
    SEARCH_TYPE: str = db.Column(
        db.String(10), 
        nullable=False,
        index=True
    )
    
    SEARCH_VALUE: str = db.Column(
        db.String(50), 
        nullable=False
    )
    
    USER_AGENT: Optional[str] = db.Column(db.String(500), nullable=True)
    
    RESULT_COUNT: int = db.Column(db.Integer, nullable=False, default=0)
    RESPONSE_TIME: float = db.Column(db.Float, nullable=True)
    
    STATUS: str = db.Column(
        db.String(20),
        nullable=False,
        default='SUCCESS',
        server_default='SUCCESS'
    )
    ERROR_MESSAGE: Optional[str] = db.Column(db.Text, nullable=True)
    
    CREATED_AT: datetime = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=db.func.current_timestamp(),
        index=True
    )
    
    __table_args__ = (
        db.Index('ix_search_log_ip_time', 'IP_ADDRESS', 'CREATED_AT'),
        db.Index('ix_search_log_type_time', 'SEARCH_TYPE', 'CREATED_AT'),
        db.Index('ix_search_log_status', 'STATUS'),
    )
    
    def __repr__(self) -> str:
        return f"<SearchLog(id={self.id}, IP='{self.IP_ADDRESS}', SEARCH_TYPE='{self.SEARCH_TYPE}', STATUS='{self.STATUS}')>"
    
    def mark_success(self, result_count: int, response_time: float) -> None:
        self.RESULT_COUNT = result_count
        self.RESPONSE_TIME = response_time
        self.STATUS = 'SUCCESS'
        db.session.commit()
    
    def mark_not_found(self, response_time: float) -> None:
        self.RESULT_COUNT = 0
        self.RESPONSE_TIME = response_time
        self.STATUS = 'NOT_FOUND'
        db.session.commit()
    
    def mark_error(self, error_message: str, response_time: float) -> None:
        self.RESULT_COUNT = 0
        self.RESPONSE_TIME = response_time
        self.STATUS = 'ERROR'
        self.ERROR_MESSAGE = error_message
        db.session.commit()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'IP_ADDRESS': self.IP_ADDRESS,
            'SEARCH_TYPE': self.SEARCH_TYPE,
            'SEARCH_VALUE': self.SEARCH_VALUE,
            'RESULT_COUNT': self.RESULT_COUNT,
            'RESPONSE_TIME': self.RESPONSE_TIME,
            'STATUS': self.STATUS,
            'ERROR_MESSAGE': self.ERROR_MESSAGE,
            'CREATED_AT': self.CREATED_AT.isoformat() if self.CREATED_AT else None
        }
    
    @classmethod
    def log_search(cls, ip_address: str, search_type: str, search_value: str,
                  user_agent: Optional[str] = None,
                  result_count: int = 0,
                  response_time: float = 0,
                  status: str = 'SUCCESS',
                  error_message: Optional[str] = None) -> Optional['SearchLog']:
        try:
            log_entry = cls(
                IP_ADDRESS=ip_address,
                SEARCH_TYPE=search_type,
                SEARCH_VALUE=search_value,
                USER_AGENT=user_agent,
                RESULT_COUNT=result_count,
                RESPONSE_TIME=response_time,
                STATUS=status,
                ERROR_MESSAGE=error_message
            )
            db.session.add(log_entry)
            db.session.commit()
            return log_entry
        except Exception:
            db.session.rollback()
            return None
    
    @classmethod
    def get_recent_by_ip(cls, ip_address: str, minutes: int = 60) -> int:
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        return cls.query.filter(
            cls.IP_ADDRESS == ip_address,
            cls.CREATED_AT >= cutoff_time
        ).count()
    
    @classmethod
    def get_hourly_stats(cls, hours: int = 24) -> dict:
        from datetime import timedelta
        from sqlalchemy import func, extract
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        results = db.session.query(
            extract('hour', cls.CREATED_AT).label('hour'),
            func.count(cls.id).label('count')
        ).filter(
            cls.CREATED_AT >= cutoff_time
        ).group_by(
            extract('hour', cls.CREATED_AT)
        ).all()
        
        return {int(r.hour): r.count for r in results}
    
    @classmethod
    def cleanup_old_logs(cls, days: int = 90) -> int:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        deleted = cls.query.filter(cls.CREATED_AT < cutoff_date).delete()
        db.session.commit()
        return deleted
