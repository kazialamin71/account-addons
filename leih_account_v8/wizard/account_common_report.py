# -*- coding: utf-8 -*-
"""The filter panel shared by every Odoo 8 financial report.

Odoo 8 put the same header on all of them: a chart/company, a fiscal year, a
filter that is either *nothing*, *a date range* or *a range of periods*, a list
of journals and the posted/all switch. Every concrete report inherits this and
adds only its own options.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountCommonReport(models.AbstractModel):
    _name = 'account.common.report'
    _description = 'Common Report Filters'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    fiscalyear_id = fields.Many2one(
        'account.fiscalyear', string='Fiscal Year',
        default=lambda self: self._default_fiscalyear())
    filter = fields.Selection(
        [('filter_no', 'No Filters'),
         ('filter_date', 'Date'),
         ('filter_period', 'Periods')],
        string='Filter by', required=True, default='filter_no')
    period_from = fields.Many2one('account.period', string='Start Period')
    period_to = fields.Many2one('account.period', string='End Period')
    date_from = fields.Date('Start Date')
    date_to = fields.Date('End Date')
    journal_ids = fields.Many2many(
        'account.journal', string='Journals',
        help='Leave empty to include every journal.')
    target_move = fields.Selection(
        [('posted', 'All Posted Entries'), ('all', 'All Entries')],
        string='Target Moves', required=True, default='posted')

    @api.model
    def _default_fiscalyear(self):
        return self.env['account.fiscalyear'].find(exception=False)

    @api.onchange('fiscalyear_id', 'filter')
    def _onchange_fiscalyear(self):
        """Preselect the year's first/last period and its date span."""
        fy = self.fiscalyear_id
        if not fy:
            return
        periods = fy.period_ids.filtered(lambda p: not p.special).sorted('date_start')
        if self.filter == 'filter_period' and periods:
            self.period_from = periods[0]
            self.period_to = periods[-1]
        if self.filter == 'filter_date':
            self.date_from = self.date_from or fy.date_start
            self.date_to = self.date_to or fy.date_stop

    # ------------------------------------------------------------------
    # Filter resolution
    # ------------------------------------------------------------------
    def _get_dates(self):
        """(date_from, date_to), either of which may be None for 'no filter'."""
        self.ensure_one()
        if self.filter == 'filter_date':
            return self.date_from, self.date_to
        if self.filter == 'filter_period':
            if not self.period_from or not self.period_to:
                raise UserError(_('Select both a start and an end period.'))
            if self.period_from.date_start > self.period_to.date_stop:
                raise UserError(_('The start period is after the end period.'))
            return self.period_from.date_start, self.period_to.date_stop
        if self.fiscalyear_id:
            return self.fiscalyear_id.date_start, self.fiscalyear_id.date_stop
        return None, None

    def _base_domain(self, with_dates=True):
        """Domain selecting the journal items this report is about."""
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', 'in', ('draft', 'posted')))
        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))
        if with_dates:
            date_from, date_to = self._get_dates()
            if date_from:
                domain.append(('date', '>=', date_from))
            if date_to:
                domain.append(('date', '<=', date_to))
        return domain

    def _initial_balance_domain(self):
        """Everything strictly before the reporting window.

        Bounded by the fiscal year start for accounts that reset each year;
        unbounded for balance-sheet accounts, which is what
        ``include_initial_balance`` on the account type expresses.
        """
        self.ensure_one()
        date_from, _date_to = self._get_dates()
        if not date_from:
            return None
        domain = self._base_domain(with_dates=False)
        domain.append(('date', '<', date_from))
        return domain

    # ------------------------------------------------------------------
    # Presentation helpers
    # ------------------------------------------------------------------
    def _filter_label(self):
        self.ensure_one()
        date_from, date_to = self._get_dates()
        if self.filter == 'filter_period' and self.period_from:
            return _('Periods %(start)s to %(stop)s',
                     start=self.period_from.name, stop=self.period_to.name)
        if date_from or date_to:
            return _('%(start)s to %(stop)s',
                     start=date_from or _('beginning'), stop=date_to or _('today'))
        return _('No date filter')

    def _report_header(self):
        """Everything the PDF header needs, in one dict."""
        self.ensure_one()
        date_from, date_to = self._get_dates()
        return {
            'company': self.company_id.display_name,
            'fiscalyear': self.fiscalyear_id.display_name or '',
            'filter_label': self._filter_label(),
            'date_from': date_from,
            'date_to': date_to,
            'journals': ', '.join(self.journal_ids.mapped('code')) or _('All journals'),
            'target_move': (_('All Posted Entries') if self.target_move == 'posted'
                            else _('All Entries')),
        }

    def _result_context(self):
        """Context carried into the on-screen result action."""
        self.ensure_one()
        date_from, date_to = self._get_dates()
        return {
            'report_date_from': date_from,
            'report_date_to': date_to,
            'search_default_group_none': 1,
        }

    def _create_rows(self, model, rows, report_name):
        """Persist computed rows, dropping the display-only keys.

        ``_compute_rows`` also carries pre-resolved names (partner, account,
        entry) so the PDF never has to browse records while rendering; those keys
        are not columns, so they are filtered out here.
        """
        self.ensure_one()
        Model = self.env[model]
        columns = set(Model._fields)
        common = {
            'report_name': report_name,
            'company_id': self.company_id.id,
            'currency_id': self.company_id.currency_id.id,
        }
        return Model.create([
            {key: value for key, value in dict(common, **row).items() if key in columns}
            for row in rows
        ])

    def _result_action(self, model, name, view_xmlid, records):
        """Open the freshly computed rows in their list view."""
        self.ensure_one()
        if not records:
            raise UserError(_(
                'No journal item matches these filters, so the report is empty.'))
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': model,
            'view_mode': 'list',
            'views': [(self.env.ref(view_xmlid).id, 'list')],
            'domain': [('id', 'in', records.ids)],
            'context': self._result_context(),
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Entry points implemented by each concrete report
    # ------------------------------------------------------------------
    def _compute_rows(self):
        raise NotImplementedError

    def _report_xmlid(self):
        raise NotImplementedError

    def action_view(self):
        raise NotImplementedError

    def action_print(self):
        """Render the PDF from the same rows the screen shows."""
        self.ensure_one()
        return self.env.ref(self._report_xmlid()).report_action(self)
