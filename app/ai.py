# -*- coding: utf-8 -*-
"""AI 接入占位模块（开关式）

设计目标：
- 未配置时：不消耗任何 token，/api/ai/summary 返回内置「规则摘要」；
- 用户接入 API 后（系统 → AI 设置 填写 Base/Key/Model 并开启开关），
  摘要与后续 AI 能力自动切换为真实大模型调用；
- 仅使用 Python 标准库（urllib），兼容任意 OpenAI 风格 /chat/completions 接口
  （OpenAI / DeepSeek / 通义 / Moonshot / 本地 Ollama 等）。

接入方式（用户侧）：
  API Base 示例：https://api.openai.com/v1
                 https://api.deepseek.com/v1
                 http://127.0.0.1:11434/v1   （Ollama 本地）
"""
import json
import re
import time
import urllib.request

from .models import get_ai_setting

DEFAULT_MODEL = 'gpt-4o-mini'

# ============================================================
# 内存缓存（5 分钟 TTL，避免重复调用 LLM 烧 token）
# ============================================================
_cache = {}
_CACHE_TTL = 300  # 秒


def _cache_get(key):
    item = _cache.get(key)
    if not item:
        return None
    value, expire = item
    if time.time() > expire:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key, value):
    _cache[key] = (value, time.time() + _CACHE_TTL)


def _data_fingerprint(d):
    """从工作台数据生成缓存 key（只取影响摘要的关键字段）"""
    k = d.get('kpi') or {}
    a = d.get('alerts') or {}
    t = d.get('trend') or []
    parts = [
        k.get('today_sales', 0), k.get('month_sales_amount', 0),
        k.get('month_gross_profit', 0), k.get('ar_balance', 0),
        k.get('fund_total', 0),
        a.get('overdue_ar_count', 0), a.get('low_stock_count', 0),
        a.get('pending_sales_count', 0), a.get('pending_purchase_count', 0),
    ]
    for m in t[-3:]:
        parts.extend([m.get('month', ''), m.get('sales', 0), m.get('profit', 0)])
    return 'dash:' + str(hash(tuple(parts)))


# ============================================================
# AI 调用日志（成本统计与可观测性）
# ============================================================

def log_ai_call(call_type, status, duration_ms=0, prompt_tokens=0,
                completion_tokens=0, error_msg=''):
    """记录一次 AI 调用到 ai_call_logs 表"""
    try:
        from .models import get_db
        db = get_db()
        db.execute(
            "INSERT INTO ai_call_logs (call_type,status,duration_ms,prompt_tokens,completion_tokens,error_msg) "
            "VALUES (?,?,?,?,?,?)",
            (call_type, status, int(duration_ms), int(prompt_tokens),
             int(completion_tokens), str(error_msg)[:300]))
        db.commit()
    except Exception:
        pass  # 日志失败不影响主流程


class AINotConfigured(Exception):
    """AI 尚未配置或开关未打开"""


def ai_enabled():
    return get_ai_setting('enabled', '0') == '1'


def get_config():
    return {
        'enabled': ai_enabled(),
        'api_base': (get_ai_setting('api_base') or '').strip(),
        'api_key': (get_ai_setting('api_key') or '').strip(),
        'model': (get_ai_setting('model') or DEFAULT_MODEL).strip(),
    }


