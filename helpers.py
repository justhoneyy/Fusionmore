import os
import re
import uuid
import hashlib
import logging
from datetime import datetime, date, timedelta
from decimal import Decimal

from flask import current_app
from twilio.rest import Client as TwilioClient
import bleach

from models import db, Student, Teacher, Parent, Admin, Class, Subject, StudentClass
from models import Attendance, Marks, FeePayment, FeeReminder, WhatsAppLog, AuditLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== TWILIO WHATSAPP INTEGRATION =====================
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', '+14155238886')

def get_twilio_client():
    """Initialize Twilio client with credentials."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured")
        return None
    try:
        return TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        logger.error(f"Failed to initialize Twilio client: {e}")
        return None

def format_phone(phone):
    """Format phone number for WhatsApp (E.164 format with country code)."""
    if not phone:
        return None
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', str(phone))
    
    # If it starts with 0, remove it
    if digits.startswith('0'):
        digits = digits[1:]
    
    # If it doesn't have country code, assume India (+91)
    if len(digits) == 10:
        digits = '91' + digits
    elif len(digits) == 11 and digits.startswith('0'):
        digits = '91' + digits[1:]
    
    # Ensure it starts with +
    if not digits.startswith('+'):
        digits = '+' + digits
    
    # Validate: must be between 10 and 15 digits total (with +)
    phone_digits = digits.lstrip('+')
    if len(phone_digits) < 10 or len(phone_digits) > 15:
        return None
    
    return digits

def send_whatsapp_message(to, body, media_url=None):
    """Send a WhatsApp message via Twilio API.
    
    Args:
        to: Recipient phone number (will be formatted)
        body: Message text content
        media_url: Optional media URL to attach
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    client = get_twilio_client()
    if not client:
        logger.error("Twilio client not available")
        log_whatsapp(to, body, 'failed', 'Twilio not configured')
        return False
    
    formatted_to = format_phone(to)
    if not formatted_to:
        logger.error(f"Invalid phone number: {to}")
        log_whatsapp(to, body, 'failed', 'Invalid phone number')
        return False
    
    try:
        message_data = {
            'from': f'whatsapp:{TWILIO_WHATSAPP_NUMBER}',
            'body': body,
            'to': f'whatsapp:{formatted_to}'
        }
        
        if media_url:
            message_data['media_url'] = [media_url]
        
        message = client.messages.create(**message_data)
        
        logger.info(f"WhatsApp sent to {formatted_to}: SID {message.sid}")
        log_whatsapp(to, body, 'sent', f"Twilio SID: {message.sid}")
        return True
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to send WhatsApp to {formatted_to}: {error_msg}")
        log_whatsapp(to, body, 'failed', error_msg)
        return False

