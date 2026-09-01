import io
import json

from odoo import _, http
from odoo.http import content_disposition, request
from odoo.tools import osutil


class AccountHierarchyController(http.Controller):

    @http.route(
        '/account_parent_hierarchy/download_xlsx',
        type='http',
        auth='user',
        methods=['GET'],
        readonly=True,
    )
    def download_xlsx(self, **kwargs):
        try:
            unfolded_ids = json.loads(kwargs.get('unfolded_ids', '[]'))
            if not isinstance(unfolded_ids, list):
                unfolded_ids = []
        except (TypeError, ValueError, json.JSONDecodeError):
            unfolded_ids = []

        def _as_bool(name):
            return str(kwargs.get(name, '')).lower() in ('1', 'true', 'yes')

        result = request.env['account.account'].get_hierarchy_data(
            company_id=kwargs.get('company_id'),
            date_from=kwargs.get('date_from') or False,
            date_to=kwargs.get('date_to') or False,
            target_move=kwargs.get('target_move', 'posted'),
            hierarchy_by=kwargs.get('hierarchy_by', 'account'),
            display_account=kwargs.get('display_account', 'not_zero'),
            show_unfolded=_as_bool('show_unfolded'),
            include_zero=_as_bool('include_zero'),
            unfolded_ids=unfolded_ids,
        )
        lines = result['lines']
        totals = result['totals']
        company = result['company']

        output = io.BytesIO()
        import xlsxwriter  # noqa: PLC0415
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet(_('Account Hierarchy')[:31])
        sheet.hide_gridlines(2)
        sheet.freeze_panes(4, 3)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(0.25, 0.25, 0.5, 0.5)

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 18,
            'font_color': '#2f3367',
            'align': 'left',
            'valign': 'vcenter',
        })
        subtitle_format = workbook.add_format({
            'font_size': 10,
            'font_color': '#6b7280',
            'align': 'left',
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_color': '#ffffff',
            'bg_color': '#4f46a5',
            'border': 0,
            'align': 'center',
            'valign': 'vcenter',
        })
        text_format = workbook.add_format({'font_color': '#273142'})
        parent_format = workbook.add_format({
            'bold': True,
            'font_color': '#2f3367',
            'bg_color': '#f2f0ff',
        })
        muted_format = workbook.add_format({'font_color': '#6b7280'})
        amount_format = workbook.add_format({
            'num_format': '#,##0.00;[Red]-#,##0.00;–',
            'font_color': '#273142',
        })
        parent_amount_format = workbook.add_format({
            'num_format': '#,##0.00;[Red]-#,##0.00;–',
            'bold': True,
            'font_color': '#2f3367',
            'bg_color': '#f2f0ff',
        })
        total_label_format = workbook.add_format({
            'bold': True,
            'font_color': '#ffffff',
            'bg_color': '#312e81',
            'align': 'right',
        })
        total_amount_format = workbook.add_format({
            'num_format': '#,##0.00;[Red]-#,##0.00;–',
            'bold': True,
            'font_color': '#ffffff',
            'bg_color': '#312e81',
        })

        sheet.merge_range(0, 0, 0, 6, company['name'], title_format)
        period = self._get_period_label(kwargs.get('date_from'), kwargs.get('date_to'))
        subtitle = _(
            "Chart of Accounts Hierarchy · %(period)s · %(currency)s",
            period=period,
            currency=company['currency_name'],
        )
        sheet.merge_range(1, 0, 1, 6, subtitle, subtitle_format)

        header_row = 3
        headers = [
            _('Account'),
            _('Code'),
            _('Type'),
            _('Opening'),
            _('Debit'),
            _('Credit'),
            _('Closing'),
        ]
        sheet.write_row(header_row, 0, headers, header_format)
        sheet.set_row(header_row, 24)
        sheet.set_column(0, 0, 46)
        sheet.set_column(1, 1, 15)
        sheet.set_column(2, 2, 22)
        sheet.set_column(3, 6, 17)

        row = header_row + 1
        folded_level = None
        for line in lines:
            if folded_level is not None and line['level'] <= folded_level:
                folded_level = None
            hidden = folded_level is not None and line['level'] > folded_level
            is_parent = line.get('is_parent', False)
            name_format = parent_format if is_parent else text_format
            number_format = parent_amount_format if is_parent else amount_format
            sheet.write(row, 0, line.get('name', ''), name_format)
            sheet.write(row, 1, line.get('code', ''), name_format)
            sheet.write(row, 2, line.get('account_type_display', ''), parent_format if is_parent else muted_format)
            sheet.write_number(row, 3, line.get('initial_balance', 0.0), number_format)
            sheet.write_number(row, 4, line.get('debit', 0.0), number_format)
            sheet.write_number(row, 5, line.get('credit', 0.0), number_format)
            sheet.write_number(row, 6, line.get('closing_balance', 0.0), number_format)
            sheet.set_row(row, 21, None, {
                'level': min(int(line.get('level', 0)), 7),
                'hidden': hidden,
                'collapsed': bool(is_parent and line.get('folded')),
            })
            if is_parent and line.get('folded'):
                folded_level = line['level']
            row += 1

        sheet.autofilter(header_row, 0, max(row - 1, header_row), 6)
        row += 1
        sheet.merge_range(row, 0, row, 2, _('GRAND TOTAL'), total_label_format)
        sheet.write_number(row, 3, totals['initial_balance'], total_amount_format)
        sheet.write_number(row, 4, totals['debit'], total_amount_format)
        sheet.write_number(row, 5, totals['credit'], total_amount_format)
        sheet.write_number(row, 6, totals['closing_balance'], total_amount_format)
        sheet.set_row(row, 25)
        sheet.print_area(0, 0, row, 6)
        sheet.repeat_rows(header_row, header_row)

        workbook.close()
        content = output.getvalue()
        output.close()

        filename = osutil.clean_filename(
            _('Account Hierarchy - %(company)s - %(period)s', company=company['name'], period=period)
        ) + '.xlsx'
        return request.make_response(content, headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename)),
        ])

    @staticmethod
    def _get_period_label(date_from, date_to):
        if date_from and date_to:
            return _('%(date_from)s to %(date_to)s', date_from=date_from, date_to=date_to)
        if date_from:
            return _('From %(date_from)s', date_from=date_from)
        if date_to:
            return _('Up to %(date_to)s', date_to=date_to)
        return _('All Time')
