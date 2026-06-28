import os
import sys
import json
import uuid
import hashlib
import hmac
from datetime import datetime, date, timedelta
from decimal import Decimal

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, make_response
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, extract, and_, or_, desc
import bleach

from config import Config
from models import db, Student, Teacher, Parent, Admin, Class, Subject, Timetable, StudentClass
from models import Attendance, AttendanceSession, Marks, FeePayment, WhatsAppLog, FeeReminder
from models import Exam, TestScore, Doubt, StudyMaterial, BulkMarksEntry, AuditLog, Notification

from auth import login_manager, role_required, check_role
from helpers import send_whatsapp_message, generate_student_id, log_audit
from helpers import check_fee_status, send_fee_reminders, validate_file, sanitize_input, format_phone

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config.from_object(Config)

db.init_app(app)
CORS(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

# ===================== MIDDLEWARE =====================
@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=24)
    if request.endpoint and request.endpoint != 'static' and current_user.is_authenticated:
        log_audit(current_user.role, current_user.get_id(), 'page_view', f'Accessed {request.endpoint}', request.remote_addr)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# ===================== ERROR HANDLERS =====================
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ===================== AUTH ROUTES =====================
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    email = sanitize_input(data.get('email', '').lower().strip())
    password = data.get('password', '')
    role = data.get('role', 'student')
    
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    
    user = None
    if role == 'student':
        user = Student.query.filter_by(email=email).first()
    elif role == 'teacher':
        user = Teacher.query.filter_by(email=email).first()
    elif role == 'parent':
        user = Parent.query.filter_by(email=email).first()
    elif role == 'admin':
        user = Admin.query.filter_by(email=email).first()
    
    if not user or not check_password_hash(user.password_hash, password):
        log_audit(None, email, 'login_failed', f'Failed login attempt as {role}', request.remote_addr)
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    
    if hasattr(user, 'is_active') and not user.is_active:
        return jsonify({'success': False, 'error': 'Account is deactivated'}), 403
    
    login_user(user, remember=data.get('remember', False))
    log_audit(role, user.get_id(), 'login', f'Logged in successfully', request.remote_addr)
    
    return jsonify({
        'success': True,
        'role': role,
        'user': {
            'id': user.get_id(),
            'name': user.name,
            'email': user.email,
            'role': role
        }
    })

@app.route('/api/auth/check', methods=['GET'])
def auth_check():
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'role': current_user.role,
            'user': {
                'id': current_user.get_id(),
                'name': current_user.name,
                'email': current_user.email,
                'role': current_user.role
            }
        })
    return jsonify({'authenticated': False})

@app.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    log_audit(current_user.role, current_user.get_id(), 'logout', 'User logged out', request.remote_addr)
    logout_user()
    session.clear()
    return jsonify({'success': True})

# ===================== ADMIN DASHBOARD =====================
@app.route('/api/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    total_students = Student.query.filter_by(is_active=True).count()
    total_teachers = Teacher.query.count()
    total_classes = Class.query.count()
    
    fee_summary = db.session.query(
        func.count(FeePayment.id).label('total_payments'),
        func.coalesce(func.sum(FeePayment.amount), 0).label('total_collected')
    ).filter(FeePayment.status == 'paid').first()
    
    pending_fees = FeeReminder.query.filter_by(status='pending').count()
    
    recent = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
    
    stats = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_classes': total_classes,
        'total_payments': fee_summary.total_payments or 0,
        'total_collected': float(fee_summary.total_collected) if fee_summary.total_collected else 0,
        'pending_fees': pending_fees
    }
    
    return jsonify({
        'success': True,
        'stats': stats,
        'recent_activity': [{'action': a.action, 'details': a.details, 'time': a.created_at.strftime('%Y-%m-%d %H:%M')} for a in recent]
    })

