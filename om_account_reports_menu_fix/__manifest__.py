{
    'name': 'Account Reports Menu Fix',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Hide the accounting_pdf_reports menus that cannot open',
    'description': """
Account Reports Menu Fix
========================

``accounting_pdf_reports`` and ``leih_account_v8`` both define the classic Odoo 8
financial reports. Only one definition of each shared model can win, and
``leih_account_v8`` does, so the ``accounting_pdf_reports`` wizards are missing
the fields their own form views ask for. Opening one of those menus raises
``"<field> is undefined"`` in the browser.

Both modules stay installed. This only deactivates the seven menus that lead to a
view the model can no longer satisfy. The working reports remain available under
*Accounting (Classic)/Reports*.

Re-activate any of them from Settings > Technical > User Interface > Menu Items
if the underlying conflict is ever resolved.
""",
    'author': 'Kazi Alamin',
    'license': 'LGPL-3',
    'depends': ['accounting_pdf_reports', 'leih_account_v8'],
    'data': [
        'data/menu_fix.xml',
    ],
    'installable': True,
    'application': False,
}
