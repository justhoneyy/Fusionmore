import os
import uuid
from datetime import datetime, date, timedelta

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ===================== MIXINS =====================
class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ===================== USER MODELS (Flask-Login compatible) =====================
class Student(UserMixin, db.Model, TimestampMixin):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    roll_number = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    role = db.Column(db.String(20), default='student')
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id'))
    date_of_birth = db.Column(db.Date)
    address = db.Column(db.Text)
    emergency_contact = db.Column(db.String(20))
    blood_group = db.Column(db.String(5))
    medical_notes = db.Column(db.Text)
    photo_url = db.Column(db.String(500))
    last_login = db.Column(db.DateTime)
    
    # Relationships
    attendances = db.relationship('Attendance', backref='student', lazy='dynamic')
    marks = db.relationship('Marks', backref='student', lazy='dynamic')
    fee_payments = db.relationship('FeePayment', backref='student', lazy='dynamic')
    fee_reminders = db.relationship('FeeReminder', backref='student', lazy='dynamic')
    doubts = db.relationship('Doubt', backref='student', lazy='dynamic')
    class_enrollments = db.relationship('StudentClass', backref='student', lazy='dynamic')
    test_scores = db.relationship('TestScore', backref='student', lazy='dynamic')
    notifications = db.relationship('Notification', backref='student', lazy='dynamic',
                                   foreign_keys='Notification.user_id',
                                   primaryjoin='and_(Notification.user_id == Student.id, Notification.user_type == "student")')
    
    def get_id(self):
        return str(self.id)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'roll_number': self.roll_number,
            'is_active': self.is_active,
            'role': self.role
        }


class Teacher(UserMixin, db.Model, TimestampMixin):
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    qualification = db.Column(db.String(200))
    experience = db.Column(db.Integer, default=0)  # years
    subject = db.Column(db.String(100))
    specialization = db.Column(db.String(200))
    role = db.Column(db.String(20), default='teacher')
    is_active = db.Column(db.Boolean, default=True)
    joining_date = db.Column(db.Date, default=date.today)
    salary = db.Column(db.Float, default=0.0)
    address = db.Column(db.Text)
    photo_url = db.Column(db.String(500))
    last_login = db.Column(db.DateTime)
    
    # Relationships
    doubts_resolved = db.relationship('Doubt', backref='resolver', lazy='dynamic',
                                     foreign_keys='Doubt.resolved_by',
                                     primaryjoin='and_(Doubt.resolved_by == Teacher.id)')
    notifications = db.relationship('Notification', backref='teacher', lazy='dynamic',
                                   foreign_keys='Notification.user_id',
                                   primaryjoin='and_(Notification.user_id == Teacher.id, Notification.user_type == "teacher")')
    
    def get_id(self):
        return str(self.id)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'teacher_id': self.teacher_id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'qualification': self.qualification,
            'experience': self.experience,
            'subject': self.subject,
            'role': self.role
        }


class Parent(UserMixin, db.Model, TimestampMixin):
    __tablename__ = 'parents'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    linked_students = db.Column(db.JSON, default=list)  # List of student IDs
    role = db.Column(db.String(20), default='parent')
    is_active = db.Column(db.Boolean, default=True)
    occupation = db.Column(db.String(100))
    address = db.Column(db.Text)
    photo_url = db.Column(db.String(500))
    last_login = db.Column(db.DateTime)
    
    # Relationships
    students = db.relationship('Student', backref='parent', lazy='dynamic',
                              foreign_keys='Student.parent_id')
    notifications = db.relationship('Notification', backref='parent', lazy='dynamic',
                                   foreign_keys='Notification.user_id',
                                   primaryjoin='and_(Notification.user_id == Parent.id, Notification.user_type == "parent")')
    
    def get_id(self):
        return str(self.id)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def link_student(self, student_id):
        if self.linked_students is None:
            self.linked_students = []
        if student_id not in self.linked_students:
            self.linked_students.append(student_id)
    
    def unlink_student(self, student_id):
        if self.linked_students and student_id in self.linked_students:
            self.linked_students.remove(student_id)


