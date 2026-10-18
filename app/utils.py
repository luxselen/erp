# -*- coding: utf-8 -*-
"""公共响应与通用工具：供各蓝图复用，消除重复定义"""
from flask import jsonify


def ok(data=None, msg='操作成功'):
    return jsonify({'code': 0, 'msg': msg, 'data': data})


def fail(msg='操作失败', code=1):
    return jsonify({'code': code, 'msg': msg, 'data': None})
