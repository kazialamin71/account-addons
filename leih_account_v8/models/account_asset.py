# -*- coding: utf-8 -*-
"""Fixed assets and depreciation boards (Odoo 8 ``account_asset``).

An asset holds its gross value and a *depreciation board*: one line per
instalment, each of which becomes a journal entry crediting the depreciation
account and debiting the expense account when its date is reached.
"""
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class AccountAssetCategory(models.Model):
    _name = 'account.asset.category'
    _description = 'Asset Category'
    _order = 'name'

    active = fields.Boolean(default=True)
    name = fields.Char('Name', required=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, check_company=True,
        domain="[('type', '=', 'general')]")
    account_asset_id = fields.Many2one(
        'account.account', string='Asset Account', required=True, check_company=True,
        domain="[('account_type', '=', 'asset_fixed')]",
        help='Balance-sheet account holding the gross value of the asset.')
    account_depreciation_id = fields.Many2one(
        'account.account', string='Depreciation Account', required=True, check_company=True,
        help='Contra-asset account accumulating the depreciation (credited).')
    account_depreciation_expense_id = fields.Many2one(
        'account.account', string='Depreciation Expense Account', required=True,
        check_company=True, domain="[('internal_group', '=', 'expense')]",
        help='Profit & loss account charged with the depreciation (debited).')

    method = fields.Selection(
        [('linear', 'Linear'), ('degressive', 'Degressive')],
        string='Computation Method', required=True, default='linear')
    method_number = fields.Integer(
        'Number of Depreciations', default=5,
        help='How many instalments the asset is written off over.')
    method_period = fields.Integer(
        'Period Length (months)', default=12, required=True,
        help='Months between two depreciation entries.')
    method_progress_factor = fields.Float('Degressive Factor', default=0.3)
    method_time = fields.Selection(
        [('number', 'Number of Depreciations'), ('end', 'Ending Date')],
        string='Time Method', required=True, default='number')
    method_end = fields.Date('Ending Date')
    prorata = fields.Boolean(
        'Prorata Temporis',
        help='Start depreciating on the asset date rather than on the first day '
             'of the first period.')
    open_asset = fields.Boolean(
        'Confirm Asset on Creation',
        help='Skip the draft state: assets in this category are confirmed straight away.')

    @api.constrains('method_period')
    def _check_method_period(self):
        for category in self:
            if category.method_period <= 0:
                raise ValidationError(_('The period length must be at least one month.'))