def chat(messages, max_tokens=800, timeout=30, call_type='chat', retries=2):
    """调用 OpenAI 兼容 /chat/completions。未配置时抛 AINotConfigured。
    自动重试（指数退避）+ 输出安全过滤 + 调用日志。
    """
    cfg = get_config()
    if not cfg['enabled'] or not cfg['api_key']:
        raise AINotConfigured('AI 未配置或开关未开启')
    base = (cfg['api_base'] or 'https://api.openai.com/v1').rstrip('/')
    body = json.dumps({
        'model': cfg['model'] or DEFAULT_MODEL,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': 0.3,
    }).encode('utf-8')

    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(base + '/chat/completions', data=body, headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + cfg['api_key'],
        })
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            duration = (time.time() - t0) * 1000
            usage = data.get('usage') or {}
            raw = data['choices'][0]['message']['content'].strip()
            result = _sanitize_ai_output(raw)
            log_ai_call(call_type, 'success', duration,
                        usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            return result
        except urllib.error.HTTPError as e:
            duration = (time.time() - t0) * 1000
            detail = e.read().decode('utf-8', 'ignore')[:200]
            last_err = RuntimeError('HTTP %s: %s' % (e.code, detail))
            # 429(限流) / 5xx(服务端) 才重试
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = 2 ** attempt * 0.5  # 0.5s, 1s
                time.sleep(wait)
                continue
            log_ai_call(call_type, 'failed', duration, error_msg='HTTP %s: %s' % (e.code, detail))
            raise last_err
        except Exception as e:
            duration = (time.time() - t0) * 1000
            last_err = RuntimeError('网络请求失败: %s' % e)
            if attempt < retries:
                time.sleep(2 ** attempt * 0.5)
                continue
            log_ai_call(call_type, 'failed', duration, error_msg=str(e)[:200])
            raise last_err
    raise last_err


def _sanitize_ai_output(text):
    """AI 输出安全过滤：防止 prompt injection 残留的指令泄漏
    - 去除常见注入标记（如 "Ignore previous instructions"）
    - 截断过长输出
    - 去除控制字符
    """
    if not text:
        return ''
    # 去除控制字符（保留换行和制表）
    cleaned = ''.join(c for c in text if c == '\n' or c == '\t' or ord(c) >= 32)
    # 去除常见 prompt injection 标记
    injection_patterns = [
        r'(?i)ignore\s+(all\s+)?previous\s+instructions?',
        r'(?i)disregard\s+(all\s+)?previous\s+',
        r'(?i)you\s+are\s+now\s+',
        r'(?i)system\s*:\s*',
    ]
    for pat in injection_patterns:
        cleaned = re.sub(pat, '[已过滤]', cleaned)
    # 截断过长输出（最多 4000 字符）
    if len(cleaned) > 4000:
        cleaned = cleaned[:4000] + '\n...（输出已截断）'
    return cleaned.strip()


# ============================================================
# 经营摘要
# ============================================================

def _fmt(v):
    return '¥{:,.2f}'.format(v)


def summarize_dashboard(d):
    """工作台经营摘要：AI 优先，未配置或失败时回退规则摘要。
    5 分钟内存缓存（按数据指纹），避免重复调用 LLM 烧 token。
    返回结构化：{source, overview, anomalies:[{level,text}], actions:[...], raw_text, cached}
    """
    cache_key = _data_fingerprint(d)
    cached = _cache_get(cache_key)
    if cached:
        cached['cached'] = True
        log_ai_call('summary', 'cached', 0)
        return cached

    if ai_enabled():
        try:
            prompt = _dashboard_prompt(d)
            text = chat([{'role': 'user', 'content': prompt}], max_tokens=500, call_type='summary')
            structured = _parse_ai_summary_json(text)
            structured['source'] = 'ai'
            structured['ai_error'] = None
            structured['cached'] = False
            _cache_set(cache_key, structured)
            return structured
        except AINotConfigured:
            pass
        except Exception as e:
            r = rule_summary(d)
            r['source'] = 'fallback'
            r['ai_error'] = str(e)
            r['cached'] = False
            log_ai_call('summary', 'fallback', error_msg=str(e)[:200])
            return r
    r = rule_summary(d)
    r['source'] = 'rule'
    r['ai_error'] = None
    r['cached'] = False
    _cache_set(cache_key, r)
    return r


def _parse_ai_summary_json(text):
    """尝试把 AI 返回的文本解析成结构化摘要；失败则把全文当 overview"""
    t = (text or '').strip()
    if t.startswith('```'):
        t = t.strip('`')
        if t.startswith('json'):
            t = t[4:]
    try:
        data = json.loads(t)
        if isinstance(data, dict):
            overview = (data.get('overview') or '').strip()
            anomalies = []
            for a in (data.get('anomalies') or []):
                if isinstance(a, dict):
                    level = a.get('level', 'warning')
                    if level not in ('danger', 'warning', 'info'):
                        level = 'warning'
                    txt = (a.get('text') or a.get('msg') or '').strip()
                    if txt:
                        anomalies.append({'level': level, 'text': txt})
                elif isinstance(a, str) and a.strip():
                    anomalies.append({'level': 'warning', 'text': a.strip()})
            actions = []
            for a in (data.get('actions') or []):
                if isinstance(a, dict):
                    txt = (a.get('text') or a.get('action') or '').strip()
                    if txt:
                        actions.append({'text': txt, 'nav': a.get('nav')})
                elif isinstance(a, str) and a.strip():
                    actions.append({'text': a.strip(), 'nav': None})
            if overview or anomalies or actions:
                return {
                    'overview': overview,
                    'anomalies': anomalies,
                    'actions': actions,
                    'raw_text': text or '',
                }
    except Exception:
        pass
    return {'overview': text or '', 'anomalies': [], 'actions': [], 'raw_text': text or ''}


# ============================================================
# AI 调用统计
# ============================================================

def get_ai_stats():
    """返回 AI 调用统计：今日/总计调用次数、成功/失败、总 token、平均耗时"""
    try:
        from .models import get_db
        db = get_db()
        today = time.strftime('%Y-%m-%d')
        total_row = db.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(duration_ms),0) d, "
            "COALESCE(SUM(prompt_tokens),0) pt, COALESCE(SUM(completion_tokens),0) ct "
            "FROM ai_call_logs").fetchone()
        today_row = db.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(duration_ms),0) d, "
            "COALESCE(SUM(prompt_tokens),0) pt, COALESCE(SUM(completion_tokens),0) ct "
            "FROM ai_call_logs WHERE date(created_at)=?", (today,)).fetchone()
        status_row = db.execute(
            "SELECT status, COUNT(*) c FROM ai_call_logs "
            "WHERE date(created_at)=? GROUP BY status", (today,)).fetchall()
        status_map = {r['status']: r['c'] for r in status_row}
        return {
            'today': {
                'calls': today_row['c'],
                'avg_ms': int(today_row['d'] / today_row['c']) if today_row['c'] else 0,
                'prompt_tokens': today_row['pt'],
                'completion_tokens': today_row['ct'],
                'success': status_map.get('success', 0),
                'failed': status_map.get('failed', 0),
                'cached': status_map.get('cached', 0),
                'fallback': status_map.get('fallback', 0),
            },
            'total': {
                'calls': total_row['c'],
                'avg_ms': int(total_row['d'] / total_row['c']) if total_row['c'] else 0,
                'prompt_tokens': total_row['pt'],
                'completion_tokens': total_row['ct'],
            },
        }
    except Exception:
        return {'today': {'calls': 0, 'avg_ms': 0, 'prompt_tokens': 0, 'completion_tokens': 0,
                           'success': 0, 'failed': 0, 'cached': 0, 'fallback': 0},
                'total': {'calls': 0, 'avg_ms': 0, 'prompt_tokens': 0, 'completion_tokens': 0}}


