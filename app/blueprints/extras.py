# -*- coding: utf-8 -*-
"""演示数据 + 开放接口文档（P0/P2）

- POST /api/demo/seed    一键生成演示数据（首次自动备份 erp.db -> erp.db.demo_backup）
- POST /api/demo/clear   清理演示数据（还原备份，100% 可逆）
- GET  /api/demo/status  查询演示数据状态
- GET  /api/openapi      开放接口清单（供 RPA / 二次开发 / 面试演示）
"""
from flask import Blueprint, current_app

from ..demo import has_demo, seed, clear
from ..security import admin_required, login_required
from ..utils import ok, fail

bp = Blueprint('extras', __name__)

# 接口说明词典（路径 -> {desc, params, group}）
API_DOCS = {
    '/api/login': {'desc': '登录，返回用户信息与 CSRF Token', 'params': '{"username":"admin","password":"admin123"}', 'group': '认证'},
    '/api/logout': {'desc': '退出登录', 'params': '-', 'group': '认证'},
    '/api/current_user': {'desc': '当前登录用户信息', 'params': '-', 'group': '认证'},
    '/api/csrf_token': {'desc': '获取 CSRF Token（所有写操作需携带 X-CSRF-Token 头）', 'params': '-', 'group': '认证'},
    '/api/categories': {'desc': '商品分类列表 / 新增', 'params': 'POST: {"name":"办公耗材","remark":""}', 'group': '基础资料'},
    '/api/products': {'desc': '商品列表（支持 keyword） / 新增', 'params': 'POST: {"code":"P1001","name":"A4纸","category_id":1,...}', 'group': '基础资料'},
    '/api/customers': {'desc': '客户列表 / 新增', 'params': 'POST: {"code":"C001","name":"广州启航","credit_limit":50000}', 'group': '基础资料'},
    '/api/suppliers': {'desc': '供应商列表 / 新增', 'params': 'POST: {"code":"S001","name":"广东纸业"}', 'group': '基础资料'},
    '/api/warehouses': {'desc': '仓库列表 / 新增', 'params': 'POST: {"code":"WH01","name":"总仓"}', 'group': '基础资料'},
    '/api/employees': {'desc': '员工列表 / 新增', 'params': 'POST: {"name":"张三","position":"仓管"}', 'group': '基础资料'},
    '/api/users': {'desc': '系统用户列表 / 新增', 'params': 'POST: {"username":"kefu","password":"123","role":"staff"}', 'group': '基础资料'},
    '/api/sales_orders': {'desc': '销售订单列表 / 创建', 'params': 'POST: {"customer_id":1,"warehouse_id":1,"items":[{"product_id":1,"price":18,"qty":50}],"discount":0}', 'group': '销售'},
    '/api/sales_orders/<id>/confirm': {'desc': '销售订单确认出库（扣库存 + 生成应收）', 'params': '-', 'group': '销售'},
    '/api/sales_orders/<id>/cancel': {'desc': '取消销售订单', 'params': '-', 'group': '销售'},
    '/api/purchase_orders': {'desc': '采购订单列表 / 创建', 'params': 'POST: {"supplier_id":1,"warehouse_id":1,"items":[{"product_id":1,"price":12,"qty":100}]}', 'group': '采购'},
    '/api/purchase_orders/<id>/confirm': {'desc': '采购订单确认入库（加库存 + 加权成本 + 生成应付）', 'params': '-', 'group': '采购'},
    '/api/receivables': {'desc': '应收账款列表（支持 overdue 过滤）', 'params': 'GET: ?overdue=1', 'group': '财务'},
    '/api/payables': {'desc': '应付账款列表', 'params': '-', 'group': '财务'},
    '/api/receipts': {'desc': '回款单列表 / 登记回款', 'params': 'POST: {"customer_id":1,"account_id":1,"amount":1800,"items":[{"receivable_id":1,"amount":1800}]}', 'group': '财务'},
    '/api/payments': {'desc': '付款单列表 / 登记付款', 'params': 'POST: {"supplier_id":1,"account_id":1,"amount":1200,"items":[{"payable_id":1,"amount":1200}]}', 'group': '财务'},
    '/api/fund_accounts': {'desc': '资金账户列表 / 新增', 'params': 'POST: {"code":"ACC01","name":"工行基本户","atype":"银行"}', 'group': '财务'},
    '/api/fund_logs': {'desc': '资金日记账', 'params': 'GET: ?account_id=1', 'group': '财务'},
    '/api/stock_logs': {'desc': '库存流水', 'params': 'GET: ?product_id=1', 'group': '库存'},
    '/api/stock/transfer': {'desc': '库存调拨', 'params': 'POST: {"product_id":1,"from_warehouse_id":1,"to_warehouse_id":2,"qty":10}', 'group': '库存'},
    '/api/stock/replenish': {'desc': '补货建议（低于安全库存的商品）', 'params': '-', 'group': '库存'},
    '/api/stock/compare': {'desc': '供应商比价', 'params': '-', 'group': '库存'},
    '/api/dashboard': {'desc': '工作台数据（角色化 KPI + 待办 + 趋势）', 'params': '-', 'group': '报表'},
    '/api/profit_report': {'desc': '利润分析', 'params': 'GET: ?dim=product&start=2026-09-01&end=2026-10-31', 'group': '报表'},
    '/api/operation_logs': {'desc': '操作日志', 'params': '-', 'group': '报表'},
    '/api/export/<kind>': {'desc': 'CSV 导出（products/customers/suppliers/sales_orders/purchase_orders/receivables/payables）', 'params': '-', 'group': '报表'},
    '/api/invoices': {'desc': '发票列表 / 登记（invoice_type: 进项/销项, partner_type: customer/supplier）', 'params': 'POST: {"invoice_type":"销项","partner_type":"customer","partner_id":1,...}', 'group': '发票'},
    '/api/vouchers': {'desc': '会计凭证列表', 'params': '-', 'group': '凭证'},
    '/api/vouchers/generate': {'desc': '按日期段批量生成凭证', 'params': 'GET: ?start=2026-09-01&end=2026-10-31', 'group': '凭证'},
    '/api/vouchers/export': {'desc': '金蝶 CSV 导出', 'params': 'GET: ?start=&end=', 'group': '凭证'},
    '/api/import/templates/<kind>': {'desc': '下载 Excel 导入模板', 'params': '-', 'group': '高级'},
    '/api/import/upload': {'desc': 'Excel 批量导入（商品/客户等）', 'params': 'multipart: file=...', 'group': '高级'},
    '/api/backup': {'desc': '数据库备份（返回下载地址）', 'params': '-', 'group': '高级'},
    '/api/restore': {'desc': '从备份恢复数据库', 'params': 'multipart: file=...', 'group': '高级'},
    '/api/statement/customer/<id>': {'desc': '客户对账单', 'params': 'GET: ?start=&end=', 'group': '高级'},
    '/api/print_templates': {'desc': '打印模板列表 / 管理', 'params': '-', 'group': '高级'},
    '/api/ai/status': {'desc': 'AI 接入状态（不返回 Key）', 'params': '-', 'group': 'AI'},
    '/api/ai/settings': {'desc': '保存 AI 配置（enabled/api_base/api_key/model，Key 留空不覆盖）', 'params': 'PUT: {"enabled":true,"api_base":"https://api.deepseek.com/v1","model":"deepseek-chat","api_key":"sk-..."}', 'group': 'AI'},
    '/api/ai/test': {'desc': 'AI 连通性测试（接入后消耗极少量 token）', 'params': '-', 'group': 'AI'},
    '/api/ai/summary': {'desc': 'AI 经营摘要（未接入时返回规则摘要）', 'params': '-', 'group': 'AI'},
    '/api/ai/parse_order': {'desc': '自然语言解析销售订单（Text-to-Action 雏形）', 'params': 'POST: {"text":"帮我给客户A开一张销售单，A4纸50包，8折"}', 'group': 'AI'},
    '/api/demo/status': {'desc': '演示数据状态', 'params': '-', 'group': '演示'},
    '/api/demo/seed': {'desc': '一键生成演示数据（自动备份）', 'params': '-', 'group': '演示'},
    '/api/demo/clear': {'desc': '清理演示数据（还原备份）', 'params': '-', 'group': '演示'},
}


