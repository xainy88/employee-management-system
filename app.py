from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import StringIO
import base64

# PostgreSQL import with fallback
try:
    import psycopg
    POSTGRES_AVAILABLE = True
    print("DEBUG: psycopg3 available")
except ImportError:
    POSTGRES_AVAILABLE = False
    print("DEBUG: psycopg3 not available, using SQLite")

app = Flask(__name__)
app.secret_key = 'employee_management_system_secret_key_2024'

def get_db_connection():
    # Try PostgreSQL first (for production)
    database_url = os.environ.get('DATABASE_URL')
    
    print(f"DEBUG: DATABASE_URL from environment: {database_url}")
    
    if database_url and POSTGRES_AVAILABLE:
        try:
            conn = psycopg.connect(database_url)
            print("DEBUG: Successfully connected to PostgreSQL with psycopg3!")
            return conn
        except Exception as e:
            print(f"DEBUG: PostgreSQL connection failed: {str(e)}")
            print("DEBUG: Falling back to SQLite...")
    
    # Fallback to SQLite (for development)
    try:
        conn = sqlite3.connect('employees.db')
        conn.row_factory = sqlite3.Row
        print("DEBUG: Successfully connected to SQLite!")
        return conn
    except Exception as e:
        print(f"DEBUG: SQLite connection also failed: {str(e)}")
        raise e

