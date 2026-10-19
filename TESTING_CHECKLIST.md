# Manual smoke-test checklist
1. Run `python app.py`, then open http://127.0.0.1:5000.
2. Check the home page on desktop and around 375px mobile width.
3. Open and close the mobile menu.
4. Register with a valid email and password of at least 8 characters.
5. Sign in, apply for a pass, and check the success message.
6. Confirm the application appears on the dashboard as `Pending`.
7. Open application details.
8. Sign out and confirm protected routes ask for sign-in.
9. Visit `/this-page-does-not-exist` to see the custom 404 page.
10. Confirm the page title and favicon appear in the browser.

This is a manual checklist, not a claim that every browser/device combination has been tested.
