"""
Configuration Module for Tax Obligation Management System
Handles environment variables and database connection pooling for Supabase PostgreSQL
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """
    Base configuration class with Supabase PostgreSQL connection settings.
    Implements connection pooling optimized for cloud-based PostgreSQL (Supabase).
    """
    
    # Base Directory
    BASE_DIR = Path(__file__).parent.absolute()
    
    # Security Keys
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production-min-32-chars'
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'dev-wtf-csrf-key-change-in-production'
    
    # Application Environment
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    APP_ENV = os.environ.get('APP_ENV', 'production')
    
    # Supabase PostgreSQL Database Connection
    # Connection string with SSL/TLS required for Supabase Cloud
    # Format: postgresql://user:password@host:port/dbname?sslmode=require
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:password@aws-0 region.pooler.supabase.com:6543/postgres?sslmode=require'
    )
    
    # SQLAlchemy Engine Options for Supabase Connection Pooling
    # Optimized settings for cloud PostgreSQL with SSL
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,              # Number of connections to maintain in the pool
        'max_overflow': 20,            # Additional connections when pool is exhausted
        'pool_recycle': 300,          # Recycle connections after 5 minutes (prevents stale connections)
        'pool_pre_ping': True,         # Verify connection validity before using (handles idle timeouts)
        'pool_timeout': 30,            # Wait up to 30 seconds for a connection from pool
        'echo': False,                 # Set to True for SQL query logging (debugging only)
        'connect_args': {
            'sslmode': 'require',      # Enforce SSL/TLS encryption
            'connect_timeout': 10,     # Connection timeout in seconds
            'application_name': 'TaxObligationSystem',  # Identify app in PostgreSQL logs
        }
    }
    
    # SQLAlchemy Settings
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Set True to log SQL queries (use only in development)
    
    # Session Configuration
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    
    # Cookie Security Settings
    SESSION_COOKIE_SECURE = False                   # Override in ProductionConfig
    SESSION_COOKIE_HTTPONLY = True                  # Prevent JavaScript access
    SESSION_COOKIE_SAMESITE = 'Lax'                # CSRF protection
    
    # WTForms Configuration
    WTF_CSRF_ENABLED = False  # Disabled for debugging
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    
    # Rate Limiting Configuration
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"
    RATELIMIT_STORAGE_URL = "memory://"
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_HEADERS_ENABLED = True
    
    # Upload Configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file size
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    
    # Captcha Configuration
    CAPTCHA_LENGTH = 4
    CAPTCHA_EXPIRY = 300  # 5 minutes
    CAPTCHA_IMAGE_SIZE = (120, 40)
    CAPTCHA_FONT_SIZE = 28
    
    # Logging Configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.path.join(BASE_DIR, 'logs', 'app.log')
    
    # Batch Processing Configuration
    BATCH_SIZE = 5000  # Rows per batch for Excel import
    CHUNK_SIZE = 1000  # Chunks for reading large Excel files
    
    # Admin Default Credentials
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
    
    @classmethod
    def init_app(cls):
        """Initialize application-specific configurations"""
        # Ensure upload folder exists
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        
        # Ensure logs folder exists
        log_dir = os.path.join(cls.BASE_DIR, 'logs')
        os.makedirs(log_dir, exist_ok=True)


class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development
    RATELIMIT_ENABLED = False  # Disable rate limiting during development


class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    SESSION_COOKIE_SECURE = True
    RATELIMIT_ENABLED = True


class TestingConfig(Config):
    """Testing environment configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


# Configuration mapping
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig
}


def get_config():
    """
    Get configuration based on APP_ENV environment variable.
    Falls back to production config if not specified.
    """
    env = os.environ.get('APP_ENV', 'production').lower()
    return config_by_name.get(env, ProductionConfig)
