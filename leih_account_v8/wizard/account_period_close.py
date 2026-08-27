# -*- coding: utf-8 -*-
"""Close a range of accounting periods."""
from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountPeriodClose(models.TransientModel):
    _name = 'account.period.close'
    _description = 'Close Accounting Periods'

    period_ids = fields.Many2many(
        'account.period', string='Periods to Close', required=True,
        domain="[('state', '=', 'draft')]")
    sure = fields.Boolean('I confirm, close these periods')

    def action_close(self):
        self.ensure_one()
        if not self.sure:
            raise UserError(_('Tick the confirmation box to close the selected periods.'))
        draft_moves = self.env['account.move'].search_count([
            ('period_id', 'in', self.period_ids.ids), ('state', '=', 'draft')])
        if draft_moves:
            raise UserError(_(
                'There are still %s draft journal entries in the selected periods. '
                'Post or delete them before closing.', draft_moves))
        self.period_ids.write({'state': 'done'})
        return {'type': 'ir.actions.act_window_close'}
