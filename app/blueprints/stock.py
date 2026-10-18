# -*- coding: utf-8 -*-
from flask import Blueprint, request
from ..models import (get_db, to_int, atomic_deduct_stock,
                      atomic_add_stock, log_stock)
from ..security import login_required
from ..utils import ok, fail

bp = Blueprint('stock', __name__)


@bp.route('/stock_logs')
@login_required
def api_stock_logs():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    change_type = (request.args.get('change_type') or '').strip()
    sql = ("SELECT s.*, p.name AS product_name, p.code AS product_code, w.name AS warehouse_name "
           "FROM stock_logs s LEFT JOIN products p ON p.id=s.product_id "
           "LEFT JOIN warehouses w ON w.id=s.warehouse_id WHERE 1=1")
    params = []
    if keyword:
        sql += " AND (p.name LIKE ? OR p.code LIKE ? OR s.ref_no LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like, like])
    if change_type:
        sql += " AND s.change_type=?"
        params.append(change_type)
    sql += " ORDER BY s.id DESC LIMIT 500"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/stock/adjust', methods=['POST'])
@login_required
def api_stock_adjust():
    data = request.get_json(silent=True) or {}
    pid = to_int(data.get('product_id'))
    wid = to_int(data.get('warehouse_id'))
    qty = to_int(data.get('qty'), 0)
    if not pid or not wid:
        return fail('请选择商品和仓库')
    if qty == 0:
        return fail('调整数量不能为 0')

    db = get_db()
    if qty > 0:
        atomic_add_stock(db, pid, wid, qty)
    else:
        if not atomic_deduct_stock(db, pid, wid, -qty):
            return fail('库存不足')

    log_stock(db, pid, wid, '库存调整', qty, 'ADJUST',
              (data.get('remark') or '手工调整'))
    db.commit()
    return ok(msg='调整成功')


@bp.route('/replenish_suggest')
@login_required
def api_replenish_suggest():
    db = get_db()
    from datetime import datetime, timedelta
    since = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    rows = db.execute(
        "SELECT p.id, p.code, p.name, p.stock, p.safety_stock, p.cost_price, "
        "IFNULL((SELECT SUM(i.qty) FROM sales_order_items i JOIN sales_orders o ON o.id=i.order_id "
        "        WHERE i.product_id=p.id AND o.status='已出库' AND o.order_date>=?), 0) AS sold30 "
        "FROM products p WHERE p.status=1 ORDER BY p.id", (since,)
    ).fetchall()
    result = []
    for r in rows:
        avg_daily = (r['sold30'] or 0) / 30.0
        suggest = max(round(avg_daily * 30 + (r['safety_stock'] or 0) - (r['stock'] or 0)), 0)
        if suggest > 0:
            result.append({
                'id': r['id'], 'code': r['code'], 'name': r['name'],
                'stock': r['stock'], 'safety_stock': r['safety_stock'],
                'sold30': r['sold30'], 'avg_daily': round(avg_daily, 2),
                'suggest_qty': suggest,
                'est_amount': suggest * (r['cost_price'] or 0)
            })
    return ok(result)


@bp.route('/supplier_compare/<int:pid>')
@login_required
def api_supplier_compare(pid):
    db = get_db()
    rows = db.execute(
        "SELECT s.id AS supplier_id, s.name AS supplier_name, i.price, o.order_date "
        "FROM purchase_order_items i JOIN purchase_orders o ON o.id=i.order_id "
        "JOIN suppliers s ON s.id=o.supplier_id WHERE i.product_id=? AND o.status='已入库' "
        "ORDER BY o.order_date DESC", (pid,)
    ).fetchall()
    seen = {}
    for r in rows:
        if r['supplier_id'] not in seen:
            seen[r['supplier_id']] = dict(r)
    return ok(list(seen.values()))