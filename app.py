import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'safecircle_secure_key_2026'

# --- 1. CONFIGURATION FOR PHOTO UPLOADS ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 

# --- 2. DATABASE CONNECTION ---
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='college_voting'
    )

# --- 3. AUTOMATIC ADMIN SETUP ---
def setup_admin():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE roll_no = 'ADMIN01'")
    if not cur.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cur.execute("""INSERT INTO users(roll_no, fullname, email, dept, password, role, is_approved) 
                       VALUES (%s, %s, %s, %s, %s, 'admin', 1)""",
                    ('ADMIN01', 'System Admin', 'admin@college.edu', 'IT', hashed_pw))
        conn.commit()
    cur.close(); conn.close()

# --- 4. INDEX ROUTE ---
@app.route('/')
def index():
    return render_template('index.html')

# --- 5. LOGIN ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        roll = request.form.get('roll_no')
        pw = request.form.get('password')
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE roll_no = %s", [roll])
        user = cur.fetchone(); cur.close(); conn.close()
        
        if user and check_password_hash(user['password'], pw):
            if user['is_approved'] == 0:
                flash("Account pending admin approval.", "warning")
                return redirect(url_for('login'))
            
            # --- CRITICAL UPDATE: Add 'dept' to session ---
            session.update({
                'user_id': user['id'], 
                'name': user['fullname'], 
                'role': user['role'],
                'dept': user['dept']  # This allows the dashboard to filter
            })
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'student_dashboard'))
        flash("Invalid credentials!", "danger")
    return render_template('login.html')

