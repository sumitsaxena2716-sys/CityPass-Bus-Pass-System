import os
import re
import secrets
import sqlite3
from datetime import datetime, date, timedelta
from calendar import monthrange
from functools import wraps
from pathlib import Path
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import click

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('CITYPASS_DATABASE', str(BASE / 'citypass.db'))).resolve()
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',
    PERMANENT_SESSION_LIFETIME=3600,
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
ROLES = {'user', 'manager', 'admin'}
PASS_TYPES = {'Student', 'Regular', 'Senior'}
DURATIONS = {'Monthly', 'Quarterly'}
PASS_STATUSES = {'Pending', 'Approved', 'Rejected', 'Expired'}


def db():
    if 'db' not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
        g.db.execute('PRAGMA busy_timeout=10000')
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS passes (
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        pass_type TEXT NOT NULL, route TEXT NOT NULL, duration TEXT NOT NULL,
        start_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending',
        reference TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
    );
    ''')
    # Non-destructive migrations for databases created by earlier versions.
    user_columns = {r[1] for r in conn.execute('PRAGMA table_info(users)')}
    if 'role' not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if 'is_active' not in user_columns:
        conn.execute('ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
    pass_columns = {r[1] for r in conn.execute('PRAGMA table_info(passes)')}
    if 'decision_note' not in pass_columns:
        conn.execute('ALTER TABLE passes ADD COLUMN decision_note TEXT NOT NULL DEFAULT \'\'')
    if 'reviewed_by' not in pass_columns:
        conn.execute('ALTER TABLE passes ADD COLUMN reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL')
    if 'reviewed_at' not in pass_columns:
        conn.execute('ALTER TABLE passes ADD COLUMN reviewed_at TEXT')
    if 'expires_at' not in pass_columns:
        conn.execute('ALTER TABLE passes ADD COLUMN expires_at TEXT')
    # Backfill expiry dates for previously approved passes without changing their status/data.
    approved_rows = conn.execute(
        "SELECT id, start_date, duration FROM passes WHERE status='Approved' AND (expires_at IS NULL OR expires_at='')"
    ).fetchall()
    for pass_id, start_value, duration_value in approved_rows:
        try:
            expiry = pass_expiry_date(start_value, duration_value)
        except (ValueError, TypeError):
            continue
        conn.execute('UPDATE passes SET expires_at=? WHERE id=?', (expiry, pass_id))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_passes_user_id ON passes(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_passes_status ON passes(status)")
    conn.commit()
    conn.close()


def pass_expiry_date(start_value, duration_value):
    """Return the inclusive last valid day for a Monthly or Quarterly pass."""
    start = date.fromisoformat(start_value)
    months = {'Monthly': 1, 'Quarterly': 3}.get(duration_value)
    if months is None:
        raise ValueError('Unknown pass duration')
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp the day when the target month is shorter (e.g. Jan 31 -> Feb 28/29).
    day = min(start.day, monthrange(year, month)[1])
    next_period = date(year, month, day)
    # A pass is valid through the day before the matching date in the next period.
    return (next_period - timedelta(days=1)).isoformat()


def refresh_expired_passes():
    """Keep approved passes expired after their inclusive expiry date."""
    db().execute(
        "UPDATE passes SET status='Expired' WHERE status='Approved' AND expires_at IS NOT NULL AND expires_at < ?",
        (date.today().isoformat(),)
    )
    db().commit()


def timestamp():
    return datetime.now().isoformat(timespec='seconds')


def valid_email(value):
    return len(value) <= 254 and bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value))


def valid_date(value):
    try:
        return date.fromisoformat(value) >= date.today()
    except (ValueError, TypeError):
        return False


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return db().execute('SELECT id,name,email,role,is_active,created_at FROM users WHERE id=?', (uid,)).fetchone()


@app.before_request
def csrf_check():
    refresh_expired_passes()
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    if request.method == 'POST':
        sent, expected = request.form.get('csrf_token', ''), session.get('csrf', '')
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, description='Your form session expired. Refresh the page and try again.')


@app.context_processor
def globals_for_templates():
    user = current_user()
    return {'current_year': datetime.now().year, 'csrf_token': session.get('csrf', ''), 'current_user': user}


@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    resp.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    resp.headers['Cache-Control'] = 'no-store' if request.endpoint in {'login','register','dashboard','admin_dashboard','manager_dashboard','admin_users','admin_passes','manager_passes'} else 'public, max-age=0, must-revalidate'
    return resp


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash('Please sign in to continue.', 'info')
            return redirect(url_for('login', next=request.path))
        if not user['is_active']:
            session.clear()
            flash('This account is disabled. Contact an administrator.', 'error')
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if user['role'] not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def safe_next(target):
    return target if target and target.startswith('/') and not target.startswith('//') and '\\' not in target else None


def role_home(role):
    return {'admin': 'admin_dashboard', 'manager': 'manager_dashboard'}.get(role, 'dashboard')


@app.route('/')
def home():
    return render_template('home.html', title='CityPass — Bus Pass Management', description='Apply for a city bus pass online and track your application.')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not name or len(name) > 80 or any(ord(ch) < 32 for ch in name):
            flash('Enter a valid name (up to 80 characters).', 'error')
        elif not valid_email(email):
            flash('Enter a valid email address.', 'error')
        elif len(password) < 10:
            flash('Password must be at least 10 characters long.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        else:
            try:
                db().execute('INSERT INTO users(name,email,password_hash,created_at,role,is_active) VALUES(?,?,?,?,?,1)',
                             (name, email, generate_password_hash(password), timestamp(), 'user'))
                db().commit()
                flash('Account created successfully. You can now sign in.', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('An account with this email already exists. Please sign in.', 'error')
    return render_template('register.html', title='Create account — CityPass', description='Create an account to apply for and manage your bus pass.')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if user and user['is_active'] and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['csrf'] = secrets.token_urlsafe(32)
            session.permanent = True
            flash(f"Welcome back, {user['name'].split()[0]}!", 'success')
            target = safe_next(request.args.get('next', ''))
            return redirect(target or url_for(role_home(user['role'])))
        flash('Email or password is incorrect. Please try again.', 'error')
    return render_template('login.html', title='Sign in — CityPass', description='Sign in to manage your bus pass applications.')


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    flash('You have been signed out.', 'success')
    return redirect(url_for('home'))


@app.route('/dashboard')
@roles_required('user')
def dashboard():
    items = db().execute('SELECT * FROM passes WHERE user_id=? ORDER BY id DESC', (session['user_id'],)).fetchall()
    return render_template('dashboard.html', title='My dashboard — CityPass', description='View your applications and status.', passes=items)


@app.route('/apply', methods=['GET', 'POST'])
@roles_required('user')
def apply_pass():
    if request.method == 'POST':
        typ = request.form.get('pass_type', '')
        route = request.form.get('route', '').strip()
        duration = request.form.get('duration', '')
        start = request.form.get('start_date', '')
        if typ not in PASS_TYPES:
            flash('Choose a valid pass category.', 'error')
        elif not route or len(route) > 120 or any(ord(ch) < 32 for ch in route):
            flash('Enter a valid route (up to 120 characters).', 'error')
        elif duration not in DURATIONS:
            flash('Choose a valid pass duration.', 'error')
        elif not valid_date(start):
            flash('Choose a valid start date from today onwards.', 'error')
        else:
            ref = 'CP-' + secrets.token_hex(4).upper()
            db().execute("INSERT INTO passes(user_id,pass_type,route,duration,start_date,status,reference,created_at) VALUES(?,?,?,?,?,'Pending',?,?)",
                         (session['user_id'], typ, route, duration, start, ref, timestamp()))
            db().commit()
            flash(f'Application submitted successfully. Reference: {ref}', 'success')
            return redirect(url_for('dashboard'))
    return render_template('apply.html', title='Apply for a pass — CityPass', description='Apply for a city bus pass.', today=date.today().isoformat())


@app.route('/pass/<int:pass_id>')
@roles_required('user')
def pass_detail(pass_id):
    item = db().execute('SELECT * FROM passes WHERE id=? AND user_id=?', (pass_id, session['user_id'])).fetchone()
    if item is None:
        abort(404)
    return render_template('pass_detail.html', title='Pass application — CityPass', description='View application details.', item=item)


@app.route('/admin')
@roles_required('admin')
def admin_dashboard():
    conn = db()
    stats = {
        'users': conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0],
        'managers': conn.execute("SELECT COUNT(*) FROM users WHERE role='manager'").fetchone()[0],
        'applications': conn.execute('SELECT COUNT(*) FROM passes').fetchone()[0],
        'pending': conn.execute("SELECT COUNT(*) FROM passes WHERE status='Pending'").fetchone()[0],
        'expired': conn.execute("SELECT COUNT(*) FROM passes WHERE status='Expired'").fetchone()[0],
    }
    recent = conn.execute('SELECT p.*,u.name AS applicant_name,u.email AS applicant_email FROM passes p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 8').fetchall()
    return render_template('admin_dashboard.html', title='Admin dashboard — CityPass', stats=stats, recent=recent)


@app.route('/admin/users', methods=['GET', 'POST'])
@roles_required('admin')
def admin_users():
    conn = db()
    if request.method == 'POST':
        try:
            user_id = int(request.form.get('user_id', '0'))
        except ValueError:
            abort(400, description='Invalid account identifier.')
        action = request.form.get('action', '')
        target = conn.execute('SELECT id,role,is_active FROM users WHERE id=?', (user_id,)).fetchone()
        if not target:
            abort(404)
        if user_id == session['user_id']:
            flash('You cannot change your own role or account status here.', 'error')
        elif target['role'] == 'admin':
            flash('Administrator accounts cannot be changed from this screen.', 'error')
        elif action == 'role':
            role = request.form.get('role', '')
            if role not in {'user', 'manager'}:
                flash('Choose a valid role.', 'error')
            else:
                conn.execute('UPDATE users SET role=? WHERE id=?', (role, user_id)); conn.commit()
                flash('Account role updated.', 'success')
        elif action == 'status':
            active = request.form.get('active', '')
            if active not in {'0', '1'}:
                flash('Choose a valid account status.', 'error')
            else:
                conn.execute('UPDATE users SET is_active=? WHERE id=?', (int(active), user_id)); conn.commit()
                flash('Account status updated.', 'success')
        else:
            abort(400, description='Unknown account action.')
        return redirect(url_for('admin_users'))
    users = conn.execute('SELECT id,name,email,role,is_active,created_at FROM users ORDER BY id DESC').fetchall()
    return render_template('admin_users.html', title='Manage accounts — CityPass', users=users)


@app.route('/admin/passes')
@roles_required('admin')
def admin_passes():
    items = db().execute('SELECT p.*,u.name AS applicant_name,u.email AS applicant_email,m.name AS reviewer_name FROM passes p JOIN users u ON u.id=p.user_id LEFT JOIN users m ON m.id=p.reviewed_by ORDER BY p.id DESC').fetchall()
    return render_template('admin_passes.html', title='All applications — CityPass', passes=items, readonly=True)


@app.route('/manager')
@roles_required('manager', 'admin')
def manager_dashboard():
    counts = {status.lower(): db().execute('SELECT COUNT(*) FROM passes WHERE status=?', (status,)).fetchone()[0] for status in PASS_STATUSES}
    items = db().execute('SELECT p.*,u.name AS applicant_name,u.email AS applicant_email FROM passes p JOIN users u ON u.id=p.user_id ORDER BY CASE p.status WHEN \'Pending\' THEN 0 ELSE 1 END, p.id DESC LIMIT 12').fetchall()
    return render_template('manager_dashboard.html', title='Manager dashboard — CityPass', counts=counts, passes=items)


@app.route('/manager/passes', methods=['GET', 'POST'])
@roles_required('manager', 'admin')
def manager_passes():
    conn = db()
    if request.method == 'POST':
        try:
            pass_id = int(request.form.get('pass_id', '0'))
        except ValueError:
            abort(400, description='Invalid application identifier.')
        status = request.form.get('status', '')
        note = request.form.get('decision_note', '').strip()
        if status not in {'Approved', 'Rejected'}:
            flash('Choose Approved or Rejected.', 'error')
        elif len(note) > 500:
            flash('Decision note must be 500 characters or fewer.', 'error')
        else:
            item = conn.execute('SELECT id,status FROM passes WHERE id=?', (pass_id,)).fetchone()
            if not item:
                abort(404)
            if item['status'] != 'Pending':
                flash('Only pending applications can be reviewed.', 'error')
            else:
                expires_at = None
                if status == 'Approved':
                    pass_dates = conn.execute('SELECT start_date,duration FROM passes WHERE id=?', (pass_id,)).fetchone()
                    try:
                        expires_at = pass_expiry_date(pass_dates['start_date'], pass_dates['duration'])
                    except (ValueError, TypeError):
                        flash('Could not calculate the pass expiry date. Check the start date and duration.', 'error')
                        return redirect(url_for('manager_passes'))
                conn.execute('UPDATE passes SET status=?,decision_note=?,reviewed_by=?,reviewed_at=?,expires_at=? WHERE id=? AND status=\'Pending\'',
                             (status, note, session['user_id'], timestamp(), expires_at, pass_id))
                conn.commit()
                flash(f'Application {status.lower()} successfully.', 'success')
                return redirect(url_for('manager_passes'))
        return redirect(url_for('manager_passes'))
    items = conn.execute('SELECT p.*,u.name AS applicant_name,u.email AS applicant_email FROM passes p JOIN users u ON u.id=p.user_id ORDER BY CASE p.status WHEN \'Pending\' THEN 0 ELSE 1 END,p.id DESC').fetchall()
    return render_template('admin_passes.html', title='Review applications — CityPass', passes=items, readonly=False)


@app.route('/health')
def health():
    return {'status': 'ok', 'service': 'CityPass'}


@app.errorhandler(400)
def bad_request(err):
    return render_template('error.html', title='Request error — CityPass', description='Your request could not be processed.', code=400, message=getattr(err, 'description', 'Please try again.')), 400


@app.errorhandler(403)
def forbidden(err):
    return render_template('error.html', title='Access denied — CityPass', description='You do not have permission to view this page.', code=403, message='You do not have permission to access this page.'), 403


@app.errorhandler(404)
def not_found(err):
    return render_template('error.html', title='Page not found — CityPass', description='The page you are looking for could not be found.', code=404, message='We couldn’t find that page. It may have moved or the address may be incorrect.'), 404


@app.errorhandler(413)
def too_large(err):
    return render_template('error.html', title='Request too large — CityPass', description='The submitted request is too large.', code=413, message='This request is too large. Please reduce its size and try again.'), 413


@app.cli.command('create-admin')
def create_admin():
    """Create the first administrator account securely from the terminal."""
    init_db()
    name = click.prompt('Administrator full name').strip()
    email = click.prompt('Administrator email').strip().lower()
    password = click.prompt('Administrator password', hide_input=True, confirmation_prompt=True)
    if not name or len(name) > 80 or not valid_email(email) or len(password) < 10:
        raise click.ClickException('Provide a valid name/email and a password with at least 10 characters.')
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        if existing:
            raise click.ClickException('That email already exists. Use the admin account management screen to assign roles.')
        conn.execute('INSERT INTO users(name,email,password_hash,created_at,role,is_active) VALUES(?,?,?,?,?,1)',
                     (name, email, generate_password_hash(password), timestamp(), 'admin'))
    click.echo('Administrator created. Sign in using the credentials you just configured.')


init_db()
if __name__ == '__main__':
    app.run(host=os.environ.get('FLASK_HOST', '127.0.0.1'), port=int(os.environ.get('FLASK_PORT', '5000')), debug=False)
