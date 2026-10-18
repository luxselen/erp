# -*- coding: utf-8 -*-
from flask import Blueprint, request, session
from datetime import datetime, timedelta
from ..models import (get_db, now_str, today_str, to_int, yuan_to_fen, gen_no,
                      atomic_add_stock, log_stock, update_weighted_cost, log_op)
from ..security import login_required
from ..utils import ok, fail

bp = Blueprint('purchase', __name__)


@bp.route('/purchase_orders')
@login_required
def api_po_list():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    status = (request.args.get('status') or '').strip()
    sql = ("SELECT o.*, s.name AS supplier_name, w.name AS warehouse_name "
           "FROM purchase_orders o LEFT JOIN suppliers s ON s.id=o.supplier_id "
           "LEFT JOIN warehouses w ON w.id=o.warehouse_id WHERE 1=1")
    params = []
    if keyword:
        sql += " AND (o.order_no LIKE ? OR s.name LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like])
    if status:
        sql += " AND o.status=?"
        params.append(status)
    sql += " ORDER BY o.id DESC LIMIT 300"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/purchase_orders/<int:oid>')
@login_required
def api_po_detail(oid):
    db = get_db()
    order = db.execute(
        "SELECT o.*, s.name AS supplier_name, s.contact, s.phone, w.name AS warehouse_name "
        "FROM purchase_orders o LEFT JOIN suppliers s ON s.id=o.supplier_id "
        "LEFT JOIN warehouses w ON w.id=o.warehouse_id WHERE o.id=?", (oid,)
    ).fetchone()
    if not order:
        return fail('订单不存在')
    items = db.execute(
        "SELECT i.*, p.code AS product_code, p.name AS product_name, p.unit "
        "FROM purchase_order_items i LEFT JOIN products p ON p.id=i.product_id WHERE i.order_id=?", (oid,)
    ).fetchall()
    data = dict(order)
    data['items'] = [dict(r) for r in items]
    return ok(data)


@bp.route('/purchase_orders', methods=['POST'])
@login_required
def api_po_create():
    data = request.get_json(silent=True) or {}
    supplier_id = to_int(data.get('supplier_id'))
    warehouse_id = to_int(data.get('warehouse_id'))
    items_raw = data.get('items') or []

    if not supplier_id:
        return fail('请选择供应商')
    if not warehouse_id:
        return fail('请选择入库仓库')
    if not items_raw:
        return fail('请添加商品明细')

    db = get_db()
    if not db.execute("SELECT id FROM suppliers WHERE id=?", (supplier_id,)).fetchone():
        return fail('供应商不存在')

    total = 0
    norm = []
    for it in items_raw:
        pid = to_int(it.get('product_id'))
        qty = to_int(it.get('qty'), 0)
        price = yuan_to_fen(it.get('price', 0))
        if not pid or qty <= 0:
            return fail('商品明细不合法')
        if not db.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone():
            return fail('商品不存在')
        amt = price * qty
        total += amt
        norm.append((pid, price, qty, amt,
                     (it.get('batch_no') or '').strip(),
                     (it.get('expire_date') or '').strip()))

    discount = yuan_to_fen(data.get('discount', 0))
    final_amount = max(total - discount, 0)
    order_no = gen_no(db, 'PO', 'purchase_orders')

    cur = db.execute(
        "INSERT INTO purchase_orders (order_no,supplier_id,warehouse_id,order_date,total_amount,"
        "discount,final_amount,status,remark,created_by,created_at) "
        "VALUES (?,?,?,?,?,?,?,'待确认',?,?,?)",
        (order_no, supplier_id, warehouse_id,
         (data.get('order_date') or '').strip() or today_str(),
         total, discount, final_amount,
         (data.get('remark') or '').strip(),
         session.get('real_name') or session.get('username') or '', now_str())
    )
    oid = cur.lastrowid
    for pid, price, qty, amt, batch_no, expire_date in norm:
        db.execute("INSERT INTO purchase_order_items (order_id,product_id,price,qty,amount,batch_no,expire_date) "
                   "VALUES (?,?,?,?,?,?,?)", (oid, pid, price, qty, amt, batch_no, expire_date))
    db.commit()
    return ok({'id': oid, 'order_no': order_no}, '采购订单创建成功')


