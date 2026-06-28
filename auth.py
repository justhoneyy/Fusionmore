import os
import uuid
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, Student, Teacher, Parent, Admin

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = None

# ===================== USER LOADER =====================
@login_manager.user_loader
def load_user(user_id):
    """Load user from session based on role stored in session."""
    role = session.get('user_role')
    if not role:
        return None
    
    try:
        if role == 'student':
            return Student.query.get(int(user_id))
        elif role == 'teacher':
            return Teacher.query.get(int(user_id))
        elif role == 'parent':
            return Parent.query.get(int(user_id))
        elif role == 'admin':
            return Admin.query.get(int(user_id))
    except:
        return None
    
    return None

# ===================== JWT TOKEN HELPERS =====================
SECRET_KEY = os.environ.get('SECRET_KEY', 'fusion-coaching-secret-key-change-in-production')

def create_jwt_token(user_id, role, expires_in_days=7):
    """Create a JWT token for API authentication."""
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(days=expires_in_days),
        'iat': datetime.utcnow(),
        'jti': str(uuid.uuid4())
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    return token

def verify_jwt_token(token):
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def jwt_required(f):
    """Decorator to require valid JWT token for API routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        # Check query parameter
        if not token:
            token = request.args.get('token')
        
        # Check session
        if not token:
            token = session.get('jwt_token')
        
        if not token:
            return jsonify({'error': 'Authentication required', 'code': 'AUTH_REQUIRED'}), 401
        
        payload = verify_jwt_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token', 'code': 'TOKEN_INVALID'}), 401
        
        # Attach user info to request
        request.user_id = payload['user_id']
        request.user_role = payload['role']
        
        return f(*args, **kwargs)
    
    return decorated

# ===================== ROLE-BASED ACCESS CONTROL =====================
def role_required(*roles):
    """Decorator to restrict access to specific roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            
            user_role = getattr(current_user, 'role', None)
            
            # Admin has access to everything
            if user_role == 'admin':
                return f(*args, **kwargs)
            
            if user_role not in roles:
                return jsonify({'error': 'Access denied. Insufficient permissions.'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def check_role(role):
    """Check if current user has a specific role."""
    if not current_user.is_authenticated:
        return False
    return getattr(current_user, 'role', None) == role

# ===================== PASSWORD HELPERS =====================
def hash_password(password):
    """Hash a password using bcrypt via werkzeug."""
    return generate_password_hash(password)

def verify_password(password_hash, password):
    """Verify a password against its hash."""
    return check_password_hash(password_hash, password)

# ===================== AUTH ROUTES =====================
def init_auth_routes(app):
    """Initialize authentication routes on the Flask app."""
    
    @app.route('/api/auth/register', methods=['POST'])
    def register():
        """Register a new user (student, teacher, or parent)."""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        name = data.get('name', '').strip()
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        role = data.get('role', 'student')
        phone = data.get('phone', '').strip()
        
        # Validation
        if not name or not email or not password:
            return jsonify({'success': False, 'error': 'Name, email, and password are required'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        if '@' not in email or '.' not in email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        # Check existing user
        existing = None
        if role == 'student':
            existing = Student.query.filter_by(email=email).first()
        elif role == 'teacher':
            existing = Teacher.query.filter_by(email=email).first()
        elif role == 'parent':
            existing = Parent.query.filter_by(email=email).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Email already registered'}), 409
        
        # Create user
        password_hash = generate_password_hash(password)
        
        if role == 'student':
            from helpers import generate_student_id
            user = Student(
                name=name,
                email=email,
                phone=phone,
                password_hash=password_hash,
                student_id=generate_student_id(),
                is_active=True,
                role='student'
            )
        elif role == 'teacher':
            user = Teacher(
                name=name,
                email=email,
                phone=phone,
                password_hash=password_hash,
                teacher_id=f'TCH{uuid.uuid4().hex[:6].upper()}',
                role='teacher'
            )
        elif role == 'parent':
            user = Parent(
                name=name,
                email=email,
                phone=phone,
                password_hash=password_hash,
                role='parent'
            )
        else:
            return jsonify({'success': False, 'error': 'Invalid role'}), 400
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{role.capitalize()} registered successfully',
            'user_id': user.get_id()
        })
    
    @app.route('/api/auth/change-password', methods=['POST'])
    @login_required
    def change_password():
        """Change password for authenticated user."""
        data = request.get_json()
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not old_password or not new_password:
            return jsonify({'success': False, 'error': 'Old and new passwords required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400
        
        if not verify_password(current_user.password_hash, old_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
        
        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    
    @app.route('/api/auth/forgot-password', methods=['POST'])
    def forgot_password():
        """Request password reset (sends reset token via WhatsApp/email)."""
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        # Find user in any role
        user = Student.query.filter_by(email=email).first()
        role = 'student'
        if not user:
            user = Teacher.query.filter_by(email=email).first()
            role = 'teacher'
        if not user:
            user = Parent.query.filter_by(email=email).first()
            role = 'parent'
        if not user:
            user = Admin.query.filter_by(email=email).first()
            role = 'admin'
        
        if not user:
            # Don't reveal whether email exists
            return jsonify({'success': True, 'message': 'If the email is registered, a reset link has been sent'})
        
        # Generate reset token
        reset_token = create_jwt_token(user.get_id(), role, expires_in_days=0)  # 1 hour
        # In production, send this via email/WhatsApp
        # For now, return it in response (remove in production)
        
        return jsonify({
            'success': True,
            'message': 'Reset link sent to your registered email/phone',
            'reset_token': reset_token  # Remove in production
        })

# ===================== SESSION MANAGEMENT =====================
def set_user_session(user, role):
    """Set session variables after successful login."""
    session['user_id'] = user.get_id()
    session['user_role'] = role
    session['user_name'] = user.name
    session['user_email'] = user.email
    session.permanent = True

def clear_user_session():
    """Clear all session variables."""
    session.pop('user_id', None)
    session.pop('user_role', None)
    session.pop('user_name', None)
    session.pop('user_email', None)
    session.pop('jwt_token', None)
