# -*- coding: utf-8 -*-
from flask import Blueprint, request, session
from datetime import datetime, timedelta
from ..models import (get_db, now_str, today_str, to_int, yuan_to_fen, fen_to_yuan,
                      gen_no, atomic_deduct_stock, atomic_add_stock, log_stock, log_op)
from ..security import login_required
from ..utils import ok, fail

bp = Blueprint('sales', __name__)


@bp.route('/sales_orders')
@login_required
def api_so_list():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    status = (request.args.get('status') or '').strip()
    sql = ("SELECT o.*, c.name AS customer_name, w.name AS warehouse_name "
           "FROM sales_orders o LEFT JOIN customers c ON c.id=o.customer_id "
           "LEFT JOIN warehouses w ON w.id=o.warehouse_id WHERE 1=1")
    params = []
    if keyword:
        sql += " AND (o.order_no LIKE ? OR c.name LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like])
    if status:
        sql += " AND o.status=?"
        params.append(status)
    sql += " ORDER BY o.id DESC LIMIT 300"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/sales_orders/<int:oid>')
@login_required
def api_so_detail(oid):
    db = get_db()
    order = db.execute(
        "SELECT o.*, c.name AS customer_name, c.contact, c.phone, w.name AS warehouse_name "
        "FROM sales_orders o LEFT JOIN customers c ON c.id=o.customer_id "
        "LEFT JOIN warehouses w ON w.id=o.warehouse_id WHERE o.id=?", (oid,)
    ).fetchone()
    if not order:
        return fail('订单不存在')
    items = db.execute(
        "SELECT i.*, p.code AS product_code, p.name AS product_name, p.unit "
        "FROM sales_order_items i LEFT JOIN products p ON p.id=i.product_id WHERE i.order_id=?", (oid,)
    ).fetchall()
    data = dict(order)
    data['items'] = [dict(r) for r in items]
    return ok(data)


@bp.route('/sales_orders', methods=['POST'])
@login_required
def api_so_create():
    data = request.get_json(silent=True) or {}
    customer_id = to_int(data.get('customer_id'))
    warehouse_id = to_int(data.get('warehouse_id'))
    items_raw = data.get('items') or []

    if not customer_id:
        return fail('请选择客户')
    if not warehouse_id:
        return fail('请选择出库仓库')
    if not items_raw:
        return fail('请添加商品明细')

    db = get_db()
    cust = db.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not cust:
        return fail('客户不存在')

    total = 0
    norm = []
    for it in items_raw:
        pid = to_int(it.get('product_id'))
        qty = to_int(it.get('qty'), 0)
        price = yuan_to_fen(it.get('price', 0))
        if not pid or qty <= 0:
            return fail('商品明细不合法')
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            return fail('商品不存在')
        amt = price * qty
        total += amt
        norm.append((pid, price, qty, amt, p['cost_price'] or 0))

    discount = yuan_to_fen(data.get('discount', 0))
    final_amount = max(total - discount, 0)

    # 信用额度校验
    if cust['credit_limit'] and cust['credit_limit'] > 0:
        ar_bal = db.execute(
            "SELECT IFNULL(SUM(amount - received),0) AS v FROM receivables "
            "WHERE customer_id=? AND status!='已收完'", (customer_id,)
        ).fetchone()['v'] or 0
        if ar_bal + final_amount > cust['credit_limit'] and data.get('force') != 1:
            return fail(
                '超过信用额度（余额 ¥%s + 本单 ¥%s > 额度 ¥%s）' % (
                    fen_to_yuan(ar_bal), fen_to_yuan(final_amount),
                    fen_to_yuan(cust['credit_limit'])
                ),
                2
            )

    order_no = gen_no(db, 'SO', 'sales_orders')
    order_date = (data.get('order_date') or '').strip() or today_str()

    cur = db.execute(
        "INSERT INTO sales_orders (order_no,customer_id,warehouse_id,order_date,total_amount,"
        "discount,final_amount,total_cost,gross_profit,status,remark,created_by,created_at) "
        "VALUES (?,?,?,?,?,?,?,0,0,'待确认',?,?,?)",
        (order_no, customer_id, warehouse_id, order_date, total, discount, final_amount,
         (data.get('remark') or '').strip(),
         session.get('real_name') or session.get('username') or '', now_str())
    )
    oid = cur.lastrowid
    for pid, price, qty, amt, cost in norm:
        db.execute("INSERT INTO sales_order_items (order_id,product_id,price,cost_price,qty,amount) "
                   "VALUES (?,?,?,?,?,?)", (oid, pid, price, cost, qty, amt))
    db.commit()
    return ok({'id': oid, 'order_no': order_no}, '订单创建成功')


