# CityPass — Bus Pass Management System

A light, responsive Flask web app for applying for and tracking city bus pass applications. Designed for local educational use; no paid cloud service is required.

## Features
- Responsive, mobile-first layout and collapsible mobile menu
- User registration, sign-in and sign-out
- Werkzeug password hashing and parameterized SQLite queries
- Bus pass application form with validation
- Personal dashboard and application details
- Success, information and error messages
- CSRF tokens on POST forms and security response headers
- Custom 400, 404 and 413 pages
- Per-page titles and meta descriptions
- Local SVG favicon; no external CDN or image dependencies
- Clickable logo, phone and email links; working footer/navigation links
- Automatically updated copyright year and mobile overflow safeguards

## Requirements
Python 3.10+ and pip.

## Run on Windows PowerShell
```powershell
cd path\to\CityPass_Bus_Pass_System
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:FLASK_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```
Open http://127.0.0.1:5000. The app creates `citypass.db` automatically. Register an account, sign in, apply for a pass, and view the application in your dashboard.

## Demo limitations
This is an educational local demo, not an official transport authority service. Applications remain `Pending`; approval, payments, SMS/email delivery, real pass issuance and transport-agency integration are not implemented. Contact details in the footer are placeholders (`+91 98765 43210`, `hello@citypass.example`) and must be replaced before public release. Do not enter real identity documents or sensitive data.

Before public deployment, configure a stable secret key, HTTPS and secure cookies, use a managed database, and perform a security review. Local testing is not a production security audit.
