from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccountHierarchy(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.root_account, cls.child_account, cls.counterpart_account = cls.env[
            'account.account'
        ].create([
            {
                'name': 'Hierarchy Test Root',
                'code': 'APH99100',
                'account_type': 'asset_current',
                'company_ids': [Command.link(cls.company.id)],
            },
            {
                'name': 'Hierarchy Test Child',
                'code': 'APH99101',
                'account_type': 'asset_current',
                'company_ids': [Command.link(cls.company.id)],
            },
            {
                'name': 'Hierarchy Test Counterpart',
                'code': 'APH99102',
                'account_type': 'liability_current',
                'company_ids': [Command.link(cls.company.id)],
            },
        ])
        cls.child_account.parent_id = cls.root_account

    def test_parent_path_and_recursion_guard(self):
        self.assertEqual(self.child_account.hierarchy_level, 1)
        self.assertTrue(self.child_account.parent_path.endswith(f'{self.child_account.id}/'))
        with self.assertRaises(UserError):
            self.root_account.parent_id = self.child_account

    def test_zero_balance_tree_and_rollup(self):
        result = self.env['account.account'].get_hierarchy_data(
            company_id=self.company.id,
            display_account='all',
            include_zero=True,
            show_unfolded=True,
        )
        lines = {line['id']: line for line in result['lines']}
        self.assertIn(self.root_account.id, lines)
        self.assertIn(self.child_account.id, lines)
        self.assertTrue(lines[self.root_account.id]['is_parent'])
        self.assertEqual(lines[self.root_account.id]['level'], 0)
        self.assertEqual(lines[self.child_account.id]['level'], 1)

    def test_opening_period_and_parent_rollup(self):
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id),
            ('type', '=', 'general'),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({
                'name': 'Hierarchy Test Journal',
                'code': 'APHJ',
                'type': 'general',
                'company_id': self.company.id,
            })

        for move_date, amount in ((date(2026, 1, 1), 100.0), (date(2026, 2, 1), 25.0)):
            move = self.env['account.move'].create({
                'date': move_date,
                'journal_id': journal.id,
                'line_ids': [
                    Command.create({
                        'name': 'Hierarchy test debit',
                        'account_id': self.child_account.id,
                        'debit': amount,
                    }),
                    Command.create({
                        'name': 'Hierarchy test credit',
                        'account_id': self.counterpart_account.id,
                        'credit': amount,
                    }),
                ],
            })
            move.action_post()

        result = self.env['account.account'].get_hierarchy_data(
            company_id=self.company.id,
            date_from='2026-02-01',
            date_to='2026-02-28',
            display_account='not_zero',
            show_unfolded=True,
        )
        lines = {line['id']: line for line in result['lines']}
        child = lines[self.child_account.id]
        root = lines[self.root_account.id]
        self.assertEqual(child['initial_balance'], 100.0)
        self.assertEqual(child['debit'], 25.0)
        self.assertEqual(child['closing_balance'], 125.0)
        self.assertEqual(root['initial_balance'], 100.0)
        self.assertEqual(root['debit'], 25.0)
        self.assertEqual(root['closing_balance'], 125.0)
        self.assertEqual(result['totals']['closing_balance'], 0.0)
