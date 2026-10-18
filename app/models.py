# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime
from flask import g, current_app

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    real_name TEXT DEFAULT '',
    role TEXT NOT NULL DEFAULT 'staff',
    status INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, username TEXT DEFAULT '',
    action TEXT DEFAULT '', module TEXT DEFAULT '',
    detail TEXT DEFAULT '', ip TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    wtype TEXT DEFAULT '正常仓',
    address TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    status INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category_id INTEGER,
    spec TEXT DEFAULT '',
    unit TEXT DEFAULT '个',
    barcode TEXT DEFAULT '',
    purchase_price INTEGER DEFAULT 0,
    sale_price INTEGER DEFAULT 0,
    cost_price INTEGER DEFAULT 0,
    stock INTEGER DEFAULT 0,
    safety_stock INTEGER DEFAULT 0,
    status INTEGER DEFAULT 1,
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    warehouse_id INTEGER NOT NULL,
    stock INTEGER DEFAULT 0,
    UNIQUE(product_id, warehouse_id)
);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    contact TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    email TEXT DEFAULT '',
    address TEXT DEFAULT '',
    credit_limit INTEGER DEFAULT 0,
    level TEXT DEFAULT '普通',
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_follows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    content TEXT DEFAULT '',
    follower TEXT DEFAULT '',
    follow_date TEXT DEFAULT '',
    next_date TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    contact TEXT DEFAULT '', phone TEXT DEFAULT '',
    email TEXT DEFAULT '', address TEXT DEFAULT '',
    remark TEXT DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL, gender TEXT DEFAULT '男',
    dept TEXT DEFAULT '', position TEXT DEFAULT '',
    phone TEXT DEFAULT '', email TEXT DEFAULT '',
    salary INTEGER DEFAULT 0,
    hire_date TEXT DEFAULT '',
    status INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL,
    warehouse_id INTEGER,
    order_date TEXT NOT NULL,
    total_amount INTEGER DEFAULT 0,
    discount INTEGER DEFAULT 0,
    final_amount INTEGER DEFAULT 0,
    total_cost INTEGER DEFAULT 0,
    gross_profit INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT '待确认',
    remark TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    price INTEGER DEFAULT 0,
    cost_price INTEGER DEFAULT 0,
    qty INTEGER DEFAULT 0,
    amount INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL,
    warehouse_id INTEGER,
    order_date TEXT NOT NULL,
    total_amount INTEGER DEFAULT 0,
    discount INTEGER DEFAULT 0,
    final_amount INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT '待确认',
    remark TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    price INTEGER DEFAULT 0,
    qty INTEGER DEFAULT 0,
    amount INTEGER DEFAULT 0,
    batch_no TEXT DEFAULT '',
    expire_date TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS receivables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER, order_no TEXT DEFAULT '',
    customer_id INTEGER NOT NULL,
    amount INTEGER DEFAULT 0,
    received INTEGER DEFAULT 0,
    status TEXT DEFAULT '未收',
    due_date TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER, order_no TEXT DEFAULT '',
    supplier_id INTEGER NOT NULL,
    amount INTEGER DEFAULT 0,
    paid INTEGER DEFAULT 0,
    status TEXT DEFAULT '未付',
    due_date TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL,
    account_id INTEGER,
    amount INTEGER DEFAULT 0,
    method TEXT DEFAULT '银行转账',
    receipt_date TEXT NOT NULL,
    remark TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipt_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL,
    receivable_id INTEGER NOT NULL,
    amount INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_no TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL,
    account_id INTEGER,
    amount INTEGER DEFAULT 0,
    method TEXT DEFAULT '银行转账',
    payment_date TEXT NOT NULL,
    remark TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL,
    payable_id INTEGER NOT NULL,
    amount INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fund_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    atype TEXT DEFAULT '银行',
    balance INTEGER DEFAULT 0,
    remark TEXT DEFAULT '',
    status INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fund_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    change_type TEXT DEFAULT '',
    amount INTEGER DEFAULT 0,
    before_balance INTEGER DEFAULT 0,
    after_balance INTEGER DEFAULT 0,
    ref_no TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    warehouse_id INTEGER,
    change_type TEXT NOT NULL,
    qty INTEGER DEFAULT 0,
    before_stock INTEGER DEFAULT 0,
    after_stock INTEGER DEFAULT 0,
    ref_no TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_so_customer ON sales_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_rec_customer ON receivables(customer_id);
