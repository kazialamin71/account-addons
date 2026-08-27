{
    'name': 'LEIS Automatic Cash Collection',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Every amount received in LEIS lands on a cash collection sheet automatically',
    'description': """
LEIS Automatic Cash Collection
==============================

``cash.collection`` and ``cash.collection.line`` already existed but nothing ever
created them, so money received across the hospital never reached a collection
sheet.

Every section funnels its payment through ``leih.money.receipt``, so that is the
single place this hooks. When a receipt is created the amount is added to the
pending collection sheet for its section and day, carrying:

* the **Money Receipt No.**,
* the **bill / admission / OPD number** it was taken against,
* the amount.

OPD tickets never produced a money receipt, so they now do, which gives OPD a real
MR number and lets the same hook cover it.

Configuration
-------------
A sheet posts one journal entry, so it needs a debit and a credit account.
The debit comes from the payment type used; the credit is configured per section
under *Accounting > Configuration > LEIS Cash Collection Accounts*. Receipts taken
before a section is configured are left uncollected and can be picked up later with
*Collect Pending Receipts* — no payment is ever blocked.
""",
    'author': 'Kazi Alamin',
    'license': 'LGPL-3',
    'depends': ['leih19', 'leih_admission'],
    'data': [
        'security/ir.model.access.csv',
        'data/cash_collection_sequence.xml',
        'views/cash_collection_account_views.xml',
        'views/cash_collection_views.xml',
    ],
    'installable': True,
    'application': False,
}
