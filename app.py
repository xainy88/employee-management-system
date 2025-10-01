from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import StringIO
import base64

app = Flask(__name__)
app.secret_key = 'employee_management_system_secret_key_2024'

# Database initialization - FIXED: No sample data insertion
def init_db():
    # Check if database already exists to prevent recreation
    if os.path.exists('employees.db'):
        print("Database already exists, skipping initialization.")
        return
    
    conn = sqlite3.connect('employees.db')
    c = conn.cursor()
    
    # Create employees table WITH BANK FIELDS
    c.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            hourly_rate REAL NOT NULL,
            passport_number TEXT,  -- NEW FIELD
            bank_name TEXT,        -- NEW FIELD
            bank_account_name TEXT, -- NEW FIELD
            bank_account_number TEXT, -- NEW FIELD
            status TEXT DEFAULT 'Active',
            created_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create work entries table
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
            created_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
        )
    ''')
    
    # Create advance payments table
    c.execute('''
        CREATE TABLE IF NOT EXISTS advance_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            amount REAL NOT NULL,
            payment_date TEXT NOT NULL,
            reason TEXT,
            created_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
        )
    ''')
    
    # Create food expenses table
    c.execute('''
        CREATE TABLE IF NOT EXISTS food_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            amount REAL NOT NULL,
            expense_date TEXT NOT NULL,
            description TEXT,
            created_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
        )
    ''')
    
    # Create attendance photos table
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            work_date TEXT NOT NULL,
            photo_type TEXT NOT NULL,
            photo_data TEXT NOT NULL,
            created_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
        )
    ''')
    
    # Create payment_records table
    c.execute('''
        CREATE TABLE IF NOT EXISTS payment_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            amount_paid REAL NOT NULL,
            payment_type TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'paid',
            created_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
        )
    ''')
    
    # REMOVED SAMPLE DATA INSERTION - Database will start empty
    
    conn.commit()
    conn.close()
    print("Database initialized successfully with empty tables!")

def get_db_connection():
    conn = sqlite3.connect('employees.db')
    conn.row_factory = sqlite3.Row
    return conn

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

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    user_type = request.form.get('user_type')
    
    print(f"Login attempt - User Type: {user_type}, Username: {username}, Password: {password}")  # Debug log
    
    if user_type == 'admin':
        # Admin credentials - username: admin, password: admin
        if username == 'admin' and password == 'admin':
            session['logged_in'] = True
            session['username'] = username
            session['user_type'] = 'admin'
            print("Admin login successful")  # Debug log
            return redirect(url_for('admin_dashboard'))
        else:
            print("Admin login failed - invalid credentials")  # Debug log
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
            print(f"Employee login successful: {employee['full_name']}")  # Debug log
            return redirect(url_for('employee_dashboard'))
        else:
            print("Employee login failed - invalid employee ID")  # Debug log
            flash('Invalid employee ID!', 'error')
            return redirect(url_for('index'))
    else:
        print(f"Invalid user type: {user_type}")  # Debug log
        flash('Invalid login type!', 'error')
        return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        print("Admin dashboard access denied - not logged in or not admin")  # Debug log
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
    
    employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    
    # Calculate payment totals
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
        conn.execute('''
            INSERT INTO payment_records (employee_id, payment_date, amount_paid, payment_type, description)
            VALUES (?, DATE("now"), ?, ?, ?)
        ''', (employee_id, amount_paid, payment_type, description))
        
        conn.commit()
        flash(f'Payment of RM {amount_paid:.2f} recorded successfully!', 'success')
        conn.close()
        return redirect(url_for('admin_payments'))
    
    # GET request - show payment form
    employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    
    # Calculate totals
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

