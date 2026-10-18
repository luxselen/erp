# -*- coding: utf-8 -*-
"""发票管理：进项 / 销项发票登记、查询、作废"""
from flask import Blueprint, request, session
from ..models import (get_db, now_str, today_str, to_int, yuan_to_fen,
                      fen_to_yuan, log_op)
from ..security import login_required, admin_required
from ..utils import ok, fail

bp = Blueprint('invoice', __name__)


@bp.route('/invoices')
@login_required
def api_list():
    db = get_db()
    itype = (request.args.get('invoice_type') or '').strip()
    keyword = (request.args.get('keyword') or '').strip()
    status = (request.args.get('status') or '').strip()
    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()

    sql = "SELECT * FROM invoices WHERE 1=1"
    params = []
    if itype:
        sql += " AND invoice_type=?"
        params.append(itype)
    if keyword:
        sql += " AND (invoice_no LIKE ? OR partner_name LIKE ? OR related_order LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like, like])
    if status:
        sql += " AND status=?"
        params.append(status)
    if start:
        sql += " AND invoice_date >= ?"
        params.append(start)
    if end:
        sql += " AND invoice_date <= ?"
        params.append(end)
    sql += " ORDER BY id DESC LIMIT 500"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/invoices/<int:iid>')
@login_required
def api_detail(iid):
    db = get_db()
    row = db.execute("SELECT * FROM invoices WHERE id=?", (iid,)).fetchone()
    if not row:
        return fail('发票不存在')
    return ok(dict(row))


@bp.route('/invoices', methods=['POST'])
@login_required
def api_create():
    data = request.get_json(silent=True) or {}
    invoice_no = (data.get('invoice_no') or '').strip()
    invoice_type = (data.get('invoice_type') or '').strip()
    partner_type = (data.get('partner_type') or '').strip()
    partner_id = to_int(data.get('partner_id'))
    amount = yuan_to_fen(data.get('amount', 0))
    tax_rate = float(data.get('tax_rate') or 13)
    invoice_date = (data.get('invoice_date') or '').strip() or today_str()

    if not invoice_no:
        return fail('发票号不能为空')
    if invoice_type not in ('进项', '销项'):
        return fail('发票类型不正确')
    if partner_type not in ('customer', 'supplier'):
        return fail('对方类型不正确')
    if not partner_id:
        return fail('请选择对方')
    if amount <= 0:
        return fail('不含税金额必须大于 0')

    # 自动算税额
    tax_amount = round(amount * tax_rate / 100)
    total_amount = amount + tax_amount

    db = get_db()
    partner_name = ''
    if partner_type == 'customer':
        p = db.execute("SELECT name FROM customers WHERE id=?", (partner_id,)).fetchone()
        partner_name = p['name'] if p else ''
    else:
        p = db.execute("SELECT name FROM suppliers WHERE id=?", (partner_id,)).fetchone()
        partner_name = p['name'] if p else ''

    cur = db.execute(
        "INSERT INTO invoices (invoice_no, invoice_code, invoice_type, partner_type, partner_id, "
        "partner_name, amount, tax_rate, tax_amount, total_amount, invoice_date, status, "
        "related_order, remark, created_by, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (invoice_no, (data.get('invoice_code') or '').strip(), invoice_type,
         partner_type, partner_id, partner_name, amount, tax_rate, tax_amount, total_amount,
         invoice_date, (data.get('status') or '已开').strip(),
         (data.get('related_order') or '').strip(), (data.get('remark') or '').strip(),
         session.get('real_name') or session.get('username') or '', now_str())
    )
    db.commit()
    log_op('新增', '发票', '%s %s' % (invoice_type, invoice_no))
    return ok({'id': cur.lastrowid}, '发票登记成功')


@bp.route('/invoices/<int:iid>', methods=['PUT'])
@login_required
def api_update(iid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM invoices WHERE id=?", (iid,)).fetchone()
    if not row:
        return fail('发票不存在')

    amount = yuan_to_fen(data.get('amount', fen_to_yuan(row['amount'])))
    tax_rate = float(data.get('tax_rate') or row['tax_rate'] or 13)
    tax_amount = round(amount * tax_rate / 100)
    total_amount = amount + tax_amount

    db.execute(
        "UPDATE invoices SET invoice_no=?, invoice_code=?, amount=?, tax_rate=?, tax_amount=?, "
        "total_amount=?, invoice_date=?, status=?, related_order=?, remark=? WHERE id=?",
        ((data.get('invoice_no') or row['invoice_no']).strip(),
         (data.get('invoice_code') or '').strip(),
         amount, tax_rate, tax_amount, total_amount,
         (data.get('invoice_date') or row['invoice_date']).strip(),
         (data.get('status') or row['status']).strip(),
         (data.get('related_order') or '').strip(),
         (data.get('remark') or '').strip(), iid)
    )
    db.commit()
    log_op('修改', '发票', row['invoice_no'])
    return ok(msg='修改成功')


@bp.route('/invoices/<int:iid>', methods=['DELETE'])
@login_required
@admin_required
def api_delete(iid):
    db = get_db()
    row = db.execute("SELECT * FROM invoices WHERE id=?", (iid,)).fetchone()
    if not row:
        return fail('发票不存在')
    db.execute("DELETE FROM invoices WHERE id=?", (iid,))
    db.commit()
    log_op('删除', '发票', row['invoice_no'])
    return ok(msg='删除成功')


@bp.route('/invoices/stats')
@login_required
def api_stats():
    """发票统计：按月汇总进项/销项税额"""
    db = get_db()
    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()

    where = " WHERE status != '已作废'"
    params = []
    if start:
        where += " AND invoice_date >= ?"
        params.append(start)
    if end:
        where += " AND invoice_date <= ?"
        params.append(end)

    out = db.execute(
        "SELECT IFNULL(SUM(amount),0) AS amt, IFNULL(SUM(tax_amount),0) AS tax, "
        "IFNULL(SUM(total_amount),0) AS total FROM invoices "
        + where + " AND invoice_type='销项'", params
    ).fetchone()
    inp = db.execute(
        "SELECT IFNULL(SUM(amount),0) AS amt, IFNULL(SUM(tax_amount),0) AS tax, "
        "IFNULL(SUM(total_amount),0) AS total FROM invoices "
        + where + " AND invoice_type='进项'", params
    ).fetchone()

    return ok({
        'output': {'amount': out['amt'], 'tax': out['tax'], 'total': out['total']},
        'input':  {'amount': inp['amt'], 'tax': inp['tax'], 'total': inp['total']},
        'diff_tax': (out['tax'] or 0) - (inp['tax'] or 0)
    })