{
    'name': 'Accounting (Odoo 8 Feature Set)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Fiscal years & periods, tax codes, vouchers, assets, budgets and the classic financial reports',
    'description': """
Odoo 8 Accounting features for Odoo 19
======================================

Brings back the accounting features that existed in Odoo 8 but were dropped
from (or moved out of) Odoo Community in later versions. It builds *on top of*
the standard ``account`` module: the double-entry engine, journals, taxes,
reconciliation and analytic accounting all remain core Odoo.

Feature blocks
--------------
* **Fiscal years & periods** - ``account.fiscalyear`` / ``account.period``
  including the special opening period, ``period_id`` on journal entries,
  period & year closing, and generation of the year-end opening entry.
* **Tax codes** - the Odoo 8 ``account.tax.code`` hierarchy, wired to the
  modern tax repartition lines, with the classic Taxes Report.
* **Vouchers** - customer receipts and supplier payments with invoice
  allocation lines, plus Cash Book, Bank Book and Day Book.
* **Assets** - asset categories, asset register and depreciation boards with
  automatic depreciation postings.
* **Budgets** - budgetary positions and crossovered budgets with planned,
  practical and theoretical amounts.
* **Financial reports** - General Ledger, Trial Balance, Partner Ledger,
  Aged Partner Balance, Journal report and a configurable Balance Sheet /
  Profit & Loss, each available on screen and as a PDF.
""",
    'author': 'Mufti Muntasir Ahmed',
    'license': 'LGPL-3',
    'depends': ['account', 'analytic', 'mail'],
    'data': [
        'security/account_v8_security.xml',
        'security/ir.model.access.csv',

        'data/account_financial_report_data.xml',
        'data/account_asset_cron.xml',

        'views/account_menuitem.xml',
        'views/account_fiscalyear_views.xml',
        'views/account_period_views.xml',
        'views/account_move_views.xml',
        'views/account_tax_code_views.xml',
        'views/account_voucher_views.xml',
        'views/account_asset_views.xml',
        'views/account_budget_views.xml',
        'views/account_financial_report_views.xml',
        'views/report_result_views.xml',

        'wizard/account_fiscalyear_close_views.xml',
        'wizard/account_period_close_views.xml',
        'wizard/account_report_general_ledger_views.xml',
        'wizard/account_report_trial_balance_views.xml',
        'wizard/account_report_partner_ledger_views.xml',
        'wizard/account_report_aged_partner_views.xml',
        'wizard/account_report_journal_views.xml',
        'wizard/account_report_financial_views.xml',
        'wizard/account_report_tax_views.xml',
        'wizard/account_report_book_views.xml',

        'report/report_layouts.xml',
        'report/report_general_ledger.xml',
        'report/report_trial_balance.xml',
        'report/report_partner_ledger.xml',
        'report/report_aged_partner.xml',
        'report/report_journal.xml',
        'report/report_financial.xml',
        'report/report_tax.xml',
        'report/report_book.xml',
        'report/report_voucher.xml',
        'report/report_asset.xml',
        'report/report_budget.xml',
        'report/report_actions.xml',

        'views/account_menus_final.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
