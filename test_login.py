# -*- coding: utf-8 -*-
from app import create_app
import re

app = create_app()
with app.test_client() as client:
    # Get login page
    r1 = client.get('/auth/login')
    print('Login page status:', r1.status_code)
    
    # Extract CSRF token from form
    match = re.search(r'name="csrf_token" value="([^"]+)"', r1.text)
    if match:
        csrf_token = match.group(1)
        print('CSRF token found:', csrf_token[:20] + '...')
        
        # Try login
        r2 = client.post('/auth/login', data={
            'csrf_token': csrf_token,
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=False)
        print('Login status:', r2.status_code)
        print('Location:', r2.headers.get('Location', 'None'))
        
        if r2.status_code == 302:
            print('LOGIN SUCCESS!')
        else:
            print('LOGIN FAILED')
    else:
        print('No CSRF token found in form!')