CREATE INDEX IF NOT EXISTS idx_log_product ON stock_logs(product_id);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT NOT NULL,
    invoice_code TEXT DEFAULT '',
    invoice_type TEXT NOT NULL,          -- 进项 / 销项
    partner_type TEXT NOT NULL,          -- customer / supplier
    partner_id INTEGER,
    partner_name TEXT DEFAULT '',
    amount INTEGER DEFAULT 0,            -- 不含税金额（分）
    tax_rate REAL DEFAULT 13,            -- 税率 %
    tax_amount INTEGER DEFAULT 0,        -- 税额（分）
    total_amount INTEGER DEFAULT 0,      -- 价税合计（分）
    invoice_date TEXT NOT NULL,
    status TEXT DEFAULT '已开',          -- 未认证/已认证/已开/已作废
    related_order TEXT DEFAULT '',
    remark TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    biz_key TEXT NOT NULL UNIQUE,        -- sales_revenue 等
    code TEXT DEFAULT '',
    name TEXT DEFAULT '',
    direction TEXT DEFAULT '借',
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS vouchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_no TEXT NOT NULL UNIQUE,
    voucher_date TEXT NOT NULL,
    biz_type TEXT DEFAULT '',
    biz_id INTEGER,
    summary TEXT DEFAULT '',
    entries_json TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS print_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ttype TEXT NOT NULL,                 -- delivery / sales / purchase / statement
    company_name TEXT DEFAULT '',
    header_text TEXT DEFAULT '',
    footer_text TEXT DEFAULT '',
    is_default INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invoice_type ON invoices(invoice_type);
CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoices(invoice_date);

