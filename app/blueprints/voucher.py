# -*- coding: utf-8 -*-
"""会计凭证生成与导出（可导入金蝶/用友）"""
from flask import Blueprint, request, Response
from datetime import datetime
from ..models import (get_db, now_str, get_account_map,
                      fen_to_yuan)
from ..security import login_required
from ..utils import ok

bp = Blueprint('voucher', __name__)


@bp.route('/vouchers/generate')
@login_required
def api_generate():
    """生成凭证预览，不写库"""
    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()
    vtype = (request.args.get('type') or 'all').strip()  # all/sales/purchase/receipt/payment

    db = get_db()
    acc = get_account_map(db)

    where_date = ""
    params = []
    if start:
        where_date += " AND order_date >= ?"
        params.append(start)
    if end:
        where_date += " AND order_date <= ?"
        params.append(end)

    vouchers = []

    # 销售出库
    if vtype in ('all', 'sales'):
        orders = db.execute(
            "SELECT * FROM sales_orders WHERE status='已出库'" + where_date +
            " ORDER BY id", params
        ).fetchall()
        for o in orders:
            entries = []
            # 借：应收账款 贷：主营业务收入
            entries.append({'summary': '销售给 %s' % o['order_no'], 'code': acc['receivable']['code'],
                            'name': acc['receivable']['name'], 'debit': o['final_amount'], 'credit': 0})
            entries.append({'summary': '销售收入', 'code': acc['sales_revenue']['code'],
                            'name': acc['sales_revenue']['name'], 'debit': 0, 'credit': o['final_amount']})
            # 结转成本
            entries.append({'summary': '结转成本', 'code': acc['sales_cost']['code'],
                            'name': acc['sales_cost']['name'], 'debit': o['total_cost'], 'credit': 0})
            entries.append({'summary': '结转成本', 'code': acc['inventory']['code'],
                            'name': acc['inventory']['name'], 'debit': 0, 'credit': o['total_cost']})

            vouchers.append({
                'voucher_no': 'SALE-' + o['order_no'],
                'voucher_date': o['order_date'],
                'biz_type': '销售',
                'biz_id': o['id'],
                'summary': '销售出库 %s' % o['order_no'],
                'entries': entries
            })

    # 采购入库
    if vtype in ('all', 'purchase'):
        orders = db.execute(
            "SELECT * FROM purchase_orders WHERE status='已入库'" + where_date +
            " ORDER BY id", params
        ).fetchall()
        for o in orders:
            entries = [
                {'summary': '采购入库 %s' % o['order_no'], 'code': acc['inventory']['code'],
                 'name': acc['inventory']['name'], 'debit': o['final_amount'], 'credit': 0},
                {'summary': '采购应付', 'code': acc['payable']['code'],
                 'name': acc['payable']['name'], 'debit': 0, 'credit': o['final_amount']},
            ]
            vouchers.append({
                'voucher_no': 'PUR-' + o['order_no'],
                'voucher_date': o['order_date'],
                'biz_type': '采购',
                'biz_id': o['id'],
                'summary': '采购入库 %s' % o['order_no'],
                'entries': entries
            })

    # 回款
    if vtype in ('all', 'receipt'):
        p2 = []
        w2 = ""
        if start:
            w2 += " AND receipt_date >= ?"
            p2.append(start)
        if end:
            w2 += " AND receipt_date <= ?"
            p2.append(end)
        receipts = db.execute("SELECT * FROM receipts WHERE 1=1" + w2 + " ORDER BY id", p2).fetchall()
        for r in receipts:
            entries = [
                {'summary': '客户回款 %s' % r['receipt_no'], 'code': acc['bank']['code'],
                 'name': acc['bank']['name'], 'debit': r['amount'], 'credit': 0},
                {'summary': '客户回款', 'code': acc['receivable']['code'],
                 'name': acc['receivable']['name'], 'debit': 0, 'credit': r['amount']},
            ]
            vouchers.append({
                'voucher_no': 'REC-' + r['receipt_no'],
                'voucher_date': r['receipt_date'],
                'biz_type': '回款',
                'biz_id': r['id'],
                'summary': '客户回款 %s' % r['receipt_no'],
                'entries': entries
            })

    # 付款
    if vtype in ('all', 'payment'):
        p3 = []
        w3 = ""
        if start:
            w3 += " AND payment_date >= ?"
            p3.append(start)
        if end:
            w3 += " AND payment_date <= ?"
            p3.append(end)
        payments = db.execute("SELECT * FROM payments WHERE 1=1" + w3 + " ORDER BY id", p3).fetchall()
        for pm in payments:
            entries = [
                {'summary': '供应商付款 %s' % pm['payment_no'], 'code': acc['payable']['code'],
                 'name': acc['payable']['name'], 'debit': pm['amount'], 'credit': 0},
                {'summary': '供应商付款', 'code': acc['bank']['code'],
                 'name': acc['bank']['name'], 'debit': 0, 'credit': pm['amount']},
            ]
            vouchers.append({
                'voucher_no': 'PAY-' + pm['payment_no'],
                'voucher_date': pm['payment_date'],
                'biz_type': '付款',
                'biz_id': pm['id'],
                'summary': '供应商付款 %s' % pm['payment_no'],
                'entries': entries
            })

    # 计算合计
    total_debit = sum(sum(e['debit'] for e in v['entries']) for v in vouchers)
    total_credit = sum(sum(e['credit'] for e in v['entries']) for v in vouchers)

    return ok({
        'vouchers': vouchers,
        'summary': {
            'count': len(vouchers),
            'total_debit': total_debit,
            'total_credit': total_credit
        }
    })


