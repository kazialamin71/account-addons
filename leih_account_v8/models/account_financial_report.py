# -*- coding: utf-8 -*-
"""Configurable Balance Sheet / Profit & Loss (Odoo 8 ``account.financial.report``).

The report is a tree of nodes. Each node either sums its children, or pulls a
balance from a list of accounts, from a set of account types, or from another
report. This is what made the Odoo 8 Balance Sheet and P&L editable without code.
"""
from odoo import _, api, fields, models


class AccountReportAccountType(models.Model):
    """The Odoo 8 ``account.account.type`` concept.

    Odoo 19 turned account types into a plain selection on ``account.account``.
    Financial report nodes still need to *pick several of them*, so each
    selection key gets a record here and nodes link to these.
    """
    _name = 'account.report.account.type'
    _description = 'Account Type (report grouping)'
    _order = 'sequence, id'

    name = fields.Char('Name', required=True, translate=True)
    account_type = fields.Char(
        'Account Type Key', required=True,
        help='Value of account.account.account_type this record stands for.')
    internal_group = fields.Char('Internal Group')
    sequence = fields.Integer('Sequence', default=10)

    _account_type_uniq = models.Constraint(
        'unique (account_type)',
        'There can be only one record per account type.',
    )


class AccountFinancialReport(models.Model):
    _name = 'account.financial.report'
    _description = 'Financial Report'
    _order = 'sequence, id'
    _parent_store = True

    name = fields.Char('Report Name', required=True, translate=True)
    parent_id = fields.Many2one(
        'account.financial.report', string='Parent', ondelete='cascade', index=True)
    parent_path = fields.Char(index=True)
    children_ids = fields.One2many(
        'account.financial.report', 'parent_id', string='Account Report')
    sequence = fields.Integer('Sequence', default=10)
    level = fields.Integer('Level', compute='_compute_level', store=True, recursive=True)

    type = fields.Selection(
        [('sum', 'View / Sum of children'),
         ('accounts', 'Sum of specific accounts'),
         ('account_type', 'Sum of account types'),
         ('account_report', 'Balance of another report')],
        string='Type', required=True, default='sum')
    account_ids = fields.Many2many(
        'account.account', 'account_financial_report_account_rel',
        'report_id', 'account_id', string='Accounts')
    account_report_id = fields.Many2one(
        'account.financial.report', string='Report Value')
    account_type_ids = fields.Many2many(
        'account.report.account.type', 'account_financial_report_type_rel',
        'report_id', 'type_id', string='Account Types')

    sign = fields.Selection(
        [('-1', 'Reverse balance sign'), ('1', 'Preserve balance sign')],
        string='Sign on Reports', required=True, default='1',
        help='Set to reverse on income and liability nodes so that a credit '
             'balance prints as a positive figure.')
    display_detail = fields.Selection(
        [('no_detail', 'No detail'),
         ('detail_flat', 'Display children flat'),
         ('detail_with_hierarchy', 'Display children with hierarchy')],
        string='Display Details', default='detail_flat')
    style_overwrite = fields.Selection(
        [('0', 'Automatic formatting'),
         ('1', 'Main Title 1 (bold, underlined)'),
         ('2', 'Title 2 (bold)'),
         ('3', 'Title 3 (bold, smaller)'),
         ('4', 'Normal Text'),
         ('5', 'Italic Text (smaller)'),
         ('6', 'Smallest Text')],
        string='Financial Report Style', default='0')

    @property
    def sign_factor(self):
        """``sign`` as a number, for arithmetic."""
        self.ensure_one()
        return int(self.sign or '1')

    @api.depends('parent_id', 'parent_id.level')
    def _compute_level(self):
        for report in self:
            report.level = report.parent_id.level + 1 if report.parent_id else 0

    def _get_children_by_order(self):
        """This node followed by its whole subtree, in display order."""
        result = self.env['account.financial.report']
        for report in self:
            result |= report
            children = self.search([('parent_id', '=', report.id)], order='sequence, id')
            if children:
                result |= children._get_children_by_order()
        return result

    def _accounts(self):
        """Every general account whose balance this node aggregates."""
        self.ensure_one()
        Account = self.env['account.account']
        if self.type == 'accounts':
            return self.account_ids
        if self.type == 'account_type':
            keys = self.account_type_ids.mapped('account_type')
            return Account.search([('account_type', 'in', keys)]) if keys else Account
        if self.type == 'account_report' and self.account_report_id:
            accounts = Account
            for node in self.account_report_id._get_children_by_order():
                if node.type in ('accounts', 'account_type'):
                    accounts |= node._accounts()
            return accounts
        # 'sum': the union of everything below.
        accounts = Account
        for child in self.children_ids:
            accounts |= child._accounts()
        return accounts
