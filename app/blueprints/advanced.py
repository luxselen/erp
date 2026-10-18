# -*- coding: utf-8 -*-
"""高级工具：Excel 批量导入、数据备份恢复、客户对账单、打印数据"""
import os
import io
import shutil
from datetime import datetime
from flask import (Blueprint, request,
                   send_file, current_app, g)
from ..models import (get_db, now_str, today_str, to_int, yuan_to_fen,
                      log_op, atomic_add_stock, log_stock)
from ..security import login_required, admin_required
from ..utils import ok, fail

bp = Blueprint('advanced', __name__)


# ==================== Excel 批量导入 ====================

def _read_excel(file, headers_expected):
    """读取 Excel，返回 [[col1, col2, ...], ...]，跳过表头"""
    from openpyxl import load_workbook
    data = io.BytesIO(file.read())
    wb = load_workbook(data, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], headers_expected
    header = [str(x).strip() if x else '' for x in rows[0]]
    return rows[1:], header


@bp.route('/import/products', methods=['POST'])
@login_required
def api_import_products():
    """商品批量导入
    表头：编码* | 名称* | 分类 | 规格 | 单位 | 条码 | 进价 | 售价 | 安全库存
    """
    f = request.files.get('file')
    if not f:
        return fail('未上传文件')
    try:
        rows, header = _read_excel(f, [])
    except Exception as e:
        return fail('Excel 解析失败：' + str(e))

    db = get_db()
    success, updated, errors = 0, 0, []
    for i, row in enumerate(rows, start=2):
        if not row or not row[0]:
            continue
        try:
            code = str(row[0]).strip()
            name = str(row[1]).strip() if len(row) > 1 and row[1] else ''
            cat_name = str(row[2]).strip() if len(row) > 2 and row[2] else ''
            spec = str(row[3]).strip() if len(row) > 3 and row[3] else ''
            unit = str(row[4]).strip() if len(row) > 4 and row[4] else '个'
            barcode = str(row[5]).strip() if len(row) > 5 and row[5] else ''
            purchase = row[6] if len(row) > 6 else 0
            sale = row[7] if len(row) > 7 else 0
            safety = row[8] if len(row) > 8 else 0

            if not code or not name:
                errors.append('第 %d 行：编码或名称为空' % i)
                continue

            cat_id = None
            if cat_name:
                c = db.execute("SELECT id FROM categories WHERE name=?", (cat_name,)).fetchone()
                if c:
                    cat_id = c['id']
                else:
                    cur = db.execute("INSERT INTO categories (name, remark, created_at) VALUES (?,?,?)",
                                     (cat_name, '导入自动创建', now_str()))
                    cat_id = cur.lastrowid

            exists = db.execute("SELECT id FROM products WHERE code=?", (code,)).fetchone()
            p_purchase = yuan_to_fen(purchase)
            p_sale = yuan_to_fen(sale)
            if exists:
                db.execute(
                    "UPDATE products SET name=?, category_id=?, spec=?, unit=?, barcode=?, "
                    "purchase_price=?, sale_price=?, safety_stock=? WHERE id=?",
                    (name, cat_id, spec, unit, barcode,
                     p_purchase, p_sale, to_int(safety, 0), exists['id'])
                )
                updated += 1
            else:
                cur = db.execute(
                    "INSERT INTO products (code,name,category_id,spec,unit,barcode,"
                    "purchase_price,sale_price,cost_price,stock,safety_stock,status,"
                    "remark,created_at) VALUES (?,?,?,?,?,?,?,?,?,0,?,1,'',?)",
                    (code, name, cat_id, spec, unit, barcode,
                     p_purchase, p_sale, p_purchase, to_int(safety, 0), now_str())
                )
                db.execute("INSERT INTO product_stocks (product_id,warehouse_id,stock) VALUES (?,1,0)",
                           (cur.lastrowid,))
                success += 1
        except Exception as e:
            errors.append('第 %d 行：%s' % (i, str(e)))

    db.commit()
    log_op('导入', '商品', '成功 %d，更新 %d' % (success, updated))
    return ok({'success': success, 'updated': updated, 'errors': errors},
              '导入完成：新增 %d，更新 %d，失败 %d' % (success, updated, len(errors)))


