from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import StringIO
import base64
import psycopg2
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = 'employee_management_system_secret_key_2024'

def get_db_connection():
    # Try PostgreSQL first (for production)
    database_url = os.environ.get('DATABASE_URL')
    
    print(f"DEBUG: DATABASE_URL from environment: {database_url}")
    
    if database_url:
        try:
            # Parse the database URL
            result = urlparse(database_url)
            print(f"DEBUG: Parsed URL - username: {result.username}, hostname: {result.hostname}, port: {result.port}, database: {result.path[1:]}")
            
            conn = psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port
            )
            print("DEBUG: Successfully connected to PostgreSQL!")
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
    c = conn.cursor()
    
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
    total_employees = conn.execute('SELECT COUNT(*) FROM employees').fetchone()[0]
    active_employees = conn.execute('SELECT COUNT(*) FROM employees WHERE status = "Active"').fetchone()[0]
    inactive_employees = conn.execute('SELECT COUNT(*) FROM employees WHERE status = "Inactive"').fetchone()[0]
    
    # Get payroll summary for current month
    current_month = datetime.now().strftime('%Y-%m')
    payroll_data = conn.execute('''
        SELECT e.employee_id, e.full_name, e.hourly_rate,
               COALESCE(SUM(w.normal_hours), 0) as total_normal_hours,
               COALESCE(SUM(w.overtime_hours), 0) as total_overtime_hours,
               COALESCE(SUM(w.holiday_hours), 0) as total_holiday_hours,
               COALESCE(SUM(a.amount), 0) as total_advances,
               COALESCE(SUM(f.amount), 0) as total_food_expenses
        FROM employees e
        LEFT JOIN work_entries w ON e.employee_id = w.employee_id AND to_char(w.work_date, 'YYYY-MM') = %s
        LEFT JOIN advance_payments a ON e.employee_id = a.employee_id AND to_char(a.payment_date, 'YYYY-MM') = %s
        LEFT JOIN food_expenses f ON e.employee_id = f.employee_id AND to_char(f.expense_date, 'YYYY-MM') = %s
        GROUP BY e.employee_id, e.full_name, e.hourly_rate
    ''', (current_month, current_month, current_month)).fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
                         total_employees=total_employees,
                         active_employees=active_employees,
                         inactive_employees=inactive_employees,
                         payroll_data=payroll_data,
                         current_month=current_month)

# ... (rest of your routes remain the same, but I'll include the key ones)

@app.route('/admin/employees')
def manage_employees():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
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
        conn.execute('''
            INSERT INTO employees (employee_id, full_name, email, phone, hourly_rate, passport_number, bank_name, bank_account_name, bank_account_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (employee_id, full_name, email, phone, float(hourly_rate), passport_number, bank_name, bank_account_name, bank_account_number))
        conn.commit()
        conn.close()
        flash('Employee added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding employee: {str(e)}', 'error')
    
    return redirect(url_for('manage_employees'))

# PRODUCTION FIX: Initialize database in both development and production
if __name__ == '__main__':
    # Development
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # Production - initialize database if needed
    init_db()
