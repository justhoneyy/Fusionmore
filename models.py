from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date, timedelta
import uuid

db = SQLAlchemy()

# ===================== ASSOCIATION TABLES =====================

student_subjects = db.Table('student_subjects',
    db.Column('student_id', db.Integer, db.ForeignKey('students.id'), primary_key=True),
    db.Column('subject_id', db.Integer, db.ForeignKey('subjects.id'), primary_key=True)
)

teacher_subjects = db.Table('teacher_subjects',
    db.Column('teacher_id', db.Integer, db.ForeignKey('teachers.id'), primary_key=True),
    db.Column('subject_id', db.Integer, db.ForeignKey('subjects.id'), primary_key=True)
)

class_subjects = db.Table('class_subjects',
    db.Column('class_id', db.Integer, db.ForeignKey('classes.id'), primary_key=True),
    db.Column('subject_id', db.Integer, db.ForeignKey('subjects.id'), primary_key=True)
)

# ===================== USER MIXIN =====================

class User(UserMixin):
    """Base user mixin for authentication"""
    pass

# ===================== ADMIN =====================

class Admin(db.Model, User):
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    profile_pic = db.Column(db.String(256))
    is_super_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def get_id(self):
        return f'admin_{self.id}'

# ===================== CLASS =====================

class Class(db.Model):
    __tablename__ = 'classes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # e.g., "Class 11 PCM"
    section = db.Column(db.String(10), default='A')
    code = db.Column(db.String(20), unique=True)  # e.g., "11PCM-A"
    stream = db.Column(db.String(20))  # science, commerce
    academic_year = db.Column(db.String(20), default='2026-27')
    fees = db.Column(db.Float, default=0.0)
    room_number = db.Column(db.String(20))
    class_teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    subjects = db.relationship('Subject', secondary=class_subjects, backref='classes')
    students = db.relationship('Student', backref='class_info', lazy='dynamic')
    
    def __repr__(self):
        return f'{self.name} - {self.section}'

# ===================== SUBJECT =====================

class Subject(db.Model):
    __tablename__ = 'subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True)
    description = db.Column(db.Text)
    is_lab = db.Column(db.Boolean, default=False)
    max_marks = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return self.name

# ===================== STUDENT =====================

class Student(db.Model, User):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)  # e.g., FUS-2026-0001
    admission_number = db.Column(db.String(30), unique=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    parent_phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    address = db.Column(db.Text)
    
    # Class info
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    roll_number = db.Column(db.Integer)
    section = db.Column(db.String(10))
    
    # Profile
    profile_pic = db.Column(db.String(256))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_fee_locked = db.Column(db.Boolean, default=False)
    fee_due_date = db.Column(db.Date)
    fee_lock_date = db.Column(db.Date)
    
    # Parent info
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    current_device_id = db.Column(db.String(256))
    current_session_token = db.Column(db.String(256))
    
    # Relationships
    attendance_records = db.relationship('Attendance', backref='student', lazy='dynamic')
    marks_records = db.relationship('Marks', backref='student', lazy='dynamic')
    fee_records = db.relationship('FeePayment', backref='student', lazy='dynamic')
    doubts = db.relationship('Doubt', backref='student', lazy='dynamic')
    test_attempts = db.relationship('TestAttempt', backref='student', lazy='dynamic')
    notifications = db.relationship('Notification', backref='student', lazy='dynamic')
    device_sessions = db.relationship('DeviceSession', backref='student', lazy='dynamic')
    
    subjects = db.relationship('Subject', secondary=student_subjects, backref='students')
    
    def get_id(self):
        return f'student_{self.id}'
    
    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name or ""}'.strip()
    
    @property
    def attendance_percentage(self):
        total = self.attendance_records.count()
        if total == 0:
            return 0
        present = self.attendance_records.filter_by(status='present').count()
        return round((present / total) * 100, 1)
    
    @property
    def is_fee_overdue(self):
        if not self.fee_due_date:
            return False
        return date.today() > self.fee_due_date
    
    @property
    def grace_days_remaining(self):
        if not self.fee_due_date:
            return 999
        from config import Config
        grace_end = self.fee_due_date + timedelta(days=Config.FEE_GRACE_PERIOD_DAYS)
        remaining = (grace_end - date.today()).days
        return max(0, remaining)

