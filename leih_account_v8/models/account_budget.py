# -*- coding: utf-8 -*-
"""Crossovered budgets (Odoo 8 ``account_budget``).

A budget is a set of lines, each crossing a *budgetary position* (a named group
of general accounts) with an analytic account over a date range. Each line
compares three figures:

* **planned** - what you budgeted, entered by hand;
* **practical** - what actually happened, read from the ledger;
* **theoretical** - what you should have spent by now if spending were even.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class AccountBudgetPost(models.Model):
    _name = 'account.budget.post'
    _description = 'Budgetary Position'
    _order = 'name'

    name = fields.Char('Name', required=True)
    code = fields.Char('Code')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    account_ids = fields.Many2many(
        'account.account', 'account_budget_rel', 'budget_id', 'account_id',
        string='Accounts', check_company=True,
        help='General accounts whose journal items count towards this position.')
    crossovered_budget_line = fields.One2many(
        'crossovered.budget.lines', 'general_budget_id', string='Budget Lines')


class CrossoveredBudget(models.Model):
    _name = 'crossovered.budget'
    _description = 'Budget'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, id desc'

    name = fields.Char('Budget Name', required=True, tracking=True)
    code = fields.Char('Code', copy=False)
    creating_user_id = fields.Many2one(
        'res.users', string='Responsible', default=lambda self: self.env.user)
    validating_user_id = fields.Many2one('res.users', string='Validated By', readonly=True, copy=False)
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('confirm', 'Confirmed'), ('validate', 'Validated'),
         ('done', 'Done'), ('cancel', 'Cancelled')],
        string='Status', required=True, readonly=True, copy=False,
        default='draft', tracking=True)
    crossovered_budget_line = fields.One2many(
        'crossovered.budget.lines', 'crossovered_budget_id', string='Budget Lines',
        copy=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_to < budget.date_from:
                raise ValidationError(_('The budget end date cannot be before its start date.'))

    def action_budget_confirm(self):
        self.write({'state': 'confirm'})

    def action_budget_validate(self):
        self.write({'state': 'validate', 'validating_user_id': self.env.user.id})

    def action_budget_done(self):
        self.write({'state': 'done'})

    def action_budget_cancel(self):
        self.write({'state': 'cancel'})

    def action_budget_draft(self):
        self.write({'state': 'draft', 'validating_user_id': False})


class CrossoveredBudgetLines(models.Model):
    _name = 'crossovered.budget.lines'
    _description = 'Budget Line'
    _order = 'date_from, id'

    crossovered_budget_id = fields.Many2one(
        'crossovered.budget', string='Budget', required=True, ondelete='cascade', index=True)
    general_budget_id = fields.Many2one(
        'account.budget.post', string='Budgetary Position', required=True, check_company=True)
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', check_company=True)
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    paid_date = fields.Date('Paid Date')
    planned_amount = fields.Monetary(
        'Planned Amount', required=True,
        help='Amount you plan to spend (expense budget) or earn (revenue budget).')
    practical_amount = fields.Monetary(
        'Practical Amount', compute='_compute_practical_amount',
        help='What the ledger actually shows for this position over the period.')
    theoritical_amount = fields.Monetary(
        'Theoretical Amount', compute='_compute_theoritical_amount',
        help='Share of the planned amount that should have been consumed by today.')
    percentage = fields.Float(
        'Achievement', compute='_compute_percentage',
        help='Practical amount over theoretical amount.')
    company_id = fields.Many2one(
        related='crossovered_budget_id.company_id', string='Company',
        store=True, readonly=True)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', readonly=True)
    state = fields.Selection(
        related='crossovered_budget_id.state', string='Status', readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for line in self:
            if line.date_to < line.date_from:
                raise ValidationError(_('A budget line cannot end before it starts.'))

    def _is_expense_position(self):
        """True when every account of the position is a cost account.

        Consumption should read positive whichever way the budget points, so an
        expense budget is measured debit-minus-credit and a revenue budget the
        other way round. Mixed positions fall back to the revenue convention,
        which is what Odoo has always used.
        """
        self.ensure_one()
        groups = set(self.general_budget_id.account_ids.mapped('internal_group'))
        return bool(groups) and groups <= {'expense'}

    def _compute_practical_amount(self):
        """Analytic actuals when the line is analytic, general ledger otherwise."""
        for line in self:
            expense = line._is_expense_position()
            if line.analytic_account_id:
                domain = [
                    ('auto_account_id', '=', line.analytic_account_id.id),
                    ('date', '>=', line.date_from), ('date', '<=', line.date_to),
                ]
                if line.general_budget_id.account_ids:
                    domain.append(
                        ('general_account_id', 'in', line.general_budget_id.account_ids.ids))
                lines = self.env['account.analytic.line'].search(domain)
                # Analytic costs are stored negative, revenue positive.
                total = sum(lines.mapped('amount'))
                line.practical_amount = -total if expense else total
            else:
                accounts = line.general_budget_id.account_ids
                if not accounts:
                    line.practical_amount = 0.0
                    continue
                items = self.env['account.move.line'].search([
                    ('account_id', 'in', accounts.ids),
                    ('date', '>=', line.date_from), ('date', '<=', line.date_to),
                    ('parent_state', '=', 'posted'),
                    ('company_id', '=', line.company_id.id),
                ])
                total = sum(items.mapped('balance'))
                line.practical_amount = total if expense else -total

    def _compute_theoritical_amount(self):
        today = fields.Date.context_today(self)
        for line in self:
            total_days = (line.date_to - line.date_from).days + 1
            if total_days <= 0:
                line.theoritical_amount = 0.0
                continue
            if today < line.date_from:
                elapsed = 0
            elif today > line.date_to:
                elapsed = total_days
            else:
                elapsed = (today - line.date_from).days + 1
            line.theoritical_amount = line.planned_amount * elapsed / total_days

    def _compute_percentage(self):
        for line in self:
            if float_is_zero(line.theoritical_amount, precision_digits=2):
                line.percentage = 0.0
            else:
                line.percentage = line.practical_amount / line.theoritical_amount

    def action_open_entries(self):
        """Drill from a budget line down to the journal items behind it."""
        self.ensure_one()
        accounts = self.general_budget_id.account_ids
        domain = [
            ('account_id', 'in', accounts.ids),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
            ('parent_state', '=', 'posted'),
        ]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Items'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': domain,
        }
