# -*- coding: utf-8 -*-
from flask import Blueprint, request, session
from datetime import datetime
from ..models import (get_db, now_str, today_str, to_int, yuan_to_fen,
                      gen_no, log_fund)
from ..security import login_required, admin_required
from ..utils import ok, fail

bp = Blueprint('finance', __name__)


# ============ 应收 ============
@bp.route('/receivables')
@login_required
def api_rec_list():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    status = (request.args.get('status') or '').strip()
    sql = ("SELECT r.*, c.name AS customer_name FROM receivables r "
           "LEFT JOIN customers c ON c.id=r.customer_id WHERE 1=1")
    params = []
    if keyword:
        sql += " AND (r.order_no LIKE ? OR c.name LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like])
    if status:
        sql += " AND r.status=?"
        params.append(status)
    sql += " ORDER BY r.id DESC LIMIT 300"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/receivables/aging')
@login_required
def api_rec_aging():
    db = get_db()
    rows = db.execute(
        "SELECT r.*, c.name AS customer_name FROM receivables r "
        "LEFT JOIN customers c ON c.id=r.customer_id WHERE r.amount > r.received"
    ).fetchall()
    today = datetime.now().date()
    result = []
    buckets = {'0-30': 0, '31-60': 0, '61-90': 0, '90+': 0}
    for r in rows:
        bal = (r['amount'] or 0) - (r['received'] or 0)
        try:
            due = datetime.strptime(r['created_at'][:10], '%Y-%m-%d').date()
            days = (today - due).days
        except Exception:
            days = 0
        if days <= 30:
            k = '0-30'
        elif days <= 60:
            k = '31-60'
        elif days <= 90:
            k = '61-90'
        else:
            k = '90+'
        buckets[k] += bal
        result.append({'order_no': r['order_no'], 'customer_name': r['customer_name'],
                       'amount': r['amount'], 'received': r['received'],
                       'balance': bal, 'days': days, 'bucket': k})
    return ok({'details': result,
               'summary': [{'bucket': k, 'amount': v} for k, v in buckets.items()]})


# ============ 应付 ============
@bp.route('/payables')
@login_required
def api_pay_list():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    status = (request.args.get('status') or '').strip()
    sql = ("SELECT p.*, s.name AS supplier_name FROM payables p "
           "LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1")
    params = []
    if keyword:
        sql += " AND (p.order_no LIKE ? OR s.name LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like])
    if status:
        sql += " AND p.status=?"
        params.append(status)
    sql += " ORDER BY p.id DESC LIMIT 300"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


# ============ 回款 ============
@bp.route('/receipts')
@login_required
def api_receipt_list():
    db = get_db()
    rows = db.execute(
        "SELECT r.*, c.name AS customer_name, a.name AS account_name "
        "FROM receipts r LEFT JOIN customers c ON c.id=r.customer_id "
        "LEFT JOIN fund_accounts a ON a.id=r.account_id ORDER BY r.id DESC LIMIT 300"
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.route('/receipts', methods=['POST'])
@login_required
def api_receipt_create():
    data = request.get_json(silent=True) or {}
    customer_id = to_int(data.get('customer_id'))
    account_id = to_int(data.get('account_id'))
    amount = yuan_to_fen(data.get('amount', 0))
    items = data.get('items') or []

    if not customer_id:
        return fail('请选择客户')
    if not account_id:
        return fail('请选择收款账户')
    if amount <= 0:
        return fail('金额必须大于 0')
    if not items:
        return fail('请选择核销明细')

    total = sum(yuan_to_fen(it.get('amount', 0)) for it in items)
    if total != amount:
        return fail('核销金额合计与收款金额不一致')

    db = get_db()
    for it in items:
        rec = db.execute("SELECT * FROM receivables WHERE id=? AND customer_id=?",
                         (to_int(it.get('receivable_id')), customer_id)).fetchone()
        if not rec:
            return fail('应收记录不存在')
        bal = (rec['amount'] or 0) - (rec['received'] or 0)
        if yuan_to_fen(it.get('amount', 0)) > bal:
            return fail('核销金额超过应收余额')

    receipt_no = gen_no(db, 'RC', 'receipts', 'receipt_no')
    cur = db.execute(
        "INSERT INTO receipts (receipt_no,customer_id,account_id,amount,method,receipt_date,"
        "remark,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (receipt_no, customer_id, account_id, amount,
         (data.get('method') or '银行转账').strip(),
         (data.get('receipt_date') or '').strip() or today_str(),
         (data.get('remark') or '').strip(),
         session.get('real_name') or session.get('username') or '', now_str())
    )
    rid = cur.lastrowid
    for it in items:
        rec_id = to_int(it.get('receivable_id'))
        amt = yuan_to_fen(it.get('amount', 0))
        db.execute("INSERT INTO receipt_items (receipt_id,receivable_id,amount) VALUES (?,?,?)",
                   (rid, rec_id, amt))
        rec = db.execute("SELECT * FROM receivables WHERE id=?", (rec_id,)).fetchone()
        new_received = (rec['received'] or 0) + amt
        new_status = '已收完' if new_received >= (rec['amount'] or 0) else '部分收款'
        db.execute("UPDATE receivables SET received=?, status=? WHERE id=?",
                   (new_received, new_status, rec_id))

    log_fund(db, account_id, '收款', amount, receipt_no, '客户回款')
    db.commit()
    return ok({'id': rid, 'receipt_no': receipt_no}, '回款登记成功')