# ============================================================
# 每日简报（为主动推送打基础：生成后缓存，后续可推微信/邮件）
# ============================================================

def daily_brief(d):
    """生成每日经营简报（适合推送的格式），缓存 1 小时。
    返回：{date, title, sections:[{title, items}], summary_text}
    """
    cache_key = 'brief:' + time.strftime('%Y-%m-%d') + ':' + _data_fingerprint(d)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    k = d.get('kpi') or {}
    a = d.get('alerts') or {}
    overdue = d.get('overdue_receivables') or []
    low_stock = d.get('low_stock') or []

    sections = []
    # 经营概览
    sections.append({
        'title': '经营概览',
        'items': [
            '今日销售额 %s（%s 笔订单）' % (_fmt((k.get('today_sales') or 0) / 100.0), k.get('today_order_count', 0)),
            '本月销售额 %s，毛利 %s' % (_fmt((k.get('month_sales_amount') or 0) / 100.0),
                                        _fmt((k.get('month_gross_profit') or 0) / 100.0)),
            '资金总额 %s' % _fmt((k.get('fund_total') or 0) / 100.0),
        ]
    })
    # 紧急待办
    urgent = []
    if (a.get('overdue_ar_count') or 0) > 0:
        urgent.append('%s 笔应收逾期，合计 %s' % (
            a['overdue_ar_count'], _fmt((a.get('overdue_ar_amount') or 0) / 100.0)))
    if (a.get('low_stock_count') or 0) > 0:
        urgent.append('%s 个商品低于安全库存' % a['low_stock_count'])
    if (a.get('pending_sales_count') or 0) > 0:
        urgent.append('%s 张销售单待确认出库' % a['pending_sales_count'])
    if urgent:
        sections.append({'title': '紧急待办', 'items': urgent})

    # 行动建议
    actions = []
    if (a.get('overdue_ar_count') or 0) > 0:
        actions.append('优先催收逾期应收，避免坏账')
    if (a.get('low_stock_count') or 0) > 0:
        actions.append('尽快补货，防止缺货断单')
    if not actions:
        actions.append('经营状态良好，保持节奏')
    sections.append({'title': '今日建议', 'items': actions})

    # 纯文本版本（用于推送）
    lines = ['【每日经营简报 %s】' % time.strftime('%Y-%m-%d')]
    for sec in sections:
        lines.append('■ %s' % sec['title'])
        for it in sec['items']:
            lines.append('  · %s' % it)
    summary_text = '\n'.join(lines)

    result = {
        'date': time.strftime('%Y-%m-%d'),
        'title': '每日经营简报',
        'sections': sections,
        'summary_text': summary_text,
    }
    # 简报缓存 1 小时
    _cache[cache_key] = (result, time.time() + 3600)
    return result


