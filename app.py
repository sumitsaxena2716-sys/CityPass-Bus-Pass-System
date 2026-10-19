import os, re, secrets, sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CITYPASS_DATABASE", BASE / "citypass.db"))
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)


def db():
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS passes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, pass_type TEXT NOT NULL, route TEXT NOT NULL, duration TEXT NOT NULL, start_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', reference TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL);"""
    )
    conn.commit()
    conn.close()


def timestamp():
    return datetime.now().isoformat(timespec="seconds")


def valid_email(s):
    return len(s) <= 254 and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s))


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date() >= datetime.now().date()
    except (ValueError, TypeError):
        return False


@app.before_request
def csrf_check():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    if request.method == "POST":
        sent, expected = request.form.get("csrf_token", ""), session.get("csrf", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(
                400,
                description="Your form session expired. Refresh the page and try again.",
            )


@app.context_processor
def globals_for_templates():
    return {"current_year": datetime.now().year, "csrf_token": session.get("csrf", "")}


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    return resp


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapped


@app.route("/")
def home():
    return render_template(
        "home.html",
        title="CityPass — Simple Bus Passes",
        description="Apply for a city bus pass online with CityPass. Manage your application and check its status in one simple place.",
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not name or len(name) > 80:
            flash("Enter your name (up to 80 characters).", "error")
        elif not valid_email(email):
            flash("Enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            try:
                db().execute(
                    "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                    (name, email, generate_password_hash(password), timestamp()),
                )
                db().commit()
                flash("Account created successfully. You can now sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash(
                    "An account with this email already exists. Please sign in.",
                    "error",
                )
    return render_template(
        "register.html",
        title="Create account — CityPass",
        description="Create a CityPass account to apply for and manage your bus pass.",
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["csrf"] = secrets.token_urlsafe(32)
            flash(f"Welcome back, {user['name'].split()[0]}!", "success")
            target = request.args.get("next", "")
            return redirect(
                target
                if target.startswith("/") and not target.startswith("//")
                else url_for("dashboard")
            )
        flash("Email or password is incorrect. Please try again.", "error")
    return render_template(
        "login.html",
        title="Sign in — CityPass",
        description="Sign in to manage your CityPass bus pass applications.",
    )


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@login_required
def dashboard():
    items = (
        db()
        .execute(
            "SELECT * FROM passes WHERE user_id=? ORDER BY id DESC",
            (session["user_id"],),
        )
        .fetchall()
    )
    return render_template(
        "dashboard.html",
        title="My dashboard — CityPass",
        description="View your CityPass applications and current status.",
        passes=items,
    )


@app.route("/apply", methods=["GET", "POST"])
@login_required
def apply_pass():
    if request.method == "POST":
        typ = request.form.get("pass_type", "")
        route = request.form.get("route", "").strip()
        duration = request.form.get("duration", "")
        start = request.form.get("start_date", "")
        if typ not in {"Student", "Regular", "Senior"}:
            flash("Choose a valid pass category.", "error")
        elif not route or len(route) > 120:
            flash("Enter a route (up to 120 characters).", "error")
        elif duration not in {"Monthly", "Quarterly"}:
            flash("Choose a valid pass duration.", "error")
        elif not valid_date(start):
            flash("Choose a valid start date.", "error")
        else:
            ref = "CP-" + secrets.token_hex(4).upper()
            db().execute(
                "INSERT INTO passes(user_id,pass_type,route,duration,start_date,status,reference,created_at) VALUES(?,?,?,?,?,'Pending',?,?)",
                (session["user_id"], typ, route, duration, start, ref, timestamp()),
            )
            db().commit()
            flash(f"Application submitted successfully. Reference: {ref}", "success")
            return redirect(url_for("dashboard"))
    return render_template(
        "apply.html",
        title="Apply for a pass — CityPass",
        description="Apply for a student, regular, or senior city bus pass.",
        today=datetime.now().date().isoformat(),
    )


@app.route("/pass/<int:pass_id>")
@login_required
def pass_detail(pass_id):
    item = (
        db()
        .execute(
            "SELECT * FROM passes WHERE id=? AND user_id=?",
            (pass_id, session["user_id"]),
        )
        .fetchone()
    )
    if item is None:
        abort(404)
    return render_template(
        "pass_detail.html",
        title="Pass application — CityPass",
        description="View your CityPass application details.",
        item=item,
    )


@app.route("/health")
def health():
    return {"status": "ok", "service": "CityPass"}


@app.errorhandler(400)
def bad_request(err):
    return (
        render_template(
            "error.html",
            title="Request error — CityPass",
            description="Your request could not be processed.",
            code=400,
            message=getattr(err, "description", "Please try again."),
        ),
        400,
    )


@app.errorhandler(404)
def not_found(err):
    return (
        render_template(
            "error.html",
            title="Page not found — CityPass",
            description="The page you are looking for could not be found.",
            code=404,
            message="We couldn’t find that page. It may have moved or the address may be incorrect.",
        ),
        404,
    )


@app.errorhandler(413)
def too_large(err):
    return (
        render_template(
            "error.html",
            title="Request too large — CityPass",
            description="The submitted request is too large.",
            code=413,
            message="This request is too large. Please reduce its size and try again.",
        ),
        413,
    )


init_db()
if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=False,
    )
