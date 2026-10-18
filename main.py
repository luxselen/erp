# -*- coding: utf-8 -*-
"""
ERP 系统双模式启动入口
- 桌面模式：双击 exe，弹原生窗口（单人/单机用）
- 服务器模式：命令行启动，主机保持开启，其他人浏览器访问
"""
import os
import sys
import time
import socket
import base64

# ============ 兼容打包后路径 ============
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    if hasattr(sys, '_MEIPASS'):
        sys.path.insert(0, sys._MEIPASS)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, BASE_DIR)

from app import create_app
from app.models import init_db

app = create_app()

# ============ 运行模式 ============
RUN_MODE = os.environ.get('ERP_MODE', 'desktop').lower()

# 服务器模式端口（可改）
SERVER_PORT = int(os.environ.get('ERP_PORT', '5000'))


def find_free_port():
    """桌面模式：自动找空闲端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def print_banner(title, lines):
    """打印启动横幅"""
    width = 62
    print('=' * width)
    print('  ' + title)
    print('=' * width)
    for line in lines:
        print('  ' + line)
    print('=' * width)
    print()


# ============================================================
# 服务器模式
# ============================================================
def run_server_mode():
    # 初始化数据库（首次启动会建表和种子数据）
    with app.app_context():
        try:
            init_db()
        except Exception as e:
            print('[警告] 数据库初始化：', e)

    local_ip = get_local_ip()
    db_type = app.config.get('DB_TYPE', 'sqlite')

    print_banner('ERP 企业资源管理系统 - 服务器模式', [
        '数据库类型 : %s' % db_type.upper(),
        '数据库路径 : %s' % app.config.get('DB_PATH', ''),
        '',
        '本机访问   : http://127.0.0.1:%d' % SERVER_PORT,
        '局域网访问 : http://%s:%d' % (local_ip, SERVER_PORT),
        '',
        '★ 保持本窗口开启，其他人才能使用',
        '★ 关闭本窗口即停止服务',
        '★ 首次使用请在主机上登录 admin/admin123 修改密码',
    ])

    try:
        app.run(
            host='0.0.0.0',       # 监听所有网卡
            port=SERVER_PORT,
            debug=False,
            use_reloader=False,
            threaded=True,        # 多线程，支持多人同时访问
        )
    except KeyboardInterrupt:
        print('\n服务已停止')
    except OSError as e:
        print('\n[错误] 端口 %d 可能被占用：%s' % (SERVER_PORT, e))
        print('请关闭占用端口的程序，或修改 ERP_PORT 环境变量')
        input('按回车退出...')


# ============================================================
# 桌面模式
# ============================================================
def run_desktop_mode():
    import webview
    import threading

    # 初始化数据库
    with app.app_context():
        init_db()

    # 后台线程跑 Flask
    port = find_free_port()
    t = threading.Thread(
        target=lambda: app.run(
            host='127.0.0.1', port=port,
            debug=False, use_reloader=False, threaded=True
        ),
        daemon=True
    )
    t.start()

    # 等 Flask 启动
    time.sleep(2.0)

    # 窗口 API
    class WindowApi:
        def __init__(self):
            self._window = None

        def set_window(self, w):
            self._window = w

        def minimize(self):
            if self._window:
                self._window.minimize()

        def toggle_maximize(self):
            if self._window:
                self._window.toggle_fullscreen()

        def close(self):
            if self._window:
                self._window.destroy()

        def save_file(self, filename, data_b64):
            """原生另存为对话框"""
            try:
                result = self._window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=filename,
                    file_types=(
                        'Excel 文件 (*.xlsx)',
                        '数据库文件 (*.db)',
                        'CSV 文件 (*.csv)',
                        '所有文件 (*.*)'
                    )
                )
            except Exception as e:
                return 'ERROR: ' + str(e)

            if not result:
                return None
            path = result if isinstance(result, str) else result[0]
            try:
                with open(path, 'wb') as f:
                    f.write(base64.b64decode(data_b64))
                return path
            except Exception as e:
                return 'ERROR: ' + str(e)

    # 创建窗口
    api = WindowApi()
    window = webview.create_window(
        title='ERP 企业资源管理系统',
        url='http://127.0.0.1:%d' % port,
        width=1400,
        height=900,
        min_size=(1024, 680),
        js_api=api,
    )
    api.set_window(window)

    # 启动 GUI
    webview.start(http_server=True)


# ============================================================
# 入口
# ============================================================
def main():
    if RUN_MODE == 'server':
        run_server_mode()
    else:
        run_desktop_mode()


if __name__ == '__main__':
    main()