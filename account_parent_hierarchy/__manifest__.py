{
    "name": "Account Parent Hierarchy",
    "version": "19.0.2.0.0",
    "author": "Salauddin & Rocky",
    "category": "Accounting",
    "summary": "Interactive chart of accounts hierarchy with PDF and XLSX export",
    "description": """
Account Parent Hierarchy
========================
Adds a parent/child structure to the chart of accounts and provides an
interactive, multi-company aware hierarchy report with opening, debit,
credit and closing balances. The report can be exported to PDF and XLSX.
    """,
    "depends": ["account", "accounting_pdf_reports"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "views/account_parent_views.xml",
        "views/account_hierarchy_wizard_views.xml",
        "views/account_hierarchy_client_action.xml",
        "views/accounting_reports_ext_views.xml",
        "reports/account_hierarchy_report.xml",
        "reports/account_hierarchy_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_parent_hierarchy/static/src/css/hierarchy_style.css",
            "account_parent_hierarchy/static/src/js/hierarchy_view.js",
            "account_parent_hierarchy/static/src/xml/account_hierarchy.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
