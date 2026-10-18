# -*- coding: utf-8 -*-
"""AI 设置与摘要接口（开关式占位）

- /api/ai/status    查看 AI 是否已接入（不返回 Key 本身）
- PUT /api/ai/settings  保存 AI 配置（仅管理员；Key 留空则不覆盖）
- POST /api/ai/test 连通性测试（仅在已配置并开启时真正消耗少量 token）
- GET  /api/ai/summary  经营摘要：AI 优先，未配置/失败回退内置规则摘要
"""
from flask import Blueprint, request, Response, stream_with_context

from .. import ai as ai_mod
from ..models import set_ai_setting
from ..security import admin_required, login_required
from ..utils import fail, ok
from .report import collect_dashboard_data

bp = Blueprint('ai', __name__)


@bp.route('/ai/status')
@login_required
def api_ai_status():
    cfg = ai_mod.get_config()
    return ok({
        'enabled': cfg['enabled'],
        'api_base': cfg['api_base'],
        'model': cfg['model'],
        'has_key': bool(cfg['api_key']),
        'default_model': ai_mod.DEFAULT_MODEL,
    })


@bp.route('/ai/settings', methods=['PUT'])
@login_required
@admin_required
def api_ai_save():
    data = request.get_json(silent=True) or {}
    set_ai_setting('enabled', 1 if data.get('enabled') else 0)
    set_ai_setting('api_base', (data.get('api_base') or '').strip())
    set_ai_setting('model', (data.get('model') or ai_mod.DEFAULT_MODEL).strip())
    api_key = (data.get('api_key') or '').strip()
    if api_key:
        set_ai_setting('api_key', api_key)  # 留空则不覆盖旧 Key
    return ok(msg='AI 配置已保存，开关状态：%s' % ('已开启' if data.get('enabled') else '已关闭'))


@bp.route('/ai/test', methods=['POST'])
@login_required
@admin_required
def api_ai_test():
    """连通性测试：真实消耗极少量 token，仅验证链路"""
    try:
        reply = ai_mod.chat(
            [{'role': 'user', 'content': '请只回复两个字：正常'}], max_tokens=10, timeout=20)
        return ok({'reply': reply}, 'AI 连接正常')
    except ai_mod.AINotConfigured:
        return fail('尚未配置 AI 接口：请先在「系统 → AI 设置」填写 API 信息并打开开关')
    except Exception as e:
        return fail('连接失败：%s' % e)


@bp.route('/ai/summary')
@login_required
def api_ai_summary():
    """经营摘要：AI 优先，未配置/失败回退规则摘要"""
    try:
        d = collect_dashboard_data()
        result = ai_mod.summarize_dashboard(d)
        return ok(result)
    except Exception as e:
        return fail('摘要生成失败：%s' % e)


@bp.route('/ai/parse_order', methods=['POST'])
@login_required
def api_ai_parse_order():
    """对话式开单（Text-to-Action 雏形）：自然语言 -> 结构化销售订单"""
    from ..models import get_db
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return fail('请输入开单描述，例如：帮我给客户张三开一张销售单，A4纸 50 包，8 折')
    db = get_db()
    customers = [dict(r) for r in db.execute(
        "SELECT id, code, name FROM customers ORDER BY id").fetchall()]
    products = [dict(r) for r in db.execute(
        "SELECT id, code, name, unit, sale_price FROM products WHERE status=1 ORDER BY id").fetchall()]
    if not customers:
        return fail('系统还没有客户，请先在客户管理中添加')
    if not products:
        return fail('系统还没有商品，请先在商品管理中添加')
    try:
        result = ai_mod.parse_order(text, customers, products)
        return ok(result)
    except Exception as e:
        return fail('解析失败：%s' % e)


@bp.route('/ai/stats')
@login_required
@admin_required
def api_ai_stats():
    """AI 调用统计：今日/总计调用次数、token、平均耗时、成功率"""
    return ok(ai_mod.get_ai_stats())


@bp.route('/ai/daily_brief')
@login_required
def api_ai_daily_brief():
    """每日经营简报（为主动推送打基础：生成后缓存 1 小时）"""
    try:
        d = collect_dashboard_data()
        return ok(ai_mod.daily_brief(d))
    except Exception as e:
        return fail('简报生成失败：%s' % e)


@bp.route('/ai/query', methods=['POST'])
@login_required
def api_ai_query():
    """AI 对话式经营查询（Text-to-Insight）
    未接入 AI 时用规则引擎；接入后自动切换 LLM 意图识别。
    """
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return fail('请输入问题')
    try:
        result = ai_mod.answer_query(question)
        return ok(result)
    except Exception as e:
        return fail('查询失败：%s' % e)


