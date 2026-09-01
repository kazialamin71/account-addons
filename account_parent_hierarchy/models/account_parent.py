from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountAccount(models.Model):
    _inherit = "account.account"
    _parent_name = "parent_id"
    _parent_store = True

    # Kept for databases that already use the Odoo 17 module's non-posting
    # account type. In Odoo 19 the corresponding internal group is named `off`.
    account_type = fields.Selection(
        selection_add=[('off_balance_view', 'View')],
        ondelete={
            'off_balance_view': lambda accounts: accounts.write({
                'account_type': 'off_balance',
            }),
        },
    )

    parent_id = fields.Many2one(
        'account.account',
        string='Parent Account',
        index=True,
        ondelete='set null',
        tracking=True,
        help="Optional parent used to arrange this account in hierarchy reports.",
    )
    child_ids = fields.One2many(
        'account.account',
        'parent_id',
        string='Child Accounts',
    )
    parent_path = fields.Char(index=True)
    hierarchy_level = fields.Integer(
        string="Hierarchy Level",
        compute="_compute_hierarchy_level",
        recursive=True,
        store=True,
    )

    @api.depends('parent_id', 'parent_id.hierarchy_level')
    def _compute_hierarchy_level(self):
        for account in self:
            account.hierarchy_level = (
                account.parent_id.hierarchy_level + 1 if account.parent_id else 0
            )

    @api.constrains('parent_id')
    def _check_parent_id_recursion(self):
        if self._has_cycle():
            raise ValidationError(_("An account hierarchy cannot contain a recursive loop."))

    def _get_internal_group(self, account_type):
        if account_type == 'off_balance_view':
            return 'off'
        return super()._get_internal_group(account_type)

    @api.model
    def _normalize_hierarchy_options(
        self,
        company_id,
        date_from,
        date_to,
        target_move,
        hierarchy_by,
        display_account,
    ):
        try:
            company_id = int(company_id or self.env.company.id)
        except (TypeError, ValueError):
            raise UserError(_("Please select a valid company.")) from None

        company = self.env['res.company'].browse(company_id).exists()
        if not company or company not in self.env.user.company_ids:
            raise AccessError(_("You are not allowed to view accounting data for this company."))
        company.check_access('read')

        try:
            date_from = fields.Date.to_date(date_from) if date_from else False
            date_to = fields.Date.to_date(date_to) if date_to else False
        except (TypeError, ValueError):
            raise UserError(_("Please provide a valid report date.")) from None
        if date_from and date_to and date_from > date_to:
            raise UserError(_("The start date must be earlier than or equal to the end date."))
        if target_move not in ('posted', 'all'):
            raise UserError(_("Unsupported target move option."))
        if hierarchy_by != 'account':
            raise UserError(_("Unsupported hierarchy option."))
        if display_account not in ('all', 'movement', 'not_zero'):
            raise UserError(_("Unsupported account display option."))

        return company, date_from, date_to

    @api.model
    def _get_move_line_domain(self, company, target_move='posted'):
        domain = [
            ('company_id', '=', company.id),
            ('parent_state', '!=', 'cancel'),
        ]
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        return domain

    @api.model
    def _sum_move_lines(self, domain):
        rows = self.env['account.move.line']._read_group(
            domain,
            groupby=['account_id'],
            aggregates=['debit:sum', 'credit:sum'],
        )
        return {
            account.id: (debit or 0.0, credit or 0.0)
            for account, debit, credit in rows
            if account
        }

    @api.model
    def _compute_balances_opening_period(
        self,
        company,
        target_move='posted',
        date_from=False,
        date_to=False,
    ):
        base_domain = self._get_move_line_domain(company, target_move)
        balances = defaultdict(lambda: {
            'initial_balance': 0.0,
            'debit': 0.0,
            'credit': 0.0,
        })

        if date_from:
            for account_id, (debit, credit) in self._sum_move_lines(
                base_domain + [('date', '<', date_from)]
            ).items():
                balances[account_id]['initial_balance'] = debit - credit

        period_domain = list(base_domain)
        if date_from:
            period_domain.append(('date', '>=', date_from))
        if date_to:
            period_domain.append(('date', '<=', date_to))
        for account_id, (debit, credit) in self._sum_move_lines(period_domain).items():
            balances[account_id].update(debit=debit, credit=credit)

        return dict(balances)

    @api.model
    def get_hierarchy_data(
        self,
        company_id=None,
        date_from=False,
        date_to=False,
        target_move='posted',
        hierarchy_by='account',
        display_account='not_zero',
        show_unfolded=False,
        include_zero=False,
        unfolded_ids=None,
    ):
        company, date_from, date_to = self._normalize_hierarchy_options(
            company_id,
            date_from,
            date_to,
            target_move,
            hierarchy_by,
            display_account,
        )
        try:
            unfolded_ids = {int(account_id) for account_id in (unfolded_ids or [])}
        except (TypeError, ValueError):
            unfolded_ids = set()

        Account = self.with_company(company).with_context(active_test=False)
        accounts = Account.search(
            [('company_ids', 'parent_of', company.id)],
            order='code, name, id',
        )
        balances = self._compute_balances_opening_period(
            company=company,
            target_move=target_move,
            date_from=date_from,
            date_to=date_to,
        )
        currency = company.currency_id
        selection = Account.fields_get(['account_type'])['account_type']['selection']
        type_labels = dict(selection)

        valid_ids = set(accounts.ids)
        effective_parent = {}
        children_map = defaultdict(list)
        for account in accounts:
            parent_id = account.parent_id.id
            if parent_id not in valid_ids:
                parent_id = 0
            effective_parent[account.id] = parent_id
            children_map[parent_id].append(account)

        def _sort_key(account):
            return ((account.code or '').casefold(), (account.name or '').casefold(), account.id)

        for children in children_map.values():
            children.sort(key=_sort_key)

        account_data = {}
        for account in accounts:
            values = balances.pop(account.id, {})
            opening = values.get('initial_balance', 0.0)
            debit = values.get('debit', 0.0)
            credit = values.get('credit', 0.0)
            closing = opening + debit - credit
            account_data[account.id] = {
                'id': account.id,
                'code': account.code or '',
                'name': account.name or '',
                'parent_id': effective_parent[account.id],
                'is_parent': bool(children_map.get(account.id)),
                'folded': not (show_unfolded or account.id in unfolded_ids),
                'active': account.active,
                'account_type': account.account_type,
                'account_type_display': type_labels.get(
                    account.account_type,
                    account.account_type or '',
                ),
                'initial_balance': currency.round(opening),
                'debit': currency.round(debit),
                'credit': currency.round(credit),
                'closing_balance': currency.round(closing),
                'balance': currency.round(closing),
                'level': 0,
            }

        def _is_zero(value):
            return currency.is_zero(value)

        def _keep_account(data):
            if include_zero or display_account == 'all':
                return True
            if display_account == 'movement':
                return not (_is_zero(data['debit']) and _is_zero(data['credit']))
            return not _is_zero(data['closing_balance'])

        visited = set()

        def _walk(parent_id, level, ancestry):
            node_lines = []
            totals = [0.0, 0.0, 0.0]
            for account in children_map.get(parent_id, []):
                if account.id in ancestry or account.id in visited:
                    continue
                visited.add(account.id)
                data = account_data[account.id]
                data['level'] = level
                child_lines, child_totals = _walk(
                    account.id,
                    level + 1,
                    ancestry | {account.id},
                )
                if data['is_parent']:
                    data['initial_balance'] = currency.round(
                        data['initial_balance'] + child_totals[0]
                    )
                    data['debit'] = currency.round(data['debit'] + child_totals[1])
                    data['credit'] = currency.round(data['credit'] + child_totals[2])
                    data['closing_balance'] = currency.round(
                        data['initial_balance'] + data['debit'] - data['credit']
                    )
                    data['balance'] = data['closing_balance']

                totals[0] += data['initial_balance']
                totals[1] += data['debit']
                totals[2] += data['credit']
                if _keep_account(data) or child_lines:
                    node_lines.append(data)
                    node_lines.extend(child_lines)
            return node_lines, totals

        lines, total_values = _walk(0, 0, frozenset())

        # Old databases can contain malformed parent links. Do not lose those
        # accounts from a financial report while the data is being corrected.
        for account in accounts:
            if account.id in visited:
                continue
            account_data[account.id]['parent_id'] = 0
            orphan_lines, orphan_totals = _walk(
                effective_parent[account.id],
                0,
                frozenset(),
            )
            lines.extend(orphan_lines)
            for index, value in enumerate(orphan_totals):
                total_values[index] += value

        # Preserve balance integrity if record rules hide an account referenced
        # by otherwise readable journal items.
        for values in balances.values():
            total_values[0] += values.get('initial_balance', 0.0)
            total_values[1] += values.get('debit', 0.0)
            total_values[2] += values.get('credit', 0.0)

        initial_balance, debit, credit = map(currency.round, total_values)
        closing_balance = currency.round(initial_balance + debit - credit)
        return {
            'lines': lines,
            'totals': {
                'initial_balance': initial_balance,
                'debit': debit,
                'credit': credit,
                'closing_balance': closing_balance,
                'balance': closing_balance,
            },
            'company': {
                'id': company.id,
                'name': company.display_name,
                'currency_id': currency.id,
                'currency_name': currency.name,
            },
        }
