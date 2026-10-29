# CityPass verification checklist

Run `python -m unittest discover -s tests -v` from the project root. The automated suite contains 26 test cases covering:

- Home page, health route, security headers, registration page, and custom 404.
- Registration validation, duplicate emails, and password hashing.
- Valid and invalid login, CSRF rejection, logout, and safe redirect handling.
- Authentication-required dashboard and cross-user pass-detail denial.
- Valid application creation and invalid category rejection.
- Role separation for User, Manager, and Admin.
- Manager approval, review note persistence, and prevention of repeat decisions.
- Admin dashboard, role assignment, self-protection, account disablement, and disabled-account login denial.

These automated tests do not replace manual mobile-layout checks, real browser workflows, dependency scanning, penetration testing, or production deployment verification. Record those separately rather than marking them passed without execution.
