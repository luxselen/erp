# -*- coding: utf-8 -*-
"""安全：密码、CSRF、登录锁定、会话超时"""
import functools
import hmac
import hashlib
import os
import time

from flask import session, request, jsonify, current_app

_fail_counter = {}


def record_login_fail(ip):
    now = time.time()
    info = _fail_counter.setdefault(ip, {'count': 0, 'locked_until': 0})
    info['count'] += 1
    if info['count'] >= current_app.config['MAX_LOGIN_FAILS']:
        info['locked_until'] = now + current_app.config['LOCKOUT_SECONDS']
        info['count'] = 0


def is_locked(ip):
    info = _fail_counter.get(ip)
    if not info:
        return False
    if info['locked_until'] > time.time():
        return True
    if info['locked_until'] and info['locked_until'] <= time.time():
        _fail_counter.pop(ip, None)
    return False


def clear_login_fail(ip):
    _fail_counter.pop(ip, None)


def generate_csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = hashlib.sha256(os.urandom(32)).hexdigest()
    return session['_csrf']


def validate_csrf():
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return True
    token = request.headers.get('X-CSRF-Token') or (request.get_json(silent=True) or {}).get('_csrf')
    stored = session.get('_csrf')
    if not stored or not token:
        return False
    return hmac.compare_digest(str(stored), str(token))


def login_required(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        if not session.get('user_id'):
            return jsonify({'code': 401, 'msg': '未登录', 'data': None})

        last = session.get('_last_active', 0)
        now = time.time()
        timeout = current_app.config.get('SESSION_TIMEOUT', 7200)
        if last and now - last > timeout:
            session.clear()
            return jsonify({'code': 401, 'msg': '会话已过期', 'data': None})
        session['_last_active'] = now

        if not validate_csrf():
            return jsonify({'code': 403, 'msg': 'CSRF Token 无效', 'data': None})

        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*a, **kw):
        if session.get('role') != 'admin':
            return jsonify({'code': 403, 'msg': '无权限', 'data': None})
        return f(*a, **kw)
    return wrapper