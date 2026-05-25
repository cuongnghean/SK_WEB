"""
Import History Model
Tracks Excel file imports for audit and monitoring purposes
"""
from datetime import datetime
from typing import Optional

from models import db


class ImportHistory(db.Model):
    """
    Import History Model
    """
    __tablename__ = 'import_history'
    
    id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_name: str = db.Column(db.String(255), nullable=False)
    file_size: int = db.Column(db.BigInteger, nullable=True)
    total_rows: int = db.Column(db.Integer, nullable=False, default=0)
    success_rows: int = db.Column(db.Integer, nullable=False, default=0)
    failed_rows: int = db.Column(db.Integer, nullable=False, default=0)
    error_details: Optional[str] = db.Column(db.Text, nullable=True)
    import_time: float = db.Column(db.Float, nullable=True)
    
    import_by: int = db.Column(
        db.Integer, 
        db.ForeignKey('users.id', onupdate='SET NULL', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    status: str = db.Column(
        db.String(20), 
        nullable=False, 
        default='PENDING',
        server_default='PENDING'
    )
    
    created_at: datetime = db.Column(
        db.DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        server_default=db.func.current_timestamp()
    )
    completed_at: Optional[datetime] = db.Column(db.DateTime, nullable=True)
    
    imported_by_user = db.relationship('User', back_populates='imports')
    
    __table_args__ = (
        db.Index('ix_import_history_created', 'created_at'),
        db.Index('ix_import_history_status', 'status'),
    )
    
    def __repr__(self) -> str:
        return f"<ImportHistory(id={self.id}, file_name='{self.file_name}', status='{self.status}')>"
    
    def mark_completed(self, success_rows: int, failed_rows: int, error_details: Optional[str] = None) -> None:
        self.success_rows = success_rows
        self.failed_rows = failed_rows
        self.error_details = error_details
        self.status = 'COMPLETED' if failed_rows == 0 else 'PARTIAL'
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def mark_failed(self, error_message: str) -> None:
        self.status = 'FAILED'
        self.error_details = error_message
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def update_progress(self, processed_rows: int) -> None:
        self.total_rows = processed_rows
        db.session.commit()
    
    @property
    def success_rate(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return round((self.success_rows / self.total_rows) * 100, 2)
    
    @property
    def is_completed(self) -> bool:
        return self.status in ('COMPLETED', 'PARTIAL', 'FAILED')
    
    @property
    def is_successful(self) -> bool:
        return self.status == 'COMPLETED'
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'total_rows': self.total_rows,
            'success_rows': self.success_rows,
            'failed_rows': self.failed_rows,
            'success_rate': self.success_rate,
            'import_time': self.import_time,
            'import_by': self.imported_by_user.username if self.imported_by_user else None,
            'status': self.status,
            'error_details': self.error_details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