# ===================== TEACHER =====================

class Teacher(db.Model, User):
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.String(20), unique=True)  # e.g., FAC-2026-0001
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    qualification = db.Column(db.String(256))
    specialization = db.Column(db.String(256))
    experience_years = db.Column(db.Integer)
    date_of_joining = db.Column(db.Date)
    gender = db.Column(db.String(10))
    address = db.Column(db.Text)
    profile_pic = db.Column(db.String(256))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    classes_teaching = db.relationship('Class', backref='class_teacher', lazy='dynamic')
    subjects_teaching = db.relationship('Subject', secondary=teacher_subjects, backref='teachers')
    attendance_marked = db.relationship('Attendance', backref='marked_by_teacher', lazy='dynamic')
    
    def get_id(self):
        return f'teacher_{self.id}'
    
    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name or ""}'.strip()

# ===================== PARENT =====================

class Parent(db.Model, User):
    __tablename__ = 'parents'
    
    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.String(20), unique=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    alternate_phone = db.Column(db.String(20))
    occupation = db.Column(db.String(100))
    address = db.Column(db.Text)
    profile_pic = db.Column(db.String(256))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    children = db.relationship('Student', backref='parent_info', lazy='dynamic')
    
    def get_id(self):
        return f'parent_{self.id}'
    
    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name or ""}'.strip()

# ===================== ATTENDANCE =====================

class Attendance(db.Model):
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), nullable=False)  # present, absent, late, holiday
    marked_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    remarks = db.Column(db.String(256))
    period = db.Column(db.String(20))  # morning, afternoon, full_day
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'date', 'period', name='unique_attendance'),
    )

# ===================== MARKS =====================

class Marks(db.Model):
    __tablename__ = 'marks'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    exam_type = db.Column(db.String(50), nullable=False)  # unit_test, half_yearly, final, monthly_test
    exam_name = db.Column(db.String(100))
    marks_obtained = db.Column(db.Float, nullable=False)
    max_marks = db.Column(db.Float, nullable=False, default=100)
    grade = db.Column(db.String(5))
    remarks = db.Column(db.String(256))
    exam_date = db.Column(db.Date, default=date.today)
    entered_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'subject_id', 'exam_type', 'exam_name', name='unique_marks'),
    )
    
    @property
    def percentage(self):
        if self.max_marks > 0:
            return round((self.marks_obtained / self.max_marks) * 100, 1)
        return 0

# ===================== FEE PAYMENT =====================

class FeePayment(db.Model):
    __tablename__ = 'fee_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    receipt_number = db.Column(db.String(50), unique=True)
    amount = db.Column(db.Float, nullable=False)
    paid_amount = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0.0)
    fine = db.Column(db.Float, default=0.0)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.Date)
    payment_mode = db.Column(db.String(30))  # cash, online, cheque, razorpay
    payment_status = db.Column(db.String(20), default='paid')  # paid, pending, failed
    transaction_id = db.Column(db.String(100))
    razorpay_order_id = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    month = db.Column(db.String(20))
    year = db.Column(db.String(10))
    remarks = db.Column(db.String(256))
    
    def __repr__(self):
        return f'FeePayment {self.receipt_number} - ₹{self.paid_amount}'

# ===================== ONLINE TEST =====================

