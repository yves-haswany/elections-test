from flask import Flask, render_template, request, redirect, session, url_for, send_file,abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import pandas as pd
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash

MAX_USERS = 361
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///electors.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure exports directory exists
os.makedirs('exports', exist_ok=True)

# Initialize database
db = SQLAlchemy(app)

# Candidate list model
class CandidateList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    list_votes=db.Column(db.Integer,default=0)
    candidates = db.relationship('Candidate', backref='candidate_list', lazy=True)

# Candidate model
class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    party = db.Column(db.String(80), nullable=False)
    votes = db.Column(db.Integer, default=0)
    candidate_list_id = db.Column(db.Integer, db.ForeignKey('candidate_list.id'), nullable=False)

# Ballot pen model
class BallotPen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    serial_number = db.Column(db.String(80), unique=True, nullable=False)
    status = db.Column(db.String(20), default='available')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User',  back_populates='ballot_pens', foreign_keys=[user_id])


# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    electors = db.relationship('Elector', backref='user', lazy=True)
    ballot_pens = db.relationship('BallotPen', back_populates='user', lazy=True)

    

# Elector model
class Elector(db.Model):
    elector_id = db.Column(db.Integer, primary_key=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        else:
            return render_template('LoginPage.html', error="Invalid credentials")
    return render_template('LoginPage.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Only allow developer machine (localhost) to access registration
    if request.remote_addr != '127.0.0.1':
        return "Access Denied", 403

    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        pen=request.form.get("BallotPen")

        # Check if maximum user limit is reached
        if User.query.count() >= MAX_USERS:
            return render_template('register.html', error="User limit reached. Registration is closed.")

        # Validate input
        if not username or not password:
            return render_template('register.html', error="Username and password are required.")

        # Check if the username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error="Username already exists.")

        # Hash password and create new user
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('register'))

    return render_template('register.html')
@app.route('/create-candidate-list', methods=['GET', 'POST'])
def create_candidate_list():
    if request.remote_addr != '127.0.0.1':
        return "Access Denied", 403

    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            new_list = CandidateList(name=name)
            db.session.add(new_list)
            db.session.commit()
            return render_template('create_candidate_list.html')
    return render_template('create_candidate_list.html')
@app.route('/create-candidate', methods=['GET', 'POST'])
def create_candidate():
    if request.remote_addr != '127.0.0.1':
        return "Access Denied", 403

    candidate_lists = CandidateList.query.all()

    if request.method == 'POST':
        name = request.form.get('name')
        party = request.form.get('party')
        list_id = request.form.get('list_id')

        if name and party and list_id:
            new_candidate = Candidate(
                name=name,
                party=party,
                candidate_list_id=int(list_id)
            )
            db.session.add(new_candidate)
            db.session.commit()
            return render_template('create_candidate.html', lists=candidate_lists)

    return render_template('create_candidate.html', lists=candidate_lists)
def is_developer():
    return request.remote_addr == '127.0.0.1'
@app.route('/view-candidate-lists')
def view_candidate_lists():
    if not is_developer():
        return "Access Denied", 403

    candidate_lists = CandidateList.query.all()
    return render_template('view_candidate_lists.html', candidate_lists=candidate_lists)
@app.route('/create-ballot-pen', methods=['GET', 'POST'])
def create_ballot_pen():
    # Only allow access from developer's machine
    users= User.query.all()
    if request.remote_addr != '127.0.0.1':
        return "Access Denied", 403

    if request.method == 'POST':
        serial_number = request.form.get('serial_number')
        user_id = request.form.get('user_id')
        if BallotPen.query.filter_by(serial_number=serial_number).first():
            return render_template('create_ballot_pen.html', error="Ballot pen with this serial number already exists.")

        ballot_pen = BallotPen(
            serial_number=serial_number,
            user_id=user_id  # Make sure this line exists
        )
        db.session.add(ballot_pen)
        db.session.commit()
        return render_template('create_ballot_pen.html', users=users)

    return render_template('create_ballot_pen.html', users=users)
@app.route('/cast-vote', methods=['GET', 'POST'])
def cast_vote():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        list_id = request.form.get('list_id')
        candidate_id = request.form.get('candidate_id')

        if list_id and candidate_id:
            clist = CandidateList.query.get(list_id)
            candidate = Candidate.query.get(candidate_id)

            if clist and candidate and candidate.candidate_list_id == clist.id:
                clist.list_votes += 1
                candidate.votes += 1
                db.session.commit()
                return redirect(url_for('dashboard'))

    # ✅ Fix: fetch all candidates for JS dropdown logic
    all_candidates = [
    {
        'id': c.id,
        'name': c.name,
        'party': c.party,
        'votes': c.votes,
        'candidate_list_id': c.candidate_list_id
    }
    for c in Candidate.query.all()
]
    candidate_lists = CandidateList.query.all()

    return render_template('vote.html', candidate_lists=candidate_lists, all_candidates=all_candidates)


@app.route('/vote', methods=['GET', 'POST'])
def vote():
    if 'user_id' not in session:
       return redirect(url_for('login'))

    candidate_lists = CandidateList.query.all()

    if request.method == 'POST':
        list_id = request.form.get('list_id')
        candidate_id = request.form.get('candidate_id')

        selected_list = CandidateList.query.get(list_id)
        selected_candidate = Candidate.query.get(candidate_id)

        # Validate candidate belongs to the list
        if selected_candidate and selected_candidate.candidate_list_id == selected_list.id:
            selected_list.list_votes += 1
            selected_candidate.votes += 1

             #Ensure candidate's votes do not exceed list's
            if selected_candidate.votes > selected_list.list_votes:
                return "Invalid vote count", 400

            db.session.commit()
            return redirect(url_for('dashboard'))
        else:
            return "Candidate does not belong to selected list", 400

    return render_template('vote.html', candidate_lists=candidate_lists)

@app.route('/assign-ballot-pen', methods=['GET', 'POST'])
def assign_ballot_pen():
    if request.remote_addr != '127.0.0.1':
        return "Access Denied", 403

    users = User.query.all()  # ✅ Fetch all users
    pens = BallotPen.query.filter_by(user_id=None).all()

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        pen_id = request.form.get('pen_id')

        pen = BallotPen.query.get(pen_id)
        if pen:
            pen.user_id = user_id
            pen.status = 'in_use'
            db.session.commit()
            return render_template('assign_ballot_pen.html', users=users, pens=pens, success="Ballot pen assigned successfully.")

    return render_template('assign_ballot_pen.html', users=users, pens=pens)
@app.route('/export-list/<int:list_id>')
def export_single_candidate_list(list_id):
    #if 'user_id' not in session:
       # return redirect(url_for('login'))

    clist = CandidateList.query.get_or_404(list_id)
    candidates = clist.candidates

    # Prepare data for export
    data = [{
        'Candidate Name': c.name,
        'Party': c.party,
        'Votes': c.votes
    } for c in candidates]

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=clist.name)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f'{clist.name}_candidates.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/export-candidate-lists')
def export_candidate_lists():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    candidate_lists = CandidateList.query.all()

    export_data = []
    for clist in candidate_lists:
        for candidate in clist.candidates:
            export_data.append({
                'List Name': clist.name,
                'List Votes': clist.list_votes,
                'Candidate Name': candidate.name,
                'Party': candidate.party,
                'Candidate Votes': candidate.votes
            })

     #Convert to DataFrame
    df = pd.DataFrame(export_data)

     #Export to Excel in-memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='CandidateLists')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name='candidate_lists.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )




