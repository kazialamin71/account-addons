from odoo import _, api, fields, models


class AccountChartHierarchyReport(models.AbstractModel):
    """Data provider for the hierarchical Chart of Accounts client action."""
    _name = 'account.chart.hierarchy.report'
    _description = 'Chart of Accounts Hierarchy Report'

    @api.model
    def get_filters(self):
        """Return the companies and fiscal years the current user can report on."""
        companies = self.env.user.company_ids
        fiscal_years = self.env['account.fiscal.year'].search(
            [('company_id', 'in', companies.ids)], order='date_from desc')
        return {
            'companies': [{'id': c.id, 'name': c.display_name} for c in companies],
            'default_company_id': self.env.company.id,
            'fiscal_years': [{
                'id': fy.id,
                'name': fy.name,
                'company_id': fy.company_id.id,
                'date_from': fields.Date.to_string(fy.date_from),
                'date_to': fields.Date.to_string(fy.date_to),
            } for fy in fiscal_years],
        }

    @api.model
    def get_lines(self, company_id, date_from, date_to, target_move='posted'):
        """Return the chart of accounts as a tree of rows for ``date_from..date_to``.

        Each row carries its own journal item totals plus those of every
        descendant, so a parent shows the roll-up of the accounts under it.
        """
        company = self.env['res.company'].browse(company_id)
        accounts = self.env['account.account'].with_company(company).search(
            self.env['account.account']._check_company_domain(company))
        amounts = self._get_account_amounts(accounts, company, date_from, date_to, target_move)

        rows = {}
        for account in accounts:
            debit, credit = amounts.get(account.id, (0.0, 0.0))
            rows[account.id] = {
                'id': account.id,
                'code': account.code or '',
                'name': account.name or '',
                'parent_id': account.parent_id.id,
                'is_view': account.is_view,
                'internal_type': self._get_internal_type(account),
                'debit': debit,
                'credit': credit,
                'children': [],
            }

        # Attach every row to its parent. A row whose parent is not part of this
        # company's chart is shown as a root rather than dropped.
        roots = []
        for row in rows.values():
            parent = rows.get(row['parent_id'])
            if parent is None:
                roots.append(row)
            else:
                parent['children'].append(row)

        # Depth-first order: a parent is always listed before its own children.
        ordered, stack = [], list(roots)
        while stack:
            row = stack.pop()
            ordered.append(row)
            stack.extend(row['children'])

        for row in ordered:
            parent = rows.get(row['parent_id'])
            row['level'] = parent['level'] + 1 if parent is not None else 0

        # Walking the same order backwards visits every child before its parent,
        # which is what makes a single pass enough to roll the totals all the way up.
        for row in reversed(ordered):
            parent = rows.get(row['parent_id'])
            if parent is not None:
                parent['debit'] += row['debit']
                parent['credit'] += row['credit']

        for row in ordered:
            row['balance'] = row['debit'] - row['credit']
            row['children'].sort(key=self._row_sort_key)
        roots.sort(key=self._row_sort_key)

        return {
            'lines': roots,
            'company_name': company.display_name,
            'currency_id': company.currency_id.id,
            'currency_name': company.currency_id.name,
            'date_from': date_from,
            'date_to': date_to,
        }

    @api.model
    def _get_account_amounts(self, accounts, company, date_from, date_to, target_move):
        """Sum debit and credit per account over the period, ignoring the hierarchy."""
        domain = [
            ('account_id', 'in', accounts.ids),
            ('company_id', 'child_of', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', 'in', ('draft', 'posted')))
        groups = self.env['account.move.line']._read_group(
            domain, groupby=['account_id'], aggregates=['debit:sum', 'credit:sum'])
        return {account.id: (debit or 0.0, credit or 0.0) for account, debit, credit in groups}

    @api.model
    def _row_sort_key(self, row):
        return (row['code'], row['name'])

    @api.model
    def _get_internal_type(self, account):
        """Label shown in the Internal Type column."""
        if account.is_view:
            return _('View')
        if account.account_type == 'liability_payable':
            return _('Payable')
        if account.account_type == 'asset_receivable':
            return _('Receivable')
        return _('Regular')

    @api.model
    def action_open_journal_items(self, account_id, company_id, date_from, date_to, target_move='posted'):
        """Drill down from a row to the journal items behind its amounts.

        For a view account that means the items of every account below it, which
        is what keeps the drill-down consistent with the rolled-up totals.
        """
        account = self.env['account.account'].browse(account_id)
        domain = [
            ('account_id', 'child_of', account.id),
            ('company_id', 'child_of', company_id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
            domain.append(('parent_state', 'in', ('draft', 'posted')))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Items: %s', account.display_name),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            # The web client reads ``views`` directly and no longer derives it
            # from ``view_mode`` for actions returned as a dictionary.
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
            # A view account spans many accounts, so grouping keeps the drill-down
            # readable; for a single account it would only add noise.
            'context': {'search_default_group_by_account': account.is_view},
        }