class Test(db.Model):
    __tablename__ = 'tests'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    # Test configuration
    duration_minutes = db.Column(db.Integer, nullable=False)
    total_marks = db.Column(db.Integer, nullable=False)
    passing_marks = db.Column(db.Integer, default=0)
    negative_marking = db.Column(db.Boolean, default=False)
    negative_mark_value = db.Column(db.Float, default=0.0)
    shuffle_questions = db.Column(db.Boolean, default=True)
    fullscreen_mode = db.Column(db.Boolean, default=True)
    auto_submit = db.Column(db.Boolean, default=True)
    show_result_immediately = db.Column(db.Boolean, default=True)
    
    # Schedule
    scheduled_date = db.Column(db.DateTime)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    questions = db.relationship('Question', backref='test', lazy='dynamic', cascade='all, delete-orphan')
    attempts = db.relationship('TestAttempt', backref='test', lazy='dynamic')

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id'), nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # mcq, subjective
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON)  # For MCQ: {"A": "text", "B": "text", "C": "text", "D": "text"}
    correct_answer = db.Column(db.Text)  # For MCQ: "A"/"B"/"C"/"D", For subjective: answer text
    marks = db.Column(db.Float, nullable=False, default=1.0)
    difficulty = db.Column(db.String(20), default='medium')
    order_index = db.Column(db.Integer, default=0)
    
    def to_dict(self, show_answer=False):
        data = {
            'id': self.id,
            'question_type': self.question_type,
            'question_text': self.question_text,
            'marks': self.marks,
            'order_index': self.order_index,
        }
        if self.question_type == 'mcq':
            data['options'] = self.options
        if show_answer:
            data['correct_answer'] = self.correct_answer
        return data

class TestAttempt(db.Model):
    __tablename__ = 'test_attempts'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    # Status
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)
    is_submitted = db.Column(db.Boolean, default=False)
    
    # Auto-save
    answers = db.Column(db.JSON)  # {"question_id": "selected_answer"}
    
    # Evaluation
    total_marks_obtained = db.Column(db.Float)
    correct_count = db.Column(db.Integer, default=0)
    incorrect_count = db.Column(db.Integer, default=0)
    unanswered_count = db.Column(db.Integer, default=0)
    negative_marks = db.Column(db.Float, default=0.0)
    percentage = db.Column(db.Float)
    rank = db.Column(db.Integer)
    
    # Anti-cheat
    fullscreen_exits = db.Column(db.Integer, default=0)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(256))
    
    __table_args__ = (
        db.UniqueConstraint('test_id', 'student_id', name='unique_test_attempt'),
    )

# ===================== DOUBT SECTION =====================

class Doubt(db.Model):
    __tablename__ = 'doubts'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    title = db.Column(db.String(200))
    question_text = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(256))
    
    # Status
    is_resolved = db.Column(db.Boolean, default=False)
    resolved_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    answer_text = db.Column(db.Text)
    answer_image = db.Column(db.String(256))
    resolved_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    teacher = db.relationship('Teacher', backref='answered_doubts')

# ===================== STUDY MATERIAL =====================

class StudyMaterial(db.Model):
    __tablename__ = 'study_materials'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    file_type = db.Column(db.String(20))  # pdf, ppt, doc, image, video
    file_path = db.Column(db.String(256), nullable=False)
    file_size = db.Column(db.Integer)
    
    # Ownership
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    # Type
    material_type = db.Column(db.String(30))  # notes, assignment, lecture, reference
    is_downloadable = db.Column(db.Boolean, default=False)
    
    # Watermark
    watermark_text = db.Column(db.String(256))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    download_count = db.Column(db.Integer, default=0)

# ===================== LECTURE VIDEO =====================

class LectureVideo(db.Model):
    __tablename__ = 'lecture_videos'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    video_path = db.Column(db.String(256), nullable=False)
    thumbnail_path = db.Column(db.String(256))
    duration_seconds = db.Column(db.Integer)
    
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    view_count = db.Column(db.Integer, default=0)

class VideoProgress(db.Model):
    __tablename__ = 'video_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('lecture_videos.id'), nullable=False)
    progress_seconds = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    last_watched = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'video_id', name='unique_video_progress'),
    )

# ===================== NOTICE =====================

class Notice(db.Model):
    __tablename__ = 'notices'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    
    # Targeting
    target_type = db.Column(db.String(20))  # all, class, section
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    
    created_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    created_by_admin = db.Column(db.Integer, db.ForeignKey('admins.id'))
    
    is_urgent = db.Column(db.Boolean, default=False)
    attachment_path = db.Column(db.String(256))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

