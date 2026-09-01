from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountHierarchyWizard(models.TransientModel):
    _name = "account.hierarchy.wizard"
    _description = "Account Hierarchy Wizard"

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(string="Start Date")
    date_to = fields.Date(string="End Date")
    target_move = fields.Selection(
        [
            ('posted', 'Posted Entries'),
            ('all', 'All Entries'),
        ],
        string="Target Moves",
        default='posted',
        required=True,
    )
    hierarchy_by = fields.Selection(
        [
            ('account', 'Account'),
        ],
        string="Hierarchy By",
        default='account',
        required=True,
        readonly=True,
    )
    display_account = fields.Selection(
        [
            ('all', 'All'),
            ('movement', 'With movements'),
            ('not_zero', 'With balance not equal to 0'),
        ],
        string="Display Accounts",
        default='not_zero',
        required=True,
    )
    show_unfolded = fields.Boolean(
        string="Show Unfolded",
        help="Show all levels unfolded.",
    )
    include_zero = fields.Boolean(
        string="Include Zero-Balance Accounts",
        help="Include zero-balance accounts even when another display filter would hide them.",
    )

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("The start date must be earlier than or equal to the end date."))

    def action_open_hierarchy(self):
        self.ensure_one()
        action = self.env.ref('account_parent_hierarchy.action_account_hierarchy_client').read()[0]
        action['context'] = {
            'wizard_company_id': self.company_id.id,
            'wizard_date_from': self.date_from and self.date_from.isoformat(),
            'wizard_date_to': self.date_to and self.date_to.isoformat(),
            'wizard_target_move': self.target_move,
            'wizard_hierarchy_by': self.hierarchy_by,
            'wizard_display_account': self.display_account,
            'wizard_show_unfolded': self.show_unfolded,
            'wizard_include_zero': self.include_zero,
        }
        return action