# NEW: Edit Payment Route
@app.route('/admin/edit_payment/<int:payment_id>', methods=['GET', 'POST'])
def edit_payment(payment_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        amount_paid = float(request.form['amount_paid'])
        payment_type = request.form['payment_type']
        payment_date = request.form['payment_date']
        description = request.form.get('description', '')
        status = request.form['status']
        
        try:
            conn.execute('''
                UPDATE payment_records 
                SET amount_paid = ?, payment_type = ?, payment_date = ?, description = ?, status = ?
                WHERE id = ?
            ''', (amount_paid, payment_type, payment_date, description, status, payment_id))
            
            conn.commit()
            flash('Payment updated successfully!', 'success')
            conn.close()
            return redirect(url_for('payment_history', employee_id=request.form.get('employee_id')))
        except Exception as e:
            flash(f'Error updating payment: {str(e)}', 'error')
            conn.close()
            return redirect(url_for('payment_history', employee_id=request.form.get('employee_id')))
    
    # GET request - show edit form
    payment = conn.execute('''
        SELECT p.*, e.full_name, e.employee_id 
        FROM payment_records p 
        JOIN employees e ON p.employee_id = e.employee_id 
        WHERE p.id = ?
    ''', (payment_id,)).fetchone()
    
    conn.close()
    
    if payment:
        return render_template('admin_edit_payment.html', payment=payment)
    else:
        flash('Payment record not found!', 'error')
        return redirect(url_for('admin_payments'))

# NEW: Delete Payment Route
@app.route('/admin/delete_payment/<int:payment_id>', methods=['POST'])
def delete_payment(payment_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    try:
        # Get employee_id before deleting for redirect
        payment = conn.execute('SELECT employee_id FROM payment_records WHERE id = ?', (payment_id,)).fetchone()
        employee_id = payment['employee_id'] if payment else None
        
        conn.execute('DELETE FROM payment_records WHERE id = ?', (payment_id,))
        conn.commit()
        flash('Payment record deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting payment: {str(e)}', 'error')
    
    conn.close()
    
    if employee_id:
        return redirect(url_for('payment_history', employee_id=employee_id))
    else:
        return redirect(url_for('admin_payments'))

@app.route('/admin/payment_history/<employee_id>')
def payment_history(employee_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    payment_history = conn.execute('''
        SELECT * FROM payment_records 
        WHERE employee_id = ? 
        ORDER BY payment_date DESC
    ''', (employee_id,)).fetchall()
    conn.close()
    
    return render_template('admin_payment_history.html', 
                         employee=employee, 
                         payment_history=payment_history)

# Employee Payment Routes
@app.route('/employee/payment_details')
def employee_payment_details():
    if not session.get('logged_in') or session.get('user_type') != 'employee':
        return redirect(url_for('index'))
    
    employee_id = session.get('employee_id')
    conn = get_db_connection()
    
    employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    
    # Calculate totals
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
    payment_history = conn.execute('''
        SELECT * FROM payment_records 
        WHERE employee_id = ? 
        ORDER BY payment_date DESC
    ''', (employee_id,)).fetchall()
    
    conn.close()
    
    return render_template('employee_payment_details.html',
                         employee=employee,
                         payment_history=payment_history,
                         total_earnings=total_earnings,
                         total_paid=total_paid,
                         pending_amount=pending_amount)

# NEW: Photo Viewing Routes - COMPLETELY FIXED VERSION
@app.route('/admin/view_photo/<int:photo_id>')
def view_photo(photo_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    photo = conn.execute('''
        SELECT ap.*, e.full_name 
        FROM attendance_photos ap 
        JOIN employees e ON ap.employee_id = e.employee_id 
        WHERE ap.id = ?
    ''', (photo_id,)).fetchone()
    conn.close()
    
    if photo:
        return render_template('view_photo.html', photo=photo)
    else:
        flash('Photo not found!', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/photo_data/<int:photo_id>')
def photo_data(photo_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return "Unauthorized", 401
    
    conn = get_db_connection()
    photo = conn.execute('SELECT * FROM attendance_photos WHERE id = ?', (photo_id,)).fetchone()
    conn.close()
    
    if photo and photo['photo_data']:
        try:
            # Clean the base64 data - remove any data URL prefix
            image_data = photo['photo_data']
            if 'base64,' in image_data:
                image_data = image_data.split('base64,')[1]
            
            # Ensure it's proper base64
            image_data = image_data.strip()
            
            # Decode base64 and return as image
            image_bytes = base64.b64decode(image_data)
            from flask import Response
            return Response(image_bytes, mimetype='image/jpeg')
        except Exception as e:
            print(f"Error decoding photo {photo_id}: {str(e)}")
            # Return a placeholder image
            from flask import send_file
            import io
            placeholder = io.BytesIO()
            # Create a simple placeholder image
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (300, 200), color='lightgray')
            d = ImageDraw.Draw(img)
            d.text((50, 80), "Photo Not Available", fill='black')
            img.save(placeholder, format='JPEG')
            placeholder.seek(0)
            return send_file(placeholder, mimetype='image/jpeg')
    else:
        # Return placeholder image
        from flask import send_file
        import io
        placeholder = io.BytesIO()
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (300, 200), color='lightgray')
        d = ImageDraw.Draw(img)
        d.text((50, 80), "No Photo Data", fill='black')
        img.save(placeholder, format='JPEG')
        placeholder.seek(0)
        return send_file(placeholder, mimetype='image/jpeg')

# FIXED: Selfie Check-in Route with proper photo handling
@app.route('/employee/check_in_with_photo', methods=['POST'])
def check_in_with_photo():
    if not session.get('logged_in') or session.get('user_type') != 'employee':
        return jsonify({'success': False, 'message': 'Not authorized'})
    
    employee_id = session.get('employee_id')
    current_time = datetime.now().strftime('%H:%M')
    today = datetime.now().strftime('%Y-%m-%d')
    photo_data = request.form.get('photo_data')
    
    try:
        conn = get_db_connection()
        
        # Check if already checked in today
        existing_entry = conn.execute(
            'SELECT * FROM work_entries WHERE employee_id = ? AND work_date = ?',
            (employee_id, today)
        ).fetchone()
        
        if existing_entry:
            return jsonify({'success': False, 'message': 'You have already checked in today!'})
        else:
            # Create new work entry with check-in time
            conn.execute('''
                INSERT INTO work_entries (employee_id, work_date, start_time, end_time, break_minutes, normal_hours, overtime_hours, holiday_hours)
                VALUES (?, ?, ?, ?, 60, 0, 0, 0)
            ''', (employee_id, today, current_time, current_time))
            
            # Store the check-in photo with proper base64 handling
            if photo_data:
                # Clean the photo data
                if 'base64,' in photo_data:
                    photo_data = photo_data.split('base64,')[1]
                
                conn.execute('''
                    INSERT INTO attendance_photos (employee_id, work_date, photo_type, photo_data)
                    VALUES (?, ?, 'check_in', ?)
                ''', (employee_id, today, photo_data))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True, 
                'message': f'Checked in successfully at {current_time} with photo verification!',
                'check_in_time': current_time
            })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error checking in: {str(e)}'})

# FIXED: Selfie Check-out Route with proper photo handling
@app.route('/employee/check_out_with_photo', methods=['POST'])
def check_out_with_photo():
    if not session.get('logged_in') or session.get('user_type') != 'employee':
        return jsonify({'success': False, 'message': 'Not authorized'})
    
    employee_id = session.get('employee_id')
    current_time = datetime.now().strftime('%H:%M')
    today = datetime.now().strftime('%Y-%m-%d')
    photo_data = request.form.get('photo_data')
    
    try:
        conn = get_db_connection()
        
        # Get today's work entry
        work_entry = conn.execute(
            'SELECT * FROM work_entries WHERE employee_id = ? AND work_date = ?',
            (employee_id, today)
        ).fetchone()
        
        if not work_entry:
            return jsonify({'success': False, 'message': 'You need to check in first!'})
        elif work_entry['end_time'] != work_entry['start_time']:
            return jsonify({'success': False, 'message': 'You have already checked out today!'})
        else:
            # Update end time and calculate hours
            start_time = work_entry['start_time']
            end_time = current_time
            break_minutes = work_entry['break_minutes']
            
            # Calculate hours (assuming normal work day, not holiday)
            normal_hours, overtime_hours, holiday_hours = calculate_hours(start_time, end_time, break_minutes, False)
            
            conn.execute('''
                UPDATE work_entries 
                SET end_time = ?, normal_hours = ?, overtime_hours = ?, holiday_hours = ?
                WHERE employee_id = ? AND work_date = ?
            ''', (end_time, normal_hours, overtime_hours, holiday_hours, employee_id, today))
            
            # Store the check-out photo with proper base64 handling
            if photo_data:
                # Clean the photo data
                if 'base64,' in photo_data:
                    photo_data = photo_data.split('base64,')[1]
                
                conn.execute('''
                    INSERT INTO attendance_photos (employee_id, work_date, photo_type, photo_data)
                    VALUES (?, ?, 'check_out', ?)
                ''', (employee_id, today, photo_data))
            
            conn.commit()
            conn.close()
            
            # Calculate total hours worked
            total_hours = normal_hours + overtime_hours + holiday_hours
            
            return jsonify({
                'success': True, 
                'message': f'Checked out successfully at {current_time}. Total hours: {total_hours:.2f}',
                'check_out_time': current_time,
                'total_hours': total_hours
            })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error checking out: {str(e)}'})

@app.route('/employee/today_status')
def today_status():
    if not session.get('logged_in') or session.get('user_type') != 'employee':
        return jsonify({'error': 'Not authorized'})
    
    employee_id = session.get('employee_id')
    today = datetime.now().strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    work_entry = conn.execute(
        'SELECT * FROM work_entries WHERE employee_id = ? AND work_date = ?',
        (employee_id, today)
    ).fetchone()
    conn.close()
    
    if work_entry:
        return jsonify({
            'checked_in': True,
            'checked_out': work_entry['end_time'] != work_entry['start_time'],
            'start_time': work_entry['start_time'],
            'end_time': work_entry['end_time'] if work_entry['end_time'] != work_entry['start_time'] else None,
            'normal_hours': work_entry['normal_hours'],
            'overtime_hours': work_entry['overtime_hours'],
            'holiday_hours': work_entry['holiday_hours']
        })
    else:
        return jsonify({'checked_in': False})

# Admin Management Routes
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (employee_id, full_name, email, phone, float(hourly_rate), passport_number, bank_name, bank_account_name, bank_account_number))
        conn.commit()
        conn.close()
        flash('Employee added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Employee ID already exists!', 'error')
    except Exception as e:
        flash(f'Error adding employee: {str(e)}', 'error')
    
    return redirect(url_for('manage_employees'))

@app.route('/admin/employees/delete/<employee_id>', methods=['POST'])
def delete_employee(employee_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
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

@app.route('/admin/employees/edit/<employee_id>', methods=['POST'])
def edit_employee(employee_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    hourly_rate = request.form.get('hourly_rate')
    status = request.form.get('status')
    passport_number = request.form.get('passport_number', '')
    bank_name = request.form.get('bank_name', '')
    bank_account_name = request.form.get('bank_account_name', '')
    bank_account_number = request.form.get('bank_account_number', '')
    
    try:
        conn = get_db_connection()
        conn.execute('''
            UPDATE employees 
            SET full_name = ?, email = ?, phone = ?, hourly_rate = ?, status = ?, 
                passport_number = ?, bank_name = ?, bank_account_name = ?, bank_account_number = ?
            WHERE employee_id = ?
        ''', (full_name, email, phone, float(hourly_rate), status, passport_number, bank_name, bank_account_name, bank_account_number, employee_id))
        conn.commit()
        conn.close()
        flash('Employee updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating employee: {str(e)}', 'error')
    
    return redirect(url_for('manage_employees'))

@app.route('/admin/work_entries')
def manage_work_entries():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    work_entries = conn.execute('''
        SELECT w.*, e.full_name 
        FROM work_entries w 
        JOIN employees e ON w.employee_id = e.employee_id 
        ORDER BY w.work_date DESC
    ''').fetchall()
    employees = conn.execute('SELECT employee_id, full_name FROM employees WHERE status = "Active"').fetchall()
    conn.close()
    
    return render_template('manage_work_entries.html', work_entries=work_entries, employees=employees)

@app.route('/admin/work_entries/add', methods=['POST'])
def add_work_entry():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    employee_id = request.form.get('employee_id')
    work_date = request.form.get('work_date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    break_minutes = request.form.get('break_minutes', 60)
    is_holiday = request.form.get('is_holiday') == 'on'
    
    try:
        normal_hours, overtime_hours, holiday_hours = calculate_hours(start_time, end_time, int(break_minutes), is_holiday)
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO work_entries (employee_id, work_date, start_time, end_time, break_minutes, normal_hours, overtime_hours, holiday_hours)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (employee_id, work_date, start_time, end_time, break_minutes, normal_hours, overtime_hours, holiday_hours))
        conn.commit()
        conn.close()
        flash('Work entry added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding work entry: {str(e)}', 'error')
    
    return redirect(url_for('manage_work_entries'))

@app.route('/admin/work_entries/delete/<int:entry_id>', methods=['POST'])
def delete_work_entry(entry_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM work_entries WHERE id = ?', (entry_id,))
        conn.commit()
        conn.close()
        flash('Work entry deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting work entry: {str(e)}', 'error')
    
    return redirect(url_for('manage_work_entries'))

@app.route('/admin/work_entries/edit/<int:entry_id>', methods=['POST'])
def edit_work_entry(entry_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    employee_id = request.form.get('employee_id')
    work_date = request.form.get('work_date')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    break_minutes = request.form.get('break_minutes', 60)
    is_holiday = request.form.get('is_holiday') == 'on'
    
    try:
        normal_hours, overtime_hours, holiday_hours = calculate_hours(start_time, end_time, int(break_minutes), is_holiday)
        
        conn = get_db_connection()
        conn.execute('''
            UPDATE work_entries 
            SET employee_id = ?, work_date = ?, start_time = ?, end_time = ?, break_minutes = ?, 
                normal_hours = ?, overtime_hours = ?, holiday_hours = ?
            WHERE id = ?
        ''', (employee_id, work_date, start_time, end_time, break_minutes, normal_hours, overtime_hours, holiday_hours, entry_id))
        conn.commit()
        conn.close()
        flash('Work entry updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating work entry: {str(e)}', 'error')
    
    return redirect(url_for('manage_work_entries'))

@app.route('/admin/employee_entries/<employee_id>')
def view_employee_entries(employee_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get employee details
    employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    
    # Get all work entries for this employee
    work_entries = conn.execute('''
        SELECT * FROM work_entries 
        WHERE employee_id = ? 
        ORDER BY work_date DESC
    ''', (employee_id,)).fetchall()
    
    # Get advance payments
    advances = conn.execute('''
        SELECT * FROM advance_payments 
        WHERE employee_id = ? 
        ORDER BY payment_date DESC
    ''', (employee_id,)).fetchall()
    
    # Get food expenses
    food_expenses = conn.execute('''
        SELECT * FROM food_expenses 
        WHERE employee_id = ? 
        ORDER BY expense_date DESC
    ''', (employee_id,)).fetchall()
    
    # Get attendance photos
    attendance_photos = conn.execute('''
        SELECT * FROM attendance_photos 
        WHERE employee_id = ? 
        ORDER BY work_date DESC, photo_type
    ''', (employee_id,)).fetchall()
    
    # Get payment records
    payment_records = conn.execute('''
        SELECT * FROM payment_records 
        WHERE employee_id = ? 
        ORDER BY payment_date DESC
    ''', (employee_id,)).fetchall()
    
    conn.close()
    
    return render_template('admin_employee_entries.html', 
                         employee=employee,
                         work_entries=work_entries,
                         advances=advances,
                         food_expenses=food_expenses,
                         attendance_photos=attendance_photos,
                         payment_records=payment_records)

@app.route('/admin/advance_payments')
def manage_advance_payments():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    advances = conn.execute('''
        SELECT a.*, e.full_name 
        FROM advance_payments a 
        JOIN employees e ON a.employee_id = e.employee_id 
        ORDER BY a.payment_date DESC
    ''').fetchall()
    employees = conn.execute('SELECT employee_id, full_name FROM employees WHERE status = "Active"').fetchall()
    conn.close()
    
    return render_template('manage_advance_payments.html', advances=advances, employees=employees)

@app.route('/admin/advance_payments/add', methods=['POST'])
def add_advance_payment():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    employee_id = request.form.get('employee_id')
    amount = request.form.get('amount')
    payment_date = request.form.get('payment_date')
    reason = request.form.get('reason')
    
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO advance_payments (employee_id, amount, payment_date, reason)
            VALUES (?, ?, ?, ?)
        ''', (employee_id, float(amount), payment_date, reason))
        conn.commit()
        conn.close()
        flash('Advance payment added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding advance payment: {str(e)}', 'error')
    
    return redirect(url_for('manage_advance_payments'))

@app.route('/admin/advance_payments/delete/<int:advance_id>', methods=['POST'])
def delete_advance_payment(advance_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM advance_payments WHERE id = ?', (advance_id,))
        conn.commit()
        conn.close()
        flash('Advance payment deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting advance payment: {str(e)}', 'error')
    
    return redirect(url_for('manage_advance_payments'))

@app.route('/admin/food_expenses')
def manage_food_expenses():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    expenses = conn.execute('''
        SELECT f.*, e.full_name 
        FROM food_expenses f 
        JOIN employees e ON f.employee_id = e.employee_id 
        ORDER BY f.expense_date DESC
    ''').fetchall()
    employees = conn.execute('SELECT employee_id, full_name FROM employees WHERE status = "Active"').fetchall()
    conn.close()
    
    return render_template('manage_food_expenses.html', expenses=expenses, employees=employees)

@app.route('/admin/food_expenses/add', methods=['POST'])
def add_food_expense():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    employee_id = request.form.get('employee_id')
    amount = request.form.get('amount')
    expense_date = request.form.get('expense_date')
    description = request.form.get('description')
    
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO food_expenses (employee_id, amount, expense_date, description)
            VALUES (?, ?, ?, ?)
        ''', (employee_id, float(amount), expense_date, description))
        conn.commit()
        conn.close()
        flash('Food expense added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding food expense: {str(e)}', 'error')
    
    return redirect(url_for('manage_food_expenses'))

@app.route('/admin/food_expenses/delete/<int:expense_id>', methods=['POST'])
def delete_food_expense(expense_id):
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM food_expenses WHERE id = ?', (expense_id,))
        conn.commit()
        conn.close()
        flash('Food expense deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting food expense: {str(e)}', 'error')
    
    return redirect(url_for('manage_food_expenses'))

@app.route('/admin/reports')
def reports():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    
    conn = get_db_connection()
    
    # Get payroll report for selected month
    payroll_report = conn.execute('''
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
    ''', (month, month, month)).fetchall()
    
    conn.close()
    
    return render_template('reports.html', payroll_report=payroll_report, selected_month=month)

@app.route('/admin/export_excel')
def export_excel():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    month = request.args.get('month', datetime.now().strftime('%Y-%m'))
    
    conn = get_db_connection()
    
    # Get payroll report for selected month
    payroll_report = conn.execute('''
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
    ''', (month, month, month)).fetchall()
    
    conn.close()
    
    # Create CSV data
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Employee ID', 'Full Name', 'Hourly Rate', 'Normal Hours', 'Overtime Hours', 
                    'Holiday Hours', 'Normal Pay', 'Overtime Pay', 'Holiday Pay', 'Total Earnings',
                    'Advance Payments', 'Food Expenses', 'Grand Total'])
    
    # Write data
    for employee in payroll_report:
        hourly_rate = employee['hourly_rate']
        normal_pay = employee['total_normal_hours'] * hourly_rate
        overtime_pay = employee['total_overtime_hours'] * hourly_rate * 1.5
        holiday_pay = employee['total_holiday_hours'] * hourly_rate * 1.5
        total_earnings = normal_pay + overtime_pay + holiday_pay
        grand_total = total_earnings - employee['total_advances'] - employee['total_food_expenses']
        
        writer.writerow([
            employee['employee_id'],
            employee['full_name'],
            hourly_rate,
            round(employee['total_normal_hours'], 2),
            round(employee['total_overtime_hours'], 2),
            round(employee['total_holiday_hours'], 2),
            round(normal_pay, 2),
            round(overtime_pay, 2),
            round(holiday_pay, 2),
            round(total_earnings, 2),
            round(employee['total_advances'], 2),
            round(employee['total_food_expenses'], 2),
            round(grand_total, 2)
        ])
    
    output.seek(0)
    
    return app.response_class(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=payroll_report_{month}.csv'}
    )

# Settings Routes
@app.route('/admin/settings')
def admin_settings():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return redirect(url_for('index'))
    
    return render_template('admin_settings.html')

@app.route('/admin/change_password', methods=['POST'])
def change_admin_password():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        return jsonify({'success': False, 'message': 'Not authorized'})
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Validate inputs
    if not current_password or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': 'All fields are required'})
    
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': 'New passwords do not match'})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'})
    
    # Check current password (for demo, we're using 'admin' as default)
    if current_password != 'admin':
        return jsonify({'success': False, 'message': 'Current password is incorrect'})
    
    # Here you would update the password in your database
    # For now, we'll just return success (in real app, store hashed password)
    
    flash('Admin password changed successfully! Please update the application code to store the new password securely.', 'success')
    return jsonify({'success': True, 'message': 'Password changed successfully'})

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully!', 'success')
    return redirect(url_for('index'))

# PRODUCTION FIX: Initialize database in both development and production
if __name__ == '__main__':
    # Development
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # Production - initialize database if needed
    init_db()
