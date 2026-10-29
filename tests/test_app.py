import os
import tempfile
import unittest
from datetime import date, timedelta

_fd, _db_path = tempfile.mkstemp(prefix='citypass-tests-', suffix='.db')
os.close(_fd)
os.environ['CITYPASS_DATABASE'] = _db_path
os.environ['FLASK_SECRET_KEY'] = 'test-only-secret-key-not-for-production'

import app as cityapp
from werkzeug.security import generate_password_hash


class CityPassTests(unittest.TestCase):
    def setUp(self):
        cityapp.app.config.update(TESTING=True, SECRET_KEY='test-only-secret-key')
        with cityapp.app.app_context():
            conn = cityapp.db()
            conn.execute('DELETE FROM passes')
            conn.execute('DELETE FROM users')
            conn.commit()
        self.client = cityapp.app.test_client()
        self.user_id = self.create_account('User One', 'user@example.com', 'user-password-123', 'user')
        self.manager_id = self.create_account('Manager One', 'manager@example.com', 'manager-password-123', 'manager')
        self.admin_id = self.create_account('Admin One', 'admin@example.com', 'admin-password-123', 'admin')

    def tearDown(self):
        pass

    def create_account(self, name, email, password, role):
        with cityapp.app.app_context():
            conn = cityapp.db()
            cur = conn.execute('INSERT INTO users(name,email,password_hash,created_at,role,is_active) VALUES(?,?,?,?,?,1)',
                               (name, email, generate_password_hash(password), cityapp.timestamp(), role))
            conn.commit()
            return cur.lastrowid

    def csrf(self):
        with self.client.session_transaction() as sess:
            return sess['csrf']

    def login(self, email, password):
        self.client.get('/login')
        return self.client.post('/login', data={'csrf_token': self.csrf(), 'email': email, 'password': password}, follow_redirects=False)

    def add_pass(self, owner_id=None, status='Pending'):
        owner_id = owner_id or self.user_id
        with cityapp.app.app_context():
            conn = cityapp.db()
            cur = conn.execute('INSERT INTO passes(user_id,pass_type,route,duration,start_date,status,reference,created_at) VALUES(?,?,?,?,?,?,?,?)',
                               (owner_id, 'Student', 'Central to Market', 'Monthly', date.today().isoformat(), status, 'CP-TEST%04d' % (conn.execute('SELECT COUNT(*) FROM passes').fetchone()[0]+1), cityapp.timestamp()))
            conn.commit()
            return cur.lastrowid

    def test_01_homepage_loads(self): self.assertEqual(self.client.get('/').status_code, 200)
    def test_02_health_endpoint(self): self.assertEqual(self.client.get('/health').json['status'], 'ok')
    def test_03_security_headers(self):
        r=self.client.get('/'); self.assertEqual(r.headers['X-Frame-Options'],'DENY'); self.assertIn('Content-Security-Policy',r.headers)
    def test_04_registration_page_loads(self): self.assertEqual(self.client.get('/register').status_code,200)
    def test_05_registration_rejects_short_password(self):
        self.client.get('/register'); r=self.client.post('/register',data={'csrf_token':self.csrf(),'name':'New Person','email':'new@example.com','password':'short','confirm_password':'short'}); self.assertIn(b'at least 10',r.data)
    def test_06_registration_creates_hashed_user(self):
        self.client.get('/register'); self.client.post('/register',data={'csrf_token':self.csrf(),'name':'New Person','email':'new@example.com','password':'long-password-123','confirm_password':'long-password-123'})
        with cityapp.app.app_context():
            row=cityapp.db().execute('SELECT password_hash FROM users WHERE email=?',('new@example.com',)).fetchone()
            self.assertTrue(row and row['password_hash'] != 'long-password-123')
    def test_07_registration_duplicate_email_rejected(self):
        self.client.get('/register'); r=self.client.post('/register',data={'csrf_token':self.csrf(),'name':'Duplicate','email':'user@example.com','password':'long-password-123','confirm_password':'long-password-123'}); self.assertIn(b'already exists',r.data)
    def test_08_login_success_redirects_user(self): self.assertEqual(self.login('user@example.com','user-password-123').status_code,302)
    def test_09_login_wrong_password_rejected(self): self.assertIn(b'incorrect',self.login('user@example.com','wrong-password').data)
    def test_10_post_without_csrf_rejected(self): self.assertEqual(self.client.post('/logout').status_code,400)
    def test_11_user_dashboard_requires_login(self): self.assertEqual(self.client.get('/dashboard').status_code,302)
    def test_12_user_can_apply_pass(self):
        self.login('user@example.com','user-password-123'); r=self.client.post('/apply',data={'csrf_token':self.csrf(),'pass_type':'Student','route':'Central to Market','duration':'Monthly','start_date':(date.today()+timedelta(days=1)).isoformat()}); self.assertEqual(r.status_code,302)
        with cityapp.app.app_context(): self.assertEqual(cityapp.db().execute('SELECT COUNT(*) FROM passes WHERE user_id=?',(self.user_id,)).fetchone()[0],1)
    def test_13_invalid_pass_category_rejected(self):
        self.login('user@example.com','user-password-123'); r=self.client.post('/apply',data={'csrf_token':self.csrf(),'pass_type':'Fake','route':'route','duration':'Monthly','start_date':date.today().isoformat()}); self.assertIn(b'valid pass category',r.data)
    def test_14_user_cannot_read_another_users_pass(self):
        pass_id=self.add_pass(self.manager_id); self.login('user@example.com','user-password-123'); self.assertEqual(self.client.get(f'/pass/{pass_id}').status_code,404)
    def test_15_user_cannot_open_admin(self):
        self.login('user@example.com','user-password-123'); self.assertEqual(self.client.get('/admin').status_code,403)
    def test_16_manager_can_open_dashboard(self):
        self.login('manager@example.com','manager-password-123'); self.assertEqual(self.client.get('/manager').status_code,200)
    def test_17_manager_can_approve_pending_pass(self):
        pass_id=self.add_pass(); self.login('manager@example.com','manager-password-123'); r=self.client.post('/manager/passes',data={'csrf_token':self.csrf(),'pass_id':str(pass_id),'status':'Approved','decision_note':'Verified'}); self.assertEqual(r.status_code,302)
        with cityapp.app.app_context(): self.assertEqual(cityapp.db().execute('SELECT status FROM passes WHERE id=?',(pass_id,)).fetchone()['status'],'Approved')
    def test_18_manager_cannot_change_decided_pass(self):
        pass_id=self.add_pass(status='Approved'); self.login('manager@example.com','manager-password-123'); self.client.post('/manager/passes',data={'csrf_token':self.csrf(),'pass_id':str(pass_id),'status':'Rejected'}); self.assertEqual(self.client.get('/manager/passes').status_code,200)
        with cityapp.app.app_context(): self.assertEqual(cityapp.db().execute('SELECT status FROM passes WHERE id=?',(pass_id,)).fetchone()['status'],'Approved')
    def test_19_admin_dashboard_loads(self):
        self.login('admin@example.com','admin-password-123'); self.assertEqual(self.client.get('/admin').status_code,200)
    def test_20_admin_can_promote_user_to_manager(self):
        self.login('admin@example.com','admin-password-123'); r=self.client.post('/admin/users',data={'csrf_token':self.csrf(),'user_id':str(self.user_id),'action':'role','role':'manager'}); self.assertEqual(r.status_code,302)
        with cityapp.app.app_context(): self.assertEqual(cityapp.db().execute('SELECT role FROM users WHERE id=?',(self.user_id,)).fetchone()['role'],'manager')
    def test_21_admin_cannot_demote_self(self):
        self.login('admin@example.com','admin-password-123'); self.client.post('/admin/users',data={'csrf_token':self.csrf(),'user_id':str(self.admin_id),'action':'role','role':'user'})
        with cityapp.app.app_context(): self.assertEqual(cityapp.db().execute('SELECT role FROM users WHERE id=?',(self.admin_id,)).fetchone()['role'],'admin')
    def test_22_admin_can_disable_user(self):
        self.login('admin@example.com','admin-password-123'); self.client.post('/admin/users',data={'csrf_token':self.csrf(),'user_id':str(self.user_id),'action':'status','active':'0'}); self.client.post('/logout',data={'csrf_token':self.csrf()})
        with cityapp.app.app_context(): self.assertEqual(cityapp.db().execute('SELECT is_active FROM users WHERE id=?',(self.user_id,)).fetchone()['is_active'],0)
    def test_23_disabled_account_cannot_login(self):
        with cityapp.app.app_context(): cityapp.db().execute('UPDATE users SET is_active=0 WHERE id=?',(self.user_id,)); cityapp.db().commit()
        self.assertIn(b'incorrect',self.login('user@example.com','user-password-123').data)
    def test_24_open_redirect_is_rejected(self):
        self.client.get('/login'); r=self.client.post('/login?next=//evil.example',data={'csrf_token':self.csrf(),'email':'user@example.com','password':'user-password-123'}); self.assertEqual(r.location,'/dashboard')
    def test_25_unknown_route_uses_custom_404(self): self.assertEqual(self.client.get('/not-a-real-route').status_code,404)
    def test_26_logout_clears_session(self):
        self.login('user@example.com','user-password-123'); self.client.post('/logout',data={'csrf_token':self.csrf()}); self.assertEqual(self.client.get('/dashboard').status_code,302)


if __name__ == '__main__': unittest.main(verbosity=2)