class Admin(UserMixin, db.Model, TimestampMixin):
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='admin')
    is_superadmin = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    
    def get_id(self):
        return str(self.id)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'role': self.role,
            'is_superadmin': self.is_superadmin
        }


# ===================== ACADEMIC MODELS =====================
class Class(db.Model, TimestampMixin):
    __tablename__ = 'classes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Class 11", "Class 12"
    section = db.Column(db.String(10), default='A')
    academic_year = db.Column(db.String(20), default=lambda: f'{date.today().year}-{date.today().year + 1}')
    description = db.Column(db.Text)
    room_number = db.Column(db.String(20))
    class_teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    enrollments = db.relationship('StudentClass', backref='class_', lazy='dynamic')
    exams = db.relationship('Exam', backref='class_', lazy='dynamic')
    timetables = db.relationship('Timetable', backref='class_', lazy='dynamic')
    study_materials = db.relationship('StudyMaterial', backref='class_', lazy='dynamic',
                                     foreign_keys='StudyMaterial.class_id')
    class_teacher = db.relationship('Teacher', backref='class_teacher_of', lazy='joined',
                                   foreign_keys='Class.class_teacher_id')
    
    def __repr__(self):
        return f'{self.name} - {self.section}'
    
    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'section': self.section, 'academic_year': self.academic_year}


class Subject(db.Model, TimestampMixin):
    __tablename__ = 'subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True)
    description = db.Column(db.Text)
    is_lab = db.Column(db.Boolean, default=False)  # Whether it has practical component
    max_marks_theory = db.Column(db.Integer, default=70)
    max_marks_practical = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    marks = db.relationship('Marks', backref='subject', lazy='dynamic')
    exams = db.relationship('Exam', backref='subject', lazy='dynamic')
    study_materials = db.relationship('StudyMaterial', backref='subject', lazy='dynamic',
                                     foreign_keys='StudyMaterial.subject_id')
    doubts = db.relationship('Doubt', backref='subject', lazy='dynamic',
                            foreign_keys='Doubt.subject_id')
    
    def __repr__(self):
        return self.name
    
    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'code': self.code}


class StudentClass(db.Model, TimestampMixin):
    """Junction table: Student <-> Class enrollment (supports multiple years)"""
    __tablename__ = 'student_classes'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    academic_year = db.Column(db.String(20), default=lambda: f'{date.today().year}-{date.today().year + 1}')
    roll_number = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    enrolled_date = db.Column(db.Date, default=date.today)
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'class_id', 'academic_year', name='uq_student_class_year'),
    )


# ===================== ATTENDANCE MODELS =====================
class AttendanceSession(db.Model, TimestampMixin):
    """Tracks attendance marking sessions (who marked what when)"""
    __tablename__ = 'attendance_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    period = db.Column(db.String(20), default='morning')  # morning, afternoon, evening
    total_students = db.Column(db.Integer, default=0)
    present_count = db.Column(db.Integer, default=0)
    absent_count = db.Column(db.Integer, default=0)
    late_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='completed')  # in_progress, completed, cancelled
    
    teacher = db.relationship('Teacher', backref='attendance_sessions', lazy='joined',
                             foreign_keys='AttendanceSession.teacher_id')
    class_rel = db.relationship('Class', backref='attendance_sessions', lazy='joined',
                               foreign_keys='AttendanceSession.class_id')
    
    __table_args__ = (
        db.UniqueConstraint('class_id', 'date', 'period', name='uq_attendance_session'),
    )


class Attendance(db.Model, TimestampMixin):
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), default='present')  # present, absent, late, holiday, not_marked
    period = db.Column(db.String(20), default='morning')  # morning, afternoon, evening, full_day
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'))
    remarks = db.Column(db.String(500))
    marked_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    marker = db.relationship('Teacher', backref='marked_attendance', lazy='joined',
                            foreign_keys='Attendance.marked_by')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'date', 'period', name='uq_student_attendance'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'date': self.date.strftime('%Y-%m-%d') if self.date else '',
            'status': self.status,
            'period': self.period
        }


