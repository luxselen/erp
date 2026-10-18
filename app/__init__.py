# -*- coding: utf-8 -*-
import json
import logging
import os
import sys
import time

from flask import Flask, render_template, jsonify, request, g
from .config import Config
from . import models
from .security import generate_csrf_token

# ============================================================
# 结构化日志配置（S 级标准：JSON 格式，可被 ELK/Loki 采集）
# ============================================================
class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'ts': self.formatTime(record, '%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'module': record.module,
            'func': record.funcName,
            'line': record.lineno,
            'msg': record.getMessage(),
        }
        if hasattr(record, 'duration_ms'):
            payload['duration_ms'] = record.duration_ms
        if hasattr(record, 'path'):
            payload['path'] = record.path
        if hasattr(record, 'status_code'):
            payload['status_code'] = record.status_code
        if record.exc_info:
            payload['exc'] = self.formatException(record.exc_info)[:500]
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging(app):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    handler = logging.FileHandler(os.path.join(log_dir, 'erp.log'), encoding='utf-8')
    handler.setFormatter(JsonFormatter())
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 避免重复添加 handler（reload 场景）
    if not any(isinstance(h, JsonFormatter) or getattr(h, '_erp_json', False) for h in root.handlers):
        handler._erp_json = True
        root.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def resource_path(relative):
    """兼容 PyInstaller 打包后的资源路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative)


def create_app():
    template_dir = resource_path('templates')
    static_dir = resource_path(os.path.join('app', 'static'))

    app = Flask(__name__,
                template_folder=template_dir,
                static_folder=static_dir)
    app.config.from_object(Config)
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 上传最大 20MB
    app.teardown_appcontext(models.close_db)
    _setup_logging(app)

    from .blueprints.auth import bp as auth_bp
    from .blueprints.base import bp as base_bp
    from .blueprints.sales import bp as sales_bp
    from .blueprints.purchase import bp as purchase_bp
    from .blueprints.finance import bp as finance_bp
    from .blueprints.stock import bp as stock_bp
    from .blueprints.report import bp as report_bp
    from .blueprints.invoice import bp as invoice_bp
    from .blueprints.voucher import bp as voucher_bp
    from .blueprints.advanced import bp as advanced_bp
    from .blueprints.ai import bp as ai_bp
    from .blueprints.extras import bp as extras_bp

    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(base_bp, url_prefix='/api')
    app.register_blueprint(sales_bp, url_prefix='/api')
    app.register_blueprint(purchase_bp, url_prefix='/api')
    app.register_blueprint(finance_bp, url_prefix='/api')
    app.register_blueprint(stock_bp, url_prefix='/api')
    app.register_blueprint(report_bp, url_prefix='/api')
    app.register_blueprint(invoice_bp, url_prefix='/api')
    app.register_blueprint(voucher_bp, url_prefix='/api')
    app.register_blueprint(advanced_bp, url_prefix='/api')
    app.register_blueprint(ai_bp, url_prefix='/api')
    app.register_blueprint(extras_bp, url_prefix='/api')

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/csrf_token')
    def csrf_token():
        return jsonify({'code': 0, 'msg': 'ok', 'data': generate_csrf_token()})

    # ---- 统一 JSON 错误响应，避免前端拿到 HTML 报错页 ----
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'code': 404, 'msg': '接口不存在', 'data': None}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({'code': 405, 'msg': '请求方式不允许', 'data': None}), 405

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'code': 500, 'msg': '服务器内部错误', 'data': None}), 500

    # ---- API 响应禁用缓存，防止退出登录后页面残留旧数据 ----
    @app.after_request
    def no_cache_api(resp):
        if request.path.startswith('/api/'):
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
        return resp

    # ---- 请求耗时记录（S 级可观测性：慢请求可追踪） ----
    @app.before_request
    def _start_timer():
        g._start_time = time.time()

    @app.after_request
    def _log_request(resp):
        if request.path.startswith('/api/') and hasattr(g, '_start_time'):
            duration_ms = int((time.time() - g._start_time) * 1000)
            if duration_ms > 1000:  # 只记录慢请求（>1s），避免日志爆炸
                app.logger.info(
                    'slow_request',
                    extra={'duration_ms': duration_ms, 'path': request.path,
                           'status_code': resp.status_code,
                           'method': request.method})
        return resp

    # ---- 500 错误记录完整堆栈 ----
    @app.errorhandler(Exception)
    def _handle_unexpected(e):
        app.logger.exception('unhandled_exception: %s', e)
        return jsonify({'code': 500, 'msg': '服务器内部错误', 'data': None}), 500

    return app