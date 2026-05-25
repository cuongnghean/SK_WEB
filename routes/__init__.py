"""
Routes Package Initialization
Blueprint registration for all route modules
"""
from flask import Blueprint

# Create blueprints
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
public_bp = Blueprint('public', __name__, url_prefix='/')
user_bp = Blueprint('user', __name__, url_prefix='/user')

# Import routes to register them with blueprints
from routes import auth, admin, public, user

__all__ = [
    'auth_bp',
    'admin_bp',
    'public_bp',
    'user_bp'
]