def _dashboard_prompt(d):
    """把工作台数据压缩成提示词，要求 AI 返回严格 JSON：
    {"overview":"一句话概览","anomalies":[{"level":"danger|warning|info","text":"..."}],"actions":["建议1","建议2"]}
    """
    k, a, t = d.get('kpi') or {}, d.get('alerts') or {}, d.get('trend') or []
    trend_txt = '，'.join('%s:销售%s/毛利%s' % (
        m.get('month', ''),
        _fmt((m.get('sales') or 0) / 100.0),
        _fmt((m.get('profit') or 0) / 100.0)) for m in t[-3:])
    return (
        '你是这家中小企业的经营助手。基于以下工作台数据，只返回 JSON（不要任何解释、不要 markdown），格式：\n'
        '{"overview":"一句话概览（含今日/本月销售额与回款）",'
        '"anomalies":[{"level":"danger|warning|info","text":"异常描述"}],'
        '"actions":["可执行建议1","可执行建议2"]}\n'
        'level 取值：danger=紧急（逾期/断货），warning=需关注（毛利率下降/待确认），info=提示。\n'
        '今日销售额：%s（%s 笔订单）\n本月销售额：%s，本月毛利：%s，本月回款：%s，本月付款：%s\n'
        '应收余额：%s，应付余额：%s，资金总额：%s\n'
        '待办：应收逾期%s笔/应付逾期%s笔/低库存%s项/待确认销售%s张/待确认采购%s张\n'
        '近3月趋势：%s\n'
        % (_fmt((k.get('today_sales') or 0) / 100.0), k.get('today_order_count', 0),
           _fmt((k.get('month_sales_amount') or 0) / 100.0),
           _fmt((k.get('month_gross_profit') or 0) / 100.0),
           _fmt((k.get('month_receipt') or 0) / 100.0),
           _fmt((k.get('month_payment') or 0) / 100.0),
           _fmt((k.get('ar_balance') or 0) / 100.0),
           _fmt((k.get('ap_balance') or 0) / 100.0),
           _fmt((k.get('fund_total') or 0) / 100.0),
           a.get('overdue_ar_count', 0), a.get('overdue_ap_count', 0),
           a.get('low_stock_count', 0), a.get('pending_sales_count', 0),
           a.get('pending_purchase_count', 0), trend_txt)
    )


