from odoo import fields, models


class AccountBalanceReport(models.TransientModel):
    _inherit = 'account.balance.report'

    enable_hierarchy = fields.Boolean(
        string="Print Account Hierarchy",
        default=False,
        help="Print the account hierarchy summary instead of the standard report.",
    )

    def _print_report(self, data):
        if self.enable_hierarchy:
            records, data = self._get_report_data(data)
            data['form']['enable_hierarchy'] = True
            data['form']['report_title'] = "Hierarchical Trial Balance"
            return self.env.ref(
                'account_parent_hierarchy.action_report_account_hierarchy'
            ).report_action(records, data=data)
        return super()._print_report(data)


class AccountReportGeneralLedger(models.TransientModel):
    _inherit = 'account.report.general.ledger'

    enable_hierarchy = fields.Boolean(
        string="Print Account Hierarchy Summary",
        default=False,
        help="Print an account hierarchy summary instead of detailed journal items.",
    )

    def _print_report(self, data):
        if self.enable_hierarchy:
            records, data = self._get_report_data(data)
            data['form']['enable_hierarchy'] = True
            data['form']['report_title'] = "Account Hierarchy Summary"
            return self.env.ref(
                'account_parent_hierarchy.action_report_account_hierarchy'
            ).report_action(records, data=data)
        return super()._print_report(data)
