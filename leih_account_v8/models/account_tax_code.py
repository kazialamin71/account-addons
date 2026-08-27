# -*- coding: utf-8 -*-
"""Odoo 8 style tax codes.

Odoo 8 attached a *tax code* to every base and tax amount so a statutory tax
return could be built as a tree of codes with signed sums. Odoo 19 replaced that
with repartition lines carrying account tags. This module keeps the modern
computation engine untouched and simply hangs a ``tax_code_id`` off each
repartition line, so a single field covers all four Odoo 8 cases:

===========================  ====================================
Odoo 8 field                 Here
===========================  ====================================
``base_code_id``             invoice repartition line, type base
``tax_code_id``              invoice repartition line, type tax
``ref_base_code_id``         refund repartition line, type base
``ref_tax_code_id``          refund repartition line, type tax
===========================  ====================================

Journal items then carry the resolved ``tax_code_id`` and a signed
``tax_amount``, exactly as they did in Odoo 8.
"""
from odoo import _, api, fields, models


class AccountTaxCode(models.Model):
    _name = 'account.tax.code'
    _description = 'Tax Code'
    _order = 'code, name'
    _parent_store = True

    name = fields.Char('Tax Case Name', required=True, translate=True)
    code = fields.Char('Case Code')
    info = fields.Text('Description')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    parent_id = fields.Many2one(
        'account.tax.code', string='Parent Code', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('account.tax.code', 'parent_id', string='Child Codes')
    line_ids = fields.One2many('account.move.line', 'tax_code_id', string='Journal Items')
    sign = fields.Float(
        'Coefficient for parent', required=True, default=1.0,
        help='Use -1 to subtract this code from its parent instead of adding it.')
    notprintable = fields.Boolean(
        'Not Printable in Invoice',
        help='Hide the amount of this tax code on printed invoices.')
    sequence = fields.Integer('Sequence', default=10)

    sum = fields.Float(
        'Year Sum', compute='_compute_sum',
        help='Signed total of this code and its children over the whole fiscal year.')
    sum_period = fields.Float(
        'Period Sum', compute='_compute_sum',
        help='Signed total over the period selected in the Taxes Report wizard.')

    # ------------------------------------------------------------------
    def _sum_domain(self, period_only):
        """Domain over posted journal items, honouring the report context.

        The Taxes Report wizard puts ``from_date`` / ``to_date`` (period column)
        and ``fiscalyear_id`` (year column) into the context.
        """
        domain = [('company_id', '=', self.env.company.id)]
        if self.env.context.get('state', 'posted') == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        if period_only:
            if self.env.context.get('from_date'):
                domain.append(('date', '>=', self.env.context['from_date']))
            if self.env.context.get('to_date'):
                domain.append(('date', '<=', self.env.context['to_date']))
        elif self.env.context.get('fiscalyear_id'):
            domain.append(('fiscalyear_id', '=', self.env.context['fiscalyear_id']))
        return domain

    def _raw_totals(self, period_only):
        """{tax_code_id: untouched sum of tax_amount} for these codes' subtrees."""
        if not self:
            return {}
        all_codes = self.search([('id', 'child_of', self.ids)])
        domain = self._sum_domain(period_only) + [('tax_code_id', 'in', all_codes.ids)]
        groups = self.env['account.move.line']._read_group(
            domain, groupby=['tax_code_id'], aggregates=['tax_amount:sum'])
        return {code.id: total for code, total in groups}

    def _compute_sum(self):
        """Roll each code's own amount up through its children, applying signs."""
        for period_only, field_name in ((False, 'sum'), (True, 'sum_period')):
            raw = self._raw_totals(period_only)
            for code in self:
                code[field_name] = code._rollup(raw)

    def _rollup(self, raw):
        """Own amount plus every child's amount weighted by the child's sign."""
        self.ensure_one()
        total = raw.get(self.id, 0.0)
        for child in self.child_ids:
            total += child.sign * child._rollup(raw)
        return total

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for code in self:
            code.display_name = '%s - %s' % (code.code, code.name) if code.code else code.name


class AccountTaxRepartitionLine(models.Model):
    _inherit = 'account.tax.repartition.line'

    tax_code_id = fields.Many2one(
        'account.tax.code', string='Tax Code',
        help='Odoo 8 style tax case this repartition line feeds. On a "base" line '
             'this is the old base code; on a "tax" line the old tax code.')


class AccountTax(models.Model):
    _inherit = 'account.tax'

    tax_code_id = fields.Many2one(
        'account.tax.code', string='Tax Code',
        compute='_compute_v8_tax_codes', inverse='_inverse_tax_code_id', store=False,
        help='Shortcut to the tax code of the invoice/tax repartition line.')
    base_code_id = fields.Many2one(
        'account.tax.code', string='Base Code',
        compute='_compute_v8_tax_codes', inverse='_inverse_base_code_id', store=False,
        help='Shortcut to the tax code of the invoice/base repartition line.')

    def _repartition(self, document_type, repartition_type):
        self.ensure_one()
        return self.repartition_line_ids.filtered(
            lambda r: r.document_type == document_type
            and r.repartition_type == repartition_type)[:1]

    @api.depends('repartition_line_ids.tax_code_id')
    def _compute_v8_tax_codes(self):
        for tax in self:
            tax.tax_code_id = tax._repartition('invoice', 'tax').tax_code_id
            tax.base_code_id = tax._repartition('invoice', 'base').tax_code_id

    def _inverse_tax_code_id(self):
        for tax in self:
            tax._repartition('invoice', 'tax').tax_code_id = tax.tax_code_id

    def _inverse_base_code_id(self):
        for tax in self:
            tax._repartition('invoice', 'base').tax_code_id = tax.base_code_id


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    tax_code_id = fields.Many2one(
        'account.tax.code', string='Tax Code', index=True,
        compute='_compute_tax_code', store=True, readonly=False,
        help='Tax case this journal item feeds in the Taxes Report.')
    tax_amount = fields.Monetary(
        'Tax/Base Amount', compute='_compute_tax_code', store=True, readonly=False,
        currency_field='company_currency_id',
        help='Amount reported under the tax code: the tax itself on a tax line, '
             'the taxed base on a base line.')

    @api.depends('tax_repartition_line_id', 'tax_ids', 'balance', 'move_id.move_type')
    def _compute_tax_code(self):
        for line in self:
            code, amount = line._resolve_tax_code()
            line.tax_code_id = code
            line.tax_amount = amount

    def _resolve_tax_code(self):
        """(tax code, signed amount) for this journal item."""
        self.ensure_one()
        # A tax line points straight at its repartition line.
        if self.tax_repartition_line_id:
            return self.tax_repartition_line_id.tax_code_id, self.balance
        # A base line reports its balance under the base code of its tax. Odoo 8
        # had the same one-code-per-line limitation, so the first tax wins.
        if self.tax_ids:
            document_type = 'refund' if self.move_id.move_type in (
                'out_refund', 'in_refund') else 'invoice'
            base_line = self.tax_ids[0]._repartition(document_type, 'base')
            return base_line.tax_code_id, self.balance
        return self.env['account.tax.code'], 0.0