@bp.route('/receipts/<int:rid>', methods=['DELETE'])
@login_required
@admin_required
def api_receipt_delete(rid):
    db = get_db()
    rc = db.execute("SELECT * FROM receipts WHERE id=?", (rid,)).fetchone()
    if not rc:
        return fail('回款单不存在')
    items = db.execute("SELECT * FROM receipt_items WHERE receipt_id=?", (rid,)).fetchall()
    for it in items:
        rec = db.execute("SELECT * FROM receivables WHERE id=?", (it['receivable_id'],)).fetchone()
        if rec:
            new_received = max(0, (rec['received'] or 0) - (it['amount'] or 0))
            new_status = '已收完' if new_received >= (rec['amount'] or 0) else (
                '部分收款' if new_received > 0 else '未收')
            db.execute("UPDATE receivables SET received=?, status=? WHERE id=?",
                       (new_received, new_status, rec['id']))
    log_fund(db, rc['account_id'], '红冲收款', -rc['amount'], rc['receipt_no'], '作废回款单')
    db.execute("DELETE FROM receipt_items WHERE receipt_id=?", (rid,))
    db.execute("DELETE FROM receipts WHERE id=?", (rid,))
    db.commit()
    return ok(msg='回款单已作废')


# ============ 付款 ============
@bp.route('/payments')
@login_required
def api_payment_list():
    db = get_db()
    rows = db.execute(
        "SELECT p.*, s.name AS supplier_name, a.name AS account_name "
        "FROM payments p LEFT JOIN suppliers s ON s.id=p.supplier_id "
        "LEFT JOIN fund_accounts a ON a.id=p.account_id ORDER BY p.id DESC LIMIT 300"
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.route('/payments', methods=['POST'])
@login_required
def api_payment_create():
    data = request.get_json(silent=True) or {}
    supplier_id = to_int(data.get('supplier_id'))
    account_id = to_int(data.get('account_id'))
    amount = yuan_to_fen(data.get('amount', 0))
    items = data.get('items') or []

    if not supplier_id:
        return fail('请选择供应商')
    if not account_id:
        return fail('请选择付款账户')
    if amount <= 0:
        return fail('金额必须大于 0')
    if not items:
        return fail('请选择核销明细')

    total = sum(yuan_to_fen(it.get('amount', 0)) for it in items)
    if total != amount:
        return fail('核销金额合计与付款金额不一致')

    db = get_db()
    acc = db.execute("SELECT * FROM fund_accounts WHERE id=?", (account_id,)).fetchone()
    if not acc or (acc['balance'] or 0) < amount:
        return fail('资金账户余额不足')

    for it in items:
        pay = db.execute("SELECT * FROM payables WHERE id=? AND supplier_id=?",
                         (to_int(it.get('payable_id')), supplier_id)).fetchone()
        if not pay:
            return fail('应付记录不存在')
        bal = (pay['amount'] or 0) - (pay['paid'] or 0)
        if yuan_to_fen(it.get('amount', 0)) > bal:
            return fail('核销金额超过应付余额')

    payment_no = gen_no(db, 'PY', 'payments', 'payment_no')
    cur = db.execute(
        "INSERT INTO payments (payment_no,supplier_id,account_id,amount,method,payment_date,"
        "remark,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (payment_no, supplier_id, account_id, amount,
         (data.get('method') or '银行转账').strip(),
         (data.get('payment_date') or '').strip() or today_str(),
         (data.get('remark') or '').strip(),
         session.get('real_name') or session.get('username') or '', now_str())
    )
    pid = cur.lastrowid
    for it in items:
        pay_id = to_int(it.get('payable_id'))
        amt = yuan_to_fen(it.get('amount', 0))
        db.execute("INSERT INTO payment_items (payment_id,payable_id,amount) VALUES (?,?,?)",
                   (pid, pay_id, amt))
        pay = db.execute("SELECT * FROM payables WHERE id=?", (pay_id,)).fetchone()
        new_paid = (pay['paid'] or 0) + amt
        new_status = '已付完' if new_paid >= (pay['amount'] or 0) else '部分付款'
        db.execute("UPDATE payables SET paid=?, status=? WHERE id=?",
                   (new_paid, new_status, pay_id))

    log_fund(db, account_id, '付款', -amount, payment_no, '供应商付款')
    db.commit()
    return ok({'id': pid, 'payment_no': payment_no}, '付款登记成功')