# --- 6. REGISTER ROUTE ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form
        hashed = generate_password_hash(f['password'])
        conn = get_db_connection(); cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO users(roll_no, fullname, email, dept, password, role, is_approved) 
                           VALUES (%s, %s, %s, %s, %s, 'student', 0)""",
                        (f['roll_no'], f['fullname'], f['email'], f['dept'], hashed))
            conn.commit(); flash("Registration successful! Wait for Admin approval.", "success")
            return redirect(url_for('login'))
        except: flash("Registration failed. Roll Number may already exist.", "danger")
        finally: cur.close(); conn.close()
    return render_template('register.html')

# --- 7. ADMIN DASHBOARD (With Duplicate Prevention) ---
@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if session.get('role') != 'admin': 
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # FIXED INDENTATION HERE
        cur.execute("INSERT INTO elections (title, position, start_time, end_time, dept) VALUES (%s,%s,%s,%s,%s)",
                    (request.form.get('title'), 
                     request.form.get('position'), 
                     request.form.get('start_time'), 
                     request.form.get('end_time'),
                     request.form.get('dept'))) 
        conn.commit()
        cur.close()
        conn.close()
        flash("Election published successfully!", "success")
        return redirect(url_for('admin_dashboard')) # PRG Pattern
    
    # This runs for the GET request
    cur.execute("SELECT * FROM elections ORDER BY id DESC")
    elections = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_dashboard.html', elections=elections)

# --- 8. DELETE ELECTION (Fixed for Foreign Keys) ---
@app.route('/delete_election/<int:election_id>')    
def delete_election(election_id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM candidates WHERE election_id = %s", [election_id])
        cur.execute("DELETE FROM elections WHERE id = %s", [election_id])
        conn.commit(); flash("Election deleted successfully.", "info")
    except: flash("Error deleting election.", "danger")
    finally: cur.close(); conn.close()
    return redirect(url_for('admin_dashboard'))

# --- 9. ADD CANDIDATE (With Photo Support) ---
@app.route('/add_candidate/<int:election_id>', methods=['GET', 'POST'])
def add_candidate(election_id):
    if session.get('role') != 'admin': 
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        file = request.files.get('photo')
        filename = 'default.png'
        
        if file and file.filename != '':
            filename = secure_filename(f"cand_{election_id}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        # CHANGED: 'party' replaced with 'roll_no' in the query and the form request
        cur.execute("INSERT INTO candidates (election_id, name, dept, roll_no, photo) VALUES (%s, %s, %s, %s, %s)",
                    (election_id, request.form.get('name'), request.form.get('dept'), 
                     request.form.get('roll_no'), filename))
        conn.commit()
        
        cur.close()
        conn.close()
        flash("Candidate added successfully!", "success")
        return redirect(url_for('add_candidate', election_id=election_id)) 

    cur.execute("SELECT * FROM candidates WHERE election_id = %s", [election_id])
    cands = cur.fetchall()
    
    cur.execute("SELECT title FROM elections WHERE id = %s", [election_id])
    election = cur.fetchone()
    
    cur.close()
    conn.close()
    return render_template('add_candidate.html', candidates=cands, election=election)

# --- 10. STUDENT DASHBOARD ---
@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    
    # Filter by the department stored in the session
    student_dept = session.get('dept')
    cur.execute("SELECT * FROM elections WHERE dept = %s", [student_dept])
    elections = cur.fetchall()
    
    cur.execute("SELECT election_id FROM votes WHERE student_id = %s", [session['user_id']])
    voted = [v['election_id'] for v in cur.fetchall()]
    
    cur.close(); conn.close()
    return render_template('student_dashboard.html', elections=elections, voted=voted)
# --- 11. VOTE ROUTE ---
@app.route('/vote/<int:election_id>', methods=['GET', 'POST'])
def vote(election_id):
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    # dictionary=True is required to use election['title']
    cur = conn.cursor(dictionary=True)
    
    # 1. Fetch Election details
    cur.execute("SELECT * FROM elections WHERE id = %s", [election_id])
    election = cur.fetchone()
    
    # --- SAFETY CHECK: Prevents KeyError: 'title' ---
    if not election:
        cur.close(); conn.close()
        flash("Election not found or no longer active.", "danger")
        return redirect(url_for('student_dashboard'))
    
    if request.method == 'POST':
        cand_id = request.form.get('candidate_id')
        if cand_id:
            cur.execute("INSERT INTO votes (student_id, election_id, candidate_id) VALUES (%s, %s, %s)",
                        (session['user_id'], election_id, cand_id))
            conn.commit()
            cur.close(); conn.close()
            flash("Vote cast successfully!", "success")
            return redirect(url_for('student_dashboard'))

    # 2. Fetch candidates for this election
    cur.execute("SELECT * FROM candidates WHERE election_id = %s", [election_id])
    cands = cur.fetchall()
    
    cur.close(); conn.close()
    return render_template('vote.html', candidates=cands, title=election['title'], eid=election_id)
    # 2. ELIGIBILITY CHECK: Compare departments
    if not election or user['dept'] != election['dept']:
        cur.close()
        conn.close()
        flash(f"Access Denied: You can only vote in {user['dept']} department elections.", "danger")
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        cand_id = request.form.get('candidate_id')
        if cand_id:
            # Check if already voted
            cur.execute("SELECT id FROM votes WHERE student_id = %s AND election_id = %s", 
                        (session['user_id'], election_id))
            if cur.fetchone():
                flash("You have already voted in this election!", "warning")
            else:
                cur.execute("INSERT INTO votes (student_id, election_id, candidate_id) VALUES (%s, %s, %s)",
                            (session['user_id'], election_id, cand_id))
                conn.commit()
                flash("Vote recorded successfully!", "success")
            
            cur.close()
            conn.close()
            return redirect(url_for('student_dashboard'))
    
    # Fetch candidates for the page display
    cur.execute("SELECT * FROM candidates WHERE election_id = %s", [election_id])
    cands = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('vote.html', candidates=cands, title=election['title'], eid=election_id)

# --- 12. RESULTS ROUTE ---
@app.route('/results/<int:election_id>')
def results(election_id):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT c.name, COUNT(v.id) as vote_count FROM candidates c 
                   LEFT JOIN votes v ON c.id = v.candidate_id 
                   WHERE c.election_id = %s GROUP BY c.id""", [election_id])
    data = cur.fetchall(); cur.execute("SELECT title FROM elections WHERE id = %s", [election_id])
    election = cur.fetchone(); cur.close(); conn.close()
    return render_template('results.html', labels=[r['name'] for r in data], counts=[r['vote_count'] for r in data], title=election['title'])

# --- 13. PROFILE & LOGOUT ---
@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE id = %s", [session['user_id']])
    user_data = cur.fetchone(); cur.close(); conn.close()
    return render_template('profile.html', user=user_data)

# Route to display the approval page
@app.route('/admin/approvals')
def admin_approvals():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    # Fetch all users to display in your new table
    cur.execute("SELECT * FROM users WHERE role != 'admin' ORDER BY is_approved ASC")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_approval.html', users=users)

# Route to approve a student
@app.route('/approve_user/<int:user_id>')
def approve_user(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    # Update status from 0 to 1
    cur.execute("UPDATE users SET is_approved = 1 WHERE id = %s", [user_id])
    conn.commit()
    cur.close()
    conn.close()
    flash("User account approved successfully!", "success")
    return redirect(url_for('admin_approvals'))

# Route to reject/delete a student
@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", [user_id])
    conn.commit()
    cur.close()
    conn.close()
    flash("User account removed.", "warning")
    return redirect(url_for('admin_approvals'))

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    setup_admin(); app.run(debug=True)