# ===================== MARKS & EXAMS =====================
class Exam(db.Model, TimestampMixin):
    __tablename__ = 'exams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # e.g., "Unit Test 1 - March 2026"
    exam_type = db.Column(db.String(50), default='unit_test')  # unit_test, half_yearly, final, monthly_test, pre_board, weekly_test
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    total_marks = db.Column(db.Integer, default=100)
    passing_marks = db.Column(db.Integer, default=33)
    date = db.Column(db.Date, default=date.today)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    description = db.Column(db.Text)
    is_published = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    # Relationships
    marks_list = db.relationship('Marks', backref='exam', lazy='dynamic')
    creator = db.relationship('Teacher', backref='created_exams', lazy='joined',
                            foreign_keys='Exam.created_by')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'exam_type': self.exam_type,
            'class_id': self.class_id,
            'subject_id': self.subject_id,
            'total_marks': self.total_marks,
            'date': self.date.strftime('%Y-%m-%d') if self.date else ''
        }


class Marks(db.Model, TimestampMixin):
    __tablename__ = 'marks'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    exam_type = db.Column(db.String(50), default='unit_test')
    marks_obtained = db.Column(db.Float, nullable=False)
    max_marks = db.Column(db.Float, default=100.0)
    percentage = db.Column(db.Float)
    grade = db.Column(db.String(5))
    exam_date = db.Column(db.Date, default=date.today)
    remarks = db.Column(db.String(500))
    entered_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    is_verified = db.Column(db.Boolean, default=False)
    verified_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    verified_at = db.Column(db.DateTime)
    
    # Relationships
    enterer = db.relationship('Teacher', backref='entered_marks', lazy='joined',
                             foreign_keys='Marks.entered_by')
    verifier = db.relationship('Teacher', backref='verified_marks', lazy='joined',
                              foreign_keys='Marks.verified_by')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'exam_id', 'subject_id', name='uq_student_exam_subject'),
    )
    
    def calculate_grade(self):
        """Calculate letter grade based on percentage."""
        if self.percentage is None:
            return None
        if self.percentage >= 90: return 'A+'
        if self.percentage >= 80: return 'A'
        if self.percentage >= 70: return 'B+'
        if self.percentage >= 60: return 'B'
        if self.percentage >= 50: return 'C'
        if self.percentage >= 40: return 'D'
        return 'F'
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'subject_id': self.subject_id,
            'exam_id': self.exam_id,
            'marks_obtained': self.marks_obtained,
            'max_marks': self.max_marks,
            'percentage': round(self.percentage, 1) if self.percentage else 0,
            'grade': self.grade or self.calculate_grade()
        }


class BulkMarksEntry(db.Model, TimestampMixin):
    """Track bulk marks entry sessions"""
    __tablename__ = 'bulk_marks_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    entered_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    total_students = db.Column(db.Integer, default=0)
    marks_entered = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed
    session_data = db.Column(db.JSON)  # Backup of the entered data


# ===================== FEE & PAYMENT MODELS =====================
class FeePayment(db.Model, TimestampMixin):
    __tablename__ = 'fee_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_mode = db.Column(db.String(50), default='cash')  # cash, online, bank_transfer, cheque, razorpay
    status = db.Column(db.String(20), default='pending')  # pending, paid, failed, refunded
    receipt_no = db.Column(db.String(50), unique=True)
    razorpay_order_id = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    razorpay_signature = db.Column(db.String(200))
    transaction_id = db.Column(db.String(100))
    paid_for_month = db.Column(db.String(20))  # e.g., "2026-06"
    description = db.Column(db.String(500))
    received_by = db.Column(db.Integer, db.ForeignKey('admins.id'))
    discount = db.Column(db.Float, default=0.0)
    late_fee = db.Column(db.Float, default=0.0)
    
    receiver = db.relationship('Admin', backref='collected_payments', lazy='joined',
                              foreign_keys='FeePayment.received_by')
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'amount': self.amount,
            'payment_date': self.payment_date.strftime('%Y-%m-%d %H:%M') if self.payment_date else '',
            'payment_mode': self.payment_mode,
            'status': self.status,
            'receipt_no': self.receipt_no
        }


