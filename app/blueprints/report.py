# -*- coding: utf-8 -*-
"""工作台 / 利润分析 / 操作日志"""
from flask import Blueprint, request, Response
from datetime import datetime, timedelta
from ..models import get_db
from ..security import login_required, admin_required
from ..utils import ok, fail

bp = Blueprint('report', __name__)


@bp.route('/dashboard')
@login_required
def api_dashboard():
    """角色化工作台数据（数据收集见 collect_dashboard_data，供 AI 摘要复用）"""
    return ok(collect_dashboard_data())


def collect_dashboard_data():
    """收集工作台全部数据（KPI/待办/明细/趋势），前端与 AI 摘要共用"""
    from flask import session
    db = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    month = datetime.now().strftime('%Y-%m')
    role = session.get('role', 'staff')

    # ---- 核心 KPI ----
    today_row = db.execute(
        "SELECT IFNULL(SUM(final_amount),0) AS s, COUNT(*) AS c "
        "FROM sales_orders WHERE status!='已取消' AND order_date=?", (today,)
    ).fetchone()
    month_row = db.execute(
        "SELECT COUNT(*) AS c, IFNULL(SUM(final_amount),0) AS s, IFNULL(SUM(gross_profit),0) AS g "
        "FROM sales_orders WHERE status!='已取消' AND substr(order_date,1,7)=?", (month,)
    ).fetchone()
    rec_row = db.execute(
        "SELECT IFNULL(SUM(amount),0) AS v FROM receipts WHERE substr(receipt_date,1,7)=?", (month,)
    ).fetchone()
    pay_row = db.execute(
        "SELECT IFNULL(SUM(amount),0) AS v FROM payments WHERE substr(payment_date,1,7)=?", (month,)
    ).fetchone()
    ar = db.execute(
        "SELECT IFNULL(SUM(amount - received),0) AS v FROM receivables WHERE status!='已收完'"
    ).fetchone()['v'] or 0
    ap = db.execute(
        "SELECT IFNULL(SUM(amount - paid),0) AS v FROM payables WHERE status!='已付完'"
    ).fetchone()['v'] or 0
    fund_total = db.execute(
        "SELECT IFNULL(SUM(balance),0) AS v FROM fund_accounts WHERE status=1"
    ).fetchone()['v'] or 0

    # ---- 待办计数 ----
    low_stock_count = db.execute(
        "SELECT COUNT(*) AS c FROM products WHERE status=1 AND stock<=safety_stock"
    ).fetchone()['c']
    pending_sales_count = db.execute(
        "SELECT COUNT(*) AS c FROM sales_orders WHERE status='待确认'"
    ).fetchone()['c']
    pending_purchase_count = db.execute(
        "SELECT COUNT(*) AS c FROM purchase_orders WHERE status='待确认'"
    ).fetchone()['c']
    overdue_ar_row = db.execute(
        "SELECT COUNT(*) AS c, IFNULL(SUM(amount-received),0) AS v FROM receivables "
        "WHERE status!='已收完' AND amount>received AND due_date<?", (today,)
    ).fetchone()
    overdue_ap_row = db.execute(
        "SELECT COUNT(*) AS c, IFNULL(SUM(amount-paid),0) AS v FROM payables "
        "WHERE status!='已付完' AND amount>paid AND due_date<?", (today,)
    ).fetchone()

    # ---- 明细列表 ----
    low_stock = db.execute(
        "SELECT id, code, name, stock, safety_stock, unit FROM products "
        "WHERE status=1 AND stock<=safety_stock "
        "ORDER BY (stock - safety_stock) ASC LIMIT 10"
    ).fetchall()

    overdue_receivables = db.execute(
        "SELECT r.order_no, c.name AS customer_name, r.amount, r.received, r.due_date "
        "FROM receivables r LEFT JOIN customers c ON c.id=r.customer_id "
        "WHERE r.status!='已收完' AND r.amount>r.received AND r.due_date<? "
        "ORDER BY r.due_date ASC LIMIT 8", (today,)
    ).fetchall()
    today_dt = datetime.now().date()
    overdue_ar_list = []
    for r in overdue_receivables:
        try:
            days = (today_dt - datetime.strptime(r['due_date'], '%Y-%m-%d').date()).days
        except Exception:
            days = 0
        overdue_ar_list.append({
            'order_no': r['order_no'], 'customer_name': r['customer_name'] or '-',
            'amount': r['amount'] or 0, 'received': r['received'] or 0,
            'balance': (r['amount'] or 0) - (r['received'] or 0),
            'due_date': r['due_date'], 'days': days
        })

    pending_sales = db.execute(
        "SELECT o.id, o.order_no, o.order_date, o.final_amount, c.name AS customer_name "
        "FROM sales_orders o LEFT JOIN customers c ON c.id=o.customer_id "
        "WHERE o.status='待确认' ORDER BY o.id DESC LIMIT 6"
    ).fetchall()
    pending_purchase = db.execute(
        "SELECT o.id, o.order_no, o.order_date, o.final_amount, s.name AS supplier_name "
        "FROM purchase_orders o LEFT JOIN suppliers s ON s.id=o.supplier_id "
        "WHERE o.status='待确认' ORDER BY o.id DESC LIMIT 6"
    ).fetchall()

    recent_orders = db.execute(
        "SELECT o.id, o.order_no, o.order_date, o.final_amount, o.status, c.name AS customer_name "
        "FROM sales_orders o LEFT JOIN customers c ON c.id=o.customer_id "
        "ORDER BY o.id DESC LIMIT 8"
    ).fetchall()

    recent_fund_logs = db.execute(
        "SELECT f.change_type, f.amount, f.ref_no, f.created_at, a.name AS account_name "
        "FROM fund_logs f LEFT JOIN fund_accounts a ON a.id=f.account_id "
        "ORDER BY f.id DESC LIMIT 6"
    ).fetchall()

    # ---- 近 6 月销售趋势 ----
    months = []
    now = datetime.now()
    for i in range(5, -1, -1):
        d = now.replace(day=1) - timedelta(days=30 * i)
        months.append(d.strftime('%Y-%m'))
    trend_rows = db.execute(
        "SELECT substr(order_date,1,7) AS m, IFNULL(SUM(final_amount),0) AS s, "
        "IFNULL(SUM(gross_profit),0) AS g FROM sales_orders "
        "WHERE status!='已取消' AND order_date>=? GROUP BY m ORDER BY m",
        (months[0] + '-01',)
    ).fetchall()
    trend_map = {r['m']: {'sales': r['s'] or 0, 'profit': r['g'] or 0} for r in trend_rows}
    trend = [{'month': m, 'sales': (trend_map.get(m) or {}).get('sales', 0),
              'profit': (trend_map.get(m) or {}).get('profit', 0)} for m in months]

    return {
        'role': role,
        'kpi': {
            'today_sales': today_row['s'] or 0,
            'today_order_count': today_row['c'] or 0,
            'month_order_count': month_row['c'] or 0,
            'month_sales_amount': month_row['s'] or 0,
            'month_gross_profit': month_row['g'] or 0,
            'month_receipt': rec_row['v'] or 0,
            'month_payment': pay_row['v'] or 0,
            'ar_balance': ar,
            'ap_balance': ap,
            'fund_total': fund_total,
        },
        'alerts': {
            'low_stock_count': low_stock_count,
            'pending_sales_count': pending_sales_count,
            'pending_purchase_count': pending_purchase_count,
            'overdue_ar_count': overdue_ar_row['c'] or 0,
            'overdue_ar_amount': overdue_ar_row['v'] or 0,
            'overdue_ap_count': overdue_ap_row['c'] or 0,
            'overdue_ap_amount': overdue_ap_row['v'] or 0,
            'follow_up_count': db.execute(
                "SELECT COUNT(*) AS c FROM customers WHERE remark LIKE '最近跟进：%'"
            ).fetchone()['c'] or 0,
        },
        'low_stock': [dict(r) for r in low_stock],
        'overdue_receivables': overdue_ar_list,
        'pending_sales': [dict(r) for r in pending_sales],
        'pending_purchase': [dict(r) for r in pending_purchase],
        'recent_orders': [dict(r) for r in recent_orders],
        'recent_fund_logs': [dict(r) for r in recent_fund_logs],
        'trend': trend,
    }


