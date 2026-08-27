# -*- coding: utf-8 -*-
"""QWeb report parsers.

Every financial report renders from the very same ``_compute_rows()`` the screen
uses, so the PDF and the on-screen grid can never drift apart.
"""
from odoo import api, models


class ReportCommon(models.AbstractModel):
    """Shared plumbing: run the wizard's own computation and hand it to QWeb."""
    _name = 'report.leih_account_v8.common'
    _description = 'Financial Report Renderer (common)'

    # Set on each concrete renderer.
    _wizard_model = None

    @api.model
    def _get_report_values(self, docids, data=None):
        wizards = self.env[self._wizard_model].browse(docids)
        reports = []
        for wizard in wizards:
            reports.append({
                'wizard': wizard,
                'header': wizard._report_header(),
                'rows': wizard._compute_rows(),
            })
        return {
            'doc_ids': docids,
            'doc_model': self._wizard_model,
            'docs': wizards,
            'reports': reports,
            'company': self.env.company,
        }


class ReportGeneralLedger(models.AbstractModel):
    _name = 'report.leih_account_v8.report_general_ledger'
    _inherit = ['report.leih_account_v8.common']
    _description = 'General Ledger Renderer'
    _wizard_model = 'account.report.general.ledger'


class ReportTrialBalance(models.AbstractModel):
    _name = 'report.leih_account_v8.report_trial_balance'
    _inherit = ['report.leih_account_v8.common']
    _description = 'Trial Balance Renderer'
    _wizard_model = 'account.balance.report'


class ReportPartnerLedger(models.AbstractModel):
    _name = 'report.leih_account_v8.report_partner_ledger'
    _inherit = ['report.leih_account_v8.common']
    _description = 'Partner Ledger Renderer'
    _wizard_model = 'account.report.partnerledger'


class ReportAgedPartner(models.AbstractModel):
    _name = 'report.leih_account_v8.report_aged_partner'
    _inherit = ['report.leih_account_v8.common']
    _description = 'Aged Partner Balance Renderer'
    _wizard_model = 'account.aged.trial.balance'

    @api.model
    def _get_report_values(self, docids, data=None):
        values = super()._get_report_values(docids, data=data)
        # The bucket headers depend on the chosen bucket length.
        for report in values['reports']:
            report['labels'] = report['wizard']._bucket_labels()
        return values


class ReportJournal(models.AbstractModel):
    _name = 'report.leih_account_v8.report_journal'
    _inherit = ['report.leih_account_v8.common']
    _description = 'Journal Report Renderer'
    _wizard_model = 'account.report.journal'


class ReportFinancial(models.AbstractModel):
    _name = 'report.leih_account_v8.report_financial'
    _inherit = ['report.leih_account_v8.common']
    _description = 'Balance Sheet / P&L Renderer'
    _wizard_model = 'accounting.report'


class ReportTax(models.AbstractModel):
    _name = 'report.leih_account_v8.report_tax'
    _inherit = ['report.leih_account_v8.common']
    _description = 'Taxes Report Renderer'
    _wizard_model = 'account.tax.report.wizard'


class ReportBook(models.AbstractModel):
    _name = 'report.leih_account_v8.report_book'
    _inherit = ['report.leih_account_v8.common']
    _description = 'Cash / Bank / Day Book Renderer'
    _wizard_model = 'account.book.report'