class FeeReminder(db.Model, TimestampMixin):
    __tablename__ = 'fee_reminders'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    grace_days = db.Column(db.Integer, default=7)
    grace_end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='pending')  # pending, paid, overridden, expired
    reminder_count = db.Column(db.Integer, default=0)
    last_reminder_sent = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    paid_amount = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'))
    
    creator = db.relationship('Admin', backref='created_reminders', lazy='joined',
                             foreign_keys='FeeReminder.created_by')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.due_date and not self.grace_end_date:
            self.grace_end_date = self.due_date + timedelta(days=self.grace_days)
    
    def is_overdue(self):
        return date.today() > self.due_date
    
    def is_grace_expired(self):
        return self.grace_end_date and date.today() > self.grace_end_date
    
    def days_remaining(self):
        if not self.due_date:
            return 0
        return (self.due_date - date.today()).days
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'amount': self.amount,
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else '',
            'grace_end_date': self.grace_end_date.strftime('%Y-%m-%d') if self.grace_end_date else '',
            'status': self.status,
            'days_remaining': self.days_remaining()
        }


# ===================== DOUBT / STUDY MATERIAL =====================
class Doubt(db.Model, TimestampMixin):
    __tablename__ = 'doubts'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    title = db.Column(db.String(200))
    question = db.Column(db.Text, nullable=False)
    question_image_url = db.Column(db.String(500))
    is_resolved = db.Column(db.Boolean, default=False)
    answer = db.Column(db.Text)
    answer_image_url = db.Column(db.String(500))
    resolved_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    resolved_at = db.Column(db.DateTime)
    priority = db.Column(db.String(20), default='normal')  # low, normal, high, urgent
    
    def __repr__(self):
        return f'Doubt #{self.id} by Student #{self.student_id}'
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'subject_id': self.subject_id,
            'question': self.question[:100] + ('...' if len(self.question) > 100 else ''),
            'is_resolved': self.is_resolved,
            'answer': self.answer[:100] + ('...' if self.answer and len(self.answer) > 100 else '') if self.answer else None,
            'created': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
            'priority': self.priority
        }


class StudyMaterial(db.Model, TimestampMixin):
    __tablename__ = 'study_materials'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    file_type = db.Column(db.String(20))  # pdf, doc, video, link, image
    file_url = db.Column(db.String(500))
    file_size = db.Column(db.Integer)  # in bytes
    thumbnail_url = db.Column(db.String(500))
    is_public = db.Column(db.Boolean, default=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    tags = db.Column(db.JSON, default=list)
    download_count = db.Column(db.Integer, default=0)
    
    uploader = db.relationship('Teacher', backref='uploaded_materials', lazy='joined',
                              foreign_keys='StudyMaterial.uploaded_by')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'subject_id': self.subject_id,
            'class_id': self.class_id,
            'file_type': self.file_type,
            'file_url': self.file_url,
            'created': self.created_at.strftime('%Y-%m-%d') if self.created_at else ''
        }


# ===================== TIMETABLE =====================
class Timetable(db.Model, TimestampMixin):
    __tablename__ = 'timetables'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room_number = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    academic_year = db.Column(db.String(20), default=lambda: f'{date.today().year}-{date.today().year + 1}')
    
    teacher = db.relationship('Teacher', backref='timetable_entries', lazy='joined',
                             foreign_keys='Timetable.teacher_id')
    
    __table_args__ = (
        db.UniqueConstraint('class_id', 'day_of_week', 'start_time', 'academic_year', name='uq_timetable_slot'),
    )


