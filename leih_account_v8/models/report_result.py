# -*- coding: utf-8 -*-
"""On-screen result rows for the financial reports.

Each wizard computes its figures once and materialises them as transient rows,
which are then shown in a list view the user can filter, group and drill into.
The same rows feed the QWeb PDF, so screen and print can never disagree.
"""
from odoo import _, fields, models


class ReportLineMixin(models.AbstractModel):
    _name = 'leih.report.line.mixin'
    _description = 'Financial Report Row (common)'

    report_name = fields.Char('Report', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    level = fields.Integer('Level', readonly=True, default=0)
    is_group = fields.Boolean('Group Row', readonly=True)
    sequence = fields.Integer('Sequence', readonly=True)


class ReportLedgerLine(models.TransientModel):
    """Movement-level rows: General Ledger, Partner Ledger, Journal, day books."""
    _name = 'leih.report.ledger.line'
    _inherit = ['leih.report.line.mixin']
    _description = 'Ledger Report Row'
    _order = 'sequence, id'

    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Journal', readonly=True)
    move_id = fields.Many2one('account.move', string='Entry', readonly=True)
    move_line_id = fields.Many2one('account.move.line', string='Journal Item', readonly=True)
    label = fields.Char('Label', readonly=True)
    ref = fields.Char('Reference', readonly=True)
    date = fields.Date('Date', readonly=True)
    date_maturity = fields.Date('Due Date', readonly=True)
    reconciled = fields.Char('Matching', readonly=True)

    debit = fields.Monetary('Debit', readonly=True)
    credit = fields.Monetary('Credit', readonly=True)
    balance = fields.Monetary('Balance', readonly=True, help='Row amount (debit - credit).')
    cumulative = fields.Monetary('Cumulative Balance', readonly=True)

    def action_open_entry(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }


class ReportBalanceLine(models.TransientModel):
    """Account-level rows: Trial Balance, Balance Sheet, Profit & Loss."""
    _name = 'leih.report.balance.line'
    _inherit = ['leih.report.line.mixin']
    _description = 'Balance Report Row'
    _order = 'sequence, id'

    code = fields.Char('Code', readonly=True)
    name = fields.Char('Name', readonly=True)
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    financial_report_id = fields.Many2one(
        'account.financial.report', string='Report Node', readonly=True)

    initial_balance = fields.Monetary('Initial Balance', readonly=True)
    debit = fields.Monetary('Debit', readonly=True)
    credit = fields.Monetary('Credit', readonly=True)
    balance = fields.Monetary('Balance', readonly=True)
    balance_cmp = fields.Monetary(
        'Comparison', readonly=True,
        help='Same figure over the comparison range, when one is enabled.')

    def action_open_items(self):
        """Drill from a Trial Balance row to the journal items behind it."""
        self.ensure_one()
        if not self.account_id:
            return False
        domain = [('account_id', '=', self.account_id.id)]
        context = self.env.context
        if context.get('report_date_from'):
            domain.append(('date', '>=', context['report_date_from']))
        if context.get('report_date_to'):
            domain.append(('date', '<=', context['report_date_to']))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Items - %s', self.name or ''),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
        }


class ReportAgedLine(models.TransientModel):
    """One row per partner with the ageing buckets."""
    _name = 'leih.report.aged.line'
    _inherit = ['leih.report.line.mixin']
    _description = 'Aged Partner Balance Row'
    _order = 'sequence, id'

    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    partner_name = fields.Char('Partner Name', readonly=True)
    not_due = fields.Monetary('Not Due', readonly=True)
    period0 = fields.Monetary('Bucket 1', readonly=True)
    period1 = fields.Monetary('Bucket 2', readonly=True)
    period2 = fields.Monetary('Bucket 3', readonly=True)
    period3 = fields.Monetary('Bucket 4', readonly=True)
    period4 = fields.Monetary('Older', readonly=True)
    total = fields.Monetary('Total', readonly=True)


class ReportTaxLine(models.TransientModel):
    """One row per tax code, with the code's signed sum."""
    _name = 'leih.report.tax.line'
    _inherit = ['leih.report.line.mixin']
    _description = 'Tax Report Row'
    _order = 'sequence, id'

    tax_code_id = fields.Many2one('account.tax.code', string='Tax Code', readonly=True)
    code = fields.Char('Case Code', readonly=True)
    name = fields.Char('Case Name', readonly=True)
    amount = fields.Monetary('Amount', readonly=True)

    def action_open_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Items - %s', self.name or ''),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [('tax_code_id', 'child_of', self.tax_code_id.id)],
        }
