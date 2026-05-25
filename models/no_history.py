"""
Nợ History Model
Tracks changes in tax obligations over time for audit trail and compliance
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db

if TYPE_CHECKING:
    from models.nnt import NNT
    from models.users import User


class NO_HISTORY(db.Model):
    """
    Nợ History Model (Audit Trail for Tax Obligation Changes)
    
    Maintains a historical record of all changes to taxpayer obligations.
    """
    __tablename__ = 'no_history'
    
    # Primary Key
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True, autoincrement=True)
    
    # Foreign Keys
    ID_NNT: Mapped[str] = mapped_column(
        db.String(20), 
        db.ForeignKey('nnt.MST', onupdate='CASCADE', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    ID_NO: Mapped[Optional[int]] = mapped_column(
        db.Integer,
        db.ForeignKey('loai_no.ID_NO', onupdate='SET NULL', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # Historical Values
    NO_CU: Mapped[float] = mapped_column(db.Numeric(15, 2), nullable=False, default=0.00)
    NO_MOI: Mapped[float] = mapped_column(db.Numeric(15, 2), nullable=False, default=0.00)
    
    # Change Metadata
    SESSION_ID: Mapped[Optional[str]] = mapped_column(db.String(100), nullable=True, index=True)
    ACTION_TYPE: Mapped[str] = mapped_column(
        db.String(20), 
        nullable=False, 
        default='IMPORT',
        server_default='IMPORT'
    )
    CHANGES: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    
    # User Tracking
    CREATED_BY: Mapped[Optional[int]] = mapped_column(
        db.Integer,
        db.ForeignKey('users.id', onupdate='SET NULL', ondelete='SET NULL'),
        nullable=True
    )
    
    # Timestamp
    UPDATED_AT: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=db.func.current_timestamp()
    )
    
    # Relationships
    nnt: Mapped["NNT"] = relationship("NNT", back_populates="no_history")
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[CREATED_BY])
    
    # Table indexes
    __table_args__ = (
        Index('ix_no_history_nnt_time', 'ID_NNT', 'UPDATED_AT'),
        Index('ix_no_history_session', 'SESSION_ID'),
        Index('ix_no_history_action', 'ACTION_TYPE'),
    )
    
    def __repr__(self) -> str:
        return f"<NO_HISTORY(id={self.id}, ID_NNT='{self.ID_NNT}', NO_CU={self.NO_CU}, NO_MOI={self.NO_MOI})>"
    
    @property
    def change_amount(self) -> float:
        """Calculate the change in obligation amount"""
        return float(self.NO_MOI or 0) - float(self.NO_CU or 0)
    
    @property
    def is_increase(self) -> bool:
        """Check if obligation increased"""
        return self.change_amount > 0
    
    @property
    def is_decrease(self) -> bool:
        """Check if obligation decreased"""
        return self.change_amount < 0
    
    @property
    def is_new_record(self) -> bool:
        """Check if this is a new obligation record"""
        return float(self.NO_CU or 0) == 0 and float(self.NO_MOI or 0) > 0
    
    @property
    def is_fully_paid(self) -> bool:
        """Check if obligation was fully paid off"""
        return float(self.NO_CU or 0) > 0 and float(self.NO_MOI or 0) == 0
    
    def to_dict(self) -> dict:
        """Convert NO_HISTORY to dictionary"""
        return {
            'id': self.id,
            'ID_NNT': self.ID_NNT,
            'ID_NO': self.ID_NO,
            'NO_CU': float(self.NO_CU or 0),
            'NO_MOI': float(self.NO_MOI or 0),
            'change_amount': self.change_amount,
            'is_increase': self.is_increase,
            'is_decrease': self.is_decrease,
            'SESSION_ID': self.SESSION_ID,
            'ACTION_TYPE': self.ACTION_TYPE,
            'CHANGES': self.CHANGES,
            'CREATED_BY': self.CREATED_BY,
            'UPDATED_AT': self.UPDATED_AT.isoformat() if self.UPDATED_AT else None
        }
    
    @classmethod
    def create_record(cls, id_nnt: str, no_cu: float, no_moi: float,
                      session_id: Optional[str] = None,
                      action_type: str = 'IMPORT',
                      id_no: Optional[int] = None,
                      created_by: Optional[int] = None) -> 'NO_HISTORY':
        """Factory method to create a history record."""
        try:
            record = cls(
                ID_NNT=id_nnt,
                NO_CU=no_cu,
                NO_MOI=no_moi,
                SESSION_ID=session_id,
                ACTION_TYPE=action_type,
                ID_NO=id_no,
                CREATED_BY=created_by
            )
            db.session.add(record)
            db.session.commit()
            return record
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Failed to create history record: {str(e)}")
    
    @classmethod
    def get_history_for_nnt(cls, mst: str, limit: int = 100) -> list:
        """Get change history for a specific taxpayer."""
        return cls.query.filter_by(ID_NNT=mst)\
                       .order_by(cls.UPDATED_AT.desc())\
                       .limit(limit)\
                       .all()
    
    @classmethod
    def get_recent_changes(cls, days: int = 30, limit: int = 100) -> list:
        """Get recent obligation changes across all taxpayers."""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        return cls.query.filter(cls.UPDATED_AT >= cutoff_date)\
                       .order_by(cls.UPDATED_AT.desc())\
                       .limit(limit)\
                       .all()