def rule_summary(d):
    """内置规则摘要（零消耗），返回结构化：
    {overview, anomalies:[{level,text}], actions:[...], raw_text}
    """
    k, a, t = d.get('kpi') or {}, d.get('alerts') or {}, d.get('trend') or []
    today_sales = (k.get('today_sales') or 0) / 100.0
    month_sales = (k.get('month_sales_amount') or 0) / 100.0
    month_profit = (k.get('month_gross_profit') or 0) / 100.0
    month_receipt = (k.get('month_receipt') or 0) / 100.0

    # ---- 概览 ----
    ov_parts = []
    if today_sales > 0:
        ov_parts.append('今日销售额 %s（%s 笔订单）' % (_fmt(today_sales), k.get('today_order_count', 0)))
    else:
        ov_parts.append('今日暂无销售')
    if len(t) >= 2:
        cur, prev = t[-1], t[-2]
        cs, ps = (cur.get('sales') or 0) / 100.0, (prev.get('sales') or 0) / 100.0
        if ps > 0:
            chg = (cs - ps) / ps * 100
            ov_parts.append('本月销售额 %s，环比%s %s%%' % (
                _fmt(cs), '增长' if chg >= 0 else '下降', '%.1f' % abs(chg)))
        else:
            ov_parts.append('本月销售额 %s' % _fmt(cs))
    if month_profit and month_sales > 0:
        ov_parts.append('毛利率 %.1f%%' % (month_profit / month_sales * 100))
    overview = '，'.join(ov_parts) + '。'

    # ---- 异常检测（分级 + 可跳转 nav） ----
    anomalies = []
    actions = []
    if (a.get('overdue_ar_count') or 0) > 0:
        anomalies.append({
            'level': 'danger',
            'text': '%s 笔应收逾期，合计 %s' % (
                a['overdue_ar_count'], _fmt((a.get('overdue_ar_amount') or 0) / 100.0)),
            'nav': 'receivables'
        })
        actions.append({'text': '优先电话催收逾期应收，避免坏账', 'nav': 'receivables'})
    if (a.get('low_stock_count') or 0) > 0:
        anomalies.append({
            'level': 'danger',
            'text': '%s 个商品低于安全库存' % a['low_stock_count'],
            'nav': 'products'
        })
        actions.append({'text': '尽快下采购单补货，防止缺货断单', 'nav': 'purchase'})
    if len(t) >= 2:
        cur, prev = t[-1], t[-2]
        cs = (cur.get('sales') or 0) / 100.0
        ps = (prev.get('sales') or 0) / 100.0
        cp = (cur.get('profit') or 0) / 100.0
        pp = (prev.get('profit') or 0) / 100.0
        if ps > 0 and pp > 0:
            cur_rate = cp / cs if cs > 0 else 0
            prev_rate = pp / ps
            drop = (prev_rate - cur_rate) * 100
            if drop >= 2:
                anomalies.append({
                    'level': 'warning',
                    'text': '毛利率环比下降 %.1f 个百分点（%s%% → %s%%）' % (
                        drop, '%.1f' % (prev_rate * 100), '%.1f' % (cur_rate * 100)),
                    'nav': 'profit'
                })
                actions.append({'text': '核查采购成本上涨或折扣力度，与主要供应商议价', 'nav': 'profit'})
    if (a.get('pending_sales_count') or 0) > 0:
        anomalies.append({
            'level': 'warning',
            'text': '%s 张销售单待确认出库' % a['pending_sales_count'],
            'nav': 'sales'
        })
        actions.append({'text': '及时确认销售单以生成应收', 'nav': 'sales'})
    if (a.get('pending_purchase_count') or 0) > 0:
        anomalies.append({
            'level': 'info',
            'text': '%s 张采购单待确认入库' % a['pending_purchase_count'],
            'nav': 'purchase'
        })
        actions.append({'text': '及时确认采购入库以更新库存与成本', 'nav': 'purchase'})
    if (a.get('overdue_ap_count') or 0) > 0:
        anomalies.append({
            'level': 'info',
            'text': '%s 笔应付逾期' % a['overdue_ap_count'],
            'nav': 'payables'
        })

    if not actions:
        if today_sales == 0:
            actions.append({'text': '联系重点客户推进本周订单', 'nav': 'customers'})
        else:
            actions.append({'text': '保持节奏，关注回款与补货节奏', 'nav': None})

    raw_lines = [overview]
    if anomalies:
        raw_lines.append('异常信号：' + '；'.join(x['text'] for x in anomalies) + '。')
    else:
        raw_lines.append('当前没有需要紧急处理的预警。')
    raw_lines.append('行动建议：' + '；'.join('%d. %s' % (i + 1, a['text']) for i, a in enumerate(actions)) + '。')
    raw_lines.append('（当前为内置规则摘要，在「系统 → AI 设置」接入 API 后可获得更深入分析）')

    return {
        'overview': overview,
        'anomalies': anomalies,
        'actions': actions,
        'raw_text': '\n'.join(raw_lines),
    }


# ============================================================
# 对话式开单（Text-to-Action 雏形）
# ============================================================

def parse_order(text, customers, products):
    """自然语言 -> 销售订单结构化数据（AI 优先，规则兜底）

    customers: [{id, name, code}]；products: [{id, name, code, unit, sale_price}]
    返回: {customer_id, customer_name, items:[{product_id, name, qty, price, amount}],
          discount(元), discount_rate, source}
    价格单位：分。
    """
    if ai_enabled():
        try:
            data = _llm_parse_order(text, customers, products)
            return _normalize_parse(data, customers, products, source='ai')
        except Exception:
            pass
    return _rule_parse_order(text, customers, products)


