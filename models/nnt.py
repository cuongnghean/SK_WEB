"""
NGƯỜI NỘP THUẾ (Taxpayer) Model
Defines the main entity for taxpayers with their identification and obligation status.
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import db

if TYPE_CHECKING:
    from models.no_history import NO_HISTORY


class NNT(db.Model):
    """
    Người Nộp Thuế (Taxpayer) Model
    """
    __tablename__ = 'nnt'
    
    # Primary Key - Mã Số Thuế (Tax Identification Number)
    MST: Mapped[str] = mapped_column(db.String(20), primary_key=True, unique=True)
    
    # Identification Documents (indexed for search performance)
    CCCD: Mapped[Optional[str]] = mapped_column(db.String(15), nullable=True, index=True)
    CMT: Mapped[Optional[str]] = mapped_column(db.String(15), nullable=True, index=True)
    
    # Personal Information
    HO_TEN: Mapped[str] = mapped_column(db.String(255), nullable=False)
    DIA_CHI: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    
    # Business Status
    TRANG_THAI_HD: Mapped[str] = mapped_column(
        db.String(50), 
        nullable=False, 
        default='Active',
        server_default='Active'
    )
    
    # Tax Obligation Status
    TRANG_THAI_NO: Mapped[str] = mapped_column(
        db.String(50), 
        nullable=False, 
        default='KHONG_NO',
        server_default='KHONG_NO'
    )
    
    # Timestamps
    NGAY_TAO: Mapped[datetime] = mapped_column(
        db.DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        server_default=db.func.current_timestamp()
    )
    LAST_SYNC: Mapped[Optional[datetime]] = mapped_column(
        db.DateTime, 
        nullable=True, 
        onupdate=datetime.utcnow
    )
    
    # Relationships
    tax_obligations: Mapped[List["TT_NO"]] = relationship(
        "TT_NO", 
        back_populates="nnt", 
        cascade="all, delete-orphan",
        lazy="select"
    )
    no_history: Mapped[List["NO_HISTORY"]] = relationship(
        "NO_HISTORY", 
        back_populates="nnt",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Table indexes
    __table_args__ = (
        Index('ix_nnt_search', 'MST', 'CCCD'),
        Index('ix_nnt_ten', 'HO_TEN'),
        Index('ix_nnt_trang_thai_no', 'TRANG_THAI_NO'),
        Index('ix_nnt_trang_thai_hd', 'TRANG_THAI_HD'),
        Index('ix_nnt_ngay_tao', 'NGAY_TAO'),
    )
    
    def __repr__(self) -> str:
        return f"<NNT(MST='{self.MST}', HO_TEN='{self.HO_TEN}', TRANG_THAI_NO='{self.TRANG_THAI_NO}')>"
    
    @property
    def total_debt(self) -> float:
        """Calculate total outstanding tax obligation"""
        return sum(float(obligation.NO_TAM_TINH or 0) for obligation in self.tax_obligations)
    
    @property
    def is_active(self) -> bool:
        """Check if taxpayer is active"""
        return self.TRANG_THAI_HD == 'Active'
    
    @property
    def has_debt(self) -> bool:
        """Check if taxpayer has outstanding obligations"""
        return self.TRANG_THAI_NO == 'CO_NO'
    
    def update_debt_status(self) -> None:
        """Update debt status based on total obligation amount"""
        total = self.total_debt
        if total > 0:
            self.TRANG_THAI_NO = 'CO_NO'
        else:
            self.TRANG_THAI_NO = 'KHONG_NO'
    
    def to_dict(self, masked: bool = False) -> dict:
        """Convert NNT to dictionary."""
        from utils.security import mask_cccd
        
        data = {
            'MST': self.MST,
            'HO_TEN': self.HO_TEN,
            'DIA_CHI': self.DIA_CHI,
            'TRANG_THAI_HD': self.TRANG_THAI_HD,
            'TRANG_THAI_NO': self.TRANG_THAI_NO,
            'NGAY_TAO': self.NGAY_TAO.isoformat() if self.NGAY_TAO else None,
            'LAST_SYNC': self.LAST_SYNC.isoformat() if self.LAST_SYNC else None,
            'total_debt': self.total_debt
        }
        
        if masked:
            data['CCCD'] = mask_cccd(self.CCCD) if self.CCCD else None
            data['CMT'] = None
        else:
            data['CCCD'] = self.CCCD
            data['CMT'] = self.CMT
        
        return data


class LOAI_NO(db.Model):
    """LOẠI NỢ (Debt Type) Model"""
    __tablename__ = 'loai_no'
    
    ID_NO: Mapped[int] = mapped_column(db.Integer, primary_key=True, autoincrement=True)
    LOAI_NO: Mapped[str] = mapped_column(db.String(100), nullable=False, unique=True)
    TEN_NO: Mapped[str] = mapped_column(db.String(255), nullable=False)
    MO_TA: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    
    obligations: Mapped[List["TT_NO"]] = relationship(
        "TT_NO", 
        back_populates="loai_no",
        lazy="dynamic"
    )
    
    def __repr__(self) -> str:
        return f"<LOAI_NO(ID_NO={self.ID_NO}, LOAI_NO='{self.LOAI_NO}', TEN_NO='{self.TEN_NO}')>"
    
    def to_dict(self) -> dict:
        return {
            'ID_NO': self.ID_NO,
            'LOAI_NO': self.LOAI_NO,
            'TEN_NO': self.TEN_NO,
            'MO_TA': self.MO_TA
        }


class TT_NO(db.Model):
    """THÔNG TIN NỢ (Tax Obligation Detail) Model"""
    __tablename__ = 'tt_no'
    
    ID: Mapped[int] = mapped_column(db.Integer, primary_key=True, autoincrement=True)
    
    ID_NNT: Mapped[str] = mapped_column(
        db.String(20), 
        db.ForeignKey('nnt.MST', onupdate='CASCADE', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    ID_NO: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey('loai_no.ID_NO', onupdate='CASCADE', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    
    NO_TAM_TINH: Mapped[float] = mapped_column(
        db.Numeric(15, 2),
        nullable=False,
        default=0.00,
        server_default='0.00'
    )
    
    GHI_CHU: Mapped[Optional[str]] = mapped_column(db.Text, nullable=True)
    UPDATED_AT: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=db.func.current_timestamp(),
        onupdate=datetime.utcnow
    )
    CREATED_AT: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=db.func.current_timestamp()
    )
    
    # Relationships
    nnt: Mapped["NNT"] = relationship("NNT", back_populates="tax_obligations")
    loai_no: Mapped["LOAI_NO"] = relationship("LOAI_NO", back_populates="obligations")
    
    __table_args__ = (
        Index('ix_tt_no_nnt_no', 'ID_NNT', 'ID_NO'),
        Index('ix_tt_no_updated', 'UPDATED_AT'),
    )
    
    def __repr__(self) -> str:
        return f"<TT_NO(ID={self.ID}, ID_NNT='{self.ID_NNT}', NO_TAM_TINH={self.NO_TAM_TINH})>"
    
    def to_dict(self) -> dict:
        return {
            'ID': self.ID,
            'ID_NNT': self.ID_NNT,
            'ID_NO': self.ID_NO,
            'LOAI_NO': self.loai_no.TEN_NO if self.loai_no else None,
            'NO_TAM_TINH': float(self.NO_TAM_TINH or 0),
            'GHI_CHU': self.GHI_CHU,
            'UPDATED_AT': self.UPDATED_AT.isoformat() if self.UPDATED_AT else None,
            'CREATED_AT': self.CREATED_AT.isoformat() if self.CREATED_AT else None
        }
