"""
Models Package Initialization
Exports all database models for the Tax Obligation Management System
"""
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy instance
db = SQLAlchemy()

# Import models to make them available when importing from models package
from models.nnt import NNT, LOAI_NO, TT_NO
from models.users import User
from models.import_history import ImportHistory
from models.no_history import NO_HISTORY
from models.search_log import SearchLog

__all__ = [
    'db',
    'NNT',
    'LOAI_NO',
    'TT_NO',
    'User',
    'ImportHistory',
    'NO_HISTORY',
    'SearchLog'
]