def _rule_parse_order(text, customers, products):
    """规则解析（增强版）：支持数量前置/后置、多商品、备注提取

    匹配策略：对每个商品，在其名称前后各 24 字符内找数量；
    数量格式：数字+单位（包/盒/个/吨/件/张/台/瓶/只/箱/把/支/本/套/米/平方米）
    """
    t = text or ''
    # ---- 客户匹配（优先全名，其次编码） ----
    cust = None
    for c in sorted(customers, key=lambda x: len(x.get('name') or ''), reverse=True):
        if c.get('name') and c['name'] in t:
            cust = c
            break
    if not cust:
        for c in customers:
            if c.get('code') and c['code'].lower() in t.lower():
                cust = c
                break

    # ---- 商品匹配：支持数量前置和后置 ----
    units = r'(?:包|盒|个|吨|件|张|台|瓶|只|箱|把|支|本|套|米|平方米|平米|方|kg|公斤|斤|克|升|毫升)'
    items = []
    used_positions = set()
    for p in products:
        name = p.get('name') or ''
        if not name or name not in t:
            continue
        # 找商品名所有出现位置，取第一个未被占用的
        pos = -1
        while True:
            pos = t.find(name, pos + 1)
            if pos < 0:
                break
            if pos in used_positions:
                continue
            break
        if pos < 0:
            continue
        # 标记商品名占用的字符范围，避免短名重复匹配
        for i in range(pos, pos + len(name)):
            used_positions.add(i)

        # 在商品名前后各 24 字符内找数量
        window_start = max(0, pos - 24)
        window_end = min(len(t), pos + len(name) + 24)
        window = t[window_start:window_end]
        name_in_window = pos - window_start

        qty = 0
        # 优先：商品名后面的数量（"A4纸 50包"）
        after = window[name_in_window + len(name):]
        m = re.search(r'(\d+(?:\.\d+)?)\s*' + units, after)
        if m:
            qty = int(float(m.group(1)))
        else:
            # 其次：商品名前面的数量（"50包 A4纸"）
            before = window[:name_in_window]
            m2 = re.search(r'(\d+(?:\.\d+)?)\s*' + units + r'[\s,，、的]*$', before)
            if m2:
                qty = int(float(m2.group(1)))
            else:
                # 纯数字紧跟商品名（"50 A4纸"）
                m3 = re.search(r'(\d+(?:\.\d+)?)\s*$', before)
                if m3:
                    qty = int(float(m3.group(1)))

        if qty <= 0:
            continue
        price = int(p.get('sale_price') or 0)
        items.append({
            'product_id': p['id'], 'name': name, 'qty': qty,
            'price': price, 'amount': price * qty,
        })

    # 按商品在文本中出现顺序排序
    items.sort(key=lambda x: t.find(x['name']))

    # ---- 折扣 ----
    rate = _extract_discount_rate(t)
    total = sum(it['amount'] for it in items)
    discount = int(total * (1 - rate)) if rate < 1 else 0

    # ---- 备注提取（"备注：xxx" 或结尾的描述性文字） ----
    remark = ''
    m_remark = re.search(r'备\s*注[：:]\s*(.+?)(?:$|[,，。；])', t)
    if m_remark:
        remark = m_remark.group(1).strip()

    return {
        'customer_id': cust['id'] if cust else None,
        'customer_name': cust['name'] if cust else None,
        'items': items,
        'discount': discount,
        'discount_rate': rate,
        'remark': remark,
        'source': 'rule',
        'tip': '规则解析（未接入 AI）。' if not cust or not items else '',
    }


def _extract_discount_rate(text):
    """提取折扣率：'8折'->0.8 '85折'->0.85 '八五折'->0.85 '九五折'->0.95，无折扣返回 1"""
    m = re.search(r'(\d{1,2}(?:\.\d)?)\s*折', text)
    if m:
        n = float(m.group(1))
        if n >= 10:
            n /= 10.0
        return round(n / 10.0, 2) if n >= 1 else round(n, 2)
    cn = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9}
    m2 = re.search(r'([一二两三四五六七八九])?([一二两三四五六七八九])?折', text)
    if m2 and (m2.group(1) or m2.group(2)):
        tens = cn.get(m2.group(1) or '', 1)
        units = cn.get(m2.group(2) or '', 0)
        n = tens + units / 10.0
        if n < 1:
            n *= 10
        return round(n / 10.0, 2)
    return 1.0


def _llm_parse_order(text, customers, products):
    """AI 解析：要求返回严格 JSON"""
    cust_lines = '；'.join('id=%s %s(%s)' % (c['id'], c['name'], c.get('code', ''))
                          for c in customers[:20])
    prod_lines = '；'.join('id=%s %s 单价%s分' % (p['id'], p['name'], p.get('sale_price', 0))
                          for p in products[:30])
    prompt = (
        '你是 ERP 系统的开单解析器。用户说了一句自然语言，请从中提取销售订单信息，'
        '只返回 JSON（不要任何解释），格式：'
        '{"customer_id":数字或null,"items":[{"product_id":数字,"qty":正整数}],"discount_rate":0到1的小数}\n'
        '客户候选：%s\n商品候选：%s\n'
        '规则：客户/商品必须从候选中选；没有提到的客户填 null；折扣如“8折”=0.8、“85折”=0.85；没提折扣=1。\n'
        '用户输入：%s'
        % (cust_lines, prod_lines, text))
    raw = chat([{'role': 'user', 'content': prompt}], max_tokens=300, timeout=25)
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.strip('`')
        if raw.startswith('json'):
            raw = raw[4:]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError('AI 返回格式异常')
    return data