@bp.route('/import/customers', methods=['POST'])
@login_required
def api_import_customers():
    """表头：编码* | 名称* | 联系人 | 电话 | 邮箱 | 地址 | 信用额度 | 等级"""
    f = request.files.get('file')
    if not f:
        return fail('未上传文件')
    try:
        rows, _ = _read_excel(f, [])
    except Exception as e:
        return fail('Excel 解析失败：' + str(e))

    db = get_db()
    success, updated, errors = 0, 0, []
    for i, row in enumerate(rows, start=2):
        if not row or not row[0]:
            continue
        try:
            code = str(row[0]).strip()
            name = str(row[1]).strip() if len(row) > 1 and row[1] else ''
            contact = str(row[2]).strip() if len(row) > 2 and row[2] else ''
            phone = str(row[3]).strip() if len(row) > 3 and row[3] else ''
            email = str(row[4]).strip() if len(row) > 4 and row[4] else ''
            address = str(row[5]).strip() if len(row) > 5 and row[5] else ''
            credit = row[6] if len(row) > 6 else 0
            level = str(row[7]).strip() if len(row) > 7 and row[7] else '普通'

            if not code or not name:
                errors.append('第 %d 行：编码或名称为空' % i)
                continue

            exists = db.execute("SELECT id FROM customers WHERE code=?", (code,)).fetchone()
            if exists:
                db.execute(
                    "UPDATE customers SET name=?, contact=?, phone=?, email=?, address=?, "
                    "credit_limit=?, level=? WHERE id=?",
                    (name, contact, phone, email, address, yuan_to_fen(credit), level, exists['id'])
                )
                updated += 1
            else:
                db.execute(
                    "INSERT INTO customers (code,name,contact,phone,email,address,"
                    "credit_limit,level,remark,created_at) VALUES (?,?,?,?,?,?,?,?,'',?)",
                    (code, name, contact, phone, email, address, yuan_to_fen(credit), level, now_str())
                )
                success += 1
        except Exception as e:
            errors.append('第 %d 行：%s' % (i, str(e)))

    db.commit()
    log_op('导入', '客户', '成功 %d，更新 %d' % (success, updated))
    return ok({'success': success, 'updated': updated, 'errors': errors},
              '导入完成：新增 %d，更新 %d，失败 %d' % (success, updated, len(errors)))


@bp.route('/import/suppliers', methods=['POST'])
@login_required
def api_import_suppliers():
    """表头：编码* | 名称* | 联系人 | 电话 | 邮箱 | 地址"""
    f = request.files.get('file')
    if not f:
        return fail('未上传文件')
    try:
        rows, _ = _read_excel(f, [])
    except Exception as e:
        return fail('Excel 解析失败：' + str(e))

    db = get_db()
    success, updated, errors = 0, 0, []
    for i, row in enumerate(rows, start=2):
        if not row or not row[0]:
            continue
        try:
            code = str(row[0]).strip()
            name = str(row[1]).strip() if len(row) > 1 and row[1] else ''
            contact = str(row[2]).strip() if len(row) > 2 and row[2] else ''
            phone = str(row[3]).strip() if len(row) > 3 and row[3] else ''
            email = str(row[4]).strip() if len(row) > 4 and row[4] else ''
            address = str(row[5]).strip() if len(row) > 5 and row[5] else ''

            if not code or not name:
                errors.append('第 %d 行：编码或名称为空' % i)
                continue

            exists = db.execute("SELECT id FROM suppliers WHERE code=?", (code,)).fetchone()
            if exists:
                db.execute("UPDATE suppliers SET name=?, contact=?, phone=?, email=?, address=? WHERE id=?",
                           (name, contact, phone, email, address, exists['id']))
                updated += 1
            else:
                db.execute("INSERT INTO suppliers (code,name,contact,phone,email,address,remark,created_at) "
                           "VALUES (?,?,?,?,?,?,'',?)",
                           (code, name, contact, phone, email, address, now_str()))
                success += 1
        except Exception as e:
            errors.append('第 %d 行：%s' % (i, str(e)))

    db.commit()
    log_op('导入', '供应商', '成功 %d，更新 %d' % (success, updated))
    return ok({'success': success, 'updated': updated, 'errors': errors},
              '导入完成：新增 %d，更新 %d，失败 %d' % (success, updated, len(errors)))