class AccountAssetAsset(models.Model):
    _name = 'account.asset.asset'
    _description = 'Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    active = fields.Boolean(default=True)
    name = fields.Char('Asset Name', required=True, tracking=True)
    code = fields.Char('Reference', copy=False)
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Running'), ('close', 'Closed')],
        string='Status', required=True, copy=False, default='draft', tracking=True)
    category_id = fields.Many2one(
        'account.asset.category', string='Category', required=True,
        check_company=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id)
    partner_id = fields.Many2one('res.partner', string='Supplier', check_company=True)
    date = fields.Date(
        'Asset Date', required=True, default=fields.Date.context_today, tracking=True,
        help='Date the asset was purchased / put into service.')
    value = fields.Monetary('Gross Value', required=True, tracking=True)
    salvage_value = fields.Monetary(
        'Salvage Value', help='Residual value that is never depreciated.')
    value_residual = fields.Monetary(
        'Residual Value', compute='_compute_value_residual', store=True)
    depreciated_value = fields.Monetary(
        'Depreciated Amount', compute='_compute_value_residual', store=True)
    note = fields.Text('Notes')

    method = fields.Selection(
        [('linear', 'Linear'), ('degressive', 'Degressive')],
        string='Computation Method', required=True, default='linear',
        readonly=False)
    method_number = fields.Integer('Number of Depreciations', default=5)
    method_period = fields.Integer('Period Length (months)', default=12, required=True)
    method_progress_factor = fields.Float('Degressive Factor', default=0.3)
    method_time = fields.Selection(
        [('number', 'Number of Depreciations'), ('end', 'Ending Date')],
        string='Time Method', required=True, default='number')
    method_end = fields.Date('Ending Date')
    prorata = fields.Boolean('Prorata Temporis')

    depreciation_line_ids = fields.One2many(
        'account.asset.depreciation.line', 'asset_id',
        string='Depreciation Board', copy=False)
    entry_count = fields.Integer(compute='_compute_entry_count')

    # ------------------------------------------------------------------
    @api.depends('value', 'salvage_value', 'depreciation_line_ids.move_check',
                 'depreciation_line_ids.amount')
    def _compute_value_residual(self):
        for asset in self:
            posted = asset.depreciation_line_ids.filtered('move_check')
            asset.depreciated_value = sum(posted.mapped('amount'))
            asset.value_residual = asset.value - asset.salvage_value - asset.depreciated_value

    def _compute_entry_count(self):
        for asset in self:
            asset.entry_count = len(asset.depreciation_line_ids.filtered('move_id'))

    @api.constrains('value', 'salvage_value')
    def _check_values(self):
        for asset in self:
            if float_compare(asset.value, 0.0, precision_rounding=asset.currency_id.rounding) <= 0:
                raise ValidationError(_('The gross value of an asset must be positive.'))
            if float_compare(asset.salvage_value, asset.value,
                             precision_rounding=asset.currency_id.rounding) >= 0:
                raise ValidationError(_('The salvage value must be below the gross value.'))

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """Categories carry the depreciation policy; copy it onto the asset."""
        category = self.category_id
        if not category:
            return
        self.method = category.method
        self.method_number = category.method_number
        self.method_period = category.method_period
        self.method_progress_factor = category.method_progress_factor
        self.method_time = category.method_time
        self.method_end = category.method_end
        self.prorata = category.prorata

    # ------------------------------------------------------------------
    # Depreciation board
    # ------------------------------------------------------------------
    def _depreciation_count(self):
        """How many instalments remain to be generated."""
        self.ensure_one()
        if self.method_time == 'end':
            if not self.method_end:
                raise UserError(_(
                    'Asset %s uses the "Ending Date" method - set an ending date.', self.name))
            count, cursor = 0, self._first_depreciation_date()
            while cursor <= self.method_end:
                count += 1
                cursor += relativedelta(months=self.method_period)
            return max(count, 1)
        count = self.method_number
        # Prorata spreads the first year over two instalments.
        if self.prorata:
            count += 1
        return count

    def _first_depreciation_date(self):
        """Date of the first instalment.

        Without prorata the board starts at the end of the asset's first period;
        with prorata it starts on the asset date itself.
        """
        self.ensure_one()
        if self.prorata:
            return self.date
        # Align on the period grid: first day of the month following the asset.
        return (self.date + relativedelta(months=self.method_period)).replace(day=1) \
            - relativedelta(days=1)

    def _board_amount(self, sequence, total_count, residual, depreciable):
        """Amount of instalment ``sequence`` (1-based)."""
        self.ensure_one()
        rounding = self.currency_id.rounding
        # Last instalment always clears whatever is left, so rounding never strands
        # a few cents on the asset.
        if sequence >= total_count:
            return residual
        if self.method == 'degressive':
            amount = residual * self.method_progress_factor
            # Switch to linear once linear would write off faster.
            linear = depreciable / total_count
            if float_compare(linear, amount, precision_rounding=rounding) > 0:
                amount = linear
        else:
            amount = depreciable / total_count
            if self.prorata and sequence == 1:
                # First instalment covers only the part of the period that has run.
                months = self.method_period
                elapsed = months - ((self.date.month - 1) % months)
                amount = amount * elapsed / months
        return min(amount, residual)

    def compute_depreciation_board(self):
        """(Re)generate the unposted part of the board."""
        Line = self.env['account.asset.depreciation.line']
        for asset in self:
            posted = asset.depreciation_line_ids.filtered('move_id')
            # Only unposted lines are recomputed; posted history is untouched.
            (asset.depreciation_line_ids - posted).unlink()

            depreciable = asset.value - asset.salvage_value
            residual = depreciable - sum(posted.mapped('amount'))
            rounding = asset.currency_id.rounding
            if float_is_zero(residual, precision_rounding=rounding):
                continue

            total_count = asset._depreciation_count()
            depreciation_date = asset._first_depreciation_date()
            # Skip the dates already covered by posted instalments.
            for _unused in posted:
                depreciation_date += relativedelta(months=asset.method_period)

            depreciated = sum(posted.mapped('amount'))
            commands = []
            sequence = len(posted) + 1
            while (not float_is_zero(residual, precision_rounding=rounding)
                   and sequence <= total_count):
                amount = asset.currency_id.round(
                    asset._board_amount(sequence, total_count, residual, depreciable))
                if float_is_zero(amount, precision_rounding=rounding):
                    break
                residual -= amount
                depreciated += amount
                commands.append(fields.Command.create({
                    'name': '%s/%s' % (asset.code or asset.name, sequence),
                    'sequence': sequence,
                    'amount': amount,
                    'remaining_value': residual,
                    'depreciated_value': depreciated,
                    'depreciation_date': depreciation_date,
                }))
                depreciation_date += relativedelta(months=asset.method_period)
                sequence += 1
            if commands:
                asset.write({'depreciation_line_ids': commands})
        return True

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def validate(self):
        self.compute_depreciation_board()
        self.write({'state': 'open'})
        return True

    def set_to_draft(self):
        self.write({'state': 'draft'})
        return True

    def set_to_close(self):
        """Dispose of the asset: drop any unposted instalment."""
        for asset in self:
            asset.depreciation_line_ids.filtered(lambda l: not l.move_id).unlink()
        self.write({'state': 'close'})
        return True

    def action_view_entries(self):
        self.ensure_one()
        moves = self.depreciation_line_ids.mapped('move_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Depreciation Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }

    @api.model
    def _cron_generate_entries(self):
        """Post every depreciation instalment whose date has come."""
        today = fields.Date.context_today(self)
        lines = self.env['account.asset.depreciation.line'].search([
            ('move_id', '=', False),
            ('depreciation_date', '<=', today),
            ('asset_id.state', '=', 'open'),
        ])
        return lines.create_move()


class AccountAssetDepreciationLine(models.Model):
    _name = 'account.asset.depreciation.line'
    _description = 'Asset Depreciation Line'
    _order = 'depreciation_date, sequence, id'

    name = fields.Char('Reference', required=True)
    sequence = fields.Integer('Sequence', required=True)
    asset_id = fields.Many2one(
        'account.asset.asset', string='Asset', required=True, ondelete='cascade')
    parent_state = fields.Selection(related='asset_id.state', string='Asset Status')
    currency_id = fields.Many2one(related='asset_id.currency_id', readonly=True)
    company_id = fields.Many2one(related='asset_id.company_id', store=True, readonly=True)
    amount = fields.Monetary('Depreciation', required=True)
    remaining_value = fields.Monetary('Next Residual', readonly=True)
    depreciated_value = fields.Monetary('Cumulative Depreciation', readonly=True)
    depreciation_date = fields.Date('Depreciation Date')
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    move_check = fields.Boolean(
        'Posted', compute='_compute_move_check', store=True)

    @api.depends('move_id', 'move_id.state')
    def _compute_move_check(self):
        for line in self:
            line.move_check = bool(line.move_id) and line.move_id.state == 'posted'

    def create_move(self):
        """Book the depreciation: expense debit, accumulated depreciation credit."""
        moves = self.env['account.move']
        for line in self:
            if line.move_id:
                raise UserError(_(
                    'Instalment %s already has a journal entry.', line.name))
            asset = line.asset_id
            category = asset.category_id
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'ref': asset.code or asset.name,
                'date': line.depreciation_date,
                'journal_id': category.journal_id.id,
                'company_id': asset.company_id.id,
                'partner_id': asset.partner_id.id or False,
                'line_ids': [
                    fields.Command.create({
                        'name': line.name,
                        'account_id': category.account_depreciation_expense_id.id,
                        'partner_id': asset.partner_id.id or False,
                        'debit': line.amount,
                        'credit': 0.0,
                    }),
                    fields.Command.create({
                        'name': line.name,
                        'account_id': category.account_depreciation_id.id,
                        'partner_id': asset.partner_id.id or False,
                        'debit': 0.0,
                        'credit': line.amount,
                    }),
                ],
            })
            move.action_post()
            line.move_id = move.id
            moves |= move
            # Fully depreciated assets close themselves.
            if float_is_zero(asset.value_residual,
                             precision_rounding=asset.currency_id.rounding):
                asset.state = 'close'
        return moves

    def unlink(self):
        if any(line.move_id for line in self):
            raise UserError(_(
                'A depreciation instalment that has been posted cannot be deleted.'))
        return super().unlink()