@bp.route('/profit_report')
@login_required
def api_profit_report():
    db = get_db()
    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()
    dim = (request.args.get('dim') or 'product').strip()

    where = " WHERE o.status='已出库'"
    params = []
    if start:
        where += " AND o.order_date >= ?"
        params.append(start)
    if end:
        where += " AND o.order_date <= ?"
        params.append(end)

    if dim == 'product':
        sql = ("SELECT p.id, p.code AS code, p.name AS name, "
               "SUM(i.qty) AS qty, SUM(i.amount) AS sales_amount, "
               "SUM(i.cost_price * i.qty) AS cost_amount, "
               "SUM(i.amount - i.cost_price * i.qty) AS gross_profit "
               "FROM sales_order_items i JOIN sales_orders o ON o.id=i.order_id "
               "JOIN products p ON p.id=i.product_id " + where +
               " GROUP BY p.id ORDER BY gross_profit DESC")
    elif dim == 'customer':
        sql = ("SELECT c.id, c.code AS code, c.name AS name, "
               "SUM(i.qty) AS qty, SUM(i.amount) AS sales_amount, "
               "SUM(i.cost_price * i.qty) AS cost_amount, "
               "SUM(i.amount - i.cost_price * i.qty) AS gross_profit "
               "FROM sales_order_items i JOIN sales_orders o ON o.id=i.order_id "
               "JOIN customers c ON c.id=o.customer_id " + where +
               " GROUP BY c.id ORDER BY gross_profit DESC")
    else:
        sql = ("SELECT IFNULL(c.id,0) AS id, '' AS code, IFNULL(c.name,'未分类') AS name, "
               "SUM(i.qty) AS qty, SUM(i.amount) AS sales_amount, "
               "SUM(i.cost_price * i.qty) AS cost_amount, "
               "SUM(i.amount - i.cost_price * i.qty) AS gross_profit "
               "FROM sales_order_items i JOIN sales_orders o ON o.id=i.order_id "
               "JOIN products p ON p.id=i.product_id LEFT JOIN categories c ON c.id=p.category_id "
               + where + " GROUP BY c.id ORDER BY gross_profit DESC")

    rows = db.execute(sql, params).fetchall()
    result = []
    for r in rows:
        sales = r['sales_amount'] or 0
        cost = r['cost_amount'] or 0
        gp = r['gross_profit'] or 0
        rate = round(gp / sales * 100, 2) if sales > 0 else 0
        result.append({
            'id': r['id'], 'code': r['code'], 'name': r['name'],
            'qty': r['qty'] or 0,
            'sales_amount': sales, 'cost_amount': cost,
            'gross_profit': gp, 'gross_rate': rate
        })
    total_sales = sum(x['sales_amount'] for x in result)
    total_cost = sum(x['cost_amount'] for x in result)
    total_gp = sum(x['gross_profit'] for x in result)
    return ok({
        'details': result,
        'summary': {
            'sales_amount': total_sales,
            'cost_amount': total_cost,
            'gross_profit': total_gp,
            'gross_rate': round(total_gp / total_sales * 100, 2) if total_sales > 0 else 0
        }
    })