def log_whatsapp(phone, message, status, notes=''):
    """Log WhatsApp message to database for audit."""
    try:
        log = WhatsAppLog(
            phone_number=format_phone(phone) or phone,
            message=message[:500],
            status=status,
            notes=notes[:500],
            sent_at=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log WhatsApp: {e}")
        db.session.rollback()

# ===================== FEE REMINDERS =====================
def check_fee_status(student_id):
    """Check if a student's fee is overdue and locked.
    
    Returns:
        bool: True if student is locked (fee overdue beyond grace period)
    """
    reminder = FeeReminder.query.filter_by(
        student_id=student_id,
        status='pending'
    ).first()
    
    if not reminder:
        return False
    
    today = date.today()
    
    # If due date has passed
    if reminder.due_date and today > reminder.due_date:
        # If grace period has also passed
        if reminder.grace_end_date and today > reminder.grace_end_date:
            return True  # Locked
        return False  # Overdue but within grace period
    
    return False  # Not yet due

def send_fee_reminders():
    """Send WhatsApp fee reminders to all students with overdue fees.
    
    Returns:
        dict: Summary of sent/failed counts
    """
    today = date.today()
    
    # Find all pending fee reminders where due date is within next 7 days or past due
    reminders = FeeReminder.query.filter(
        FeeReminder.status == 'pending',
        FeeReminder.due_date <= today + timedelta(days=7)
    ).all()
    
    sent_count = 0
    failed_count = 0
    results = []
    
    for reminder in reminders:
        student = Student.query.get(reminder.student_id)
        if not student or not student.phone:
            failed_count += 1
            continue
        
        # Calculate days remaining
        days_left = (reminder.due_date - today).days if reminder.due_date else 0
        
        if days_left > 0:
            message = (
                f"📚 *Fusion Coaching - Fee Reminder*\n\n"
                f"Dear {student.name},\n\n"
                f"This is a reminder that your fee of *₹{reminder.amount}* is due in *{days_left} day{'s' if days_left != 1 else ''}*.\n\n"
                f"📅 Due Date: {reminder.due_date.strftime('%d %b %Y')}\n"
                f"⏳ Grace Period: {reminder.grace_days} days after due date\n\n"
                f"Please pay online through your student dashboard or visit the office.\n\n"
                f"Thank you,\n"
                f"*Fusion Coaching Team*"
            )
        elif days_left == 0:
            message = (
                f"⚠️ *Fusion Coaching - Fee Due Today*\n\n"
                f"Dear {student.name},\n\n"
                f"Your fee of *₹{reminder.amount}* is due *TODAY*.\n\n"
                f"📅 Due Date: {reminder.due_date.strftime('%d %b %Y')}\n"
                f"⏳ Grace Period: {reminder.grace_days} days available\n\n"
                f"Pay now to avoid late fees. Log in to your dashboard or visit the office.\n\n"
                f"Thank you,\n"
                f"*Fusion Coaching Team*"
            )
        else:  # Overdue
            grace_end = reminder.grace_end_date or (reminder.due_date + timedelta(days=reminder.grace_days))
            grace_left = (grace_end - today).days
            
            if grace_left > 0:
                message = (
                    f"🔴 *Fusion Coaching - Fee OVERDUE*\n\n"
                    f"Dear {student.name},\n\n"
                    f"Your fee of *₹{reminder.amount}* is overdue by *{abs(days_left)} day{'s' if abs(days_left) != 1 else ''}*.\n\n"
                    f"📅 Due Date Was: {reminder.due_date.strftime('%d %b %Y')}\n"
                    f"⏳ Grace Remaining: {grace_left} day{'s' if grace_left != 1 else ''}\n\n"
                    f"Please pay immediately to avoid account suspension!\n\n"
                    f"Thank you,\n"
                    f"*Fusion Coaching Team*"
                )
            else:
                # Grace period expired - lock student
                message = (
                    f"🚫 *Fusion Coaching - Account Suspended*\n\n"
                    f"Dear {student.name},\n\n"
                    f"Your account has been *suspended* due to non-payment of fees.\n\n"
                    f"Due Amount: *₹{reminder.amount}*\n"
                    f"Original Due Date: {reminder.due_date.strftime('%d %b %Y')}\n\n"
                    f"Please contact the admin office immediately to restore your access.\n\n"
                    f"Thank you,\n"
                    f"*Fusion Coaching Team*"
                )
        
        success = send_whatsapp_message(student.phone, message)
        if success:
            sent_count += 1
            reminder.last_reminder_sent = datetime.utcnow()
        else:
            failed_count += 1
        
        results.append({
            'student': student.name,
            'phone': student.phone,
            'sent': success
        })
    
    # Commit reminder updates
    try:
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to commit reminder updates: {e}")
        db.session.rollback()
    
    return {
        'sent': sent_count,
        'failed': failed_count,
        'total': len(reminders),
        'details': results
    }

# ===================== STUDENT ID GENERATION =====================
def generate_student_id():
    """Generate a unique student ID in format FUS-YYYY-XXXXX."""
    year = datetime.utcnow().year
    # Get count of students this year to make sequential IDs
    count = Student.query.filter(
        Student.student_id.like(f'FUS-{year}-%')
    ).count()
    
    seq = count + 1
    return f'FUS-{year}-{seq:05d}'

# ===================== AUDIT LOGGING =====================
def log_audit(user_role, user_id, action, details, ip_address=None):
    """Log an audit trail entry."""
    try:
        audit = AuditLog(
            user_role=user_role,
            user_id=str(user_id) if user_id else None,
            action=action,
            details=str(details)[:1000],
            ip_address=ip_address or '0.0.0.0',
            created_at=datetime.utcnow()
        )
        db.session.add(audit)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log audit: {e}")
        db.session.rollback()

# ===================== INPUT SANITIZATION =====================
ALLOWED_TAGS = [
    'b', 'i', 'u', 'em', 'strong', 'a', 'br', 'p', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'pre', 'code', 'blockquote',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div'
]

ALLOWED_ATTRS = {
    'a': ['href', 'title', 'target', 'rel'],
    'span': ['style'],
    'div': ['style'],
    'p': ['style']
}

def sanitize_input(text, strip_tags=True, max_length=5000):
    """Sanitize user input to prevent XSS and SQL injection.
    
    Args:
        text: Input text to sanitize
        strip_tags: If True, remove all HTML tags. If False, allow safe tags.
        max_length: Maximum length of output
    
    Returns:
        Sanitized string
    """
    if not text:
        return ''
    
    # Convert to string
    text = str(text)
    
    # Strip or clean HTML
    if strip_tags:
        text = bleach.clean(text, tags=[], attributes={}, strip=True)
    else:
        text = bleach.clean(
            text,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRS,
            strip=True
        )
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Truncate
    if len(text) > max_length:
        text = text[:max_length-3] + '...'
    
    return text

def sanitize_html(html_content):
    """Sanitize HTML content allowing safe tags only."""
    return sanitize_input(html_content, strip_tags=False, max_length=50000)

# ===================== FILE VALIDATION =====================
ALLOWED_EXTENSIONS = {
    # Documents
    'pdf': 'application/pdf',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'ppt': 'application/vnd.ms-powerpoint',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'txt': 'text/plain',
    # Images
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'svg': 'image/svg+xml',
    # Video
    'mp4': 'video/mp4',
    'webm': 'video/webm',
    # Archives
    'zip': 'application/zip',
    'rar': 'application/vnd.rar'
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

def validate_file(filename, content_type, file_size):
    """Validate file type and size.
    
    Args:
        filename: Original filename
        content_type: MIME type of the file
        file_size: Size in bytes
    
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check extension
    if '.' not in filename:
        return False, 'File has no extension'
    
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f'File extension .{ext} is not allowed'
    
    # Check MIME type
    expected_mime = ALLOWED_EXTENSIONS.get(ext)
    if expected_mime and content_type != expected_mime:
        return False, f'File type mismatch: expected {expected_mime}, got {content_type}'
    
    # Check size
    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        return False, f'File too large. Maximum size is {int(max_mb)}MB'
    
    return True, ''

def get_file_icon(file_type):
    """Get Font Awesome icon for file type."""
    icons = {
        'pdf': 'fa-file-pdf',
        'doc': 'fa-file-word',
        'docx': 'fa-file-word',
        'xls': 'fa-file-excel',
        'xlsx': 'fa-file-excel',
        'ppt': 'fa-file-powerpoint',
        'pptx': 'fa-file-powerpoint',
        'txt': 'fa-file-alt',
        'jpg': 'fa-file-image',
        'jpeg': 'fa-file-image',
        'png': 'fa-file-image',
        'gif': 'fa-file-image',
        'zip': 'fa-file-archive',
        'rar': 'fa-file-archive',
        'mp4': 'fa-file-video',
        'webm': 'fa-file-video'
    }
    return icons.get(file_type.lower(), 'fa-file')

# ===================== DATE HELPERS =====================
def format_date(date_obj, format_str='%d %b %Y'):
    """Format a date object to string."""
    if not date_obj:
        return ''
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
        except:
            return date_obj
    return date_obj.strftime(format_str)

def get_financial_year(date_obj=None):
    """Get the financial year for a given date.
    Indian financial year: Apr 1 to Mar 31"""
    if not date_obj:
        date_obj = date.today()
    
    year = date_obj.year
    if date_obj.month >= 4:
        return f'{year}-{year+1}'
    else:
        return f'{year-1}-{year}'

# ===================== NOTIFICATION HELPERS =====================
def create_notification(user_id, user_type, title, message, notification_type='info'):
    """Create a notification for a user."""
    from models import Notification
    
    try:
        notification = Notification(
            user_id=user_id,
            user_type=user_type,
            title=str(title)[:200],
            message=str(message)[:1000],
            notification_type=notification_type,
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        db.session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        db.session.rollback()
        return False

# ===================== CURRENCY HELPERS =====================
def format_currency(amount, show_symbol=True):
    """Format amount as Indian currency (₹)."""
    if amount is None:
        amount = 0
    
    amount = float(amount)
    
    if show_symbol:
        if amount >= 10000000:  # Crore
            return f'₹{amount/10000000:.2f} Cr'
        elif amount >= 100000:  # Lakh
            return f'₹{amount/100000:.2f} L'
        elif amount >= 1000:
            return f'₹{amount:,.0f}'
        else:
            return f'₹{amount:.0f}'
    else:
        return f'{amount:,.2f}'

# ===================== PERFORMANCE CALCULATIONS =====================
def calculate_performance_trends(student_id, months=6):
    """Calculate performance trends for a student over X months."""
    from sqlalchemy import func, extract
    
    six_months_ago = date.today() - timedelta(days=months * 30)
    
    marks_data = db.session.query(
        func.strftime('%Y-%m', Marks.exam_date).label('month'),
        func.avg(Marks.percentage).label('avg_percentage')
    ).filter(
        Marks.student_id == student_id,
        Marks.exam_date >= six_months_ago
    ).group_by('month').order_by('month').all()
    
    return [{
        'month': m.month,
        'average': round(float(m.avg_percentage), 1)
    } for m in marks_data]

def calculate_class_averages(class_id, exam_type='final'):
    """Calculate average marks for an entire class in an exam."""
    from sqlalchemy import func
    
    sc_list = StudentClass.query.filter_by(class_id=class_id).all()
    student_ids = [sc.student_id for sc in sc_list]
    
    result = db.session.query(
        Marks.subject_id,
        func.avg(Marks.percentage).label('avg_pct'),
        func.max(Marks.percentage).label('max_pct'),
        func.min(Marks.percentage).label('min_pct')
    ).filter(
        Marks.student_id.in_(student_ids),
        Marks.exam_type == exam_type
    ).group_by(Marks.subject_id).all()
    
    subjects_data = []
    for r in result:
        sub = Subject.query.get(r.subject_id)
        subjects_data.append({
            'subject': sub.name if sub else 'Unknown',
            'average': round(float(r.avg_pct), 1) if r.avg_pct else 0,
            'highest': round(float(r.max_pct), 1) if r.max_pct else 0,
            'lowest': round(float(r.min_pct), 1) if r.min_pct else 0
        })
    
    return subjects_data
