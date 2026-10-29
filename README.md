# CityPass — Bus Pass Management System

CityPass is a Flask + SQLite application for bus-pass requests with three role-based areas: **User**, **Manager**, and **Admin**. It runs locally without a paid service. It is suitable for coursework and internal demonstrations; public deployment still requires an operational and security review.

## Included functionality

### User portal
- Register, sign in, and sign out.
- Passwords stored as Werkzeug password hashes.
- Apply for Student, Regular, or Senior passes with route, duration, and future start date validation.
- View only your own applications and their current status / review note.

### Manager portal
- View all applications, with pending applications first.
- Approve or reject pending applications and add an optional decision note.
- Review decisions are stored with reviewer ID and timestamp.
- A decided application cannot be changed again from the review screen.

### Admin portal
- Overview counts for users, managers, applications, and pending requests.
- View all applications and review information.
- Promote standard accounts to Manager or return them to User; enable or disable standard accounts.
- New public registrations always receive the User role. Admin cannot change their own role/status or change other administrator accounts through the UI.
- First administrator is created through a secure interactive CLI command, not a hard-coded default password.

### Security and operations
- Parameterized SQLite statements, server-side role checks, CSRF tokens on POST forms, password hashing, session cookie settings, and common security headers.
- Non-destructive database migrations add role and review fields to existing CityPass databases.
- Health endpoint at `/health`, custom error pages, responsive layout, and local static assets.
- 66 automated tests across the test suite.

## Requirements
- Python 3.10 or newer.
- `pip`.

## Windows PowerShell setup

From the extracted project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:FLASK_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

Open `http://127.0.0.1:5000`. SQLite database `citypass.db` is created automatically in the project directory. Do not place real credentials in source code.

### Create the first administrator

Stop the server if running, then execute:

```powershell
$env:FLASK_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
flask --app app create-admin
```

Enter the administrator's name, email, and a unique password of at least 10 characters when prompted. Start the server again with `python app.py`, then sign in at `/login`. Admins can assign the Manager role to an existing account through **Accounts**. To create a manager account, first register it through the normal sign-up page, then promote it from the admin screen.

**Important:** Set a stable, randomly generated `FLASK_SECRET_KEY` in your environment each time you start the application; if it changes, existing sessions are invalidated. Do not use the sample value in `.env.example` as a real secret.

## Run tests

Activate the project's virtual environment, then run the full test suite with coverage:

```powershell
python -m pytest -q --cov=app --cov-report=term-missing
```

Run the dependency vulnerability audit:

```powershell
python -m pip_audit -r requirements.txt
```

Or run both checks, plus Git whitespace/status checks, using the included PowerShell script:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run_all_checks.ps1
```

Tests use a temporary SQLite database and do not change the application's normal database. They cover registration, hashed passwords, login, CSRF, role-based access, application creation, cross-user access denial, manager decisions, admin role/status management, redirects, headers, error routes, and the admin CLI command.

### Latest tested results

| Check | Result |
|---|---:|
| Automated tests | **66 passed, 0 failed** |
| Application code coverage | **99%** |
| Uncovered application statements | **1** (reported at `app.py` line 459) |
| Dependency audit (`pip-audit`) | **No known vulnerabilities found** |
| Git whitespace checks | **Passed** |
| Python version used for testing | **3.12.10** |

These results describe the test run in the development environment; they are not a guarantee that the application is free of security vulnerabilities. Dependency auditing only checks for known issues in audited packages, and code coverage measures which statements were executed—not whether every behavior is correct or secure.

## Optional configuration

- `FLASK_SECRET_KEY`: stable random secret for sessions (required for stable deployments).
- `FLASK_HOST`: defaults to `127.0.0.1` for local-only access.
- `FLASK_PORT`: defaults to `5000`.
- `COOKIE_SECURE=1`: only when serving through HTTPS.
- `CITYPASS_DATABASE`: optional path to the SQLite database file.

## Roles and access

- **User:** `/dashboard`, `/apply`, `/pass/<id>` (only their own records).
- **Manager:** `/manager`, `/manager/passes`.
- **Admin:** `/admin`, `/admin/users`, `/admin/passes`; can also access manager review pages.

Direct URL access is checked on the server; hiding a navigation link is not the security boundary.

## Production limitations and checklist

This package does not include email/SMS delivery, online payment, transport-authority integration, password-reset email flow, or physical pass issuance. Those require business rules and external service configuration and are intentionally not simulated. The application has not been deployed to a public production environment. Before internet-facing deployment, configure HTTPS, stable secrets, backups, monitoring, rate limiting, a supported production WSGI server, database access controls, and a separate security review. No application can be guaranteed 100% secure.
