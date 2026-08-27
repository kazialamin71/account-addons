# -*- coding: utf-8 -*-
"""Taxes Report: the tax code tree with its signed sums."""
from odoo import _, fields, models


class AccountTaxReportWizard(models.TransientModel):
    _name = 'account.tax.report.wizard'
    _inherit = 'account.common.report'
    _description = 'Taxes Report'

    based_on = fields.Selection(
        [('invoices', 'Invoices'), ('payments', 'Payments')],
        string='Based On', required=True, default='invoices',
        help='Invoices reports the tax when the document is issued; Payments '
             'only once the document has been paid (cash basis).')
    tax_code_id = fields.Many2one(
        'account.tax.code', string='Starting Tax Code',
        help='Leave empty to print every root tax code.')

    def _report_xmlid(self):
        return 'leih_account_v8.action_report_tax'

    def _root_codes(self):
        self.ensure_one()
        if self.tax_code_id:
            return self.tax_code_id
        return self.env['account.tax.code'].search([
            ('parent_id', '=', False), ('company_id', '=', self.company_id.id)])

    def _amounts(self):
        """{tax_code_id: raw sum} honouring the wizard's filters."""
        self.ensure_one()
        domain = self._base_domain() + [('tax_code_id', '!=', False)]
        if self.based_on == 'payments':
            # Cash basis: only what has actually been settled.
            domain.append(('full_reconcile_id', '!=', False))
        groups = self.env['account.move.line']._read_group(
            domain, groupby=['tax_code_id'], aggregates=['tax_amount:sum'])
        return {code.id: total for code, total in groups}

    def _walk(self, code, raw, rows, level):
        """Depth-first emit of a code and its children."""
        rows.append({
            'sequence': len(rows) + 1,
            'level': level,
            'is_group': bool(code.child_ids),
            'tax_code_id': code.id,
            'code': code.code or '',
            'name': code.name,
            'amount': code._rollup(raw),
        })
        for child in code.child_ids.sorted(lambda c: (c.code or '', c.id)):
            self._walk(child, raw, rows, level + 1)

    def _compute_rows(self):
        self.ensure_one()
        raw = self._amounts()
        rows = []
        for root in self._root_codes().sorted(lambda c: (c.code or '', c.id)):
            self._walk(root, raw, rows, 0)
        return rows

    def _materialise(self, rows):
        return self._create_rows('leih.report.tax.line', rows, _('Taxes Report'))

    def action_view(self):
        self.ensure_one()
        records = self._materialise(self._compute_rows())
        return self._result_action(
            'leih.report.tax.line', _('Taxes Report'),
            'leih_account_v8.view_report_tax_line_list', records)