@bp.route('/vouchers/export')
@login_required
def api_export():
    """导出为 CSV（金蝶 KIS 凭证导入格式）"""
    start = (request.args.get('start') or '').strip()
    end = (request.args.get('end') or '').strip()
    vtype = (request.args.get('type') or 'all').strip()

    db = get_db()
    vouchers = _build_vouchers(db, start, end, vtype)

    lines = ['凭证日期,凭证字号,摘要,科目代码,科目名称,借方金额,贷方金额']
    seq = 1
    for v in vouchers:
        word = '记'
        for e in v['entries']:
            debit = fen_to_yuan(e['debit']) if e['debit'] else ''
            credit = fen_to_yuan(e['credit']) if e['credit'] else ''
            row = [
                v['voucher_date'],
                '%s-%04d' % (word, seq),
                e['summary'].replace(',', '，'),
                e['code'],
                e['name'],
                debit,
                credit
            ]
            lines.append(','.join(str(x) for x in row))
        seq += 1

    csv_content = '\ufeff' + '\n'.join(lines)
    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename=vouchers_%s.csv'
                                   % datetime.now().strftime('%Y%m%d%H%M%S')
        }
    )


def _build_vouchers(db, start, end, vtype):
    """抽出凭证构造逻辑，供 generate 和 export 共用"""
    acc = get_account_map(db)
    vouchers = []

    where_date = ""
    params = []
    if start:
        where_date += " AND order_date >= ?"
        params.append(start)
    if end:
        where_date += " AND order_date <= ?"
        params.append(end)

    if vtype in ('all', 'sales'):
        orders = db.execute("SELECT * FROM sales_orders WHERE status='已出库'" + where_date, params).fetchall()
        for o in orders:
            entries = [
                {'summary': '销售 %s' % o['order_no'], 'code': acc['receivable']['code'],
                 'name': acc['receivable']['name'], 'debit': o['final_amount'], 'credit': 0},
                {'summary': '销售收入', 'code': acc['sales_revenue']['code'],
                 'name': acc['sales_revenue']['name'], 'debit': 0, 'credit': o['final_amount']},
                {'summary': '结转成本', 'code': acc['sales_cost']['code'],
                 'name': acc['sales_cost']['name'], 'debit': o['total_cost'], 'credit': 0},
                {'summary': '结转成本', 'code': acc['inventory']['code'],
                 'name': acc['inventory']['name'], 'debit': 0, 'credit': o['total_cost']},
            ]
            vouchers.append({'voucher_date': o['order_date'], 'biz_type': '销售',
                             'biz_id': o['id'], 'entries': entries})

    if vtype in ('all', 'purchase'):
        orders = db.execute("SELECT * FROM purchase_orders WHERE status='已入库'" + where_date, params).fetchall()
        for o in orders:
            entries = [
                {'summary': '采购 %s' % o['order_no'], 'code': acc['inventory']['code'],
                 'name': acc['inventory']['name'], 'debit': o['final_amount'], 'credit': 0},
                {'summary': '采购应付', 'code': acc['payable']['code'],
                 'name': acc['payable']['name'], 'debit': 0, 'credit': o['final_amount']},
            ]
            vouchers.append({'voucher_date': o['order_date'], 'biz_type': '采购',
                             'biz_id': o['id'], 'entries': entries})

    w2 = ""
    p2 = []
    if start:
        w2 += " AND receipt_date >= ?"
        p2.append(start)
    if end:
        w2 += " AND receipt_date <= ?"
        p2.append(end)
    if vtype in ('all', 'receipt'):
        for r in db.execute("SELECT * FROM receipts WHERE 1=1" + w2, p2).fetchall():
            entries = [
                {'summary': '回款 %s' % r['receipt_no'], 'code': acc['bank']['code'],
                 'name': acc['bank']['name'], 'debit': r['amount'], 'credit': 0},
                {'summary': '回款', 'code': acc['receivable']['code'],
                 'name': acc['receivable']['name'], 'debit': 0, 'credit': r['amount']},
            ]
            vouchers.append({'voucher_date': r['receipt_date'], 'biz_type': '回款',
                             'biz_id': r['id'], 'entries': entries})

    w3 = ""
    p3 = []
    if start:
        w3 += " AND payment_date >= ?"
        p3.append(start)
    if end:
        w3 += " AND payment_date <= ?"
        p3.append(end)
    if vtype in ('all', 'payment'):
        for pm in db.execute("SELECT * FROM payments WHERE 1=1" + w3, p3).fetchall():
            entries = [
                {'summary': '付款 %s' % pm['payment_no'], 'code': acc['payable']['code'],
                 'name': acc['payable']['name'], 'debit': pm['amount'], 'credit': 0},
                {'summary': '付款', 'code': acc['bank']['code'],
                 'name': acc['bank']['name'], 'debit': 0, 'credit': pm['amount']},
            ]
            vouchers.append({'voucher_date': pm['payment_date'], 'biz_type': '付款',
                             'biz_id': pm['id'], 'entries': entries})

    return vouchers


@bp.route('/account_mapping')
@login_required
def api_mapping_list():
    db = get_db()
    rows = db.execute("SELECT * FROM account_mapping ORDER BY id").fetchall()
    return ok([dict(r) for r in rows])


@bp.route('/account_mapping/<int:mid>', methods=['PUT'])
@login_required
def api_mapping_update(mid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        "UPDATE account_mapping SET code=?, name=?, direction=?, updated_at=? WHERE id=?",
        ((data.get('code') or '').strip(), (data.get('name') or '').strip(),
         (data.get('direction') or '借').strip(), now_str(), mid)
    )
    db.commit()
    return ok(msg='修改成功')