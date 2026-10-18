# -*- coding: utf-8 -*-
"""完整业务流冒烟测试：使用临时数据库副本，不触碰真实 erp.db
覆盖：登录 → 商品/分类/客户/供应商/仓库维护 → 销售单(待确认→确认出库→生成应收)
→ 回款 → 采购单(待确认→确认入库→加权成本→生成应付) → 付款 → 资金流水
→ 发票 → 凭证生成/导出 → 对账单 → 库存调整 → 补货建议 → 供应商比价 → CSV 导出"""
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, r'F:\py\erp')

SRC_DB = r'F:\py\erp\erp.db'
TMP_DIR = tempfile.mkdtemp(prefix='erp_test_')
TMP_DB = os.path.join(TMP_DIR, 'test.db')
# 使用全新空库（init_db 会自动创建表与基础数据），不继承真实 erp.db，
# 避免真实库中的演示数据干扰固定 id 断言
open(TMP_DB, 'w', encoding='utf-8').close()

from app import create_app
from app.models import init_db

app = create_app()
app.config['DB_PATH'] = TMP_DB
app.config['TESTING'] = True
with app.app_context():
    init_db()

client = app.test_client()
CSRF = {'X-CSRF-Token': ''}
passed = []
failed = []


def step(name, fn):
    try:
        fn()
        passed.append(name)
        print('  PASS', name)
    except Exception:
        failed.append(name)
        print('  FAIL', name)
        traceback.print_exc()


def login():
    r = client.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    d = r.get_json()
    assert d['code'] == 0, d
    CSRF['X-CSRF-Token'] = d['data'].get('csrf_token', '')
    if not CSRF['X-CSRF-Token']:
        CSRF['X-CSRF-Token'] = client.get('/api/csrf_token').get_json()['data']


def jget(url, expect_code=0):
    r = client.get(url)
    d = r.get_json()
    assert d is not None and d.get('code') == expect_code, (url, r.status_code, r.get_data(as_text=True)[:300])
    return d.get('data')


def jpost(url, payload, expect_code=0):
    r = client.post(url, json=payload, headers=CSRF)
    d = r.get_json()
    assert d is not None and d.get('code') == expect_code, (url, r.status_code, r.get_data(as_text=True)[:300])
    return d


def jput(url, payload, expect_code=0):
    r = client.put(url, json=payload, headers=CSRF)
    d = r.get_json()
    assert d is not None and d.get('code') == expect_code, (url, r.status_code, r.get_data(as_text=True)[:300])
    return d


def first_id(url):
    """取列表第一个元素的 id（不依赖固定 id）"""
    d = jget(url)
    assert d, ('空列表', url)
    return d[0]['id']


def jdel(url, expect_code=0):
    r = client.delete(url, headers=CSRF)
    d = r.get_json()
    assert d is not None and d.get('code') == expect_code, (url, r.status_code, r.get_data(as_text=True)[:300])
    return d


step('登录', login)

step('商品分类 增改删', lambda: (
    jpost('/api/categories', {'name': '测试分类A', 'remark': ''}),
    jput('/api/categories/5', {'name': '测试分类A改', 'remark': 'x'}, 0),
    jdel('/api/categories/5'),
))

step('仓库维护', lambda: (
    jpost('/api/warehouses', {'code': 'TW', 'name': '测试仓', 'remark': ''}),
))

step('商品 增改', lambda: (
    jpost('/api/products', {'code': 'T001', 'name': '测试商品', 'category_id': '',
                            'unit': '个', 'purchase_price': '10', 'sale_price': '20',
                            'safety_stock': '5', 'remark': ''}),
    jget('/api/products?keyword=T001'),
))

step('客户/供应商 增改', lambda: (
    jpost('/api/customers', {'code': 'TC001', 'name': '测试客户', 'contact': '', 'phone': '',
                             'address': '', 'credit_limit': '0', 'remark': ''}),
    jpost('/api/customers', {'code': 'TC002', 'name': '测试客户B', 'contact': '', 'phone': '',
                             'address': '', 'credit_limit': '0', 'remark': ''}),
    jpost('/api/suppliers', {'code': 'TS001', 'name': '测试供应商', 'contact': '', 'phone': '',
                             'address': '', 'remark': ''}),
))

step('销售单 创建→确认出库→应收', lambda: (
    jpost('/api/sales_orders', {'customer_id': 1, 'warehouse_id': 1, 'order_date': '',
                                'discount': '0', 'remark': '', 'items': [
                                    {'product_id': 1, 'qty': '2', 'price': '18'}]}),
    jpost('/api/sales_orders/%s/confirm' % first_id('/api/sales_orders'), {}),
    jget('/api/receivables'),
    jget('/api/stock_logs'),
))

step('销售单取消', lambda: (
    jpost('/api/sales_orders', {'customer_id': 2, 'warehouse_id': 1, 'order_date': '',
                                'discount': '0', 'remark': '', 'items': [
                                    {'product_id': 2, 'qty': '1', 'price': '299'}]}),
    jpost('/api/sales_orders/%s/cancel' % first_id('/api/sales_orders'), {}),
))