# ===================== TEST / QUIZ =====================
class TestScore(db.Model, TimestampMixin):
    __tablename__ = 'test_scores'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    test_name = db.Column(db.String(200), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    score = db.Column(db.Float, nullable=False)
    max_score = db.Column(db.Float, default=100.0)
    percentage = db.Column(db.Float)
    time_taken = db.Column(db.Integer)  # seconds
    attempted_on = db.Column(db.DateTime, default=datetime.utcnow)
    answers_json = db.Column(db.JSON)  # Store student's answers
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'test_name': self.test_name,
            'score': self.score,
            'max_score': self.max_score,
            'percentage': round(self.percentage, 1) if self.percentage else 0,
            'attempted_on': self.attempted_on.strftime('%Y-%m-%d %H:%M') if self.attempted_on else ''
        }


# ===================== WHATSAPP LOG =====================
class WhatsAppLog(db.Model, TimestampMixin):
    __tablename__ = 'whatsapp_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='sent')  # sent, failed, delivered, read
    twilio_sid = db.Column(db.String(100))
    notes = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'phone': self.phone_number,
            'message': self.message[:100],
            'status': self.status,
            'sent_at': self.sent_at.strftime('%Y-%m-%d %H:%M') if self.sent_at else ''
        }


# ===================== AUDIT LOG =====================
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_role = db.Column(db.String(20), db.Index)  # admin, teacher, student, parent, or None
    user_id = db.Column(db.String(50), db.Index)
    action = db.Column(db.String(100), nullable=False, db.Index)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    resource_type = db.Column(db.String(50))  # e.g., 'student', 'marks', 'fee'
    resource_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, db.Index)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_role': self.user_role,
            'user_id': self.user_id,
            'action': self.action,
            'details': self.details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


# ===================== NOTIFICATION =====================
class Notification(db.Model, TimestampMixin):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    user_type = db.Column(db.String(20), nullable=False)  # student, teacher, parent, admin
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='info')  # info, warning, success, error, fee, marks, attendance
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    link = db.Column(db.String(500))  # Deep link to relevant page
    image_url = db.Column(db.String(500))
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.notification_type,
            'is_read': self.is_read,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else ''
        }


# ===================== DATABASE INIT =====================
def init_db():
    """Create all tables and seed initial data."""
    db.create_all()
    
    # Create default admin if not exists
    from flask import current_app
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@fusioncoaching.in')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'Admin@Fusion2026')
    
    admin = Admin.query.filter_by(email=admin_email).first()
    if not admin:
        admin = Admin(
            name='Fusion Admin',
            email=admin_email,
            phone='+919999999999',
            password_hash=generate_password_hash(admin_password),
            role='admin',
            is_superadmin=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f'✅ Default admin created: {admin_email} / {admin_password}')
    
    # Create default subjects if empty
    if Subject.query.count() == 0:
        default_subjects = [
            Subject(name='Physics', code='PHY', max_marks_theory=70, max_marks_practical=30),
            Subject(name='Chemistry', code='CHEM', max_marks_theory=70, max_marks_practical=30),
            Subject(name='Mathematics', code='MATH', max_marks_theory=80, max_marks_practical=20),
            Subject(name='Biology', code='BIO', max_marks_theory=70, max_marks_practical=30),
            Subject(name='English', code='ENG', max_marks_theory=80, max_marks_practical=20),
            Subject(name='Hindi', code='HIN', max_marks_theory=80, max_marks_practical=20),
        ]
        db.session.add_all(default_subjects)
        db.session.commit()
        print(f'✅ {len(default_subjects)} default subjects created')
    
    # Create default classes if empty
    if Class.query.count() == 0:
        default_classes = [
            Class(name='Class 11', section='A'),
            Class(name='Class 11', section='B'),
            Class(name='Class 12', section='A'),
            Class(name='Class 12', section='B'),
            Class(name='Dropper Batch', section='A'),
        ]
        db.session.add_all(default_classes)
        db.session.commit()
        print(f'✅ {len(default_classes)} default classes created')
