{
    'name': 'Financial Report Initial Balance',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Opening balance column on the Balance Sheet / Profit & Loss report',
    'description': """
Financial Report Initial Balance
================================

The Balance Sheet / Profit & Loss report shows only what moved inside the
reporting window, so an account's opening position is invisible. This adds an
*Initial Balance* column, on screen and in the PDF, holding everything booked
strictly before the window starts.

Accounts that carry an opening balance but saw no movement in the period are
listed too, which the original report skips.
""",
    'author': 'Kazi Alamin',
    'license': 'LGPL-3',
    'depends': ['leih_account_v8'],
    'data': [
        'views/accounting_report_views.xml',
        'report/report_financial_initial_balance.xml',
    ],
    'installable': True,
    'application': False,
}
