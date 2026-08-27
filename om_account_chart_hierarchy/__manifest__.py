{
    'name': 'Chart of Accounts Hierarchy',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Hierarchical Chart of Accounts with per-fiscal-year debit, credit and balance',
    'description': """
Chart of Accounts Hierarchy
===========================

Restores the classic parent/child Chart of Accounts screen:

* an explicit ``parent_id`` on ``account.account``, so the tree is not tied to
  the code-prefix rules of ``account.group``;
* an expandable Code / Name / Debit / Credit / Balance table;
* amounts summed over the journal items of a selected fiscal year, with each
  parent showing the roll-up of its children;
* drill down from any account to its journal items for the same period.
""",
    'author': 'Kazi Alamin',
    'license': 'LGPL-3',
    'depends': ['account', 'om_fiscal_year'],
    'data': [
        'views/account_account_views.xml',
        'views/chart_of_accounts_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_account_chart_hierarchy/static/src/chart_of_accounts/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