@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/sort-votes')
def sort_votes():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Fetch candidate lists and annotate with vote totals
    candidate_lists = CandidateList.query.all()
    results = []

    for clist in candidate_lists:
        total_votes = sum(c.votes for c in clist.candidates)
        candidates = sorted(clist.candidates, key=lambda c: c.votes, reverse=True)
        results.append({
            'list_name': clist.name,
            'total_votes': total_votes,
            'candidates': candidates
        })

    return render_template('sorted_votes.html', results=results)

@app.route('/index')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    elector_id = request.form.get('electorID')
    user = User.query.get(session['user_id'])

    if elector_id:
        new_elector = Elector(elector_id=elector_id, user_id=user.id)
        db.session.add(new_elector)
        db.session.commit()

        # Save to local Excel file
        electors = user.electors
        data = [{'Elector ID': e.elector_id, 'Submitted At': e.submitted_at} for e in electors]
        df = pd.DataFrame(data)
        filepath = os.path.join('exports', f'electors_{user.username}.xlsx')
        with pd.ExcelWriter(filepath, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Electors')

    return redirect(url_for('index'))

@app.route('/export')
def export_electors():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    electors = user.electors

    # Convert to DataFrame
    data = [{'Elector ID': e.elector_id, 'Submitted At': e.submitted_at} for e in electors]
    df = pd.DataFrame(data)

    # Save to in-memory Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Electors')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f'{user.username}_electors.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/electors')
def view_electors():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    return render_template('electors.html', electors=user.electors)

@app.route('/create-list', methods=['GET', 'POST'])
def create_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        list_name = request.form.get('list_name')
        if list_name:
            new_list = CandidateList(name=list_name)
            db.session.add(new_list)
            db.session.commit()
            return redirect(url_for('dashboard'))
    return render_template('create_list.html')

@app.route('/add-candidate', methods=['GET', 'POST'])
def add_candidate():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    lists = CandidateList.query.all()
    if request.method == 'POST':
        name = request.form.get('name')
        party = request.form.get('party')
        list_id = request.form.get('list_id')
        if name and party and list_id:
            candidate = Candidate(name=name, party=party, candidate_list_id=list_id)
            db.session.add(candidate)
            db.session.commit()
            return redirect(url_for('dashboard'))
    return render_template('add_candidate.html', lists=lists)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
