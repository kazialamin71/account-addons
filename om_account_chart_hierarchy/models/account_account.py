from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountAccount(models.Model):
    """Give ``account.account`` back an explicit parent/child hierarchy.

    ``account.group`` builds its tree from code prefixes, which cannot express a
    chart where a child's code does not start with its parent's code. An explicit
    ``parent_id`` carries any shape of tree, including one migrated from Odoo 8.
    """
    _inherit = 'account.account'
    _parent_name = 'parent_id'
    _parent_store = True

    parent_id = fields.Many2one(
        comodel_name='account.account',
        string='Parent Account',
        index=True,
        ondelete='restrict',
        help="Parent account in the chart of accounts hierarchy. "
             "Leave empty to make this account a root of the tree.",
    )
    child_ids = fields.One2many(
        comodel_name='account.account',
        inverse_name='parent_id',
        string='Child Accounts',
    )
    parent_path = fields.Char(index=True)
    is_view = fields.Boolean(
        string='View Account',
        compute='_compute_is_view',
        store=True,
        help="An account that groups other accounts. Its debit, credit and balance "
             "are the roll-up of its children rather than its own journal items.",
    )

    @api.depends('child_ids')
    def _compute_is_view(self):
        for account in self:
            account.is_view = bool(account.child_ids)

    @api.constrains('parent_id')
    def _check_account_hierarchy_recursion(self):
        if self._has_cycle():
            raise ValidationError(_("You cannot create a recursive chart of accounts hierarchy."))
