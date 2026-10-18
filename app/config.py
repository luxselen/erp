# -*- coding: utf-8 -*-
import os
import sys


def get_db_path():
    """打包后数据库放在 exe 同级目录，方便用户备份"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(os.path.dirname(sys.executable), 'erp.db')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'erp.db')


class Config:
    SECRET_KEY = os.environ.get('ERP_SECRET_KEY', 'erp-desktop-secret-2026-change-me')
    SESSION_TIMEOUT = 7200
    DB_PATH = get_db_path()
    DEBUG = False
    MAX_LOGIN_FAILS = 5
    LOCKOUT_SECONDS = 300