@bp.route('/import/stock', methods=['POST'])
@login_required
def api_import_stock():
    """库存调整导入
    表头：商品编码* | 仓库编码 | 数量* | 备注
    数量为正数则增加，负数则减少
    """
    f = request.files.get('file')
    if not f:
        return fail('未上传文件')
    try:
        rows, _ = _read_excel(f, [])
    except Exception as e:
        return fail('Excel 解析失败：' + str(e))

    db = get_db()
    success, errors = 0, []
    from ..models import atomic_deduct_stock
    for i, row in enumerate(rows, start=2):
        if not row or not row[0]:
            continue
        try:
            code = str(row[0]).strip()
            wh_code = str(row[1]).strip() if len(row) > 1 and row[1] else 'WH01'
            qty = to_int(row[2], 0) if len(row) > 2 else 0
            remark = str(row[3]).strip() if len(row) > 3 and row[3] else '批量导入调整'

            if not code or qty == 0:
                errors.append('第 %d 行：编码或数量为空/0' % i)
                continue

            p = db.execute("SELECT id FROM products WHERE code=?", (code,)).fetchone()
            if not p:
                errors.append('第 %d 行：商品编码 %s 不存在' % (i, code))
                continue
            w = db.execute("SELECT id FROM warehouses WHERE code=?", (wh_code,)).fetchone()
            if not w:
                errors.append('第 %d 行：仓库编码 %s 不存在' % (i, wh_code))
                continue

            if qty > 0:
                atomic_add_stock(db, p['id'], w['id'], qty)
            else:
                if not atomic_deduct_stock(db, p['id'], w['id'], -qty):
                    errors.append('第 %d 行：库存不足无法扣减' % i)
                    continue
            log_stock(db, p['id'], w['id'], '库存调整', qty, 'IMPORT', remark)
            success += 1
        except Exception as e:
            errors.append('第 %d 行：%s' % (i, str(e)))

    db.commit()
    log_op('导入', '库存', '成功 %d 条' % success)
    return ok({'success': success, 'errors': errors},
              '导入完成：成功 %d 条，失败 %d 条' % (success, len(errors)))