@bp.route('/sales_orders/<int:oid>/confirm', methods=['POST'])
@login_required
def api_so_confirm(oid):
    db = get_db()
    order = db.execute("SELECT * FROM sales_orders WHERE id=?", (oid,)).fetchone()
    if not order:
        return fail('订单不存在')
    if order['status'] != '待确认':
        return fail('当前状态为「%s」，无法出库' % order['status'])

    items = db.execute("SELECT * FROM sales_order_items WHERE order_id=?", (oid,)).fetchall()
    if not items:
        return fail('订单没有明细')

    for it in items:
        if not atomic_deduct_stock(db, it['product_id'], order['warehouse_id'], it['qty']):
            p = db.execute("SELECT name FROM products WHERE id=?", (it['product_id'],)).fetchone()
            db.rollback()
            return fail('商品【%s】库存不足' % (p['name'] if p else it['product_id']))
        log_stock(db, it['product_id'], order['warehouse_id'],
                  '销售出库', -it['qty'], order['order_no'], '')

    total_cost = sum((it['cost_price'] or 0) * it['qty'] for it in items)
    gross = (order['total_amount'] or 0) - total_cost

    db.execute("UPDATE sales_orders SET status='已出库', total_cost=?, gross_profit=? WHERE id=?",
               (total_cost, gross, oid))

    due = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    db.execute(
        "INSERT INTO receivables (order_id,order_no,customer_id,amount,received,status,due_date,created_at) "
        "VALUES (?,?,?,?,0,'未收',?,?)",
        (oid, order['order_no'], order['customer_id'], order['final_amount'], due, now_str())
    )

    total_sales = db.execute(
        "SELECT IFNULL(SUM(final_amount),0) AS s FROM sales_orders WHERE customer_id=? AND status='已出库'",
        (order['customer_id'],)
    ).fetchone()['s'] or 0
    level = '普通'
    if total_sales >= 10000000:
        level = '钻石'
    elif total_sales >= 5000000:
        level = '金牌'
    elif total_sales >= 1000000:
        level = '银牌'
    db.execute("UPDATE customers SET level=? WHERE id=?", (level, order['customer_id']))

    db.commit()
    log_op('出库', '销售订单', '订单号：' + order['order_no'])
    return ok(msg='出库成功')


@bp.route('/sales_orders/<int:oid>/cancel', methods=['POST'])
@login_required
def api_so_cancel(oid):
    db = get_db()
    order = db.execute("SELECT * FROM sales_orders WHERE id=?", (oid,)).fetchone()
    if not order:
        return fail('订单不存在')
    if order['status'] == '已取消':
        return fail('订单已是取消状态')
    if order['status'] == '已出库':
        rec = db.execute("SELECT * FROM receivables WHERE order_id=?", (oid,)).fetchone()
        if rec and (rec['received'] or 0) > 0:
            return fail('该订单已有回款记录')
        items = db.execute("SELECT * FROM sales_order_items WHERE order_id=?", (oid,)).fetchall()
        for it in items:
            atomic_add_stock(db, it['product_id'], order['warehouse_id'], it['qty'])
            log_stock(db, it['product_id'], order['warehouse_id'],
                      '销售退回', it['qty'], order['order_no'], '取消订单')
        db.execute("DELETE FROM receivables WHERE order_id=?", (oid,))
    db.execute("UPDATE sales_orders SET status='已取消' WHERE id=?", (oid,))
    db.commit()
    return ok(msg='订单已取消')


@bp.route('/sales_orders/<int:oid>', methods=['DELETE'])
@login_required
def api_so_delete(oid):
    db = get_db()
    order = db.execute("SELECT * FROM sales_orders WHERE id=?", (oid,)).fetchone()
    if not order:
        return fail('订单不存在')
    if order['status'] == '已出库':
        return fail('已出库订单不可删除')
    db.execute("DELETE FROM sales_order_items WHERE order_id=?", (oid,))
    db.execute("DELETE FROM sales_orders WHERE id=?", (oid,))
    db.commit()
    return ok(msg='删除成功')