@bp.route('/demo/status')
@login_required
@admin_required
def api_demo_status():
    db_path = current_app.config['DB_PATH']
    has = has_demo(db_path)
    bk = db_path + '.demo_backup'
    return ok({'has_demo': has, 'backup_exists': __import__('os').path.exists(bk)})


@bp.route('/demo/seed', methods=['POST'])
@login_required
@admin_required
def api_demo_seed():
    db_path = current_app.config['DB_PATH']
    try:
        r = seed(db_path)
    except Exception as e:
        return fail('生成失败：%s' % e)
    if not r['ok']:
        return fail(r['msg'])
    return ok(r)


@bp.route('/demo/clear', methods=['POST'])
@login_required
@admin_required
def api_demo_clear():
    db_path = current_app.config['DB_PATH']
    try:
        r = clear(db_path)
    except Exception as e:
        return fail('清理失败：%s' % e)
    if not r['ok']:
        return fail(r['msg'])
    return ok(r['msg'])


@bp.route('/openapi')
@login_required
def api_openapi():
    """开放接口清单：由真实路由动态生成，说明词典人工维护"""
    from flask import current_app as app
    rules = []
    for rule in app.url_map.iter_rules():
        path = rule.rule
        if not path.startswith('/api/'):
            continue
        methods = sorted(m for m in rule.methods if m in ('GET', 'POST', 'PUT', 'DELETE'))
        if not methods:
            continue
        doc = API_DOCS.get(path) or {}
        group = doc.get('group') or '其他'
        rules.append({
            'path': path,
            'methods': methods,
            'desc': doc.get('desc', ''),
            'params': doc.get('params', ''),
            'group': group,
        })
    rules.sort(key=lambda r: (r['group'], r['path']))
    groups = {}
    for r in rules:
        groups.setdefault(r['group'], []).append(r)
    return ok({'count': len(rules), 'groups': groups})
