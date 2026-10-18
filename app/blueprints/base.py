# -*- coding: utf-8 -*-
from flask import Blueprint, request
from ..models import (get_db, now_str, to_int, yuan_to_fen)
from ..security import login_required
from ..utils import ok, fail

bp = Blueprint('base', __name__)


# ============ 分类 ============
@bp.route('/categories')
@login_required
def api_cat_list():
    db = get_db()
    rows = db.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM products p WHERE p.category_id=c.id) AS product_count "
        "FROM categories c ORDER BY c.id"
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.route('/categories', methods=['POST'])
@login_required
def api_cat_create():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('分类名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone():
        return fail('分类名称已存在')
    db.execute("INSERT INTO categories (name,remark,created_at) VALUES (?,?,?)",
               (name, (data.get('remark') or '').strip(), now_str()))
    db.commit()
    return ok(msg='新增成功')


@bp.route('/categories/<int:cid>', methods=['PUT'])
@login_required
def api_cat_update(cid):
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('分类名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM categories WHERE name=? AND id!=?", (name, cid)).fetchone():
        return fail('分类名称已存在')
    db.execute("UPDATE categories SET name=?, remark=? WHERE id=?",
               (name, (data.get('remark') or '').strip(), cid))
    db.commit()
    return ok(msg='修改成功')


@bp.route('/categories/<int:cid>', methods=['DELETE'])
@login_required
def api_cat_delete(cid):
    db = get_db()
    if db.execute("SELECT COUNT(*) AS c FROM products WHERE category_id=?", (cid,)).fetchone()['c']:
        return fail('该分类下还有商品，无法删除')
    db.execute("DELETE FROM categories WHERE id=?", (cid,))
    db.commit()
    return ok(msg='删除成功')


# ============ 仓库 ============
@bp.route('/warehouses')
@login_required
def api_wh_list():
    db = get_db()
    return ok([dict(r) for r in db.execute("SELECT * FROM warehouses ORDER BY id").fetchall()])


@bp.route('/warehouses', methods=['POST'])
@login_required
def api_wh_create():
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('编码和名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM warehouses WHERE code=?", (code,)).fetchone():
        return fail('仓库编码已存在')
    db.execute(
        "INSERT INTO warehouses (code,name,wtype,address,remark,status,created_at) VALUES (?,?,?,?,?,1,?)",
        (code, name, (data.get('wtype') or '正常仓').strip(),
         (data.get('address') or '').strip(), (data.get('remark') or '').strip(), now_str())
    )
    db.commit()
    return ok(msg='新增成功')


@bp.route('/warehouses/<int:wid>', methods=['PUT'])
@login_required
def api_wh_update(wid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute("UPDATE warehouses SET code=?, name=?, wtype=?, address=?, remark=? WHERE id=?",
               ((data.get('code') or '').strip(), (data.get('name') or '').strip(),
                (data.get('wtype') or '正常仓').strip(), (data.get('address') or '').strip(),
                (data.get('remark') or '').strip(), wid))
    db.commit()
    return ok(msg='修改成功')


@bp.route('/warehouses/<int:wid>', methods=['DELETE'])
@login_required
def api_wh_delete(wid):
    db = get_db()
    if db.execute("SELECT COUNT(*) AS c FROM product_stocks WHERE warehouse_id=? AND stock>0",
                  (wid,)).fetchone()['c']:
        return fail('该仓库尚有库存')
    db.execute("DELETE FROM warehouses WHERE id=?", (wid,))
    db.commit()
    return ok(msg='删除成功')


# ============ 商品 ============
@bp.route('/products')
@login_required
def api_product_list():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    category_id = to_int(request.args.get('category_id'))
    sql = ("SELECT p.*, c.name AS category_name FROM products p "
           "LEFT JOIN categories c ON c.id=p.category_id WHERE 1=1")
    params = []
    if keyword:
        sql += " AND (p.code LIKE ? OR p.name LIKE ? OR p.barcode LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like, like])
    if category_id:
        sql += " AND p.category_id=?"
        params.append(category_id)
    sql += " ORDER BY p.id DESC"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/products', methods=['POST'])
@login_required
def api_product_create():
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('商品编码和名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM products WHERE code=?", (code,)).fetchone():
        return fail('商品编码已存在')

    init_stock = to_int(data.get('stock'), 0)
    warehouse_id = to_int(data.get('warehouse_id'), 1)
    purchase = yuan_to_fen(data.get('purchase_price', 0))
    sale = yuan_to_fen(data.get('sale_price', 0))

    cur = db.execute(
        "INSERT INTO products (code,name,category_id,spec,unit,barcode,purchase_price,"
        "sale_price,cost_price,stock,safety_stock,status,remark,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,0,?,1,?,?)",
        (code, name, to_int(data.get('category_id')), (data.get('spec') or '').strip(),
         (data.get('unit') or '个').strip(), (data.get('barcode') or '').strip(),
         purchase, sale, purchase,
         to_int(data.get('safety_stock'), 0), (data.get('remark') or '').strip(), now_str())
    )
    pid = cur.lastrowid
    db.execute("INSERT INTO product_stocks (product_id,warehouse_id,stock) VALUES (?,?,0)",
               (pid, warehouse_id))
    if init_stock > 0:
        from ..models import atomic_add_stock, log_stock
        atomic_add_stock(db, pid, warehouse_id, init_stock)
        log_stock(db, pid, warehouse_id, '期初库存', init_stock, 'INIT', '新增商品初始化')
    db.commit()
    return ok({'id': pid}, '新增成功')


@bp.route('/products/<int:pid>', methods=['PUT'])
@login_required
def api_product_update(pid):
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('商品编码和名称不能为空')
    db = get_db()
    old = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not old:
        return fail('商品不存在')
    if db.execute("SELECT id FROM products WHERE code=? AND id!=?", (code, pid)).fetchone():
        return fail('商品编码已存在')
    db.execute(
        "UPDATE products SET code=?, name=?, category_id=?, spec=?, unit=?, barcode=?, "
        "purchase_price=?, sale_price=?, safety_stock=?, remark=? WHERE id=?",
        (code, name, to_int(data.get('category_id')), (data.get('spec') or '').strip(),
         (data.get('unit') or '个').strip(), (data.get('barcode') or '').strip(),
         yuan_to_fen(data.get('purchase_price', 0)), yuan_to_fen(data.get('sale_price', 0)),
         to_int(data.get('safety_stock'), 0), (data.get('remark') or '').strip(), pid)
    )
    db.commit()
    return ok(msg='修改成功')


@bp.route('/products/<int:pid>', methods=['DELETE'])
@login_required
def api_product_delete(pid):
    db = get_db()
    used = db.execute(
        "SELECT (SELECT COUNT(*) FROM sales_order_items WHERE product_id=?) + "
        "(SELECT COUNT(*) FROM purchase_order_items WHERE product_id=?) AS c", (pid, pid)
    ).fetchone()['c']
    if used:
        return fail('该商品已被订单引用')
    db.execute("DELETE FROM product_stocks WHERE product_id=?", (pid,))
    db.execute("DELETE FROM stock_logs WHERE product_id=?", (pid,))
    db.execute("DELETE FROM products WHERE id=?", (pid,))
    db.commit()
    return ok(msg='删除成功')


# ============ 客户 ============
@bp.route('/customers')
@login_required
def api_cust_list():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    sql = ("SELECT c.*, "
           "IFNULL((SELECT SUM(final_amount) FROM sales_orders WHERE customer_id=c.id AND status='已出库'),0) AS total_sales, "
           "IFNULL((SELECT SUM(amount - received) FROM receivables WHERE customer_id=c.id AND status!='已收完'),0) AS ar_balance "
           "FROM customers c WHERE 1=1")
    params = []
    if keyword:
        sql += " AND (c.code LIKE ? OR c.name LIKE ? OR c.contact LIKE ? OR c.phone LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like, like, like])
    sql += " ORDER BY c.id DESC"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/customers', methods=['POST'])
@login_required
def api_cust_create():
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('客户编码和名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM customers WHERE code=?", (code,)).fetchone():
        return fail('客户编码已存在')
    db.execute(
        "INSERT INTO customers (code,name,contact,phone,email,address,credit_limit,level,remark,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (code, name, (data.get('contact') or '').strip(), (data.get('phone') or '').strip(),
         (data.get('email') or '').strip(), (data.get('address') or '').strip(),
         yuan_to_fen(data.get('credit_limit', 0)), (data.get('level') or '普通').strip(),
         (data.get('remark') or '').strip(), now_str())
    )
    db.commit()
    return ok(msg='新增成功')


@bp.route('/customers/<int:cid>', methods=['PUT'])
@login_required
def api_cust_update(cid):
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('客户编码和名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM customers WHERE code=? AND id!=?", (code, cid)).fetchone():
        return fail('客户编码已存在')
    db.execute(
        "UPDATE customers SET code=?, name=?, contact=?, phone=?, email=?, address=?, "
        "credit_limit=?, level=?, remark=? WHERE id=?",
        (code, name, (data.get('contact') or '').strip(), (data.get('phone') or '').strip(),
         (data.get('email') or '').strip(), (data.get('address') or '').strip(),
         yuan_to_fen(data.get('credit_limit', 0)), (data.get('level') or '普通').strip(),
         (data.get('remark') or '').strip(), cid)
    )
    db.commit()
    return ok(msg='修改成功')


@bp.route('/customers/<int:cid>', methods=['DELETE'])
@login_required
def api_cust_delete(cid):
    db = get_db()
    if db.execute("SELECT COUNT(*) AS c FROM sales_orders WHERE customer_id=?", (cid,)).fetchone()['c']:
        return fail('该客户已有订单')
    db.execute("DELETE FROM customer_follows WHERE customer_id=?", (cid,))
    db.execute("DELETE FROM customers WHERE id=?", (cid,))
    db.commit()
    return ok(msg='删除成功')


# ============ 供应商 ============
@bp.route('/suppliers')
@login_required
def api_sup_list():
    db = get_db()
    keyword = (request.args.get('keyword') or '').strip()
    sql = "SELECT * FROM suppliers WHERE 1=1"
    params = []
    if keyword:
        sql += " AND (code LIKE ? OR name LIKE ? OR contact LIKE ?)"
        like = '%' + keyword + '%'
        params.extend([like, like, like])
    sql += " ORDER BY id DESC"
    return ok([dict(r) for r in db.execute(sql, params).fetchall()])


@bp.route('/suppliers', methods=['POST'])
@login_required
def api_sup_create():
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('编码和名称不能为空')
    db = get_db()
    if db.execute("SELECT id FROM suppliers WHERE code=?", (code,)).fetchone():
        return fail('编码已存在')
    db.execute(
        "INSERT INTO suppliers (code,name,contact,phone,email,address,remark,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (code, name, (data.get('contact') or '').strip(), (data.get('phone') or '').strip(),
         (data.get('email') or '').strip(), (data.get('address') or '').strip(),
         (data.get('remark') or '').strip(), now_str())
    )
    db.commit()
    return ok(msg='新增成功')


@bp.route('/suppliers/<int:sid>', methods=['PUT'])
@login_required
def api_sup_update(sid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute("UPDATE suppliers SET code=?, name=?, contact=?, phone=?, email=?, address=?, remark=? WHERE id=?",
               ((data.get('code') or '').strip(), (data.get('name') or '').strip(),
                (data.get('contact') or '').strip(), (data.get('phone') or '').strip(),
                (data.get('email') or '').strip(), (data.get('address') or '').strip(),
                (data.get('remark') or '').strip(), sid))
    db.commit()
    return ok(msg='修改成功')


@bp.route('/suppliers/<int:sid>', methods=['DELETE'])
@login_required
def api_sup_delete(sid):
    db = get_db()
    if db.execute("SELECT COUNT(*) AS c FROM purchase_orders WHERE supplier_id=?", (sid,)).fetchone()['c']:
        return fail('该供应商已有订单')
    db.execute("DELETE FROM suppliers WHERE id=?", (sid,))
    db.commit()
    return ok(msg='删除成功')


# ============ 员工 ============
@bp.route('/employees')
@login_required
def api_emp_list():
    db = get_db()
    return ok([dict(r) for r in db.execute("SELECT * FROM employees ORDER BY id DESC").fetchall()])


@bp.route('/employees', methods=['POST'])
@login_required
def api_emp_create():
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('工号和姓名不能为空')
    db = get_db()
    if db.execute("SELECT id FROM employees WHERE code=?", (code,)).fetchone():
        return fail('工号已存在')
    db.execute(
        "INSERT INTO employees (code,name,gender,dept,position,phone,email,salary,hire_date,status,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,1,?)",
        (code, name, (data.get('gender') or '男').strip(), (data.get('dept') or '').strip(),
         (data.get('position') or '').strip(), (data.get('phone') or '').strip(),
         (data.get('email') or '').strip(), yuan_to_fen(data.get('salary', 0)),
         (data.get('hire_date') or '').strip(), now_str())
    )
    db.commit()
    return ok(msg='新增成功')


@bp.route('/employees/<int:eid>', methods=['PUT'])
@login_required
def api_emp_update(eid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute("UPDATE employees SET name=?, gender=?, dept=?, position=?, phone=?, email=?, salary=? WHERE id=?",
               ((data.get('name') or '').strip(), (data.get('gender') or '男').strip(),
                (data.get('dept') or '').strip(), (data.get('position') or '').strip(),
                (data.get('phone') or '').strip(), (data.get('email') or '').strip(),
                yuan_to_fen(data.get('salary', 0)), eid))
    db.commit()
    return ok(msg='修改成功')


@bp.route('/employees/<int:eid>', methods=['DELETE'])
@login_required
def api_emp_delete(eid):
    db = get_db()
    db.execute("DELETE FROM employees WHERE id=?", (eid,))
    db.commit()
    return ok(msg='删除成功')