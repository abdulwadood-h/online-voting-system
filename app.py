from datetime import datetime
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
# --- 5. LOGIN ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        roll_no = request.form.get('roll_no', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE roll_no = %s", (roll_no,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        # FIXED: Use check_password_hash because your register/setup_admin uses hashing
        if user and check_password_hash(user['password'], password):
            session.clear() 
            session['user_id'] = user['id']
            session['role'] = user['role'].lower() 
            session['fullname'] = user['fullname']
            session['dept'] = user['dept']

            if session['role'] == 'admin':
                return redirect(url_for('admin_approvals'))
            
            elif session['role'] == 'student':
                if user['is_approved'] == 1:
                    return redirect(url_for('student_dashboard'))
                else:
                    flash("Your account is pending Secretary approval.", "warning")
        else:
            # This triggers if user isn't found OR password hash doesn't match
            flash("Invalid Roll Number or Password.", "danger")
            
    return render_template('login.html')
# --- 6. REGISTER ROUTE ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form
        roll_str = f['roll_no']
        dept = f['dept']
        
        # --- NEW VALIDATION LOGIC ---
        try:
            roll_int = int(roll_str)
            if dept == "Computer Science":
                if not (2313181058201 <= roll_int <= 2313181058261):
                    flash("Invalid Roll Number for Computer Science (Range: ...201 to ...261)", "danger")
                    return render_template('register.html')
            
            elif dept == "Information Technology":
                if not (2313181097001 <= roll_int <= 2313181097050):
                    flash("Invalid Roll Number for IT (Range: ...001 to ...050)", "danger")
                    return render_template('register.html')
            else:
                flash("Please select a valid department.", "danger")
                return render_template('register.html')
        except ValueError:
            flash("Roll Number must contain only digits.", "danger")
            return render_template('register.html')
        # --- END OF VALIDATION ---

        hashed = generate_password_hash(f['password'])
        conn = get_db_connection(); cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO users(roll_no, fullname, email, dept, password, role, is_approved) 
                           VALUES (%s, %s, %s, %s, %s, 'student', 0)""",
                        (roll_str, f['fullname'], f['email'], dept, hashed))
            conn.commit()
            flash("Registration successful! Wait for Admin approval.", "success")
            return redirect(url_for('login'))
        except:
            flash("Registration failed. Roll Number may already exist.", "danger")
        finally:
            cur.close(); conn.close()
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
from datetime import datetime

@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    now = datetime.now()
    
    cur.execute("SELECT * FROM elections WHERE dept = %s", [session.get('dept')])
    elections = cur.fetchall()
    
    cur.execute("SELECT election_id FROM votes WHERE student_id = %s", [session['user_id']])
    voted_ids = [v['election_id'] for v in cur.fetchall()]

    for e in elections:
        # Check if the election is actually happening
        if now > e['end_time']:
            e['status_label'] = "Expired"
            e['status_class'] = "bg-danger-subtle text-danger"
            e['is_active'] = False
        elif now < e['start_time']:
            e['status_label'] = "Upcoming"
            e['status_class'] = "bg-warning-subtle text-warning"
            e['is_active'] = False
        else:
            e['status_label'] = "Live"
            e['status_class'] = "bg-success-subtle text-success"
            e['is_active'] = True
            
        e['has_voted'] = e['id'] in voted_ids

    cur.close(); conn.close()
    return render_template('student_dashboard.html', elections=elections)

# --- 11. VOTE ROUTE ---
@app.route('/vote/<int:election_id>', methods=['GET', 'POST'])
def vote(election_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    now = datetime.now() # Get current time for comparison

    # 1. Fetch Election Data
    cur.execute("SELECT * FROM elections WHERE id = %s", [election_id])
    election = cur.fetchone()

    if not election:
        cur.close(); conn.close()
        flash("Election not found.", "danger")
        return redirect(url_for('student_dashboard'))

    # 2. Time Validation (The fix for the "Always Live" bug)
    if now < election['start_time']:
        cur.close(); conn.close()
        flash(f"Voting opens at {election['start_time'].strftime('%Y-%m-%d %H:%M')}", "info")
        return redirect(url_for('student_dashboard'))
    
    if now > election['end_time']:
        cur.close(); conn.close()
        # This will catch the case in your screenshot where the time passed
        flash("Voting period has ended.", "danger") 
        return redirect(url_for('student_dashboard'))

    # 3. Double-Vote Prevention
    cur.execute("SELECT id FROM votes WHERE student_id = %s AND election_id = %s", 
                (session['user_id'], election_id))
    if cur.fetchone():
        cur.close(); conn.close()
        flash("You have already voted in this election.", "warning")
        return redirect(url_for('student_dashboard'))

    # 4. Handle Post
    if request.method == 'POST':
        candidate_id = request.form.get('candidate_id')
        if candidate_id:
            try:
                cur.execute("INSERT INTO votes (student_id, election_id, candidate_id) VALUES (%s, %s, %s)",
                            (session['user_id'], election_id, candidate_id))
                conn.commit()
                flash("Vote successfully cast!", "success")
                return redirect(url_for('student_dashboard'))
            except Exception as e:
                conn.rollback()
                flash("Error recording vote. Please try again.", "danger")
        else:
            flash("Select a candidate.", "warning")

    # 5. Fetch Candidates for GET request
    cur.execute("SELECT * FROM candidates WHERE election_id = %s", [election_id])
    candidates = cur.fetchall()
    
    cur.close(); conn.close() # Always close before rendering
    return render_template('vote.html', election=election, candidates=candidates)
# --- 12. RESULTS ROUTE ---
@app.route('/results/<int:election_id>')
def results(election_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # This query gets EVERY candidate and their vote count
    cur.execute("""
        SELECT c.name, COUNT(v.id) as vote_count 
        FROM candidates c 
        LEFT JOIN votes v ON c.id = v.candidate_id 
        WHERE c.election_id = %s 
        GROUP BY c.id 
        ORDER BY vote_count DESC
    """, [election_id])
    
    data = cur.fetchall()
    
    cur.execute("SELECT title FROM elections WHERE id = %s", [election_id])
    election = cur.fetchone()
    cur.close()
    conn.close()

    # We pass the full lists to the template
    # The first person in these lists will be the winner (due to ORDER BY)
    return render_template('results.html', 
                           labels=[r['name'] for r in data], 
                           counts=[r['vote_count'] for r in data], 
                           title=election['title'])
# --- 13. PROFILE & LOGOUT ---
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    data = cur.fetchone()
    cur.close()
    conn.close()
    
    return render_template('profile.html', user=data) # Pass it as 'user'

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

@app.route('/approve_multiple', methods=['POST'])
def approve_multiple():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    user_ids = request.form.getlist('user_ids') # Gets list of checked IDs
    if user_ids:
        conn = get_db_connection()
        cur = conn.cursor()
        # Converts list to a format SQL understands: (ID1, ID2, ID3)
        format_strings = ','.join(['%s'] * len(user_ids))
        cur.execute(f"UPDATE users SET is_approved = 1 WHERE id IN ({format_strings})", user_ids)
        conn.commit()
        cur.close(); conn.close()
        flash(f"Successfully approved {len(user_ids)} users!", "success")
    else:
        flash("No users selected.", "warning")
        
    return redirect(url_for('admin_approvals'))

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

if __name__ == '__main__':
    setup_admin(); app.run(debug=True)

if __name__ == '__main__':
    # 1. Run the admin setup first
    setup_admin()
    
    # 2. Print a clear message so you know it's starting
    print("\n" + "="*30)
    print(" VOTING SYSTEM IS STARTING")
    print(" Access at: http://127.0.0.1:5000")
    print("="*30 + "\n")
    
    # 3. Start the server (One time only!)
    app.run(host='0.0.0.0', port=5000, debug=True)
