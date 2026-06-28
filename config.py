import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fusion-coaching-secret-key-change-in-production-2026')
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql://fusion_user:fusion_pass@localhost:5432/fusion_coaching'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Fix for Render postgres:// scheme
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    
    # Session
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
    
    # File Uploads
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm', 'ppt', 'pptx', 'doc', 'docx'}
    
    # Twilio WhatsApp
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
    
    # Razorpay
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
    
    # Fee Configuration
    FEE_GRACE_PERIOD_DAYS = int(os.environ.get('FEE_GRACE_PERIOD_DAYS', '7'))
    
    # Redis/Celery
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # Admin credentials
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@fusioncoaching.in')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@Fusion2026')