# ===================== ADMIN: STUDENT MANAGEMENT =====================
@app.route('/api/admin/students', methods=['GET'])
@login_required
@role_required('admin')
def admin_get_students():
    search = request.args.get('search', '')
    query = Student.query.filter_by(is_active=True)
    if search:
        query = query.filter(
            or_(Student.name.ilike(f'%{search}%'), Student.email.ilike(f'%{search}%'), Student.student_id.ilike(f'%{search}%'))
        )
    students = query.order_by(Student.name).all()
    
    result = []
    for s in students:
        class_name = ''
        sc = StudentClass.query.filter_by(student_id=s.id).first()
        if sc:
            cls = Class.query.get(sc.class_id)
            if cls:
                class_name = cls.name
        
        fee_locked = check_fee_status(s.id)
        
        result.append({
            'id': s.id,
            'student_id': s.student_id,
            'name': s.name,
            'email': s.email,
            'phone': s.phone,
            'class': class_name,
            'roll': s.roll_number,
            'is_active': s.is_active,
            'fee_locked': fee_locked
        })
    
    return jsonify({'students': result, 'total': len(result)})

@app.route('/api/admin/students', methods=['POST'])
@login_required
@role_required('admin')
def admin_add_student():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'}), 400
    
    name = sanitize_input(data.get('name', ''))
    email = sanitize_input(data.get('email', '').lower())
    phone = sanitize_input(data.get('phone', ''))
    password = data.get('password', 'Student@2026')
    class_id = data.get('class_id')
    roll = data.get('roll_number')
    
    if not name or not email:
        return jsonify({'success': False, 'error': 'Name and email required'}), 400
    
    if Student.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email already exists'}), 409
    
    student = Student(
        name=name,
        email=email,
        phone=phone,
        password_hash=generate_password_hash(password),
        student_id=generate_student_id(),
        roll_number=roll,
        is_active=True
    )
    db.session.add(student)
    db.session.flush()
    
    if class_id:
        sc = StudentClass(student_id=student.id, class_id=class_id)
        db.session.add(sc)
    
    db.session.commit()
    log_audit('admin', current_user.get_id(), 'create_student', f'Created student {name} ({student.student_id})', request.remote_addr)
    
    return jsonify({'success': True, 'student_id': student.student_id})