def _normalize_parse(data, customers, products, source):
    """校验并补全 AI/规则解析结果"""
    pid_map = {p['id']: p for p in products}
    cid_map = {c['id']: c for c in customers}
    customer_id = data.get('customer_id')
    if customer_id is not None and customer_id not in cid_map:
        customer_id = None
    items = []
    for it in data.get('items') or []:
        pid = it.get('product_id')
        qty = int(it.get('qty') or 0)
        if pid in pid_map and qty > 0:
            p = pid_map[pid]
            price = int(p.get('sale_price') or 0)
            items.append({'product_id': pid, 'name': p['name'], 'qty': qty,
                          'price': price, 'amount': price * qty})
    rate = float(data.get('discount_rate') or 1)
    rate = max(0.0, min(1.0, rate))
    total = sum(i['amount'] for i in items)
    discount = int(total * (1 - rate)) if rate < 1 else 0
    return {
        'customer_id': customer_id,
        'customer_name': cid_map[customer_id]['name'] if customer_id else None,
        'items': items,
        'discount': discount,
        'discount_rate': rate,
        'remark': (data.get('remark') or '').strip(),
        'source': source,
        'tip': 'AI 解析' if source == 'ai' else '规则解析（未接入 AI）',
    }


# ============================================================
# AI 对话式经营查询（Text-to-Insight）
# ============================================================
def answer_query(question):
    """用自然语言问经营问题，返回结构化答案。
    未接入 AI 时用规则引擎；接入后用 LLM 做意图识别。
    """
    from .models import get_db
    from datetime import datetime, timedelta
    db = get_db()
    q = (question or '').strip().lower()

    # ---- 意图识别（规则引擎） ----
    intent = _detect_intent(q)
    result = {'intent': intent, 'question': question, 'answer': '', 'data': None, 'nav': None}

    if intent == 'sales_today':
        today = datetime.now().strftime('%Y-%m-%d')
        row = db.execute(
            "SELECT COALESCE(SUM(final_amount),0) as amt, COUNT(*) as cnt "
            "FROM sales_orders WHERE order_date=? AND status!='已取消'", (today,)).fetchone()
        result['answer'] = '今日销售额 %s（%d 笔订单）' % (_fmt(row['amt'] / 100.0), row['cnt'])
        result['nav'] = 'dashboard'
    elif intent == 'sales_month':
        now = datetime.now()
        start = now.replace(day=1).strftime('%Y-%m-%d')
        row = db.execute(
            "SELECT COALESCE(SUM(final_amount),0) as amt, COUNT(*) as cnt "
            "FROM sales_orders WHERE order_date>=? AND status!='已取消'", (start,)).fetchone()
        result['answer'] = '本月销售额 %s（%d 笔订单）' % (_fmt(row['amt'] / 100.0), row['cnt'])
        result['nav'] = 'dashboard'
    elif intent == 'top_customers':
        rows = db.execute("""
            SELECT c.name, COALESCE(SUM(o.final_amount),0) as amt
            FROM customers c LEFT JOIN sales_orders o ON o.customer_id=c.id AND o.status!='已取消'
            GROUP BY c.id ORDER BY amt DESC LIMIT 5
        """).fetchall()
        lines = ['销售额 Top 5 客户：']
        for i, r in enumerate(rows, 1):
            if r['amt'] > 0:
                lines.append('%d. %s：%s' % (i, r['name'], _fmt(r['amt'] / 100.0)))
        result['answer'] = '\n'.join(lines) if len(lines) > 1 else '暂无销售数据'
        result['data'] = [{'name': r['name'], 'amount': r['amt']} for r in rows if r['amt'] > 0]
        result['nav'] = 'customers'
    elif intent == 'low_stock':
        rows = db.execute(
            "SELECT code,name,stock,safety_stock FROM products "
            "WHERE status=1 AND stock<=safety_stock ORDER BY stock ASC LIMIT 10").fetchall()
        if rows:
            lines = ['%d 个商品低于安全库存：' % len(rows)]
            for r in rows:
                lines.append('· %s（库存 %d，安全线 %d）' % (r['name'], r['stock'], r['safety_stock']))
            result['answer'] = '\n'.join(lines)
        else:
            result['answer'] = '当前所有商品库存充足，无预警。'
        result['data'] = [dict(r) for r in rows]
        result['nav'] = 'products'
    elif intent == 'overdue_receivables':
        rows = db.execute("""
            SELECT r.order_no, c.name, r.amount-r.received as balance, r.due_date
            FROM receivables r LEFT JOIN customers c ON c.id=r.customer_id
            WHERE r.status='未结清' AND r.due_date < date('now','localtime')
            ORDER BY r.due_date ASC LIMIT 10
        """).fetchall()
        if rows:
            total = sum(r['balance'] for r in rows)
            lines = ['%d 笔应收逾期，合计 %s：' % (len(rows), _fmt(total / 100.0))]
            for r in rows:
                lines.append('· %s（%s）：%s，到期 %s' % (
                    r['order_no'], r['name'] or '-', _fmt(r['balance'] / 100.0), r['due_date']))
            result['answer'] = '\n'.join(lines)
        else:
            result['answer'] = '当前无逾期应收。'
        result['data'] = [dict(r) for r in rows]
        result['nav'] = 'receivables'
    elif intent == 'profit':
        now = datetime.now()
        start = now.replace(day=1).strftime('%Y-%m-%d')
        row = db.execute(
            "SELECT COALESCE(SUM(final_amount),0) as sales, "
            "COALESCE(SUM(gross_profit),0) as profit "
            "FROM sales_orders WHERE order_date>=? AND status!='已取消'", (start,)).fetchone()
        sales = row['sales'] / 100.0
        profit = row['profit'] / 100.0
        rate = (profit / sales * 100) if sales > 0 else 0
        result['answer'] = '本月销售额 %s，毛利 %s，毛利率 %.1f%%' % (_fmt(sales), _fmt(profit), rate)
        result['nav'] = 'profit'
    elif intent == 'todo':
        # 汇总待办
        pending_sales = db.execute("SELECT COUNT(*) as c FROM sales_orders WHERE status='待确认'").fetchone()['c']
        pending_purchase = db.execute("SELECT COUNT(*) as c FROM purchase_orders WHERE status='待确认'").fetchone()['c']
        overdue_ar = db.execute(
            "SELECT COUNT(*) as c FROM receivables WHERE status='未结清' AND due_date<date('now','localtime')").fetchone()['c']
        low_stock = db.execute("SELECT COUNT(*) as c FROM products WHERE status=1 AND stock<=safety_stock").fetchone()['c']
        lines = ['今日待办：']
        if overdue_ar: lines.append('· [紧急] %d 笔应收逾期' % overdue_ar)
        if low_stock: lines.append('· [紧急] %d 个商品低于安全库存' % low_stock)
        if pending_sales: lines.append('· [重要] %d 张销售单待确认' % pending_sales)
        if pending_purchase: lines.append('· [提示] %d 张采购单待确认' % pending_purchase)
        if len(lines) == 1: lines.append('· 暂无待办事项')
        result['answer'] = '\n'.join(lines)
        result['nav'] = 'dashboard'
    else:
        # 通用：返回 dashboard 概览
        today = datetime.now().strftime('%Y-%m-%d')
        start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        t_row = db.execute(
            "SELECT COALESCE(SUM(final_amount),0) as amt FROM sales_orders "
            "WHERE order_date=? AND status!='已取消'", (today,)).fetchone()
        m_row = db.execute(
            "SELECT COALESCE(SUM(final_amount),0) as amt, COALESCE(SUM(gross_profit),0) as profit "
            "FROM sales_orders WHERE order_date>=? AND status!='已取消'", (start,)).fetchone()
        ar_row = db.execute(
            "SELECT COALESCE(SUM(amount-received),0) as bal FROM receivables WHERE status='未结清'").fetchone()
        result['answer'] = (
            '今日销售额 %s；本月销售额 %s，毛利 %s；应收余额 %s。'
            '可以问我：本月销售额、哪个客户买最多、库存不足的商品、逾期应收、今日待办。'
        ) % (_fmt(t_row['amt'] / 100.0), _fmt(m_row['amt'] / 100.0),
             _fmt(m_row['profit'] / 100.0), _fmt(ar_row['bal'] / 100.0))
        result['nav'] = 'dashboard'

    result['source'] = '规则引擎（未接入 AI）'
    return result


def _detect_intent(q):
    """关键词意图识别"""
    if any(k in q for k in ['今天', '今日', 'today']) and any(k in q for k in ['销售', '卖', '营收', '额']):
        return 'sales_today'
    if any(k in q for k in ['本月', '这个月', '当月', 'month']) and any(k in q for k in ['销售', '卖', '营收', '额']):
        return 'sales_month'
    if any(k in q for k in ['客户', 'customer']) and any(k in q for k in ['最多', '排行', '排名', 'top', '谁买', '贡献']):
        return 'top_customers'
    if any(k in q for k in ['库存', 'stock', '缺货', '补货', '安全库存', '低库存']):
        return 'low_stock'
    if any(k in q for k in ['逾期', '应收', '欠款', '回款', '未收']):
        return 'overdue_receivables'
    if any(k in q for k in ['利润', '毛利', '盈利', '赚钱', 'profit']):
        return 'profit'
    if any(k in q for k in ['待办', '要做', '任务', 'todo', '提醒', '今天干什么']):
        return 'todo'
    if any(k in q for k in ['销售', '卖了多少', '营收', '业绩']):
        return 'sales_month'
    return 'general'