@bp.route('/payments/<int:pid>', methods=['DELETE'])
@login_required
@admin_required
def api_payment_delete(pid):
    db = get_db()
    pay = db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    if not pay:
        return fail('付款单不存在')
    items = db.execute("SELECT * FROM payment_items WHERE payment_id=?", (pid,)).fetchall()
    for it in items:
        p = db.execute("SELECT * FROM payables WHERE id=?", (it['payable_id'],)).fetchone()
        if p:
            new_paid = max(0, (p['paid'] or 0) - (it['amount'] or 0))
            new_status = '已付完' if new_paid >= (p['amount'] or 0) else (
                '部分付款' if new_paid > 0 else '未付')
            db.execute("UPDATE payables SET paid=?, status=? WHERE id=?",
                       (new_paid, new_status, p['id']))
    log_fund(db, pay['account_id'], '红冲付款', pay['amount'], pay['payment_no'], '作废付款单')
    db.execute("DELETE FROM payment_items WHERE payment_id=?", (pid,))
    db.execute("DELETE FROM payments WHERE id=?", (pid,))
    db.commit()
    return ok(msg='付款单已作废')


# ============ 资金账户 ============
@bp.route('/fund_accounts')
@login_required
def api_fund_list():
    db = get_db()
    return ok([dict(r) for r in db.execute("SELECT * FROM fund_accounts ORDER BY id").fetchall()])


@bp.route('/fund_accounts', methods=['POST'])
@login_required
@admin_required
def api_fund_create():
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('编码和名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM fund_accounts WHERE code=?", (code,)).fetchone():
        return fail('编码已存在')
    db.execute(
        "INSERT INTO fund_accounts (code,name,atype,balance,remark,status,created_at) "
        "VALUES (?,?,?,?,?,1,?)",
        (code, name, (data.get('atype') or '银行').strip(),
         yuan_to_fen(data.get('balance', 0)),
         (data.get('remark') or '').strip(), now_str())
    )
    db.commit()
    return ok(msg='新增成功')


@bp.route('/fund_accounts/<int:aid>', methods=['PUT'])
@login_required
@admin_required
def api_fund_update(aid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute("UPDATE fund_accounts SET code=?, name=?, atype=?, remark=? WHERE id=?",
               ((data.get('code') or '').strip(), (data.get('name') or '').strip(),
                (data.get('atype') or '银行').strip(),
                (data.get('remark') or '').strip(), aid))
    db.commit()
    return ok(msg='修改成功')


@bp.route('/fund_accounts/<int:aid>', methods=['DELETE'])
@login_required
@admin_required
def api_fund_delete(aid):
    db = get_db()
    if db.execute("SELECT COUNT(*) AS c FROM receipts WHERE account_id=?", (aid,)).fetchone()['c']:
        return fail('该账户已有收款记录')
    if db.execute("SELECT COUNT(*) AS c FROM payments WHERE account_id=?", (aid,)).fetchone()['c']:
        return fail('该账户已有付款记录')
    db.execute("DELETE FROM fund_logs WHERE account_id=?", (aid,))
    db.execute("DELETE FROM fund_accounts WHERE id=?", (aid,))
    db.commit()
    return ok(msg='删除成功')


@bp.route('/fund_logs')
@login_required
def api_fund_logs():
    db = get_db()
    account_id = to_int(request.args.get('account_id'))
    sql = ("SELECT f.*, a.name AS account_name FROM fund_logs f "
           "LEFT JOIN fund_accounts a ON a.id=f.account_id WHERE 1=1")
    params = []
    if account_id:
        sql += " AND f.account_id=?"
        params.append(account_id)
    sql += " ORDER BY f.id DESC LIMIT 500"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])