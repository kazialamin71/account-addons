from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Populate Odoo 19's materialized hierarchy fields on module upgrade."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    accounts = env['account.account'].with_context(active_test=False).search([])
    accounts._parent_store_compute()
    accounts._recompute_recordset(fnames=['hierarchy_level'])
