from odoo import _, api, models


class ReportAccountHierarchy(models.AbstractModel):
    _name = 'report.account_parent_hierarchy.report_hierarchy_pdf'
    _description = 'Account Hierarchy Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        form = data.get('form') or {}
        context = self.env.context

        company_value = form.get('company_id') or context.get('company_id')
        if isinstance(company_value, (list, tuple)):
            company_value = company_value[0] if company_value else False
        company_id = company_value or self.env.company.id

        date_from = form.get('date_from') or context.get('date_from')
        date_to = form.get('date_to') or context.get('date_to')
        target_move = form.get('target_move') or context.get('target_move', 'posted')
        display_account = (
            form.get('display_account')
            or context.get('display_account', 'not_zero')
        )
        hierarchy_by = context.get('hierarchy_by', 'account')
        include_zero = form.get('include_zero', context.get('include_zero', False))
        unfolded_ids = data.get('unfolded_ids') or context.get('unfolded_ids') or []

        result = self.env['account.account'].get_hierarchy_data(
            company_id=company_id,
            date_from=date_from,
            date_to=date_to,
            target_move=target_move,
            hierarchy_by=hierarchy_by,
            display_account=display_account,
            show_unfolded=True,
            include_zero=include_zero,
        )
        lines = result['lines']

        # Reports opened from the interactive screen follow its fold state.
        # Reports opened from legacy accounting wizards print the full tree.
        report_show_unfolded = bool(form.get('enable_hierarchy')) or context.get(
            'report_show_unfolded',
            False,
        )
        if not report_show_unfolded:
            try:
                unfolded_ids = {int(account_id) for account_id in unfolded_ids}
            except (TypeError, ValueError):
                unfolded_ids = set()
            visible_lines = []
            hidden_level = None
            for line in lines:
                if hidden_level is not None and line['level'] > hidden_level:
                    continue
                if hidden_level is not None:
                    hidden_level = None
                visible_lines.append(line)
                if line['is_parent'] and line['id'] not in unfolded_ids:
                    hidden_level = line['level']
            lines = visible_lines

        company = self.env['res.company'].browse(result['company']['id'])
        report_title = (
            form.get('report_title')
            or context.get('report_title')
            or _("Chart of Accounts Hierarchy")
        )
        return {
            'doc_ids': docids,
            'doc_model': 'account.account',
            'lines': lines,
            'totals': result['totals'],
            'company': company,
            'report_title': report_title,
            'date_from': date_from,
            'date_to': date_to,
            'target_move_label': (
                _("Posted Entries") if target_move == 'posted' else _("All Entries")
            ),
        }
