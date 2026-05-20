import os
import random
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "bhai_ka_super_secret_key")

# ---- 1. MONGODB CONFIGURATION (100% PUBLIC SAFE) ----
# Agar Render dashboard par variable milega toh wahan se uthayega, nahi toh local fallback par chalega
MONGO_URI = os.environ.get("MONGO_URI")

if not MONGO_URI:
    # Local PC par testing ke liye aap apni string temporarily yahan daal sakte hain,
    # Lekin GitHub par push karne se pehle ise khali (placeholder) hi chhodna.
    MONGO_URI = "mongodb+srv://YOUR_DB_USERNAME:YOUR_DB_PASSWORD@cluster.mongodb.net/Student_Project_DB"

client = MongoClient(MONGO_URI)
db = client['Student_Project_DB']

users_collection = db['users']
notes_collection = db['notes']
queries_collection = db['queries']

# ---- 2. FILE UPLOAD CONFIGURATION ----
PERSISTENT_DATA_DIR = "/opt/render/project/src/data" if os.environ.get("RENDER") else "data"
UPLOAD_FOLDER = os.path.join(PERSISTENT_DATA_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---- 3. GMAIL OTP CONFIGURATION (100% PUBLIC SAFE) ----
GMAIL_USER = os.environ.get("GMAIL_USER", "YOUR_GMAIL_ID_HERE@gmail.com")  
GMAIL_PASS = os.environ.get("GMAIL_PASS", "YOUR_APP_PASSWORD_HERE")  

def send_otp_email(receiver_email, otp_code):
    # Check ki variables placeholders toh nahi hain
    if "YOUR_GMAIL" in GMAIL_USER or "YOUR_APP" in GMAIL_PASS:
        print("Email Error: Gmail credentials are not configured properly.")
        return False

    msg = MIMEText(f"Hello, Your OTP for Student Note Sharing System registration is: {otp_code}")
    msg['Subject'] = 'Email Verification OTP'
    msg['From'] = GMAIL_USER
    msg['To'] = receiver_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, receiver_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# ---- 4. ROUTES ----

# 1. Login Page (Home)
@app.route('/')
def index():
    return render_template('login.html')

# 2. Signup Page Link
@app.route('/signup_page')
def signup_page():
    return render_template('signup.html')

# Signup Form Submit Logic
@app.route('/signup', methods=['POST'])
def signup():
    username = request.form['username']
    full_name = request.form['full_name']
    gmail = request.form['gmail']
    password = request.form['password']
    role = request.form['role']
    
    # Validation: Duplicate Check
    if users_collection.find_one({"$or": [{"username": username}, {"gmail": gmail}]}):
        return "Username ya Gmail pehle se registered hai! <a href='/signup_page'>Wapas jayein</a>"
    
    # OTP Generate karna (6 Digits)
    otp = str(random.randint(100000, 999999))
    
    # Temporary data session me rakhna
    session['temp_user'] = {
        "username": username,
        "full_name": full_name,
        "gmail": gmail,
        "password": password,
        "role": role,
        "otp": otp
    }
    
    if send_otp_email(gmail, otp):
        return redirect(url_for('verify_page'))
    return "Email bhejni me दिक्कत aayi, credentials ya network check karne ke liye bolen! <a href='/signup_page'>Wapas jayein</a>"

# 3. OTP Verification Page
@app.route('/verify_page')
def verify_page():
    if 'temp_user' not in session:
        return redirect(url_for('signup_page'))
    return render_template('verify.html', gmail=session['temp_user']['gmail'])

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    user_otp = request.form['otp']
    temp_user = session.get('temp_user')
    
    if temp_user and user_otp == temp_user['otp']:
        # OTP Match ho gaya! Permanent Database me daalo
        users_collection.insert_one({
            "username": temp_user['username'],
            "full_name": temp_user['full_name'],
            "gmail": temp_user['gmail'],
            "password": temp_user['password'],
            "role": temp_user['role']
        })
        session.pop('temp_user', None)
        return "Registration Successful! <a href='/'>Ab Login Karein</a>"
    
    return "Galat OTP! Please sahi OTP dalein. <a href='/verify_page'>Dobara try karein</a>"

# 4. Login Logic (Username ya Gmail dono chalega)
@app.route('/login', methods=['POST'])
def login():
    login_input = request.form['login_input']
    password = request.form['password']
    
    user = users_collection.find_one({
        "$or": [{"username": login_input}, {"gmail": login_input}],
        "password": password
    })
    
    if user:
        session['username'] = user['username']
        session['role'] = user['role']
        return redirect(url_for('dashboard'))
    return "Galat Username/Gmail ya Password! <a href='/'>Wapas try karein</a>"

# 5. Dashboard
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    search_query = request.args.get('search', '')
    if search_query:
        query_filter = {
            "$or": [
                {"title": {"$regex": search_query, "$options": "i"}},
                {"subject": {"$regex": search_query, "$options": "i"}}
            ]
        }
        notes = list(notes_collection.find(query_filter))
    else:
        notes = list(notes_collection.find())
        
    return render_template('dashboard.html', notes=notes, username=session['username'], role=session['role'])

# 6. Upload Notes
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    if session['role'] != 'Teacher':
        return "Sirf Teachers hi notes upload kar sakte hain! <a href='/dashboard'>Wapas jayein</a>"
    
    title = request.form['title']
    subject = request.form['subject']
    file = request.files['file']
    
    if file and file.filename.endswith('.pdf'):
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        notes_collection.insert_one({
            "title": title,
            "subject": subject,
            "filename": filename,
            "uploaded_by": session['username']
        })
        return redirect(url_for('dashboard'))
    return "Sirf PDF files allowed hain! <a href='/dashboard'>Wapas jayein</a>"

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 7. Query Forum
@app.route('/queries', methods=['GET', 'POST'])
def queries():
    if 'username' not in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        if session['role'] == 'Student':
            question = request.form['question']
            queries_collection.insert_one({
                "question": question,
                "asked_by": session['username'],
                "answer": "No answer yet.",
                "answered_by": "None"
            })
        else:
            return "Teachers doubt post nahi kar sakte!"
        
    queries_list = list(queries_collection.find())
    return render_template('queries.html', queries=queries_list, role=session['role'])

@app.route('/answer/<string:query_id>', methods=['POST'])
def answer_query(query_id):
    if 'username' not in session:
        return redirect(url_for('index'))
    
    if session['role'] != 'Teacher':
        return "Sirf Teachers hi doubts solve kar sakte hain!"
        
    answer = request.form['answer']
    queries_collection.update_one(
        {"_id": ObjectId(query_id)},
        {"$set": {"answer": answer, "answered_by": session['username']}}
    )
    return redirect(url_for('queries'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)