"""
User Model with Flask-Login Integration
Handles user authentication and role-based access control
"""
from datetime import datetime
from typing import Optional
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from models import db


class User(db.Model, UserMixin):
    """
    User Model for Authentication and Authorization
    """
    __tablename__ = 'users'
    
    id: int = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email: str = db.Column(db.String(120), unique=True, nullable=True, index=True)
    password_hash: str = db.Column(db.String(255), nullable=False)
    full_name: str = db.Column(db.String(255), nullable=True)
    role: str = db.Column(
        db.String(20), 
        nullable=False, 
        default='USER',
        server_default='USER'
    )
    is_active: bool = db.Column(db.Boolean, nullable=False, default=True, server_default='true')
    last_login: Optional[datetime] = db.Column(db.DateTime, nullable=True)
    created_at: datetime = db.Column(
        db.DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        server_default=db.func.current_timestamp()
    )
    updated_at: Optional[datetime] = db.Column(
        db.DateTime, 
        nullable=True, 
        onupdate=datetime.utcnow
    )
    
    imports = db.relationship('ImportHistory', back_populates='imported_by_user', lazy='dynamic')
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
    
    def __init__(self, **kwargs):
        if 'password' in kwargs:
            self.set_password(kwargs.pop('password'))
        super(User, self).__init__(**kwargs)
    
    def set_password(self, password: str) -> None:
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters long")
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    @property
    def is_admin(self) -> bool:
        return self.role == 'ADMIN'
    
    @property
    def is_regular_user(self) -> bool:
        return self.role == 'USER'
    
    def update_last_login(self) -> None:
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def promote_to_admin(self) -> None:
        self.role = 'ADMIN'
        db.session.commit()
    
    def demote_to_user(self) -> None:
        self.role = 'USER'
        db.session.commit()
    
    def deactivate(self) -> None:
        self.is_active = False
        db.session.commit()
    
    def activate(self) -> None:
        self.is_active = True
        db.session.commit()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def get_id(self) -> str:
        return str(self.id)
    
    @classmethod
    def create_admin(cls, username: str, password: str, email: Optional[str] = None, 
                     full_name: Optional[str] = None) -> 'User':
        try:
            admin = cls(
                username=username,
                email=email,
                full_name=full_name,
                role='ADMIN',
                is_active=True
            )
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            return admin
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Failed to create admin: {str(e)}")
    
    @classmethod
    def find_by_username(cls, username: str) -> Optional['User']:
        return cls.query.filter_by(username=username).first()
    
    @classmethod
    def find_by_email(cls, email: str) -> Optional['User']:
        return cls.query.filter_by(email=email).first()