@bp.route('/ai/report')
@login_required
def api_ai_report():
    """AI 经营报告：生成可打印/另存为 PDF 的 HTML 报告
    包含 KPI 概览、趋势图、异常预警、行动建议。
    """
    from .report import collect_dashboard_data
    from datetime import datetime
    d = collect_dashboard_data()
    summary = ai_mod.summarize_dashboard(d)
    kpi = d.get('kpi') or {}
    trend = d.get('trend') or []
    anomalies = summary.get('anomalies') or []
    actions = summary.get('actions') or []

    # 趋势图数据（SVG 柱状图）
    max_sales = max((t.get('sales') or 0) for t in trend) / 100.0 if trend else 1
    max_sales = max(max_sales, 1)
    bars = []
    for i, t in enumerate(trend):
        h = int((t.get('sales') or 0) / 100.0 / max_sales * 120)
        x = 40 + i * 60
        bars.append('<rect x="%d" y="%d" width="36" height="%d" rx="4" fill="#3b82f6"/>'
                    '<text x="%d" y="175" text-anchor="middle" font-size="11" fill="#6b7280">%s</text>'
                    % (x, 160 - h, h, x + 18, t.get('label', '')))

    anomaly_rows = ''.join(
        '<tr><td><span class="lv-%s">%s</span></td><td>%s</td></tr>'
        % (a.get('level', 'info'), a.get('level', 'info').upper(), a.get('text', ''))
        for a in anomalies) or '<tr><td colspan="2" style="text-align:center;color:#6b7280">无异常</td></tr>'

    action_items = ''.join('<li>%s</li>' % a.get('text', a) for a in actions)

    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>经营分析报告</title>
<style>
body{font-family:-apple-system,'Segoe UI',sans-serif;max-width:800px;margin:0 auto;padding:32px;color:#1f2937}
h1{font-size:24px;margin-bottom:4px}
.sub{color:#6b7280;font-size:13px;margin-bottom:24px}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
.kpi{background:#f8fafc;border:1px solid #e5e7eb;border-radius:10px;padding:14px}
.kpi-v{font-size:20px;font-weight:700}
.kpi-l{font-size:12px;color:#6b7280;margin-top:2px}
.section{margin-bottom:24px}
.section h2{font-size:16px;margin-bottom:10px;border-left:3px solid #3b82f6;padding-left:8px}
table{width:100%%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left}
.lv-danger{color:#dc2626;font-weight:600}
.lv-warning{color:#d97706;font-weight:600}
.lv-info{color:#2563eb;font-weight:600}
ol{padding-left:20px;font-size:13px;line-height:1.8}
.footer{margin-top:32px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:11px;color:#9ca3af;text-align:center}
@media print{body{padding:16px}.kpi-grid{grid-template-columns:repeat(4,1fr)}}
</style></head><body>
<h1>经营分析报告</h1>
<div class="sub">生成时间：%s ｜ 数据来源：ERP 系统</div>
<div class="kpi-grid">
<div class="kpi"><div class="kpi-v">%s</div><div class="kpi-l">今日销售额</div></div>
<div class="kpi"><div class="kpi-v">%s</div><div class="kpi-l">本月销售额</div></div>
<div class="kpi"><div class="kpi-v">%s</div><div class="kpi-l">本月毛利</div></div>
<div class="kpi"><div class="kpi-v">%s</div><div class="kpi-l">应收余额</div></div>
</div>
<div class="section"><h2>近 6 月销售趋势</h2>
<svg width="420" height="190" viewBox="0 0 420 190">%s</svg></div>
<div class="section"><h2>异常预警</h2>
<table><tr><th>级别</th><th>描述</th></tr>%s</table></div>
<div class="section"><h2>AI 行动建议</h2><ol>%s</ol></div>
<div class="section"><h2>经营概览</h2><p style="font-size:13px;line-height:1.8">%s</p></div>
<div class="footer">本报告由 ERP 系统 AI 模块自动生成 ｜ 仅供内部参考</div>
</body></html>""" % (
        datetime.now().strftime('%Y-%m-%d %H:%M'),
        '%.2f' % ((kpi.get('today_sales') or 0) / 100.0),
        '%.2f' % ((kpi.get('month_sales') or 0) / 100.0),
        '%.2f' % ((kpi.get('month_profit') or 0) / 100.0),
        '%.2f' % ((kpi.get('ar_balance') or 0) / 100.0),
        ''.join(bars),
        anomaly_rows,
        action_items,
        summary.get('overview', ''),
    )
    from flask import Response
    return Response(html, mimetype='text/html; charset=utf-8')


@bp.route('/ai/stream', methods=['POST'])
@login_required
def api_ai_stream():
    """AI 流式输出（SSE）：逐字返回经营查询结果。
    未接入 AI 时模拟流式（逐字发送规则引擎结果）；
    接入 LLM 后可切换为真实流式调用（chat/completions stream=true）。
    """
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return fail('请输入问题')

    def generate():
        try:
            result = ai_mod.answer_query(question)
            answer = result.get('answer', '')
            nav = result.get('nav')
            # 逐字发送（模拟流式，LLM 接入后替换为真实 SSE）
            for i in range(0, len(answer), 2):
                chunk = answer[i:i + 2]
                yield 'data: %s\n\n' % chunk.replace('\n', '\\n')
                import time as _t
                _t.sleep(0.02)  # 20ms/2字 ≈ 100字/秒
            if nav:
                yield 'data: [NAV]%s\n\n' % nav
            yield 'data: [DONE]\n\n'
        except Exception as e:
            yield 'data: [ERROR]%s\n\n' % str(e)

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})