@bp.route('/operation_logs')
@login_required
@admin_required
def api_op_logs():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    sql = "SELECT * FROM operation_logs WHERE 1=1"
    params = []
    if keyword:
        sql += " AND (username LIKE ? OR module LIKE ? OR action LIKE ? OR detail LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like, like, like])
    sql += " ORDER BY id DESC LIMIT 500"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


# ============================================================
# 通用 CSV 导出（前端 7 个页面"导出CSV"按钮调用）
# ============================================================
@bp.route('/export/<kind>')
@login_required
def api_export_csv(kind):
    db = get_db()

    def csv_cell(v):
        s = '' if v is None else str(v)
        if any(c in s for c in (',', '"', '\n', '\r')):
            return '"' + s.replace('"', '""') + '"'
        return s

    def yuan(v):
        try:
            return '%.2f' % ((v or 0) / 100.0)
        except Exception:
            return '0.00'

    specs = {
        'products': (
            '编码,名称,分类,单位,进价(元),售价(元),成本价(元),库存,安全库存,备注',
            "SELECT p.code,p.name,IFNULL(c.name,''),p.unit,p.purchase_price,p.sale_price,"
            "p.cost_price,p.stock,p.safety_stock,IFNULL(p.remark,'') FROM products p "
            "LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.id",
            lambda r: [r[0], r[1], r[2], r[3], yuan(r[4]), yuan(r[5]), yuan(r[6]), r[7], r[8], r[9]]),
        'customers': (
            '编码,名称,联系人,电话,地址,信用额度(元),备注',
            "SELECT code,name,IFNULL(contact,''),IFNULL(phone,''),IFNULL(address,''),"
            "credit_limit,IFNULL(remark,'') FROM customers ORDER BY id",
            lambda r: [r[0], r[1], r[2], r[3], r[4], yuan(r[5]), r[6]]),
        'suppliers': (
            '编码,名称,联系人,电话,地址,备注',
            "SELECT code,name,IFNULL(contact,''),IFNULL(phone,''),IFNULL(address,''),"
            "IFNULL(remark,'') FROM suppliers ORDER BY id",
            lambda r: [r[0], r[1], r[2], r[3], r[4], r[5]]),
        'sales_orders': (
            '订单号,客户,日期,总额(元),优惠(元),实收(元),毛利(元),状态',
            "SELECT o.order_no,IFNULL(c.name,''),o.order_date,o.total_amount,o.discount,"
            "o.final_amount,o.gross_profit,o.status FROM sales_orders o "
            "LEFT JOIN customers c ON c.id=o.customer_id ORDER BY o.id DESC",
            lambda r: [r[0], r[1], r[2], yuan(r[3]), yuan(r[4]), yuan(r[5]), yuan(r[6]), r[7]]),
        'purchase_orders': (
            '订单号,供应商,日期,总额(元),实收(元),状态',
            "SELECT o.order_no,IFNULL(s.name,''),o.order_date,o.total_amount,o.final_amount,"
            "o.status FROM purchase_orders o LEFT JOIN suppliers s ON s.id=o.supplier_id "
            "ORDER BY o.id DESC",
            lambda r: [r[0], r[1], r[2], yuan(r[3]), yuan(r[4]), r[5]]),
        'receivables': (
            '订单号,客户,应收(元),已收(元),余额(元),到期日,状态',
            "SELECT r.order_no,IFNULL(c.name,''),r.amount,r.received,r.amount-r.received,"
            "r.due_date,r.status FROM receivables r LEFT JOIN customers c ON c.id=r.customer_id "
            "ORDER BY r.id DESC",
            lambda r: [r[0], r[1], yuan(r[2]), yuan(r[3]), yuan(r[4]), r[5], r[6]]),
        'payables': (
            '订单号,供应商,应付(元),已付(元),余额(元),到期日,状态',
            "SELECT p.order_no,IFNULL(s.name,''),p.amount,p.paid,p.amount-p.paid,"
            "p.due_date,p.status FROM payables p LEFT JOIN suppliers s ON s.id=p.supplier_id "
            "ORDER BY p.id DESC",
            lambda r: [r[0], r[1], yuan(r[2]), yuan(r[3]), yuan(r[4]), r[5], r[6]]),
    }
    if kind not in specs:
        return fail('不支持的导出类型')
    header, sql, mapper = specs[kind]
    rows = db.execute(sql).fetchall()
    lines = [header] + [','.join(csv_cell(x) for x in mapper(r)) for r in rows]
    content = '\ufeff' + '\n'.join(lines)   # BOM：Excel 直接打开不乱码
    fname = kind + '_' + datetime.now().strftime('%Y%m%d') + '.csv'
    return Response(content, mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename=%s' % fname})


# ============================================================
# 智能分析（S 级：客户价值分层 + 商品 ABC + 库存周转）
# ============================================================
@bp.route('/analytics/smart')
@login_required
def api_analytics_smart():
    """经营智能分析：客户价值分层、商品 ABC 分类、库存周转天数"""
    db = get_db()

    # ---- 客户价值分层（按累计销售额：A 前20% / B 中间30% / C 后50%） ----
    customers = db.execute("""
        SELECT c.id, c.name, c.code,
               COALESCE(SUM(o.final_amount),0) as total_sales,
               COALESCE(SUM(o.gross_profit),0) as total_profit,
               COUNT(o.id) as order_count
        FROM customers c
        LEFT JOIN sales_orders o ON o.customer_id=c.id AND o.status != '已取消'
        GROUP BY c.id
        ORDER BY total_sales DESC
    """).fetchall()
    total_cust = len(customers)
    a_count = max(1, int(total_cust * 0.2)) if total_cust else 0
    b_count = max(0, int(total_cust * 0.3)) if total_cust else 0
    cust_layers = {'A': [], 'B': [], 'C': []}
    for i, c in enumerate(customers):
        layer = 'A' if i < a_count else ('B' if i < a_count + b_count else 'C')
        cust_layers[layer].append({
            'id': c['id'], 'name': c['name'], 'code': c['code'],
            'total_sales': c['total_sales'], 'total_profit': c['total_profit'],
            'order_count': c['order_count']
        })
    cust_summary = {
        layer: {
            'count': len(items),
            'sales': sum(i['total_sales'] for i in items),
            'profit': sum(i['total_profit'] for i in items),
            'top': items[:5]
        } for layer, items in cust_layers.items()
    }

    # ---- 商品 ABC 分类（按销售额占比：累计 70%=A / 20%=B / 10%=C） ----
    products = db.execute("""
        SELECT p.id, p.code, p.name, p.stock, p.safety_stock,
               COALESCE(SUM(oi.amount),0) as total_sales,
               COALESCE(SUM(oi.qty),0) as total_qty
        FROM products p
        LEFT JOIN sales_order_items oi ON oi.product_id=p.id
        LEFT JOIN sales_orders o ON o.id=oi.order_id AND o.status != '已取消'
        WHERE p.status=1
        GROUP BY p.id
        ORDER BY total_sales DESC
    """).fetchall()
    total_sales = sum(p['total_sales'] for p in products) or 1
    cumulative = 0
    abc = {'A': [], 'B': [], 'C': []}
    for p in products:
        cumulative += p['total_sales']
        ratio = cumulative / total_sales
        layer = 'A' if ratio <= 0.7 else ('B' if ratio <= 0.9 else 'C')
        if p['total_sales'] == 0:
            layer = 'C'
        abc[layer].append({
            'id': p['id'], 'code': p['code'], 'name': p['name'],
            'stock': p['stock'], 'safety_stock': p['safety_stock'],
            'total_sales': p['total_sales'], 'total_qty': p['total_qty'],
            'sales_ratio': round(p['total_sales'] / total_sales * 100, 1)
        })
    abc_summary = {
        layer: {
            'count': len(items),
            'sales': sum(i['total_sales'] for i in items),
            'sales_ratio': round(sum(i['total_sales'] for i in items) / total_sales * 100, 1),
            'top': items[:5]
        } for layer, items in abc.items()
    }

    # ---- 库存周转天数（近 90 天） ----
    ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    turnover = db.execute("""
        SELECT p.id, p.code, p.name, p.stock, p.cost_price,
               COALESCE(SUM(oi.qty),0) as sold_qty,
               COALESCE(SUM(oi.cost_price * oi.qty),0) as cogs
        FROM products p
        LEFT JOIN sales_order_items oi ON oi.product_id=p.id
        LEFT JOIN sales_orders o ON o.id=oi.order_id
            AND o.status != '已取消' AND o.order_date >= ?
        WHERE p.status=1
        GROUP BY p.id
        HAVING p.stock > 0 OR sold_qty > 0
        ORDER BY cogs DESC
    """, (ninety_days_ago,)).fetchall()
    turnover_list = []
    for t in turnover:
        avg_daily_cogs = t['cogs'] / 90.0 if t['cogs'] else 0
        inventory_value = (t['stock'] or 0) * (t['cost_price'] or 0)
        days = round(inventory_value / avg_daily_cogs, 1) if avg_daily_cogs > 0 else 999
        turnover_list.append({
            'id': t['id'], 'code': t['code'], 'name': t['name'],
            'stock': t['stock'], 'cogs': t['cogs'],
            'turnover_days': min(days, 999),
            'status': '健康' if days <= 30 else ('偏慢' if days <= 90 else '呆滞')
        })
    turnover_list.sort(key=lambda x: x['turnover_days'], reverse=True)

    return ok({
        'customer_layers': cust_summary,
        'product_abc': abc_summary,
        'inventory_turnover': {
            'total_products': len(turnover_list),
            'healthy': sum(1 for t in turnover_list if t['turnover_days'] <= 30),
            'slow': sum(1 for t in turnover_list if 30 < t['turnover_days'] <= 90),
            'stagnant': sum(1 for t in turnover_list if t['turnover_days'] > 90),
            'top_slow': turnover_list[:10]
        }
    })
