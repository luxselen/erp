# -*- coding: utf-8 -*-
import time
from flask import Blueprint, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from ..models import get_db, now_str, log_op
from ..security import (login_required, admin_required, record_login_fail,
                        is_locked, clear_login_fail, generate_csrf_token)
from ..utils import ok, fail

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['POST'])
def api_login():
    ip = request.remote_addr or ''
    if is_locked(ip):
        return fail('登录失败次数过多，请 5 分钟后再试', 429)

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return fail('请输入用户名和密码')

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not row or not check_password_hash(row['password'], password):
        record_login_fail(ip)
        return fail('用户名或密码错误')
    if row['status'] != 1:
        return fail('账号已禁用')

    clear_login_fail(ip)
    session['user_id'] = row['id']
    session['username'] = row['username']
    session['role'] = row['role']
    session['real_name'] = row['real_name'] or row['username']
    session['_last_active'] = time.time()

    token = generate_csrf_token()
    return ok({
        'id': row['id'], 'username': row['username'],
        'real_name': session['real_name'], 'role': row['role'],
        'csrf_token': token
    }, '登录成功')


@bp.route('/logout', methods=['POST'])
def api_logout():
    session.clear()
    return ok(msg='已退出')


@bp.route('/current_user')
def api_current_user():
    if not session.get('user_id'):
        return fail('未登录', 401)
    return ok({
        'id': session['user_id'], 'username': session.get('username'),
        'real_name': session.get('real_name'), 'role': session.get('role')
    })


# ==================== 用户管理 ====================
@bp.route('/users')
@login_required
@admin_required
def api_user_list():
    db = get_db()
    rows = db.execute(
        "SELECT id, username, real_name, role, status, created_at FROM users ORDER BY id"
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.route('/users', methods=['POST'])
@login_required
@admin_required
def api_user_create():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return fail('用户名和密码不能为空')
    if len(password) < 6:
        return fail('密码长度不能少于 6 位')
    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return fail('用户名已存在')
    role = data.get('role') if data.get('role') in ('admin', 'staff') else 'staff'
    db.execute(
        "INSERT INTO users (username,password,real_name,role,status,created_at) VALUES (?,?,?,?,?,?)",
        (username, generate_password_hash(password),
         (data.get('real_name') or '').strip(), role, 1, now_str())
    )
    db.commit()
    log_op('新增', '用户', '新增用户：' + username)
    return ok(msg='新增成功')


@bp.route('/users/<int:uid>', methods=['PUT'])
@login_required
@admin_required
def api_user_update(uid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        return fail('用户不存在')
    role = data.get('role') if data.get('role') in ('admin', 'staff') else user['role']
    status = 1 if int(data.get('status', user['status'])) == 1 else 0
    if user['username'] == 'admin' and (role != 'admin' or status != 1):
        return fail('超级管理员不可降级或禁用')
    db.execute("UPDATE users SET real_name=?, role=?, status=? WHERE id=?",
               ((data.get('real_name') or '').strip(), role, status, uid))
    db.commit()
    log_op('修改', '用户', '修改用户ID：%d' % uid)
    return ok(msg='修改成功')


@bp.route('/users/<int:uid>/password', methods=['POST'])
@login_required
@admin_required
def api_user_reset(uid):
    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''
    if len(password) < 6:
        return fail('密码长度不能少于 6 位')
    db = get_db()
    db.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(password), uid))
    db.commit()
    return ok(msg='密码已重置')


@bp.route('/users/<int:uid>', methods=['DELETE'])
@login_required
@admin_required
def api_user_delete(uid):
    if uid == session.get('user_id'):
        return fail('不能删除当前登录账号')
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        return fail('用户不存在')
    if user['username'] == 'admin':
        return fail('超级管理员不可删除')
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    return ok(msg='删除成功')