@bp.route('/import/template/<string:kind>')
@login_required
def api_import_template(kind):
    """下载导入模板"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = '模板'

    configs = {
        'products':  [['商品编码', '商品名称', '分类', '规格', '单位', '条码', '进价', '售价', '安全库存']],
        'customers': [['客户编码', '客户名称', '联系人', '电话', '邮箱', '地址', '信用额度', '等级']],
        'suppliers': [['供应商编码', '供应商名称', '联系人', '电话', '邮箱', '地址']],
        'stock':     [['商品编码', '仓库编码', '数量', '备注']],
    }
    headers = configs.get(kind, [['未知类型']])
    ws.append(headers[0])
    for col in range(1, len(headers[0]) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 18

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return send_file(out, as_attachment=True,
                     download_name='template_%s.xlsx' % kind,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ==================== 数据备份与恢复 ====================

@bp.route('/backup/export')
@login_required
@admin_required
def api_backup_export():
    """下载当前数据库文件"""
    db_path = current_app.config['DB_PATH']
    # 强制关闭所有连接并 flush
    db = get_db()
    db.commit()
    # 临时复制一份，避免发送过程中被占用
    tmp = db_path + '.backup'
    try:
        shutil.copy2(db_path, tmp)
    except Exception as e:
        return fail('备份失败：' + str(e))
    log_op('备份', '系统', '导出数据库')
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(tmp, as_attachment=True,
                     download_name='erp_backup_%s.db' % ts,
                     mimetype='application/octet-stream')


@bp.route('/backup/import', methods=['POST'])
@login_required
@admin_required
def api_backup_import():
    """上传 .db 文件覆盖当前数据库"""
    f = request.files.get('file')
    if not f:
        return fail('未上传文件')

    data = f.read(16)
    if not data.startswith(b'SQLite format 3'):
        return fail('文件不是有效的 SQLite 数据库')

    f.seek(0)
    db_path = current_app.config['DB_PATH']

    # 关闭当前连接（重要！）
    if 'db' in g:
        try:
            g.db.close()
        except Exception:
            pass
        g.pop('db', None)

    # 备份原库
    backup_path = db_path + '.old_' + datetime.now().strftime('%Y%m%d%H%M%S')
    try:
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)
        f.save(db_path)
    except Exception as e:
        return fail('恢复失败：' + str(e))

    log_op('恢复', '系统', '导入数据库，原库已备份到 ' + os.path.basename(backup_path))
    return ok({'backup': os.path.basename(backup_path)}, '恢复成功，请重启程序')


# ==================== 客户对账单 ====================

@bp.route('/statement/customer/<int:cid>')
@login_required
def api_statement(cid):
    """客户对账单：期初 + 本期发生 + 期末"""
    db = get_db()
    cust = db.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    if not cust:
        return fail('客户不存在')

    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()
    if not end:
        end = today_str()
    if not start:
        start = '2020-01-01'

    # 期初：截止 start 前一天的应收余额
    opening = db.execute(
        "SELECT IFNULL(SUM(amount) - SUM(received),0) AS b FROM receivables "
        "WHERE customer_id=? AND created_at < ?", (cid, start + ' 00:00:00')
    ).fetchone()['b'] or 0

    transactions = []

    # 本期销售订单（应收）
    orders = db.execute(
        "SELECT order_no, order_date, final_amount FROM sales_orders "
        "WHERE customer_id=? AND status='已出库' AND order_date >= ? AND order_date <= ? "
        "ORDER BY order_date", (cid, start, end)
    ).fetchall()
    for o in orders:
        transactions.append({
            'date': o['order_date'], 'type': '销售', 'no': o['order_no'],
            'debit': o['final_amount'], 'credit': 0, 'memo': '销售订单出库'
        })

    # 本期回款
    receipts = db.execute(
        "SELECT receipt_no, receipt_date, amount FROM receipts "
        "WHERE customer_id=? AND receipt_date >= ? AND receipt_date <= ? "
        "ORDER BY receipt_date", (cid, start, end)
    ).fetchall()
    for r in receipts:
        transactions.append({
            'date': r['receipt_date'], 'type': '回款', 'no': r['receipt_no'],
            'debit': 0, 'credit': r['amount'], 'memo': '客户回款'
        })

    # 计算余额
    transactions.sort(key=lambda x: x['date'])
    balance = opening
    total_debit = 0
    total_credit = 0
    for t in transactions:
        balance += t['debit'] - t['credit']
        t['balance'] = balance
        total_debit += t['debit']
        total_credit += t['credit']

    return ok({
        'customer': dict(cust),
        'period': {'start': start, 'end': end},
        'opening_balance': opening,
        'transactions': transactions,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'closing_balance': balance
    })


# ==================== 打印模板 ====================

@bp.route('/print_templates')
@login_required
def api_template_list():
    db = get_db()
    rows = db.execute("SELECT * FROM print_templates ORDER BY id").fetchall()
    return ok([dict(r) for r in rows])


@bp.route('/print_templates/<int:tid>', methods=['PUT'])
@login_required
def api_template_update(tid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        "UPDATE print_templates SET name=?, company_name=?, header_text=?, footer_text=? WHERE id=?",
        ((data.get('name') or '').strip(),
         (data.get('company_name') or '').strip(),
         (data.get('header_text') or '').strip(),
         (data.get('footer_text') or '').strip(), tid)
    )
    db.commit()
    return ok(msg='模板已保存')


@bp.route('/print_templates/default/<string:ttype>')
@login_required
def api_template_default(ttype):
    db = get_db()
    row = db.execute(
        "SELECT * FROM print_templates WHERE ttype=? ORDER BY is_default DESC, id LIMIT 1",
        (ttype,)
    ).fetchone()
    if not row:
        return ok({'company_name': 'XX贸易有限公司', 'header_text': '', 'footer_text': ''})
    return ok(dict(row))