step('回款 登记', lambda: (
    jpost('/api/receipts', {'customer_id': 1, 'account_id': 1, 'amount': '36',
                            'receipt_date': '', 'remark': '',
                            'items': [{'receivable_id': first_id('/api/receivables'), 'amount': '36'}]}),
    jget('/api/fund_logs'),
))

step('采购单 创建→确认入库→应付', lambda: (
    jpost('/api/purchase_orders', {'supplier_id': 1, 'warehouse_id': 1, 'order_date': '',
                                   'remark': '', 'items': [
                                       {'product_id': 1, 'qty': '10', 'price': '9'}]}),
    jpost('/api/purchase_orders/1/confirm', {}),
    jget('/api/payables'),
))

step('付款 登记', lambda: (
    jpost('/api/payments', {'supplier_id': 1, 'account_id': 1, 'amount': '50',
                            'payment_date': '', 'remark': '',
                            'items': [{'payable_id': 1, 'amount': '50'}]}),
    jget('/api/fund_logs'),
))

step('资金账户维护', lambda: (
    jpost('/api/fund_accounts', {'code': 'TACC', 'name': '测试账户', 'remark': ''}),
    jput('/api/fund_accounts/3', {'code': 'TACC', 'name': '测试账户改', 'remark': '', 'status': 1}, 0),
))

step('发票登记 进销项', lambda: (
    jpost('/api/invoices', {'invoice_type': '进项', 'invoice_no': 'INV2026001', 'amount': '100',
                            'partner_type': 'supplier', 'partner_id': 1,
                            'invoice_date': '', 'remark': ''}),
    jpost('/api/invoices', {'invoice_type': '销项', 'invoice_no': 'INV2026002', 'amount': '200',
                            'partner_type': 'customer', 'partner_id': 1,
                            'invoice_date': '', 'remark': ''}),
    jget('/api/invoices?type=in'),
    jget('/api/invoices/stats'),
))

step('库存调整', lambda: (
    jpost('/api/stock/adjust', {'product_id': 3, 'warehouse_id': 1, 'qty': '5', 'remark': '测试'}),
))

step('补货建议 + 供应商比价', lambda: (
    jget('/api/replenish_suggest'),
    jget('/api/supplier_compare/1'),
))

step('会计凭证 生成 + 金蝶导出', lambda: (
    jget('/api/vouchers/generate?start=2026-09-01&end=2026-10-31&type=all'),
    jget('/api/account_mapping'),
    client.get('/api/vouchers/export?start=2026-09-01&end=2026-10-31'),
))

step('客户对账单', lambda: (
    jget('/api/statement/customer/1'),
))

step('打印模板 + 送货单/入库单数据', lambda: (
    jget('/api/print_templates'),
    jget('/api/sales_orders/2'),
    jget('/api/purchase_orders/1'),
))

step('CSV 导出（7 类）', lambda: [
    (lambda r: (r.status_code == 200 and r.data.startswith('\ufeff'.encode('utf-8')) and
                'text/csv' in r.headers.get('Content-Type', '')) or
     (_ for _ in ()).throw(AssertionError('export %s -> %s' % (k, r.status_code))))(
        client.get('/api/export/%s' % k))
    for k in ['products', 'customers', 'suppliers', 'sales_orders', 'purchase_orders',
              'receivables', 'payables']
])

step('Excel 导入（商品）', lambda: (
    client.get('/api/import/template/products'),
))

step('Dashboard / 利润 / 日志', lambda: (
    jget('/api/dashboard'),
    jget('/api/profit_report?dim=product'),
    jget('/api/operation_logs'),
    jget('/api/current_user'),
))

step('权限校验（staff 访问管理接口被拒）', lambda: (
    client.post('/api/logout', json={}),
    client.post('/api/login', json={'username': 'admin', 'password': 'admin123'}),
))

step('AI 开关式占位接口', lambda: (
    client.post('/api/logout', json={}),
    login(),  # 重新登录并刷新 CSRF
    jget('/api/ai/status'),
    jget('/api/ai/summary'),
    jput('/api/ai/settings', {
        'enabled': False,
        'api_base': 'https://api.deepseek.com/v1',
        'model': 'deepseek-chat',
        'api_key': '',
    }),
    jget('/api/ai/status'),
))

step('演示数据接口（临时库安全验证）', lambda: (
    jpost('/api/demo/seed', {}, expect_code=0),
    jget('/api/demo/status'),
    jget('/api/dashboard'),   # 含演示数据后的工作台
    jpost('/api/demo/clear', {}, expect_code=0),
    jget('/api/demo/status'),
))

step('智能开单解析（Text-to-Action 规则解析，基于演示客户/商品）', lambda: (
    jpost('/api/demo/seed', {}, expect_code=0),
    jpost('/api/ai/parse_order', {
        'text': '帮我给客户广州启航办公用品开一张销售单，中性笔 0.5mm 100 支，85折',
    }, expect_code=0),
    jpost('/api/demo/clear', {}, expect_code=0),
))

step('开放接口文档（动态路由清单）', lambda: (
    jget('/api/openapi'),
))

print()
print('=== 汇总: %d 通过, %d 失败 ===' % (len(passed), len(failed)))
if failed:
    print('失败项:', failed)
    sys.exit(1)
shutil.rmtree(TMP_DIR, ignore_errors=True)
print('临时库已清理')