@bp.route('/purchase_orders/<int:oid>/confirm', methods=['POST'])
@login_required
def api_po_confirm(oid):
    db = get_db()
    order = db.execute("SELECT * FROM purchase_orders WHERE id=?", (oid,)).fetchone()
    if not order:
        return fail('订单不存在')
    if order['status'] != '待确认':
        return fail('当前状态无法入库')

    items = db.execute("SELECT * FROM purchase_order_items WHERE order_id=?", (oid,)).fetchall()
    if not items:
        return fail('订单没有明细')

    for it in items:
        atomic_add_stock(db, it['product_id'], order['warehouse_id'], it['qty'])
        log_stock(db, it['product_id'], order['warehouse_id'],
                  '采购入库', it['qty'], order['order_no'], '')
        update_weighted_cost(db, it['product_id'], it['qty'], it['price'])
        db.execute("UPDATE products SET purchase_price=? WHERE id=?", (it['price'], it['product_id']))

    db.execute("UPDATE purchase_orders SET status='已入库' WHERE id=?", (oid,))

    due = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    db.execute(
        "INSERT INTO payables (order_id,order_no,supplier_id,amount,paid,status,due_date,created_at) "
        "VALUES (?,?,?,?,0,'未付',?,?)",
        (oid, order['order_no'], order['supplier_id'], order['final_amount'], due, now_str())
    )
    db.commit()
    log_op('入库', '采购订单', '订单号：' + order['order_no'])
    return ok(msg='入库成功')


@bp.route('/purchase_orders/<int:oid>/cancel', methods=['POST'])
@login_required
def api_po_cancel(oid):
    db = get_db()
    order = db.execute("SELECT * FROM purchase_orders WHERE id=?", (oid,)).fetchone()
    if not order:
        return fail('订单不存在')
    if order['status'] == '已取消':
        return fail('订单已是取消状态')
    if order['status'] == '已入库':
        pay = db.execute("SELECT * FROM payables WHERE order_id=?", (oid,)).fetchone()
        if pay and (pay['paid'] or 0) > 0:
            return fail('该订单已有付款记录')
        items = db.execute("SELECT * FROM purchase_order_items WHERE order_id=?", (oid,)).fetchall()
        for it in items:
            p = db.execute("SELECT stock, name FROM products WHERE id=?", (it['product_id'],)).fetchone()
            if p and (p['stock'] or 0) < it['qty']:
                return fail('商品【%s】库存不足，无法退回' % p['name'])
        for it in items:
            from ..models import atomic_deduct_stock
            atomic_deduct_stock(db, it['product_id'], order['warehouse_id'], it['qty'])
            log_stock(db, it['product_id'], order['warehouse_id'],
                      '采购退回', -it['qty'], order['order_no'], '取消订单')
        db.execute("DELETE FROM payables WHERE order_id=?", (oid,))
    db.execute("UPDATE purchase_orders SET status='已取消' WHERE id=?", (oid,))
    db.commit()
    return ok(msg='订单已取消')


@bp.route('/purchase_orders/<int:oid>', methods=['DELETE'])
@login_required
def api_po_delete(oid):
    db = get_db()
    order = db.execute("SELECT * FROM purchase_orders WHERE id=?", (oid,)).fetchone()
    if not order:
        return fail('订单不存在')
    if order['status'] == '已入库':
        return fail('已入库订单不可删除')
    db.execute("DELETE FROM purchase_order_items WHERE order_id=?", (oid,))
    db.execute("DELETE FROM purchase_orders WHERE id=?", (oid,))
    db.commit()
    return ok(msg='删除成功')