@app.route('/api/admin/student/<int:student_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def admin_toggle_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_active = not student.is_active
    db.session.commit()
    log_audit('admin', current_user.get_id(), 'toggle_student', f'Toggled student {student.name} to {"active" if student.is_active else "inactive"}', request.remote_addr)
    return jsonify({'success': True, 'is_active': student.is_active})

@app.route('/api/admin/student/fee/unlock/<int:student_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_unlock_student(student_id):
    student = Student.query.get_or_404(student_id)
    fr = FeeReminder.query.filter_by(student_id=student_id, status='pending').first()
    if fr:
        fr.status = 'overridden'
        fr.notes = f'Unlocked by admin on {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}'
    db.session.commit()
    log_audit('admin', current_user.get_id(), 'unlock_fee', f'Unlocked fee for student {student.name}', request.remote_addr)
    return jsonify({'success': True})

# ===================== ADMIN: TEACHERS =====================
@app.route('/api/admin/teachers', methods=['GET'])
@login_required
@role_required('admin')
def admin_get_teachers():
    teachers = Teacher.query.order_by(Teacher.name).all()
    return jsonify({
        'teachers': [{
            'id': t.id,
            'teacher_id': t.teacher_id,
            'name': t.name,
            'email': t.email,
            'phone': t.phone,
            'qualification': t.qualification,
            'experience': t.experience,
            'subject': t.subject
        } for t in teachers]
    })

@app.route('/api/admin/teachers', methods=['POST'])
@login_required
@role_required('admin')
def admin_add_teacher():
    data = request.get_json()
    name = sanitize_input(data.get('name', ''))
    email = sanitize_input(data.get('email', '').lower())
    password = data.get('password', 'Teacher@2026')
    
    if not name or not email:
        return jsonify({'success': False, 'error': 'Name and email required'}), 400
    
    teacher = Teacher(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        teacher_id=f'TCH{uuid.uuid4().hex[:6].upper()}',
        qualification=data.get('qualification', ''),
        experience=int(data.get('experience', 0)),
        subject=data.get('subject', ''),
        phone=sanitize_input(data.get('phone', ''))
    )
    db.session.add(teacher)
    db.session.commit()
    return jsonify({'success': True, 'teacher_id': teacher.teacher_id})

# ===================== ADMIN: CLASSES & SUBJECTS =====================
@app.route('/api/admin/classes', methods=['GET'])
@login_required
def get_classes():
    classes = Class.query.order_by(Class.name).all()
    return jsonify({'classes': [{'id': c.id, 'name': c.name, 'section': c.section} for c in classes]})

@app.route('/api/admin/subjects', methods=['GET'])
@login_required
def get_subjects():
    subjects = Subject.query.order_by(Subject.name).all()
    return jsonify({'subjects': [{'id': s.id, 'name': s.name, 'code': s.code} for s in subjects]})

@app.route('/api/admin/classes', methods=['POST'])
@login_required
@role_required('admin')
def add_class():
    data = request.get_json()
    name = sanitize_input(data.get('name', ''))
    if not name:
        return jsonify({'success': False, 'error': 'Class name required'}), 400
    cls = Class(name=name, section=data.get('section', ''))
    db.session.add(cls)
    db.session.commit()
    return jsonify({'success': True, 'id': cls.id})

@app.route('/api/admin/subjects', methods=['POST'])
@login_required
@role_required('admin')
def add_subject():
    data = request.get_json()
    name = sanitize_input(data.get('name', ''))
    if not name:
        return jsonify({'success': False, 'error': 'Subject name required'}), 400
    sub = Subject(name=name, code=data.get('code', ''))
    db.session.add(sub)
    db.session.commit()
    return jsonify({'success': True, 'id': sub.id})

# ===================== BULK MARKS ENTRY =====================
@app.route('/api/admin/marks/bulk', methods=['GET'])
@login_required
@role_required('admin')
def get_bulk_marks_data():
    class_id = request.args.get('class_id', type=int)
    subject_id = request.args.get('subject_id', type=int)
    exam_type = request.args.get('exam_type', 'unit_test')
    
    if not class_id or not subject_id:
        return jsonify({'error': 'class_id and subject_id required'}), 400
    
    sc_list = StudentClass.query.filter_by(class_id=class_id).all()
    student_ids = [sc.student_id for sc in sc_list]
    students = Student.query.filter(Student.id.in_(student_ids), Student.is_active == True).order_by(Student.roll_number).all()
    
    result = []
    for s in students:
        marks = Marks.query.filter_by(student_id=s.id, subject_id=subject_id, exam_type=exam_type).first()
        result.append({
            'id': s.id,
            'student_id': s.student_id,
            'name': s.name,
            'roll': s.roll_number,
            'marks': marks.marks_obtained if marks else None,
            'max_marks': marks.max_marks if marks else 100
        })
    
    return jsonify({'students': result})

@app.route('/api/admin/marks/bulk', methods=['POST'])
@login_required
@role_required('admin')
def save_bulk_marks():
    data = request.get_json()
    class_id = data.get('class_id')
    subject_id = data.get('subject_id')
    exam_type = data.get('exam_type', 'unit_test')
    exam_name = data.get('exam_name', exam_type)
    entries = data.get('entries', [])
    
    if not class_id or not subject_id or not entries:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    # Create or get exam
    exam = Exam.query.filter_by(
        name=exam_name,
        exam_type=exam_type,
        class_id=class_id,
        subject_id=subject_id
    ).first()
    if not exam:
        exam = Exam(
            name=exam_name,
            exam_type=exam_type,
            class_id=class_id,
            subject_id=subject_id,
            total_marks=100,
            date=date.today()
        )
        db.session.add(exam)
        db.session.flush()
    
    count = 0
    for entry in entries:
        student_id = entry.get('student_id')
        marks_obtained = entry.get('marks_obtained')
        max_marks = entry.get('max_marks', 100)
        
        if marks_obtained is None:
            continue
        
        marks = Marks.query.filter_by(
            student_id=student_id,
            subject_id=subject_id,
            exam_type=exam_type,
            exam_id=exam.id
        ).first()
        
        if marks:
            marks.marks_obtained = marks_obtained
            marks.max_marks = max_marks
        else:
            marks = Marks(
                student_id=student_id,
                subject_id=subject_id,
                exam_id=exam.id,
                exam_type=exam_type,
                marks_obtained=marks_obtained,
                max_marks=max_marks,
                percentage=(marks_obtained / max_marks) * 100 if max_marks > 0 else 0,
                grade=calculate_grade((marks_obtained / max_marks) * 100 if max_marks > 0 else 0)
            )
            db.session.add(marks)
        count += 1
    
    db.session.commit()
    log_audit('admin', current_user.get_id(), 'bulk_marks', f'Saved {count} marks for exam {exam_name}', request.remote_addr)
    
    return jsonify({'success': True, 'count': count})

def calculate_grade(percentage):
    if percentage >= 90: return 'A+'
    if percentage >= 80: return 'A'
    if percentage >= 70: return 'B+'
    if percentage >= 60: return 'B'
    if percentage >= 50: return 'C'
    if percentage >= 40: return 'D'
    return 'F'

# ===================== STUDENT MARKS (TEACHER VERSION) =====================
@app.route('/api/teacher/marks/bulk', methods=['GET'])
@login_required
@role_required('teacher')
def teacher_get_bulk_marks():
    return get_bulk_marks_data()

@app.route('/api/teacher/marks/bulk', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_save_bulk_marks():
    return save_bulk_marks()

# ===================== STUDENT DASHBOARD =====================
@app.route('/api/student/marks')
@login_required
@role_required('student')
def student_marks():
    student_id = current_user.id
    exams = Exam.query.join(Marks, Marks.exam_id == Exam.id)\
        .filter(Marks.student_id == student_id)\
        .order_by(Exam.date.desc()).all()
    
    exam_data = []
    total_marks = 0
    total_max = 0
    
    for exam in exams:
        marks_list = Marks.query.filter_by(student_id=student_id, exam_id=exam.id).all()
        subjects = []
        for m in marks_list:
            sub = Subject.query.get(m.subject_id)
            subjects.append({
                'subject': sub.name if sub else 'Unknown',
                'marks': float(m.marks_obtained),
                'max': float(m.max_marks),
                'percentage': round(float(m.percentage), 1) if m.percentage else 0,
                'grade': m.grade or calculate_grade(float(m.percentage) if m.percentage else 0)
            })
            total_marks += float(m.marks_obtained)
            total_max += float(m.max_marks)
        
        exam_data.append({
            'exam_name': exam.name,
            'exam_type': exam.exam_type,
            'date': exam.date.strftime('%d %b %Y') if exam.date else '',
            'subjects': subjects
        })
    
    overall_pct = round((total_marks / total_max) * 100, 1) if total_max > 0 else 0
    
    return jsonify({
        'exams': exam_data,
        'overall': {
            'total_marks': total_marks,
            'total_max': total_max,
            'overall_percentage': overall_pct
        }
    })

@app.route('/api/student/attendance')
@login_required
@role_required('student')
def student_attendance():
    records = Attendance.query.filter_by(student_id=current_user.id)\
        .order_by(Attendance.date.desc()).limit(90).all()
    
    total = len(records)
    present = sum(1 for r in records if r.status == 'present')
    absent = sum(1 for r in records if r.status == 'absent')
    late = sum(1 for r in records if r.status == 'late')
    
    return jsonify({
        'records': [{
            'date': r.date.strftime('%d %b %Y'),
            'status': r.status,
            'period': r.period
        } for r in records],
        'summary': {
            'total': total,
            'present': present,
            'absent': absent,
            'late': late,
            'percentage': round((present / total) * 100, 1) if total > 0 else 0
        }
    })

@app.route('/api/student/tests')
@login_required
@role_required('student')
def student_tests():
    sc = StudentClass.query.filter_by(student_id=current_user.id).first()
    available = []
    if sc:
        exams = Exam.query.filter_by(class_id=sc.class_id).order_by(Exam.date.desc()).limit(10).all()
        for e in exams:
            sub = Subject.query.get(e.subject_id)
            available.append({
                'id': e.id,
                'title': e.name,
                'subject': sub.name if sub else 'General',
                'marks': e.total_marks,
                'duration': 60,
                'questions': 20,
                'date': e.date.strftime('%d %b %Y') if e.date else ''
            })
    
    return jsonify({'available': available})

@app.route('/api/student/fee/status')
@login_required
@role_required('student')
def student_fee_status():
    fee = FeeReminder.query.filter_by(student_id=current_user.id).order_by(FeeReminder.due_date.desc()).first()
    payments = FeePayment.query.filter_by(student_id=current_user.id).order_by(FeePayment.payment_date.desc()).limit(5).all()
    
    if fee:
        today = date.today()
        is_overdue = fee.due_date and today > fee.due_date
        days_remaining = (fee.due_date - today).days if fee.due_date else 0
        grace_remaining = (fee.grace_end_date - today).days if fee.grace_end_date else 0
        
        return jsonify({
            'upcoming': {
                'amount': float(fee.amount),
                'due_date': fee.due_date.strftime('%d %b %Y') if fee.due_date else '',
                'days_remaining': days_remaining,
                'grace_days_remaining': grace_remaining,
                'is_overdue': is_overdue and today <= fee.grace_end_date if fee.grace_end_date else is_overdue,
                'status': fee.status
            },
            'history': [{
                'amount': float(p.amount),
                'date': p.payment_date.strftime('%d %b %Y'),
                'mode': p.payment_mode,
                'status': p.status,
                'receipt': p.receipt_no
            } for p in payments]
        })
    
    return jsonify({'upcoming': None, 'history': []})

@app.route('/api/student/doubts', methods=['GET'])
@login_required
@role_required('student')
def student_doubts():
    doubts = Doubt.query.filter_by(student_id=current_user.id).order_by(Doubt.created_at.desc()).all()
    return jsonify({
        'doubts': [{
            'id': d.id,
            'question': d.question,
            'subject': Subject.query.get(d.subject_id).name if d.subject_id else 'General',
            'is_resolved': d.is_resolved,
            'answer': d.answer or '',
            'created': d.created_at.strftime('%d %b %Y')
        } for d in doubts]
    })

@app.route('/api/student/doubts', methods=['POST'])
@login_required
@role_required('student')
def student_submit_doubt():
    data = request.get_json()
    doubt = Doubt(
        student_id=current_user.id,
        subject_id=data.get('subject_id'),
        question=sanitize_input(data.get('question', '')),
        title=sanitize_input(data.get('title', ''))
    )
    db.session.add(doubt)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/student/materials')
@login_required
@role_required('student')
def student_materials():
    sc = StudentClass.query.filter_by(student_id=current_user.id).first()
    class_id = sc.class_id if sc else None
    materials = StudyMaterial.query.filter(
        or_(StudyMaterial.class_id == class_id, StudyMaterial.class_id == None)
    ).order_by(StudyMaterial.created_at.desc()).all()
    
    return jsonify({
        'materials': [{
            'id': m.id,
            'title': m.title,
            'description': m.description,
            'subject': Subject.query.get(m.subject_id).name if m.subject_id else 'General',
            'file_type': m.file_type,
            'file_url': m.file_url,
            'created': m.created_at.strftime('%d %b %Y')
        } for m in materials]
    })

# ===================== TEACHER DASHBOARD =====================
@app.route('/api/teacher/dashboard')
@login_required
@role_required('teacher')
def teacher_dashboard():
    total_students = Student.query.filter_by(is_active=True).count()
    today = date.today()
    today_attendance = Attendance.query.filter_by(date=today).count()
    pending_doubts = Doubt.query.filter_by(is_resolved=False).count()
    
    return jsonify({
        'stats': {
            'total_students': total_students,
            'today_attendance': today_attendance,
            'pending_doubts': pending_doubts,
            'classes': Class.query.count()
        }
    })

@app.route('/api/teacher/attendance', methods=['GET'])
@login_required
@role_required('teacher')
def teacher_get_attendance():
    classes = Class.query.order_by(Class.name).all()
    class_id = request.args.get('class_id', type=int)
    att_date_str = request.args.get('date', str(date.today()))
    
    try:
        att_date = datetime.strptime(att_date_str, '%Y-%m-%d').date()
    except:
        att_date = date.today()
    
    if class_id:
        sc_list = StudentClass.query.filter_by(class_id=class_id).all()
        student_ids = [sc.student_id for sc in sc_list]
        students = Student.query.filter(Student.id.in_(student_ids), Student.is_active == True).order_by(Student.roll_number).all()
        
        result = []
        for s in students:
            att = Attendance.query.filter_by(student_id=s.id, date=att_date).first()
            result.append({
                'id': s.id,
                'name': s.name,
                'roll': s.roll_number,
                'status': att.status if att else 'not_marked'
            })
        
        return jsonify({'students': result, 'classes': [{'id': c.id, 'name': c.name} for c in classes]})
    
    return jsonify({'classes': [{'id': c.id, 'name': c.name} for c in classes]})

@app.route('/api/teacher/attendance', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_save_attendance():
    data = request.get_json()
    records = data.get('records', [])
    att_date_str = data.get('date', str(date.today()))
    period = data.get('period', 'morning')
    
    try:
        att_date = datetime.strptime(att_date_str, '%Y-%m-%d').date()
    except:
        att_date = date.today()
    
    for rec in records:
        student_id = rec.get('student_id')
        status = rec.get('status')
        if not student_id or not status:
            continue
        
        att = Attendance.query.filter_by(student_id=student_id, date=att_date, period=period).first()
        if att:
            att.status = status
        else:
            att = Attendance(student_id=student_id, date=att_date, status=status, period=period)
            db.session.add(att)
    
    db.session.commit()
    return jsonify({'success': True, 'count': len(records)})

@app.route('/api/teacher/doubts', methods=['GET'])
@login_required
@role_required('teacher')
def teacher_doubts():
    doubts = Doubt.query.filter_by(is_resolved=False).order_by(Doubt.created_at.desc()).all()
    return jsonify({
        'doubts': [{
            'id': d.id,
            'student_name': Student.query.get(d.student_id).name if d.student_id else 'Unknown',
            'question': d.question,
            'subject': Subject.query.get(d.subject_id).name if d.subject_id else 'General',
            'created': d.created_at.strftime('%d %b %Y')
        } for d in doubts]
    })

@app.route('/api/teacher/doubt/<int:doubt_id>/reply', methods=['POST'])
@login_required
@role_required('teacher')
def teacher_reply_doubt(doubt_id):
    data = request.get_json()
    doubt = Doubt.query.get_or_404(doubt_id)
    doubt.answer = sanitize_input(data.get('answer', ''))
    doubt.is_resolved = True
    doubt.resolved_by = current_user.get_id()
    doubt.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True})

# ===================== FEE & WHATSAPP =====================
@app.route('/api/admin/fees', methods=['GET'])
@login_required
@role_required('admin')
def admin_fees():
    payments = FeePayment.query.order_by(FeePayment.payment_date.desc()).limit(50).all()
    total_collected = db.session.query(func.coalesce(func.sum(FeePayment.amount), 0)).filter(FeePayment.status == 'paid').scalar()
    pending_count = FeeReminder.query.filter_by(status='pending').count()
    
    return jsonify({
        'summary': {
            'total_collected': float(total_collected),
            'pending_count': pending_count,
            'total_payments': len(payments)
        },
        'payments': [{
            'id': p.id,
            'receipt': p.receipt_no,
            'student': Student.query.get(p.student_id).name if p.student_id else 'Unknown',
            'amount': float(p.amount),
            'date': p.payment_date.strftime('%d %b %Y'),
            'mode': p.payment_mode,
            'status': p.status
        } for p in payments]
    })

@app.route('/api/admin/fee/remind-all', methods=['POST'])
@login_required
@role_required('admin')
def admin_fee_remind_all():
    result = send_fee_reminders()
    log_audit('admin', current_user.get_id(), 'fee_remind_all', f'Sent {result["sent"]} WhatsApp reminders', request.remote_addr)
    return jsonify(result)

@app.route('/api/admin/whatsapp/test', methods=['POST'])
@login_required
@role_required('admin')
def admin_whatsapp_test():
    data = request.get_json()
    phone = format_phone(data.get('phone', ''))
    if not phone:
        return jsonify({'success': False, 'error': 'Invalid phone number'}), 400
    
    success = send_whatsapp_message(
        to=phone,
        body=f'🔔 *Fusion Coaching* - Test Message\n\nThis is a test WhatsApp message from Fusion Coaching Management System.\n\nIf you received this, WhatsApp integration is working correctly!\n\n_Thank you,_\n*Fusion Coaching Team*'
    )
    
    if success:
        log_audit('admin', current_user.get_id(), 'whatsapp_test', f'Test message sent to {phone}', request.remote_addr)
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Twilio send failed. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN'})

# ===================== PARENT DASHBOARD =====================
@app.route('/api/parent/dashboard')
@login_required
@role_required('parent')
def parent_dashboard():
    linked_students = current_user.linked_students or []
    students_data = []
    
    for sid in linked_students:
        student = Student.query.get(sid)
        if student:
            sc = StudentClass.query.filter_by(student_id=student.id).first()
            class_name = Class.query.get(sc.class_id).name if sc and sc.class_id else 'N/A'
            
            # Recent marks
            recent_marks = Marks.query.filter_by(student_id=student.id).order_by(Marks.exam_id.desc()).limit(3).all()
            
            # Attendance summary
            total_att = Attendance.query.filter_by(student_id=student.id).count()
            present_att = Attendance.query.filter_by(student_id=student.id, status='present').count()
            att_pct = round((present_att / total_att) * 100, 1) if total_att > 0 else 0
            
            # Fee status
            fee_locked = check_fee_status(student.id)
            
            students_data.append({
                'id': student.id,
                'name': student.name,
                'student_id': student.student_id,
                'class': class_name,
                'roll': student.roll_number,
                'attendance_percentage': att_pct,
                'marks': [{'subject': Subject.query.get(m.subject_id).name if m.subject_id else 'N/A', 'marks': float(m.marks_obtained), 'max': float(m.max_marks)} for m in recent_marks],
                'fee_locked': fee_locked
            })
    
    return jsonify({'students': students_data})

@app.route('/api/parent/student/<int:student_id>')
@login_required
@role_required('parent')
def parent_student_details(student_id):
    if student_id not in (current_user.linked_students or []):
        return jsonify({'error': 'Not linked to this student'}), 403
    
    student = Student.query.get_or_404(student_id)
    
    # Full marks
    marks = Marks.query.filter_by(student_id=student_id).order_by(Marks.exam_id.desc()).all()
    
    # Full attendance
    attendance = Attendance.query.filter_by(student_id=student_id).order_by(Attendance.date.desc()).limit(30).all()
    
    return jsonify({
        'student': {
            'name': student.name,
            'student_id': student.student_id,
            'email': student.email,
            'phone': student.phone
        },
        'marks': [{
            'subject': Subject.query.get(m.subject_id).name if m.subject_id else 'N/A',
            'marks': float(m.marks_obtained),
            'max': float(m.max_marks),
            'percentage': float(m.percentage) if m.percentage else 0,
            'grade': m.grade,
            'exam': Exam.query.get(m.exam_id).name if m.exam_id else 'N/A'
        } for m in marks],
        'attendance': [{
            'date': a.date.strftime('%d %b %Y'),
            'status': a.status,
            'period': a.period
        } for a in attendance]
    })

# ===================== PAYMENT (RAZORPAY) =====================
@app.route('/api/payment/create-order', methods=['POST'])
@login_required
def create_payment_order():
    data = request.get_json()
    amount = int(data.get('amount', 0))
    student_id = data.get('student_id')
    
    if amount < 1:
        return jsonify({'error': 'Invalid amount'}), 400
    
    import razorpay
    client = razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))
    
    order_data = {
        'amount': amount * 100,  # paise
        'currency': 'INR',
        'receipt': f'FEE{uuid.uuid4().hex[:8].upper()}',
        'payment_capture': 1
    }
    
    try:
        order = client.order.create(order_data)
        
        # Save pending payment
        payment = FeePayment(
            student_id=student_id or current_user.id,
            amount=amount,
            payment_mode='razorpay',
            status='pending',
            receipt_no=order_data['receipt'],
            razorpay_order_id=order['id']
        )
        db.session.add(payment)
        db.session.commit()
        
        return jsonify({
            'order_id': order['id'],
            'amount': order['amount'],
            'currency': order['currency'],
            'key': Config.RAZORPAY_KEY_ID,
            'receipt': order_data['receipt']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payment/verify', methods=['POST'])
@login_required
def verify_payment():
    data = request.get_json()
    order_id = data.get('razorpay_order_id')
    payment_id = data.get('razorpay_payment_id')
    signature = data.get('razorpay_signature')
    
    # Verify signature
    expected_sig = hmac.new(
        Config.RAZORPAY_KEY_SECRET.encode(),
        f'{order_id}|{payment_id}'.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if expected_sig != signature:
        return jsonify({'success': False, 'error': 'Invalid signature'}), 400
    
    payment = FeePayment.query.filter_by(razorpay_order_id=order_id).first()
    if payment:
        payment.status = 'paid'
        payment.razorpay_payment_id = payment_id
        payment.payment_date = datetime.utcnow()
        
        # Update fee reminder
        fr = FeeReminder.query.filter_by(student_id=payment.student_id, status='pending').first()
        if fr:
            fr.status = 'paid'
            fr.paid_at = datetime.utcnow()
        
        db.session.commit()
        
        log_audit('student' if current_user.role == 'student' else 'parent', current_user.get_id(), 'fee_paid', f'Payment {payment_id} of ₹{payment.amount} completed', request.remote_addr)
    
    return jsonify({'success': True})

# ===================== WHATSAPP WEBHOOK =====================
@app.route('/api/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    data = request.get_json()
    if data and 'messages' in data:
        for msg in data['messages']:
            from_num = msg.get('from', '')
            text = msg.get('text', {}).get('body', '')
            
            # Auto-reply logic
            if 'fee' in text.lower() or 'due' in text.lower():
                send_whatsapp_message(
                    to=from_num,
                    body='📚 *Fusion Coaching - Fee Info*\n\nYour fee is due. Please contact the admin office or pay online through your dashboard.\n\n_Thank you,_\n*Fusion Coaching Team*'
                )
    
    return jsonify({'status': 'ok'})

# ===================== MAIN =====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/<path:path>')
def catch_all(path):
    return render_template('index.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default admin if not exists
        admin = Admin.query.filter_by(email=Config.ADMIN_EMAIL).first()
        if not admin:
            admin = Admin(
                name='Fusion Admin',
                email=Config.ADMIN_EMAIL,
                password_hash=generate_password_hash(Config.ADMIN_PASSWORD),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print(f'✅ Default admin created: {Config.ADMIN_EMAIL} / {Config.ADMIN_PASSWORD}')
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