# Database initialization - FIXED: No sample data insertion
def init_db():
    conn = get_db_connection()
    
    # Check if we're using PostgreSQL or SQLite
    is_postgres = POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL')
    
    if is_postgres:
        # PostgreSQL table creation
        with conn.cursor() as c:
            # Create employees table WITH BANK FIELDS
            c.execute('''
                CREATE TABLE IF NOT EXISTS employees (
                    id SERIAL PRIMARY KEY,
                    employee_id TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    hourly_rate REAL NOT NULL,
                    passport_number TEXT,
                    bank_name TEXT,
                    bank_account_name TEXT,
                    bank_account_number TEXT,
                    status TEXT DEFAULT 'Active',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create work entries table
            c.execute('''
                CREATE TABLE IF NOT EXISTS work_entries (
                    id SERIAL PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    work_date TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    break_minutes INTEGER DEFAULT 60,
                    normal_hours REAL DEFAULT 0,
                    overtime_hours REAL DEFAULT 0,
                    holiday_hours REAL DEFAULT 0,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create advance payments table
            c.execute('''
                CREATE TABLE IF NOT EXISTS advance_payments (
                    id SERIAL PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    payment_date TEXT NOT NULL,
                    reason TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create food expenses table
            c.execute('''
                CREATE TABLE IF NOT EXISTS food_expenses (
                    id SERIAL PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    expense_date TEXT NOT NULL,
                    description TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create attendance photos table
            c.execute('''
                CREATE TABLE IF NOT EXISTS attendance_photos (
                    id SERIAL PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    work_date TEXT NOT NULL,
                    photo_type TEXT NOT NULL,
                    photo_data TEXT NOT NULL,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create payment_records table
            c.execute('''
                CREATE TABLE IF NOT EXISTS payment_records (
                    id SERIAL PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    payment_date TEXT NOT NULL,
                    amount_paid REAL NOT NULL,
                    payment_type TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'paid',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
    else:
        # SQLite table creation
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                hourly_rate REAL NOT NULL,
                passport_number TEXT,
                bank_name TEXT,
                bank_account_name TEXT,
                bank_account_number TEXT,
                status TEXT DEFAULT 'Active',
                created_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS work_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                break_minutes INTEGER DEFAULT 60,
                normal_hours REAL DEFAULT 0,
                overtime_hours REAL DEFAULT 0,
                holiday_hours REAL DEFAULT 0,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS advance_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_date TEXT NOT NULL,
                reason TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS food_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                amount REAL NOT NULL,
                expense_date TEXT NOT NULL,
                description TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS attendance_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                photo_type TEXT NOT NULL,
                photo_data TEXT NOT NULL,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS payment_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                amount_paid REAL NOT NULL,
                payment_type TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'paid',
                created_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully with empty tables!")

def calculate_hours(start_time, end_time, break_minutes=60, is_holiday=False):
    """Calculate normal and overtime hours"""
    start = datetime.strptime(start_time, '%H:%M')
    end = datetime.strptime(end_time, '%H:%M')
    
    # Calculate total minutes worked
    total_minutes = (end - start).total_seconds() / 60
    total_minutes -= break_minutes  # Subtract break time
    
    total_hours = total_minutes / 60
    
    if is_holiday:
        return 0, 0, total_hours  # All hours are holiday hours (1.5x rate)
    
    # Normal working hours: 8 hours per day
    normal_hours = min(total_hours, 8)
    overtime_hours = max(total_hours - 8, 0)
    
    return normal_hours, overtime_hours, 0

# Routes
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/debug_db')
def debug_db():
    """Debug route to check database connection"""
    try:
        conn = get_db_connection()
        conn.close()
        return "Database connection successful!"
    except Exception as e:
        return f"Database connection failed: {str(e)}"

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    user_type = request.form.get('user_type')
    
    print(f"Login attempt - User Type: {user_type}, Username: {username}, Password: {password}")
    
    if user_type == 'admin':
        if username == 'admin' and password == 'admin':
            session['logged_in'] = True
            session['username'] = username
            session['user_type'] = 'admin'
            print("Admin login successful")
            return redirect(url_for('admin_dashboard'))
        else:
            print("Admin login failed - invalid credentials")
            flash('Invalid admin credentials!', 'error')
            return redirect(url_for('index'))
    
    elif user_type == 'employee':
        conn = get_db_connection()
        if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
            employee = conn.execute(
                'SELECT * FROM employees WHERE employee_id = %s AND status = %s',
                (username, 'Active')
            ).fetchone()
        else:
            employee = conn.execute(
                'SELECT * FROM employees WHERE employee_id = ? AND status = "Active"',
                (username,)
            ).fetchone()
        conn.close()
        
        if employee:
            session['logged_in'] = True
            session['username'] = employee['full_name']
            session['user_type'] = 'employee'
            session['employee_id'] = employee['employee_id']
            session['employee_data'] = dict(employee)
            print(f"Employee login successful: {employee['full_name']}")
            return redirect(url_for('employee_dashboard'))
        else:
            print("Employee login failed - invalid employee ID")
            flash('Invalid employee ID!', 'error')
            return redirect(url_for('index'))
    else:
        print(f"Invalid user type: {user_type}")
        flash('Invalid login type!', 'error')
        return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        print("Admin dashboard access denied - not logged in or not admin")
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get employee statistics
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        total_employees = conn.execute('SELECT COUNT(*) FROM employees').fetchone()[0]
        active_employees = conn.execute('SELECT COUNT(*) FROM employees WHERE status = %s', ('Active',)).fetchone()[0]
        inactive_employees = conn.execute('SELECT COUNT(*) FROM employees WHERE status = %s', ('Inactive',)).fetchone()[0]
    else:
        total_employees = conn.execute('SELECT COUNT(*) FROM employees').fetchone()[0]
        active_employees = conn.execute('SELECT COUNT(*) FROM employees WHERE status = "Active"').fetchone()[0]
        inactive_employees = conn.execute('SELECT COUNT(*) FROM employees WHERE status = "Inactive"').fetchone()[0]
    
    # Get payroll summary for current month
    current_month = datetime.now().strftime('%Y-%m')
    
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        payroll_data = conn.execute('''
            SELECT e.employee_id, e.full_name, e.hourly_rate,
                   COALESCE(SUM(w.normal_hours), 0) as total_normal_hours,
                   COALESCE(SUM(w.overtime_hours), 0) as total_overtime_hours,
                   COALESCE(SUM(w.holiday_hours), 0) as total_holiday_hours,
                   COALESCE(SUM(a.amount), 0) as total_advances,
                   COALESCE(SUM(f.amount), 0) as total_food_expenses
            FROM employees e
            LEFT JOIN work_entries w ON e.employee_id = w.employee_id AND to_char(w.work_date::timestamp, 'YYYY-MM') = %s
            LEFT JOIN advance_payments a ON e.employee_id = a.employee_id AND to_char(a.payment_date::timestamp, 'YYYY-MM') = %s
            LEFT JOIN food_expenses f ON e.employee_id = f.employee_id AND to_char(f.expense_date::timestamp, 'YYYY-MM') = %s
            GROUP BY e.employee_id, e.full_name, e.hourly_rate
        ''', (current_month, current_month, current_month)).fetchall()
    else:
        payroll_data = conn.execute('''
            SELECT e.employee_id, e.full_name, e.hourly_rate,
                   COALESCE(SUM(w.normal_hours), 0) as total_normal_hours,
                   COALESCE(SUM(w.overtime_hours), 0) as total_overtime_hours,
                   COALESCE(SUM(w.holiday_hours), 0) as total_holiday_hours,
                   COALESCE(SUM(a.amount), 0) as total_advances,
                   COALESCE(SUM(f.amount), 0) as total_food_expenses
            FROM employees e
            LEFT JOIN work_entries w ON e.employee_id = w.employee_id AND strftime('%Y-%m', w.work_date) = ?
            LEFT JOIN advance_payments a ON e.employee_id = a.employee_id AND strftime('%Y-%m', a.payment_date) = ?
            LEFT JOIN food_expenses f ON e.employee_id = f.employee_id AND strftime('%Y-%m', f.expense_date) = ?
            GROUP BY e.employee_id, e.full_name, e.hourly_rate
        ''', (current_month, current_month, current_month)).fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         total_employees=total_employees,
                         active_employees=active_employees,
                         inactive_employees=inactive_employees,
                         payroll_data=payroll_data,
                         current_month=current_month)

@app.route('/employee')
def employee_dashboard():
    if not session.get('logged_in') or session.get('user_type') != 'employee':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    employee_id = session.get('employee_id')
    
    # Get current month data
    current_month = datetime.now().strftime('%Y-%m')
    
    # Get work entries for current month
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        work_entries = conn.execute('''
            SELECT * FROM work_entries 
            WHERE employee_id = %s AND to_char(work_date::timestamp, 'YYYY-MM') = %s
            ORDER BY work_date DESC
        ''', (employee_id, current_month)).fetchall()
        
        # Get today's status
        today = datetime.now().strftime('%Y-%m-%d')
        today_entry = conn.execute(
            'SELECT * FROM work_entries WHERE employee_id = %s AND work_date = %s',
            (employee_id, today)
        ).fetchone()
    else:
        work_entries = conn.execute('''
            SELECT * FROM work_entries 
            WHERE employee_id = ? AND strftime('%Y-%m', work_date) = ?
            ORDER BY work_date DESC
        ''', (employee_id, current_month)).fetchall()
        
        # Get today's status
        today = datetime.now().strftime('%Y-%m-%d')
        today_entry = conn.execute(
            'SELECT * FROM work_entries WHERE employee_id = ? AND work_date = ?',
            (employee_id, today)
        ).fetchone()
    
    # Get payroll summary
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        payroll_summary = conn.execute('''
            SELECT 
                COALESCE(SUM(w.normal_hours), 0) as total_normal_hours,
                COALESCE(SUM(w.overtime_hours), 0) as total_overtime_hours,
                COALESCE(SUM(w.holiday_hours), 0) as total_holiday_hours,
                COALESCE(SUM(a.amount), 0) as total_advances,
                COALESCE(SUM(f.amount), 0) as total_food_expenses
            FROM work_entries w
            LEFT JOIN advance_payments a ON w.employee_id = a.employee_id AND to_char(a.payment_date::timestamp, 'YYYY-MM') = %s
            LEFT JOIN food_expenses f ON w.employee_id = f.employee_id AND to_char(f.expense_date::timestamp, 'YYYY-MM') = %s
            WHERE w.employee_id = %s AND to_char(w.work_date::timestamp, 'YYYY-MM') = %s
        ''', (current_month, current_month, employee_id, current_month)).fetchone()
    else:
        payroll_summary = conn.execute('''
            SELECT 
                COALESCE(SUM(w.normal_hours), 0) as total_normal_hours,
                COALESCE(SUM(w.overtime_hours), 0) as total_overtime_hours,
                COALESCE(SUM(w.holiday_hours), 0) as total_holiday_hours,
                COALESCE(SUM(a.amount), 0) as total_advances,
                COALESCE(SUM(f.amount), 0) as total_food_expenses
            FROM work_entries w
            LEFT JOIN advance_payments a ON w.employee_id = a.employee_id AND strftime('%Y-%m', a.payment_date) = ?
            LEFT JOIN food_expenses f ON w.employee_id = f.employee_id AND strftime('%Y-%m', f.expense_date) = ?
            WHERE w.employee_id = ? AND strftime('%Y-%m', w.work_date) = ?
        ''', (current_month, current_month, employee_id, current_month)).fetchone()
    
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = %s', (employee_id,)).fetchone()
    else:
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    
    # Calculate payment totals
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        total_earnings = conn.execute('''
            SELECT COALESCE(SUM(normal_hours + overtime_hours + holiday_hours), 0) * %s as total 
            FROM work_entries WHERE employee_id = %s
        ''', (employee['hourly_rate'], employee_id)).fetchone()[0]
        
        total_paid = conn.execute('''
            SELECT COALESCE(SUM(amount_paid), 0) as total 
            FROM payment_records WHERE employee_id = %s
        ''', (employee_id,)).fetchone()[0]
    else:
        total_earnings = conn.execute('''
            SELECT COALESCE(SUM(normal_hours + overtime_hours + holiday_hours), 0) * ? as total 
            FROM work_entries WHERE employee_id = ?
        ''', (employee['hourly_rate'], employee_id)).fetchone()[0]
        
        total_paid = conn.execute('''
            SELECT COALESCE(SUM(amount_paid), 0) as total 
            FROM payment_records WHERE employee_id = ?
        ''', (employee_id,)).fetchone()[0]
    
    pending_amount = total_earnings - total_paid
    
    conn.close()
    
    # Calculate payments
    hourly_rate = employee['hourly_rate']
    normal_pay = payroll_summary['total_normal_hours'] * hourly_rate
    overtime_pay = payroll_summary['total_overtime_hours'] * hourly_rate * 1.5  # 1.5x for overtime
    holiday_pay = payroll_summary['total_holiday_hours'] * hourly_rate * 1.5   # 1.5x for holidays
    total_earnings_calc = normal_pay + overtime_pay + holiday_pay
    grand_total = total_earnings_calc - payroll_summary['total_advances'] - payroll_summary['total_food_expenses']
    
    return render_template('employee_dashboard.html', 
                         employee=employee,
                         work_entries=work_entries,
                         payroll_summary=payroll_summary,
                         normal_pay=normal_pay,
                         overtime_pay=overtime_pay,
                         holiday_pay=holiday_pay,
                         total_earnings=total_earnings_calc,
                         grand_total=grand_total,
                         current_month=current_month,
                         total_paid=total_paid,
                         pending_amount=pending_amount,
                         today_entry=today_entry,
                         today=today)

# ===== PAYMENT MANAGEMENT ROUTES =====

@app.route('/admin/payments')
def admin_payments():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get all employees with their payment summary
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        employees = conn.execute('''
            SELECT e.*, 
                   COALESCE(SUM(w.normal_hours + w.overtime_hours + w.holiday_hours), 0) * e.hourly_rate as total_earnings,
                   COALESCE(SUM(p.amount_paid), 0) as total_paid
            FROM employees e
            LEFT JOIN work_entries w ON e.employee_id = w.employee_id
            LEFT JOIN payment_records p ON e.employee_id = p.employee_id
            GROUP BY e.id, e.employee_id, e.full_name, e.hourly_rate, e.bank_name, e.bank_account_number
            ORDER BY e.full_name
        ''').fetchall()
    else:
        employees = conn.execute('''
            SELECT e.*, 
                   COALESCE(SUM(w.normal_hours + w.overtime_hours + w.holiday_hours), 0) * e.hourly_rate as total_earnings,
                   COALESCE(SUM(p.amount_paid), 0) as total_paid
            FROM employees e
            LEFT JOIN work_entries w ON e.employee_id = w.employee_id
            LEFT JOIN payment_records p ON e.employee_id = p.employee_id
            GROUP BY e.employee_id
            ORDER BY e.full_name
        ''').fetchall()
    
    conn.close()
    
    # Calculate pending amounts
    employees_with_pay = []
    for emp in employees:
        pending_amount = emp['total_earnings'] - emp['total_paid']
        employees_with_pay.append({
            'employee_id': emp['employee_id'],
            'name': emp['full_name'],
            'hourly_rate': emp['hourly_rate'],
            'bank_name': emp['bank_name'],
            'bank_account_number': emp['bank_account_number'],
            'total_earnings': emp['total_earnings'],
            'total_paid': emp['total_paid'],
            'pending_amount': pending_amount
        })
    
    return render_template('admin_payments.html', employees=employees_with_pay)

@app.route('/admin/make_payment/<employee_id>', methods=['GET', 'POST'])
def make_payment(employee_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        amount_paid = float(request.form['amount_paid'])
        payment_type = request.form['payment_type']
        description = request.form.get('description', '')
        
        # Insert payment record
        if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
            conn.execute('''
                INSERT INTO payment_records (employee_id, payment_date, amount_paid, payment_type, description)
                VALUES (%s, CURRENT_DATE, %s, %s, %s)
            ''', (employee_id, amount_paid, payment_type, description))
        else:
            conn.execute('''
                INSERT INTO payment_records (employee_id, payment_date, amount_paid, payment_type, description)
                VALUES (?, DATE("now"), ?, ?, ?)
            ''', (employee_id, amount_paid, payment_type, description))
        
        conn.commit()
        flash(f'Payment of RM {amount_paid:.2f} recorded successfully!', 'success')
        conn.close()
        return redirect(url_for('admin_payments'))
    
    # GET request - show payment form
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = %s', (employee_id,)).fetchone()
    else:
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    
    # Calculate totals
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        total_earnings = conn.execute('''
            SELECT COALESCE(SUM(normal_hours + overtime_hours + holiday_hours), 0) * %s as total 
            FROM work_entries WHERE employee_id = %s
        ''', (employee['hourly_rate'], employee_id)).fetchone()[0]
        
        total_paid = conn.execute('''
            SELECT COALESCE(SUM(amount_paid), 0) as total 
            FROM payment_records WHERE employee_id = %s
        ''', (employee_id,)).fetchone()[0]
    else:
        total_earnings = conn.execute('''
            SELECT COALESCE(SUM(normal_hours + overtime_hours + holiday_hours), 0) * ? as total 
            FROM work_entries WHERE employee_id = ?
        ''', (employee['hourly_rate'], employee_id)).fetchone()[0]
        
        total_paid = conn.execute('''
            SELECT COALESCE(SUM(amount_paid), 0) as total 
            FROM payment_records WHERE employee_id = ?
        ''', (employee_id,)).fetchone()[0]
    
    pending_amount = total_earnings - total_paid
    
    # Get payment history
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        payment_history = conn.execute('''
            SELECT * FROM payment_records 
            WHERE employee_id = %s 
            ORDER BY payment_date DESC
        ''', (employee_id,)).fetchall()
    else:
        payment_history = conn.execute('''
            SELECT * FROM payment_records 
            WHERE employee_id = ? 
            ORDER BY payment_date DESC
        ''', (employee_id,)).fetchall()
    
    conn.close()
    
    return render_template('admin_make_payment.html', 
                         employee=employee,
                         payment_history=payment_history,
                         total_earnings=total_earnings,
                         total_paid=total_paid,
                         pending_amount=pending_amount)

# ... (other routes continue with similar PostgreSQL/SQLite checks)

@app.route('/admin/employees')
def manage_employees():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
        employees = conn.execute('SELECT * FROM employees ORDER BY created_date DESC').fetchall()
    else:
        employees = conn.execute('SELECT * FROM employees ORDER BY created_date DESC').fetchall()
    conn.close()
    
    return render_template('manage_employees.html', employees=employees)

@app.route('/admin/employees/add', methods=['POST'])
def add_employee():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    employee_id = request.form.get('employee_id')
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    hourly_rate = request.form.get('hourly_rate')
    passport_number = request.form.get('passport_number', '')
    bank_name = request.form.get('bank_name', '')
    bank_account_name = request.form.get('bank_account_name', '')
    bank_account_number = request.form.get('bank_account_number', '')
    
    try:
        conn = get_db_connection()
        if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
            conn.execute('''
                INSERT INTO employees (employee_id, full_name, email, phone, hourly_rate, passport_number, bank_name, bank_account_name, bank_account_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (employee_id, full_name, email, phone, float(hourly_rate), passport_number, bank_name, bank_account_name, bank_account_number))
        else:
            conn.execute('''
                INSERT INTO employees (employee_id, full_name, email, phone, hourly_rate, passport_number, bank_name, bank_account_name, bank_account_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (employee_id, full_name, email, phone, float(hourly_rate), passport_number, bank_name, bank_account_name, bank_account_number))
        conn.commit()
        conn.close()
        flash('Employee added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding employee: {str(e)}', 'error')
    
    return redirect(url_for('manage_employees'))

@app.route('/admin/employees/delete/<employee_id>', methods=['POST'])
def delete_employee(employee_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        if POSTGRES_AVAILABLE and os.environ.get('DATABASE_URL'):
            conn.execute('DELETE FROM employees WHERE employee_id = %s', (employee_id,))
            conn.execute('DELETE FROM work_entries WHERE employee_id = %s', (employee_id,))
            conn.execute('DELETE FROM advance_payments WHERE employee_id = %s', (employee_id,))
            conn.execute('DELETE FROM food_expenses WHERE employee_id = %s', (employee_id,))
            conn.execute('DELETE FROM attendance_photos WHERE employee_id = %s', (employee_id,))
            conn.execute('DELETE FROM payment_records WHERE employee_id = %s', (employee_id,))
        else:
            conn.execute('DELETE FROM employees WHERE employee_id = ?', (employee_id,))
            conn.execute('DELETE FROM work_entries WHERE employee_id = ?', (employee_id,))
            conn.execute('DELETE FROM advance_payments WHERE employee_id = ?', (employee_id,))
            conn.execute('DELETE FROM food_expenses WHERE employee_id = ?', (employee_id,))
            conn.execute('DELETE FROM attendance_photos WHERE employee_id = ?', (employee_id,))
            conn.execute('DELETE FROM payment_records WHERE employee_id = ?', (employee_id,))
        conn.commit()
        conn.close()
        flash('Employee deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting employee: {str(e)}', 'error')
    
    return redirect(url_for('manage_employees'))

# PRODUCTION FIX: Initialize database in both development and production
if __name__ == '__main__':
    # Development
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # Production - initialize database if needed
    init_db()
