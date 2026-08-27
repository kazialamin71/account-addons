# -*- coding: utf-8 -*-
"""Customer receipts and supplier payments (Odoo 8 ``account.voucher``).

A voucher collects one cash/bank movement and spreads it over the open
receivable / payable items of a partner. Validating it produces a regular
``account.move`` and reconciles each allocation line against the invoice item it
was allocated to, so the partner ledger and aged balance stay correct.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class AccountVoucher(models.Model):
    _name = 'account.voucher'
    _description = 'Accounting Voucher'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'number'

    number = fields.Char('Number', readonly=True, copy=False, default='/')
    name = fields.Char('Memo', readonly=False, tracking=True)
    voucher_type = fields.Selection(
        [('receipt', 'Customer Receipt'), ('payment', 'Supplier Payment')],
        string='Type', required=True, default='receipt', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, tracking=True,
        check_company=True)
    journal_id = fields.Many2one(
        'account.journal', string='Payment Method', required=True,
        domain="[('type', 'in', ('bank', 'cash'))]", check_company=True)
    account_id = fields.Many2one(
        'account.account', string='Cash/Bank Account', required=True,
        compute='_compute_account_id', store=True, readonly=False, precompute=True,
        domain="[('account_type', 'in', ('asset_cash', 'liability_credit_card'))]",
        check_company=True)
    date = fields.Date(
        'Date', required=True, default=fields.Date.context_today, tracking=True)
    period_id = fields.Many2one(
        'account.period', string='Period', compute='_compute_period_id',
        store=True, readonly=False, precompute=True)
    reference = fields.Char('Payment Ref', help='Cheque number, transfer reference, ...')
    amount = fields.Monetary('Paid Amount', required=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    line_ids = fields.One2many(
        'account.voucher.line', 'voucher_id', string='Allocations',
        copy=False)
    narration = fields.Text('Notes')
    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted'), ('cancel', 'Cancelled')],
        string='Status', readonly=True, copy=False, default='draft', tracking=True)
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True, copy=False)

    payment_option = fields.Selection(
        [('without_writeoff', 'Keep Open'), ('with_writeoff', 'Reconcile Payment Balance')],
        string='Payment Difference', required=True, default='without_writeoff',
        help='Keep Open leaves the unallocated difference as a residual on the '
             'partner account; Reconcile Payment Balance books it to a write-off account.')
    writeoff_acc_id = fields.Many2one(
        'account.account', string='Write-off Account', check_company=True)
    comment = fields.Char('Write-off Label', default=lambda self: _('Write-Off'))

    allocated = fields.Monetary(
        'Allocated', compute='_compute_allocated', store=True)
    difference = fields.Monetary(
        'Difference', compute='_compute_allocated', store=True,
        help='Paid amount minus what has been allocated to open items.')

    # ------------------------------------------------------------------
    @api.depends('journal_id')
    def _compute_account_id(self):
        for voucher in self:
            voucher.account_id = voucher.journal_id.default_account_id

    @api.depends('date', 'company_id')
    def _compute_period_id(self):
        Period = self.env['account.period']
        for voucher in self:
            if not voucher.date:
                voucher.period_id = False
                continue
            voucher.period_id = Period.search([
                ('date_start', '<=', voucher.date), ('date_stop', '>=', voucher.date),
                ('special', '=', False), ('company_id', '=', voucher.company_id.id),
            ], limit=1)

    @api.depends('amount', 'line_ids.amount')
    def _compute_allocated(self):
        for voucher in self:
            voucher.allocated = sum(voucher.line_ids.mapped('amount'))
            voucher.difference = (voucher.amount or 0.0) - voucher.allocated

    # ------------------------------------------------------------------
    # Loading the partner's open items
    # ------------------------------------------------------------------
    def _open_item_domain(self):
        """Posted, unreconciled receivable (or payable) items of the partner."""
        self.ensure_one()
        account_type = 'asset_receivable' if self.voucher_type == 'receipt' else 'liability_payable'
        return [
            ('partner_id', '=', self.partner_id.id),
            ('account_id.account_type', '=', account_type),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('company_id', '=', self.company_id.id),
        ]

    @api.onchange('partner_id', 'voucher_type', 'company_id')
    def _onchange_partner_id(self):
        """Reload the open items whenever the partner or direction changes."""
        self.line_ids = [fields.Command.clear()]
        if not self.partner_id:
            return
        lines = self.env['account.move.line'].search(
            self._open_item_domain(), order='date_maturity, date, id')
        commands = []
        for move_line in lines:
            residual = abs(move_line.amount_residual)
            if float_is_zero(residual, precision_rounding=self.currency_id.rounding or 0.01):
                continue
            commands.append(fields.Command.create({
                'move_line_id': move_line.id,
                'account_id': move_line.account_id.id,
                'name': move_line.move_id.name,
                'date_original': move_line.date,
                'date_due': move_line.date_maturity,
                'amount_original': abs(move_line.balance),
                'amount_unreconciled': residual,
                'amount': 0.0,
            }))
        self.line_ids = commands

    def action_allocate_full(self):
        """Spread the paid amount over the open items, oldest first."""
        for voucher in self:
            remaining = voucher.amount or 0.0
            for line in voucher.line_ids:
                take = min(remaining, line.amount_unreconciled)
                line.amount = take
                remaining -= take
        return True

    # ------------------------------------------------------------------
    # Posting
    # ------------------------------------------------------------------
    def _check_postable(self):
        self.ensure_one()
        rounding = self.currency_id.rounding
        if self.state != 'draft':
            raise UserError(_('Only a draft voucher can be validated.'))
        if float_compare(self.amount, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(_('The paid amount must be strictly positive.'))
        if float_compare(self.allocated, self.amount, precision_rounding=rounding) > 0:
            raise UserError(_(
                'You allocated %(allocated)s but only paid %(amount)s.',
                allocated=self.allocated, amount=self.amount))
        over = self.line_ids.filtered(lambda l: float_compare(
            l.amount, l.amount_unreconciled, precision_rounding=rounding) > 0)
        if over:
            raise UserError(_(
                'Allocation on %(items)s exceeds what is still open on those items.',
                items=', '.join(over.mapped('name'))))
        if (self.payment_option == 'with_writeoff'
                and not float_is_zero(self.difference, precision_rounding=rounding)
                and not self.writeoff_acc_id):
            raise UserError(_('Choose a write-off account for the payment difference.'))
        self.period_id._check_open()

    def _partner_account(self):
        """Fallback partner account when nothing is allocated."""
        self.ensure_one()
        partner = self.partner_id.with_company(self.company_id)
        if self.voucher_type == 'receipt':
            account = partner.property_account_receivable_id
        else:
            account = partner.property_account_payable_id
        if not account:
            raise UserError(_(
                'Partner %s has no receivable/payable account configured.',
                self.partner_id.display_name))
        return account

    def _move_line_vals(self, account, debit, credit, label):
        self.ensure_one()
        return {
            'name': label or self.name or self.number,
            'account_id': account.id,
            'partner_id': self.partner_id.id,
            'debit': debit,
            'credit': credit,
        }

    def action_post(self):
        """Create the journal entry and reconcile every allocation."""
        for voucher in self:
            voucher._check_postable()
            is_receipt = voucher.voucher_type == 'receipt'
            label = voucher.name or voucher.reference or _('Voucher')

            # 1. the cash/bank side
            lines = [voucher._move_line_vals(
                voucher.account_id,
                debit=voucher.amount if is_receipt else 0.0,
                credit=0.0 if is_receipt else voucher.amount,
                label=label)]

            # 2. one counterpart per allocation, so each can be reconciled
            #    against the invoice item it settles
            allocations = voucher.line_ids.filtered(lambda l: l.amount)
            for line in allocations:
                lines.append(voucher._move_line_vals(
                    line.account_id,
                    debit=0.0 if is_receipt else line.amount,
                    credit=line.amount if is_receipt else 0.0,
                    label=line.name or label))

            # 3. the unallocated remainder: write-off, or left open on the
            #    partner account as an advance
            rounding = voucher.currency_id.rounding
            if not float_is_zero(voucher.difference, precision_rounding=rounding):
                if voucher.payment_option == 'with_writeoff':
                    account, text = voucher.writeoff_acc_id, voucher.comment
                else:
                    account, text = voucher._partner_account(), label
                lines.append(voucher._move_line_vals(
                    account,
                    debit=0.0 if is_receipt else voucher.difference,
                    credit=voucher.difference if is_receipt else 0.0,
                    label=text))

            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': voucher.journal_id.id,
                'date': voucher.date,
                'ref': voucher.reference or voucher.name or voucher.number,
                'partner_id': voucher.partner_id.id,
                'company_id': voucher.company_id.id,
                'line_ids': [fields.Command.create(vals) for vals in lines],
            })
            if voucher.period_id:
                move.period_id = voucher.period_id.id
            move.action_post()

            # 4. reconcile: match each counterpart line with its open item
            counterparts = move.line_ids.filtered(
                lambda l: l.account_id != voucher.account_id
                and l.account_id.reconcile)
            for line in allocations:
                match = counterparts.filtered(
                    lambda l, ln=line: l.account_id == ln.account_id
                    and abs(l.balance) == ln.amount and not l.reconciled)[:1]
                if match and not line.move_line_id.reconciled:
                    (match + line.move_line_id).reconcile()
                    counterparts -= match

            voucher.write({
                'move_id': move.id,
                'state': 'posted',
                'number': voucher._next_number(),
            })
        return True

    def _next_number(self):
        self.ensure_one()
        if self.number and self.number != '/':
            return self.number
        code = ('account.voucher.receipt' if self.voucher_type == 'receipt'
                else 'account.voucher.payment')
        return self.env['ir.sequence'].with_company(
            self.company_id).next_by_code(code) or '/'

    def action_cancel(self):
        """Unreconcile and reverse the entry, then mark the voucher cancelled."""
        for voucher in self:
            move = voucher.move_id
            if move:
                move.line_ids.remove_move_reconcile()
                if move.state == 'posted':
                    move._reverse_moves([{'date': fields.Date.context_today(self)}], cancel=True)
                else:
                    move.button_draft()
                    move.unlink()
            voucher.state = 'cancel'
        return True

    def action_draft(self):
        self.filtered(lambda v: v.state == 'cancel').write({'state': 'draft'})
        return True

    def action_view_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }

    def unlink(self):
        if any(v.state == 'posted' for v in self):
            raise UserError(_('A posted voucher cannot be deleted. Cancel it first.'))
        return super().unlink()


class AccountVoucherLine(models.Model):
    _name = 'account.voucher.line'
    _description = 'Voucher Allocation Line'
    _order = 'date_due, id'

    voucher_id = fields.Many2one(
        'account.voucher', string='Voucher', required=True, ondelete='cascade')
    move_line_id = fields.Many2one(
        'account.move.line', string='Open Item', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', required=True)
    name = fields.Char('Description')
    date_original = fields.Date('Document Date', readonly=True)
    date_due = fields.Date('Due Date', readonly=True)
    amount_original = fields.Monetary('Original Amount', readonly=True)
    amount_unreconciled = fields.Monetary('Open Amount', readonly=True)
    amount = fields.Monetary('Allocation')
    currency_id = fields.Many2one(related='voucher_id.currency_id', readonly=True)
    company_id = fields.Many2one(related='voucher_id.company_id', store=True, readonly=True)