-- AI 接入配置（开关式占位：接入 API 后填写，未填写时系统使用内置规则摘要）
CREATE TABLE IF NOT EXISTS ai_settings (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

-- AI 调用日志（记录每次 LLM 调用的类型/耗时/token/状态，用于成本统计与可观测性）
CREATE TABLE IF NOT EXISTS ai_call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_type TEXT DEFAULT 'summary',   -- summary / parse_order / test / daily_brief
    status TEXT DEFAULT 'success',      -- success / failed / fallback / cached
    duration_ms INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    error_msg TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_created ON ai_call_logs(created_at);

-- ============================================================
-- 性能索引（S 级标准：高频查询字段全覆盖，大数据量下不卡）
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_sales_orders_customer ON sales_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_orders_date ON sales_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_sales_orders_status ON sales_orders(status);
CREATE INDEX IF NOT EXISTS idx_sales_orders_created ON sales_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_sales_order_items_order ON sales_order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_sales_order_items_product ON sales_order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_date ON purchase_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_status ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_purchase_order_items_order ON purchase_order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_purchase_order_items_product ON purchase_order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_receivables_customer ON receivables(customer_id);
CREATE INDEX IF NOT EXISTS idx_receivables_status ON receivables(status);
CREATE INDEX IF NOT EXISTS idx_payables_supplier ON payables(supplier_id);
CREATE INDEX IF NOT EXISTS idx_payables_status ON payables(status);
CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(receipt_date);
CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);
CREATE INDEX IF NOT EXISTS idx_stock_logs_product ON stock_logs(product_id);
CREATE INDEX IF NOT EXISTS idx_stock_logs_date ON stock_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_fund_logs_date ON fund_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_products_code ON products(code);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
CREATE INDEX IF NOT EXISTS idx_product_stocks_product ON product_stocks(product_id);
CREATE INDEX IF NOT EXISTS idx_customers_code ON customers(code);
CREATE INDEX IF NOT EXISTS idx_suppliers_code ON suppliers(code);
CREATE INDEX IF NOT EXISTS idx_operation_logs_created ON operation_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_invoices_type ON invoices(invoice_type);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
"""


def get_ai_setting(key, default=''):
    """读取 AI 配置项"""
    try:
        db = get_db()
        row = db.execute("SELECT value FROM ai_settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default
    except Exception:
        return default


def set_ai_setting(key, value):
    """写入 AI 配置项"""
    db = get_db()
    db.execute("INSERT INTO ai_settings (key,value) VALUES (?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    db.commit()


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def today_str():
    return datetime.now().strftime('%Y-%m-%d')


def to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def yuan_to_fen(v):
    try:
        return round(float(v) * 100)
    except (TypeError, ValueError):
        return 0


def fen_to_yuan(fen):
    return round((fen or 0) / 100.0, 2)


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DB_PATH'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def log_op(action, module, detail=''):
    try:
        from flask import session, request
        db = get_db()
        db.execute(
            "INSERT INTO operation_logs (user_id, username, action, module, detail, ip, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (session.get('user_id'), session.get('username', ''),
             action, module, detail, request.remote_addr or '', now_str())
        )
        db.commit()
    except Exception:
        pass


def atomic_deduct_stock(db, product_id, warehouse_id, qty):
    """原子扣减库存（防超卖）"""
    cur = db.execute(
        "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
        (qty, product_id, qty)
    )
    if cur.rowcount == 0:
        return False
    if warehouse_id:
        cur2 = db.execute(
            "UPDATE product_stocks SET stock = stock - ? "
            "WHERE product_id = ? AND warehouse_id = ? AND stock >= ?",
            (qty, product_id, warehouse_id, qty)
        )
        if cur2.rowcount == 0:
            db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (qty, product_id))
            return False
    return True


def atomic_add_stock(db, product_id, warehouse_id, qty):
    db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (qty, product_id))
    if warehouse_id:
        ps = db.execute(
            "SELECT id FROM product_stocks WHERE product_id=? AND warehouse_id=?",
            (product_id, warehouse_id)
        ).fetchone()
        if ps:
            db.execute("UPDATE product_stocks SET stock = stock + ? WHERE id=?", (qty, ps['id']))
        else:
            db.execute(
                "INSERT INTO product_stocks (product_id, warehouse_id, stock) VALUES (?,?,?)",
                (product_id, warehouse_id, qty)
            )


def log_stock(db, product_id, warehouse_id, change_type, qty, ref_no='', remark=''):
    row = db.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        return
    before = row['stock'] or 0
    after = before + qty
    db.execute(
        "INSERT INTO stock_logs (product_id, warehouse_id, change_type, qty, "
        "before_stock, after_stock, ref_no, remark, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (product_id, warehouse_id, change_type, qty, before, after, ref_no, remark, now_str())
    )


def update_weighted_cost(db, product_id, in_qty, in_price_fen):
    p = db.execute("SELECT stock, cost_price FROM products WHERE id=?", (product_id,)).fetchone()
    if not p:
        return
    old_stock = max((p['stock'] or 0) - in_qty, 0)
    old_cost = p['cost_price'] or 0
    total_qty = old_stock + in_qty
    if total_qty <= 0:
        new_cost = in_price_fen
    else:
        new_cost = round((old_stock * old_cost + in_qty * in_price_fen) / total_qty)
    db.execute("UPDATE products SET cost_price=? WHERE id=?", (new_cost, product_id))


def log_fund(db, account_id, change_type, amount_fen, ref_no='', remark=''):
    acc = db.execute("SELECT * FROM fund_accounts WHERE id=?", (account_id,)).fetchone()
    if not acc:
        return None
    before = acc['balance'] or 0
    after = before + amount_fen
    if after < 0:
        return None
    db.execute("UPDATE fund_accounts SET balance=? WHERE id=?", (after, account_id))
    db.execute(
        "INSERT INTO fund_logs (account_id, change_type, amount, before_balance, "
        "after_balance, ref_no, remark, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (account_id, change_type, amount_fen, before, after, ref_no, remark, now_str())
    )
    return after


# 单号生成白名单：仅允许内部硬编码的表/列，杜绝 SQL 注入面
_NO_GEN_TABLES = {
    'sales_orders': 'order_no',
    'purchase_orders': 'order_no',
    'receipts': 'receipt_no',
    'payments': 'payment_no',
}


def gen_no(db, prefix, table, col='order_no'):
    if table not in _NO_GEN_TABLES or _NO_GEN_TABLES[table] != col:
        raise ValueError('不支持的编号表/列：%s.%s' % (table, col))
    day = datetime.now().strftime('%Y%m%d')
    full = prefix + day
    row = db.execute(
        "SELECT %s AS n FROM %s WHERE %s LIKE ? ORDER BY %s DESC LIMIT 1" % (col, table, col, col),
        (full + '%',)
    ).fetchone()
    seq = 1
    if row and row['n']:
        try:
            seq = int(row['n'][len(full):]) + 1
        except ValueError:
            seq = 1
    return "%s%04d" % (full, seq)


def init_db():
    from werkzeug.security import generate_password_hash
    conn = sqlite3.connect(current_app.config['DB_PATH'])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)

    if cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()['c'] == 0:
        cur.execute(
            "INSERT INTO users (username,password,real_name,role,status,created_at) VALUES (?,?,?,?,?,?)",
            ('admin', generate_password_hash('admin123'), '系统管理员', 'admin', 1, now_str())
        )
    if cur.execute("SELECT COUNT(*) AS c FROM warehouses").fetchone()['c'] == 0:
        cur.executemany(
            "INSERT INTO warehouses (code,name,wtype,address,remark,status,created_at) VALUES (?,?,?,?,?,1,?)",
            [('WH01', '总仓', '正常仓', '总部', '主仓库', now_str()),
             ('WH02', '次品仓', '次品仓', '总部', '不良品仓', now_str())]
        )
    if cur.execute("SELECT COUNT(*) AS c FROM fund_accounts").fetchone()['c'] == 0:
        cur.executemany(
            "INSERT INTO fund_accounts (code,name,atype,balance,remark,status,created_at) VALUES (?,?,?,?,?,1,?)",
            [('ACC01', '工商银行基本户', '银行', 10000000, '公司基本户', now_str()),
             ('ACC02', '现金账户', '现金', 500000, '备用金', now_str())]
        )
    if cur.execute("SELECT COUNT(*) AS c FROM categories").fetchone()['c'] == 0:
        cur.executemany(
            "INSERT INTO categories (name,remark,created_at) VALUES (?,?,?)",
            [('办公用品', '耗材', now_str()),
             ('电子产品', '数码', now_str()),
             ('原材料', '生产', now_str()),
             ('其他', '', now_str())]
        )
    if cur.execute("SELECT COUNT(*) AS c FROM products").fetchone()['c'] == 0:
        prods = [
            ('P1001', 'A4复印纸 70g', 1, '500张/包', '包', '6901234500011', 1250, 1800, 1250, 50),
            ('P1002', '中性笔 0.5mm', 1, '12支/盒', '盒', '6901234500028', 800, 1500, 800, 30),
            ('P2001', '无线鼠标 2.4G', 2, '2.4G', '个', '6901234500042', 3500, 6900, 3500, 20),
            ('P2002', '机械键盘 87键', 2, '87键', '个', '6901234500059', 18000, 29900, 18000, 10),
            ('P3001', '冷轧钢板 1.0mm', 3, '1.0mm', '吨', '', 420000, 480000, 420000, 5),
        ]
        for p in prods:
            cur.execute(
                "INSERT INTO products (code,name,category_id,spec,unit,barcode,"
                "purchase_price,sale_price,cost_price,stock,safety_stock,status,remark,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,0,?,1,'',?)",
                (p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8], p[9], now_str())
            )
            pid = cur.lastrowid
            cur.execute("INSERT INTO product_stocks (product_id,warehouse_id,stock) VALUES (?,?,0)", (pid, 1))
            cur.execute("UPDATE products SET stock=100 WHERE id=?", (pid,))
            cur.execute("UPDATE product_stocks SET stock=100 WHERE product_id=? AND warehouse_id=1", (pid,))
            cur.execute(
                "INSERT INTO stock_logs (product_id,warehouse_id,change_type,qty,"
                "before_stock,after_stock,ref_no,remark,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, 1, '期初库存', 100, 0, 100, 'INIT', '系统初始化', now_str())
            )
    if cur.execute("SELECT COUNT(*) AS c FROM customers").fetchone()['c'] == 0:
        cur.executemany(
            "INSERT INTO customers (code,name,contact,phone,email,address,credit_limit,level,remark,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [('C001', '杭州蓝天贸易', '张经理', '13800138001', 'zhang@lt.com', '杭州西湖区', 5000000, '金牌', '', now_str()),
             ('C002', '上海恒信科技', '李总', '13900139002', 'li@hx.com', '上海浦东', 3000000, '银牌', '', now_str())]
        )
    if cur.execute("SELECT COUNT(*) AS c FROM suppliers").fetchone()['c'] == 0:
        cur.executemany(
            "INSERT INTO suppliers (code,name,contact,phone,email,address,remark,created_at) VALUES (?,?,?,?,?,?,?,?)",
            [('S001', '宁波文具制造', '陈厂长', '13600136001', 'chen@nb.com', '宁波鄞州', '', now_str()),
             ('S002', '深圳华强电子', '刘经理', '13500135002', 'liu@hq.com', '深圳福田', '', now_str())]
        )
    # 默认会计科目映射
    if cur.execute("SELECT COUNT(*) AS c FROM account_mapping").fetchone()['c'] == 0:
        mappings = [
            ('sales_revenue', '6001', '主营业务收入', '贷'),
            ('receivable',    '1122', '应收账款',     '借'),
            ('sales_cost',    '6401', '主营业务成本', '借'),
            ('inventory',     '1405', '库存商品',     '贷'),
            ('payable',       '2202', '应付账款',     '贷'),
            ('bank',          '1002', '银行存款',     '借'),
            ('cash',          '1001', '库存现金',     '借'),
            ('tax_output',    '2221', '应交税费-销项税额', '贷'),
            ('tax_input',     '2221', '应交税费-进项税额', '借'),
        ]
        cur.executemany(
            "INSERT INTO account_mapping (biz_key, code, name, direction, updated_at) VALUES (?,?,?,?,?)",
            [(k, c, n, d, now_str()) for k, c, n, d in mappings]
        )

    # 默认打印模板
    if cur.execute("SELECT COUNT(*) AS c FROM print_templates").fetchone()['c'] == 0:
        cur.executemany(
            "INSERT INTO print_templates (name, ttype, company_name, header_text, footer_text, is_default, created_at) "
            "VALUES (?,?,?,?,?,1,?)",
            [('默认送货单', 'delivery', 'XX贸易有限公司', '送货单',
              '签收人：________  日期：________', now_str()),
             ('默认采购入库单', 'purchase', 'XX贸易有限公司', '采购入库单',
              '仓管：________  验收：________', now_str()),
             ('默认客户对账单', 'statement', 'XX贸易有限公司', '客户对账单',
              '盖章确认：________  日期：________', now_str())]
        )

    # 统一提交并关闭连接
    # 修复：此前 commit/close 误缩进在最后一个 if 内，当该表已有数据时
    #       （如二次启动），其余种子数据不会提交、连接也不会关闭。
    conn.commit()
    conn.close()


def gen_voucher_no(db):
    """生成凭证号，例如 PZ202609290001"""
    day = datetime.now().strftime('%Y%m%d')
    full = 'PZ' + day
    row = db.execute(
        "SELECT voucher_no AS n FROM vouchers WHERE voucher_no LIKE ? ORDER BY voucher_no DESC LIMIT 1",
        (full + '%',)
    ).fetchone()
    seq = 1
    if row and row['n']:
        try:
            seq = int(row['n'][len(full):]) + 1
        except ValueError:
            seq = 1
    return "%s%04d" % (full, seq)


def get_account_map(db):
    """获取会计科目映射字典 {biz_key: {code, name, direction}}"""
    rows = db.execute("SELECT * FROM account_mapping").fetchall()
    return {r['biz_key']: {'code': r['code'], 'name': r['name'], 'direction': r['direction']} for r in rows}