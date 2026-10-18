# -*- coding: utf-8 -*-
"""演示数据生成/清理模块（P0：让系统“活”起来）

设计：
- seed(db_path)：生成一套逼真仿真数据
  · 过去 6 个月销售订单（趋势图有起伏）+ 采购入库（库存/加权成本联动）
  · 多笔逾期应收 + 部分已回款资金流水（资金账户有动静）
  · 库存低于安全线的商品（触发补货预警）
  · 客户跟进备注（触发工作台“客户待跟进”待办）
  · 少量待确认销售/采购单（触发待办）
- 安全机制：首次生成前自动备份 erp.db -> erp.db.demo_backup；
  clear(db_path) 直接恢复备份，100% 还原现场，绝不残留。
- 本模块不依赖 Flask，CLI 脚本与 Web 接口共用。
"""
import os
import shutil
import sqlite3
import random
from datetime import datetime, timedelta

DEMO_MARK = '演示数据'


def backup_path(db_path):
    return db_path + '.demo_backup'


def has_demo(db_path):
    conn = sqlite3.connect(db_path)
    try:
        c = conn.execute("SELECT COUNT(*) FROM sales_orders WHERE remark=?", (DEMO_MARK,)).fetchone()[0]
    except Exception:
        c = 0
    conn.close()
    return c > 0


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def seed(db_path):
    """生成演示数据。返回摘要 dict。"""
    if has_demo(db_path):
        return {'ok': False, 'msg': '已存在演示数据，请先「清理演示数据」再重新生成'}

    # 1) 备份现场（仅首次）
    if not os.path.exists(backup_path(db_path)):
        shutil.copy2(db_path, backup_path(db_path))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rnd = random.Random(20261018)

    # ---- 基础数据补全 ----
    customers = [dict(r) for r in cur.execute(
        "SELECT * FROM customers ORDER BY id").fetchall()]
    suppliers = [dict(r) for r in cur.execute(
        "SELECT * FROM suppliers ORDER BY id").fetchall()]
    products = [dict(r) for r in cur.execute(
        "SELECT * FROM products ORDER BY id").fetchall()]
    wh = cur.execute("SELECT * FROM warehouses WHERE status=1 ORDER BY id LIMIT 1").fetchone()
    if not wh:
        raise RuntimeError('系统中没有可用仓库，无法生成演示数据')
    accs = [dict(r) for r in cur.execute(
        "SELECT * FROM fund_accounts WHERE status=1 ORDER BY id").fetchall()]
    acc = accs[0] if accs else None

    n_cust, n_sup, n_prod = 0, 0, 0

    if len(customers) < 5:
        for name, contact in [
            ('广州启航办公用品', '王经理'), ('深圳云帆科技', '陈总'),
            ('佛山弘泰实业', '刘女士'),
        ]:
            if len(customers) >= 5:
                break
            n_cust += 1
            cid = cur.execute(
                "INSERT INTO customers (code,name,contact,phone,address,credit_limit,level,remark,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ('C%03d' % (len(customers) + n_cust), name, contact,
                 '13%d' % rnd.randint(100000000, 999999999),
                 '广州市天河区', 5000000, '金牌', DEMO_MARK, _now())).lastrowid
            customers.append({'id': cid, 'name': name, 'remark': DEMO_MARK})

    if len(suppliers) < 4:
        for name, contact in [
            ('广东纸业集团', '赵经理'), ('华东电子配件厂', '孙工'),
        ]:
            if len(suppliers) >= 4:
                break
            n_sup += 1
            sid = cur.execute(
                "INSERT INTO suppliers (code,name,contact,phone,address,remark,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                ('S%03d' % (len(suppliers) + n_sup), name, contact,
                 '13%d' % rnd.randint(100000000, 999999999), '东莞松山湖', DEMO_MARK, _now())).lastrowid
            suppliers.append({'id': sid, 'name': name, 'remark': DEMO_MARK})

    if len(products) < 9:
        for code, name, cat, spec, unit, pp, sp, safety in [
            ('P1003', '订书机 12#', 1, '标准型', '个', 900, 1800, 15),
            ('P1004', '文件夹 A4', 1, '蓝色', '个', 600, 1500, 20),
            ('P2003', 'USB扩展坞 4口', 2, 'USB3.0', '个', 4500, 8900, 8),
            ('P3002', '不锈钢板 0.8mm', 3, '0.8mm', '吨', 380000, 440000, 4),
        ]:
            if len(products) >= 9:
                break
            n_prod += 1
            pid = cur.execute(
                "INSERT INTO products (code,name,category_id,spec,unit,purchase_price,sale_price,"
                "cost_price,stock,safety_stock,status,remark,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (code, name, cat, spec, unit, pp, sp, pp, 80, safety, DEMO_MARK, _now())).lastrowid
            cur.execute("INSERT INTO product_stocks (product_id, warehouse_id, stock) VALUES (?,?,80)",
                        (pid, wh['id']))
            products.append({'id': pid, 'code': code, 'name': name, 'unit': unit,
                             'sale_price': sp, 'purchase_price': pp, 'stock': 80,
                             'safety_stock': safety, 'cost_price': pp})

    # ---- 月份销售计划（让趋势图有起伏） ----
    # 月份 -> (订单数, 总销售额目标, 峰值系数)
    months = [
        ('2026-05', 6, 2000000, 0.8),
        ('2026-06', 7, 2800000, 1.1),
        ('2026-07', 6, 2400000, 0.95),
        ('2026-08', 8, 3600000, 1.35),
        ('2026-09', 7, 3000000, 1.15),
        ('2026-10', 6, 2400000, 0.9),
    ]
    today = datetime.now()
    month_sales = []      # (month, sum)
    order_seq = 100
    n_so = n_so_items = n_rc = n_pur = n_pur_items = n_py = 0
    n_recv = n_pay = n_stock = 0

    for mi, (ym, cnt, target, peak) in enumerate(months):
        year, month = int(ym[:4]), int(ym[5:7])
        # 本月只生成到今天
        if ym == today.strftime('%Y-%m'):
            days = today.day
        else:
            days = 28 if month == 2 else (30 if month in (4, 6, 9, 11) else 31)
        acc_total = 0
        for i in range(cnt):
            day = rnd.randint(1, max(days - (0 if ym == today.strftime('%Y-%m') else 1), 1))
            if ym == today.strftime('%Y-%m') and day > today.day:
                day = today.day
            order_date = '%s-%02d' % (ym, day)
            cust = rnd.choice(customers)
            # 每单 1-3 个商品
            n_items = rnd.randint(1, 3)
            chosen = rnd.sample(products, min(n_items, len(products)))
            total = 0
            items = []
            for p in chosen:
                qty = rnd.randint(2, 40)
                price = p['sale_price']
                # 少量订单打折
                if rnd.random() < 0.25:
                    price = int(price * rnd.choice([0.85, 0.88, 0.9]))
                amt = price * qty
                total += amt
                items.append((p, qty, price, amt))
            discount = int(total * rnd.choice([0, 0, 0, 0.02, 0.05]))
            final = total - discount
            acc_total += final
            order_seq += 1
            order_no = 'SO%s%04d' % (order_date.replace('-', ''), order_seq % 10000)
            # 本月最后 2 单保持“待确认”
            pending = ym == today.strftime('%Y-%m') and i >= cnt - 2
            status = '待确认' if pending else '已出库'
            cust_id = cust['id']
            so_id = cur.execute(
                "INSERT INTO sales_orders (order_no,customer_id,warehouse_id,order_date,total_amount,"
                "discount,final_amount,total_cost,gross_profit,status,remark,created_by,created_at) "
                "VALUES (?,?,?,?,?,?,?,0,0,?,?,1,?)",
                (order_no, cust_id, wh['id'], order_date, total, discount, final,
                 status, DEMO_MARK, _now())).lastrowid
            n_so += 1
            total_cost = 0
            for p, qty, price, amt in items:
                cur.execute(
                    "INSERT INTO sales_order_items (order_id,product_id,price,cost_price,qty,amount) "
                    "VALUES (?,?,?,?,?,?)",
                    (so_id, p['id'], price, p['cost_price'], qty, amt))
                total_cost += p['cost_price'] * qty
                n_so_items += 1
            if status == '已出库':
                cur.execute("UPDATE sales_orders SET total_cost=?, gross_profit=? WHERE id=?",
                            (total_cost, final - total_cost, so_id))
                # 扣库存 + 库存流水
                for p, qty, price, amt in items:
                    cur.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?",
                                (qty, p['id'], qty))
                    cur.execute("UPDATE product_stocks SET stock=stock-? WHERE product_id=? AND warehouse_id=? AND stock>=?",
                                (qty, p['id'], wh['id'], qty))
                    n_stock += 1
                # 生成应收（账期 30 天）
                due = (datetime.strptime(order_date, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
                # 历史单：部分已回款，少数保持未收（制造逾期）
                if ym in ('2026-05', '2026-06', '2026-07'):
                    settled = rnd.random() < 0.7
                    if settled:
                        received = final
                        rstatus = '已收完'
                    else:
                        received = 0
                        rstatus = '未收'
                elif ym == '2026-08':
                    received = 0 if rnd.random() < 0.4 else int(final * 0.5)
                    rstatus = '未收' if received == 0 else '部分收款'
                elif ym == '2026-09':
                    received = 0 if rnd.random() < 0.5 else int(final * 0.3)
                    rstatus = '未收' if received == 0 else '部分收款'
                else:  # 本月
                    received = 0
                    rstatus = '未收'
                cur.execute(
                    "INSERT INTO receivables (order_id,order_no,customer_id,amount,received,status,due_date,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (so_id, order_no, cust_id, final, received, rstatus, due, _now()))
                n_recv += 1
                # 回款 → 资金流水
                if received > 0 and acc:
                    rc_no = 'RC%s%04d' % (today.strftime('%Y%m%d'), rnd.randint(1, 9999))
                    cur.execute(
                        "INSERT INTO receipts (receipt_no,customer_id,account_id,amount,method,receipt_date,"
                        "remark,created_by,created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                        (rc_no, cust_id, acc['id'], received, rnd.choice(['银行转账', '对公转账', '微信']),
                         order_date if rnd.random() < 0.8 else today.strftime('%Y-%m-%d'),
                         DEMO_MARK, _now()))
                    n_rc += 1
                    before = acc['balance']
                    cur.execute("UPDATE fund_accounts SET balance=balance+? WHERE id=?", (received, acc['id']))
                    cur.execute(
                        "INSERT INTO fund_logs (account_id,change_type,amount,before_balance,after_balance,"
                        "ref_no,remark,created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (acc['id'], '回款', received, before, before + received, rc_no, DEMO_MARK, _now()))
            month_sales.append((ym, final))
        # 该月按目标补齐波动：不强制，实际金额即可

    # ---- 采购入库（补库存 + 加权成本 + 应付） ----
    for mi, (ym, cnt, target, peak) in enumerate(months):
        if ym == today.strftime('%Y-%m'):
            continue
        month = int(ym[5:7])
        days = 28 if month == 2 else (30 if month in (4, 6, 9, 11) else 31)
        for i in range(rnd.randint(1, 2)):
            sup = rnd.choice(suppliers)
            day = rnd.randint(1, days)
            order_date = '%s-%02d' % (ym, day)
            chosen = rnd.sample(products, rnd.randint(1, 2))
            total = 0
            items = []
            for p in chosen:
                qty = rnd.randint(20, 80)
                price = int(p['purchase_price'] * rnd.choice([0.95, 1.0, 1.05]))
                amt = price * qty
                total += amt
                items.append((p, qty, price, amt))
            final = total
            order_no = 'PO%s%04d' % (order_date.replace('-', ''), rnd.randint(100, 999))
            po_id = cur.execute(
                "INSERT INTO purchase_orders (order_no,supplier_id,warehouse_id,order_date,total_amount,"
                "discount,final_amount,status,remark,created_by,created_at) VALUES (?,?,?,?,?,0,?,?,?,1,?)",
                (order_no, sup['id'], wh['id'], order_date, total, final, '已入库', DEMO_MARK, _now())).lastrowid
            n_pur += 1
            for p, qty, price, amt in items:
                cur.execute(
                    "INSERT INTO purchase_order_items (order_id,product_id,price,qty,amount,batch_no,expire_date) "
                    "VALUES (?,?,?,?,?,?,NULL)",
                    (po_id, p['id'], price, qty, amt, 'B' + order_date.replace('-', '')))
                n_pur_items += 1
                # 入库 + 加权成本 + 库存流水
                cur.execute("UPDATE products SET stock=stock+? WHERE id=?", (qty, p['id']))
                cur.execute("UPDATE product_stocks SET stock=stock+? WHERE product_id=? AND warehouse_id=?",
                            (qty, p['id'], wh['id']))
                old_stock = cur.execute("SELECT stock,cost_price FROM products WHERE id=?",
                                        (p['id'],)).fetchone()
                old_cost = old_stock['cost_price'] or 0
                new_stock = old_stock['stock']
                new_cost = round((max(new_stock - qty, 0) * old_cost + qty * price) / new_stock)
                cur.execute("UPDATE products SET cost_price=? WHERE id=?", (new_cost, p['id']))
                n_stock += 1
            # 应付（账期 45 天，部分已付）
            due = (datetime.strptime(order_date, '%Y-%m-%d') + timedelta(days=45)).strftime('%Y-%m-%d')
            paid = 0
            if ym in ('2026-05', '2026-06'):
                paid = final
                pstatus = '已付完'
            else:
                paid = int(final * 0.5)
                pstatus = '部分付款'
            cur.execute(
                "INSERT INTO payables (order_id,order_no,supplier_id,amount,paid,status,due_date,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (po_id, order_no, sup['id'], final, paid, pstatus, due, _now()))
            n_pay += 1
            if paid > 0 and acc:
                py_no = 'PY%s%04d' % (today.strftime('%Y%m%d'), rnd.randint(1, 9999))
                cur.execute(
                    "INSERT INTO payments (payment_no,supplier_id,account_id,amount,method,payment_date,"
                    "remark,created_by,created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                    (py_no, sup['id'], acc['id'], paid, rnd.choice(['银行转账', '对公转账']),
                     order_date, DEMO_MARK, _now()))
                n_py += 1
                before = acc['balance']
                cur.execute("UPDATE fund_accounts SET balance=balance-? WHERE id=?", (paid, acc['id']))
                cur.execute(
                    "INSERT INTO fund_logs (account_id,change_type,amount,before_balance,after_balance,"
                    "ref_no,remark,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (acc['id'], '付款', -paid, before, before - paid, py_no, DEMO_MARK, _now()))

    # ---- 待确认采购单（制造待办） ----
    for i in range(2):
        sup = rnd.choice(suppliers)
        p = rnd.choice(products)
        qty = rnd.randint(30, 60)
        price = int(p['purchase_price'] * 1.02)
        final = price * qty
        order_no = 'PO%s%04d' % (today.strftime('%Y%m%d'), rnd.randint(100, 999))
        po_id = cur.execute(
            "INSERT INTO purchase_orders (order_no,supplier_id,warehouse_id,order_date,total_amount,"
            "discount,final_amount,status,remark,created_by,created_at) VALUES (?,?,?,?,?,0,?,?,?,1,?)",
            (order_no, sup['id'], wh['id'], today.strftime('%Y-%m-%d'), final, final, '待确认', DEMO_MARK, _now())).lastrowid
        cur.execute(
            "INSERT INTO purchase_order_items (order_id,product_id,price,qty,amount,batch_no,expire_date) "
            "VALUES (?,?,?,?,?,?,NULL)",
            (po_id, p['id'], price, qty, final, 'B' + today.strftime('%Y%m%d')))
        n_pur_items += 1
        n_pur += 1

    # ---- 制造低库存预警（库存低于安全线） ----
    low_stock_targets = [
        ('中性笔 0.5mm', 6),
        ('无线鼠标 2.4G', 4),
        ('冷轧钢板 1.0mm', 2),
    ]
    for name, target in low_stock_targets:
        row = cur.execute("SELECT id FROM products WHERE name=? LIMIT 1", (name,)).fetchone()
        if row:
            cur.execute("UPDATE products SET stock=? WHERE id=?", (target, row['id']))
            cur.execute("UPDATE product_stocks SET stock=? WHERE product_id=? AND warehouse_id=?",
                        (target, row['id'], wh['id']))

    # ---- 客户跟进备注（触发工作台“客户待跟进”） ----
    follow_olds = [c for c in customers if c.get('remark') not in (DEMO_MARK,)]
    if len(follow_olds) >= 2:
        cur.execute("UPDATE customers SET remark='最近跟进：2026-09-18 洽谈下半年采购计划' WHERE id=?",
                    (follow_olds[0]['id'],))
        cur.execute("UPDATE customers SET remark='最近跟进：2026-09-25 已寄送报价单，待确认' WHERE id=?",
                    (follow_olds[1]['id'],))
    else:
        # 给任意前两个客户写跟进备注
        for i, c in enumerate(customers[:2]):
            cur.execute("UPDATE customers SET remark=? WHERE id=?",
                        (('最近跟进：2026-09-%02d 洽谈采购意向' % (15 + i * 5)), c['id']))

    conn.commit()

    # 汇总统计
    summary = {
        'ok': True,
        'msg': '演示数据已生成',
        'customers': n_cust,
        'suppliers': n_sup,
        'products': n_prod,
        'sales_orders': n_so,
        'sales_items': n_so_items,
        'receivables': n_recv,
        'receipts': n_rc,
        'purchase_orders': n_pur,
        'purchase_items': n_pur_items,
        'payables': n_pay,
        'payments': n_py,
        'stock_logs': n_stock,
        'backup': backup_path(db_path),
    }
    conn.close()
    return summary


def clear(db_path):
    """清理演示数据：恢复首次生成前的备份。"""
    bk = backup_path(db_path)
    if not os.path.exists(bk):
        return {'ok': False, 'msg': '没有找到演示数据备份，无需清理'}
    shutil.copy2(bk, db_path)
    os.remove(bk)
    return {'ok': True, 'msg': '演示数据已清理，数据库已还原'}
