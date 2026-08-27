from odoo import _, api, fields, models

# Mirrors the selection on cash.collection.type.
SECTION_TYPES = [
    ('bill', 'Bill [Diagnosis]'),
    ('bill_others', 'Bill [others]'),
    ('opd', 'OPD'),
    ('admission', 'Admission'),
    ('optics', 'Optics'),
]


class LeihCashCollectionAccount(models.Model):
    """Which accounts an automatically created collection sheet should carry.

    A sheet posts a single journal entry, so it needs one debit and one credit
    account. The debit follows the money in and comes from the payment type;
    the credit is the section's income side and is configured here.
    """
    _name = 'leih.cash.collection.account'
    _description = 'LEIS Cash Collection Account Configuration'
    _order = 'type'

    type = fields.Selection(SECTION_TYPES, string='Section', required=True)
    credit_account_id = fields.Many2one(
        'account.account', string='Credit Account', required=True,
        help="Booked against the money received for this section.")
    default_payment_type_id = fields.Many2one(
        'payment.type', string='Default Payment Type',
        help="Used to pick the debit account when the receipt carries no payment "
             "type of its own, which is the case for OPD tickets.")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _unique_type_per_company = models.Constraint(
        'UNIQUE(type, company_id)',
        'A section can only be configured once per company.',
    )

    @api.depends('type')
    def _compute_display_name(self):
        labels = dict(SECTION_TYPES)
        for record in self:
            record.display_name = labels.get(record.type, '')

    @api.model
    def _for_section(self, section_type, company=None):
        """Configuration for a section, or an empty recordset when unconfigured."""
        company = company or self.env.company
        return self.search([
            ('type', '=', section_type),
            ('company_id', '=', company.id),
        ], limit=1)
