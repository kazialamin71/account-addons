import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class ChartOfAccounts extends Component {
    static template = "om_account_chart_hierarchy.ChartOfAccounts";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.display = { controlPanel: {} };

        this.companies = [];
        this.fiscalYears = [];

        this.state = useState({
            companyId: null,
            fiscalYearId: null,
            targetMove: "posted",
            lines: [],
            unfolded: {},
            currencyId: null,
            currencyName: "",
            dateFrom: null,
            dateTo: null,
            hasFiscalYear: true,
        });

        onWillStart(async () => {
            const filters = await this.orm.call("account.chart.hierarchy.report", "get_filters", []);
            this.companies = filters.companies;
            this.fiscalYears = filters.fiscal_years;
            this.state.companyId = filters.default_company_id;
            this.state.fiscalYearId = this.availableFiscalYears[0]?.id || null;
            await this.loadLines();
        });
    }

    //---- Data ----

    /** Fiscal years belong to a company, so the picker follows the company selector. */
    get availableFiscalYears() {
        return this.fiscalYears.filter((fy) => fy.company_id === this.state.companyId);
    }

    get currentFiscalYear() {
        return this.availableFiscalYears.find((fy) => fy.id === this.state.fiscalYearId);
    }

    /**
     * The period to report on. Without a configured fiscal year we fall back to
     * the current calendar year so the screen still shows something usable.
     */
    get period() {
        const fiscalYear = this.currentFiscalYear;
        if (fiscalYear) {
            return { dateFrom: fiscalYear.date_from, dateTo: fiscalYear.date_to };
        }
        const year = new Date().getFullYear();
        return { dateFrom: `${year}-01-01`, dateTo: `${year}-12-31` };
    }

    async loadLines() {
        const { dateFrom, dateTo } = this.period;
        const result = await this.orm.call("account.chart.hierarchy.report", "get_lines", [
            this.state.companyId,
            dateFrom,
            dateTo,
            this.state.targetMove,
        ]);
        this.state.lines = result.lines;
        this.state.currencyId = result.currency_id;
        this.state.currencyName = result.currency_name;
        this.state.dateFrom = result.date_from;
        this.state.dateTo = result.date_to;
        this.state.hasFiscalYear = Boolean(this.currentFiscalYear);
        this.unfoldToLevel(1);
    }

    //---- Folding ----

    /** Flatten the tree, keeping only the rows whose ancestors are all unfolded. */
    get displayLines() {
        const rows = [];
        const collect = (children) => {
            for (const row of children) {
                rows.push(row);
                if (row.children.length && this.state.unfolded[row.id]) {
                    collect(row.children);
                }
            }
        };
        collect(this.state.lines);
        return rows;
    }

    /** Unfold every row down to `maxLevel`, folding everything deeper. */
    unfoldToLevel(maxLevel) {
        const unfolded = {};
        const walk = (children) => {
            for (const row of children) {
                if (row.children.length && row.level < maxLevel) {
                    unfolded[row.id] = true;
                }
                walk(row.children);
            }
        };
        walk(this.state.lines);
        this.state.unfolded = unfolded;
    }

    toggleRow(row) {
        if (this.state.unfolded[row.id]) {
            delete this.state.unfolded[row.id];
        } else {
            this.state.unfolded[row.id] = true;
        }
    }

    onClickExpandAll() {
        this.unfoldToLevel(Infinity);
    }

    onClickCollapseAll() {
        this.state.unfolded = {};
    }

    //---- Handlers ----

    async onChangeCompany(ev) {
        this.state.companyId = Number(ev.target.value);
        // The previous fiscal year belongs to the previous company.
        this.state.fiscalYearId = this.availableFiscalYears[0]?.id || null;
        await this.loadLines();
    }

    async onChangeFiscalYear(ev) {
        this.state.fiscalYearId = Number(ev.target.value);
        await this.loadLines();
    }

    async onChangeTargetMove(ev) {
        this.state.targetMove = ev.target.value;
        await this.loadLines();
    }

    async onClickAccount(row) {
        const action = await this.orm.call(
            "account.chart.hierarchy.report",
            "action_open_journal_items",
            [row.id, this.state.companyId, this.state.dateFrom, this.state.dateTo, this.state.targetMove]
        );
        return this.actionService.doAction(action);
    }

    //---- Helpers ----

    formatAmount(value) {
        return formatMonetary(value, { currencyId: this.state.currencyId, noSymbol: true });
    }

    get periodLabel() {
        const fiscalYear = this.currentFiscalYear;
        return fiscalYear ? fiscalYear.name : _t("%(from)s to %(to)s", {
            from: this.state.dateFrom,
            to: this.state.dateTo,
        });
    }
}

registry.category("actions").add("om_chart_of_accounts_hierarchy", ChartOfAccounts);
