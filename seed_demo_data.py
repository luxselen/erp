# -*- coding: utf-8 -*-
"""一键演示数据脚本（P0）

用法（在项目根目录）：
    .venv\\Scripts\\python seed_demo_data.py          # 生成演示数据
    .venv\\Scripts\\python seed_demo_data.py --clear  # 清理（还原生成前备份）

生成内容：过去 6 个月销售/采购订单、逾期应收、低库存、客户跟进、资金流水。
安全：首次生成前自动备份 erp.db -> erp.db.demo_backup，--clear 一键还原。
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import get_db_path
from app.demo import seed, clear


def main():
    parser = argparse.ArgumentParser(description='ERP 演示数据生成/清理')
    parser.add_argument('--clear', action='store_true', help='清理演示数据并还原数据库')
    parser.add_argument('--db', default=None, help='指定数据库路径（默认使用系统配置）')
    args = parser.parse_args()

    db_path = args.db or get_db_path()
    print('数据库：%s' % db_path)

    if args.clear:
        r = clear(db_path)
        print(r['msg'])
        sys.exit(0 if r['ok'] else 1)

    r = seed(db_path)
    if not r['ok']:
        print(r['msg'])
        sys.exit(1)
    print(r['msg'])
    print('  客户新增 %s · 供应商新增 %s · 商品新增 %s' % (r['customers'], r['suppliers'], r['products']))
    print('  销售单 %s（明细 %s 行）· 采购单 %s（明细 %s 行）'
          % (r['sales_orders'], r['sales_items'], r['purchase_orders'], r['purchase_items']))
    print('  应收 %s 笔 · 回款 %s 笔 · 应付 %s 笔 · 付款 %s 笔 · 库存流水 %s 条'
          % (r['receivables'], r['receipts'], r['payables'], r['payments'], r['stock_logs']))
    print('  备份：%s（用 --clear 可随时还原）' % r['backup'])


if __name__ == '__main__':
    main()