# ===================== HOMEWORK =====================

class Homework(db.Model):
    __tablename__ = 'homework'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    attachment_path = db.Column(db.String(256))
    deadline = db.Column(db.DateTime)
    max_marks = db.Column(db.Integer)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class HomeworkSubmission(db.Model):
    __tablename__ = 'homework_submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    homework_id = db.Column(db.Integer, db.ForeignKey('homework.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    submission_text = db.Column(db.Text)
    attachment_path = db.Column(db.String(256))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Evaluation
    is_evaluated = db.Column(db.Boolean, default=False)
    marks_obtained = db.Column(db.Float)
    feedback = db.Column(db.Text)
    evaluated_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    
    __table_args__ = (
        db.UniqueConstraint('homework_id', 'student_id', name='unique_homework_submission'),
    )

# ===================== NOTIFICATION =====================

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(30))  # attendance, fee, marks, notice, homework, test, doubt
    is_read = db.Column(db.Boolean, default=False)
    reference_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===================== DEVICE SESSION =====================

class DeviceSession(db.Model):
    __tablename__ = 'device_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    device_id = db.Column(db.String(256), nullable=False)
    device_name = db.Column(db.String(256))
    device_type = db.Column(db.String(50))  # mobile, desktop, tablet
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(512))
    session_token = db.Column(db.String(256), unique=True)
    is_active = db.Column(db.Boolean, default=True)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime)

# ===================== AUDIT LOG =====================

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(20))  # admin, teacher, student, parent
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===================== TIMETABLE =====================

class Timetable(db.Model):
    __tablename__ = 'timetable'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room_number = db.Column(db.String(20))
    
    __table_args__ = (
        db.UniqueConstraint('class_id', 'day_of_week', 'start_time', name='unique_timetable_slot'),
    )

# ===================== BULK MARKS ENTRY MODEL =====================

class BulkMarksEntry(db.Model):
    """Tracks bulk marks entry sessions"""
    __tablename__ = 'bulk_marks_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    exam_type = db.Column(db.String(50), nullable=False)
    exam_name = db.Column(db.String(100))
    exam_date = db.Column(db.Date, default=date.today)
    entered_by = db.Column(db.Integer, db.ForeignKey('teachers.id'))
    total_students = db.Column(db.Integer)
    entries_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_completed = db.Column(db.Boolean, default=False)

# ===================== WHATSAPP LOG =====================

class WhatsAppLog(db.Model):
    __tablename__ = 'whatsapp_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    parent_phone = db.Column(db.String(20))
    message_type = db.Column(db.String(50))  # fee_reminder, attendance, marks, notice
    message_body = db.Column(db.Text)
    status = db.Column(db.String(20))  # sent, failed, pending
    twilio_sid = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===================== DATABASE INIT =====================

def init_db():
    """Create all tables"""
    db.create_all()
    
    # Create default admin if not exists
    from werkzeug.security import generate_password_hash
    from config import Config
    
    admin = Admin.query.filter_by(email=Config.ADMIN_EMAIL).first()
    if not admin:
        admin = Admin(
            username='admin',
            email=Config.ADMIN_EMAIL,
            password_hash=generate_password_hash(Config.ADMIN_PASSWORD),
            full_name='Super Admin',
            is_super_admin=True
        )
        db.session.add(admin)
        db.session.commit()
    
    # Create default subjects if none exist
    if Subject.query.count() == 0:
        default_subjects = [
            'Physics', 'Chemistry', 'Mathematics', 'Biology',
            'English', 'Hindi', 'Computer Science',
            'Accounts', 'Economics', 'Business Studies',
            'Physical Education'
        ]
        for s in default_subjects:
            subj = Subject(name=s, code=s[:3].upper() + str(Subject.query.count() + 1))
            db.session.add(subj)
        db.session.commit()
    
    print("✅ Database initialized successfully!")
