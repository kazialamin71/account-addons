/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { formatFloat, formatMonetary } from "@web/views/fields/formatters";
import { Component, onWillStart, useState } from "@odoo/owl";


export class AccountHierarchyClient extends Component {
    static template = "account_parent_hierarchy.AccountHierarchyClient";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.action = this.props.action;
        this.state = useState({
            lines: [],
            serverTotals: {},
            company: {},
            loading: true,
            dateFrom: "",
            dateTo: "",
            query: "",
        });
        this.reportParams = {};
        this.datesInitialized = false;
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        const context = this.action.context || {};
        if (!this.datesInitialized) {
            this.state.dateFrom = context.wizard_date_from || "";
            this.state.dateTo = context.wizard_date_to || "";
            this.datesInitialized = true;
        }
        this.reportParams = {
            company_id: context.wizard_company_id || false,
            date_from: this.state.dateFrom || false,
            date_to: this.state.dateTo || false,
            target_move: context.wizard_target_move || "posted",
            hierarchy_by: context.wizard_hierarchy_by || "account",
            display_account: context.wizard_display_account || "not_zero",
            show_unfolded: Boolean(context.wizard_show_unfolded),
            include_zero: Boolean(context.wizard_include_zero),
        };
        try {
            const result = await this.orm.call(
                "account.account",
                "get_hierarchy_data",
                [],
                this.reportParams
            );
            this.state.lines = result.lines || [];
            this.state.serverTotals = result.totals || {};
            this.state.company = result.company || {};
            this.reportParams.company_id = result.company?.id || this.reportParams.company_id;
        } catch (error) {
            this.state.lines = [];
            this.state.serverTotals = {};
            this.notification.add(_t("The account hierarchy could not be loaded."), {
                type: "danger",
                sticky: true,
            });
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    onDateFromChange(event) {
        this.state.dateFrom = event.target.value;
    }

    onDateToChange(event) {
        this.state.dateTo = event.target.value;
    }

    onSearchInput(event) {
        this.state.query = event.target.value;
    }

    async onApplyDateFilter() {
        if (
            this.state.dateFrom &&
            this.state.dateTo &&
            this.state.dateFrom > this.state.dateTo
        ) {
            this.notification.add(
                _t("The start date must be earlier than or equal to the end date."),
                { type: "warning" }
            );
            return;
        }
        await this.loadData();
    }

    async onClearDates() {
        this.state.dateFrom = "";
        this.state.dateTo = "";
        await this.loadData();
    }

    get dateRangeLabel() {
        if (this.state.dateFrom && this.state.dateTo) {
            return `${this.state.dateFrom} → ${this.state.dateTo}`;
        }
        if (this.state.dateFrom) {
            return _t("From %s", this.state.dateFrom);
        }
        if (this.state.dateTo) {
            return _t("Up to %s", this.state.dateTo);
        }
        return _t("All Time");
    }

    get moveStateLabel() {
        return this.reportParams.target_move === "all" ? _t("All Entries") : _t("Posted Only");
    }

    get displayLabel() {
        const labels = {
            all: _t("All Accounts"),
            movement: _t("With Movements"),
            not_zero: _t("Non-zero Balance"),
        };
        return labels[this.reportParams.display_account] || labels.not_zero;
    }

    getUnfoldedIds() {
        return this.state.lines
            .filter((line) => line.is_parent && !line.folded)
            .map((line) => line.id);
    }

    async onPrintPdf() {
        await this.actionService.doAction(
            "account_parent_hierarchy.action_report_account_hierarchy",
            {
                additional_context: {
                    ...this.reportParams,
                    unfolded_ids: this.getUnfoldedIds(),
                    report_show_unfolded: false,
                },
            }
        );
    }

    async onExportXlsx() {
        const params = {
            ...this.reportParams,
            unfolded_ids: JSON.stringify(this.getUnfoldedIds()),
        };
        const cleanParams = Object.fromEntries(
            Object.entries(params).filter(([, value]) => value !== false && value != null)
        );
        const query = new URLSearchParams(cleanParams).toString();
        await this.actionService.doAction({
            type: "ir.actions.act_url",
            url: `/account_parent_hierarchy/download_xlsx?${query}`,
            target: "download",
        });
    }

    toggleFold(line) {
        const target = this.state.lines.find((item) => item.id === line.id);
        if (target) {
            target.folded = !target.folded;
        }
    }

    expandAll() {
        for (const line of this.state.lines) {
            if (line.is_parent) {
                line.folded = false;
            }
        }
    }

    collapseAll() {
        for (const line of this.state.lines) {
            if (line.is_parent) {
                line.folded = true;
            }
        }
    }

    async openAccountMoveLines(line) {
        const domain = [
            ["account_id", line.is_parent ? "child_of" : "=", line.id],
            ["company_id", "=", this.reportParams.company_id],
            ["parent_state", "!=", "cancel"],
        ];
        if (this.reportParams.target_move === "posted") {
            domain.push(["parent_state", "=", "posted"]);
        }
        if (this.state.dateFrom) {
            domain.push(["date", ">=", this.state.dateFrom]);
        }
        if (this.state.dateTo) {
            domain.push(["date", "<=", this.state.dateTo]);
        }
        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Journal Items: %s", line.name),
            res_model: "account.move.line",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: { create: false },
            target: "current",
        });
    }

    get displayedLines() {
        const query = this.state.query.trim().toLocaleLowerCase();
        if (query) {
            const byId = new Map(this.state.lines.map((line) => [line.id, line]));
            const visibleIds = new Set();
            for (const line of this.state.lines) {
                const haystack = `${line.code} ${line.name} ${line.account_type_display}`.toLocaleLowerCase();
                if (!haystack.includes(query)) {
                    continue;
                }
                let current = line;
                const seen = new Set();
                while (current && !seen.has(current.id)) {
                    seen.add(current.id);
                    visibleIds.add(current.id);
                    current = byId.get(current.parent_id);
                }
            }
            return this.state.lines.filter((line) => visibleIds.has(line.id));
        }

        const visible = [];
        let hiddenLevel = null;
        for (const line of this.state.lines) {
            if (hiddenLevel !== null && line.level > hiddenLevel) {
                continue;
            }
            if (hiddenLevel !== null) {
                hiddenLevel = null;
            }
            visible.push(line);
            if (line.is_parent && line.folded) {
                hiddenLevel = line.level;
            }
        }
        return visible;
    }

    formatMoney(amount) {
        if (this.state.company.currency_id) {
            return formatMonetary(amount || 0, {
                currencyId: this.state.company.currency_id,
            });
        }
        return formatFloat(amount || 0, { digits: [null, 2] });
    }

    get totals() {
        return {
            initial_balance: 0,
            debit: 0,
            credit: 0,
            closing_balance: 0,
            ...this.state.serverTotals,
        };
    }

    getBadgeClass(type) {
        if (!type) {
            return "o_hierarchy_badge_default";
        }
        if (type.includes("view") || type.includes("off_balance")) {
            return "o_hierarchy_badge_view";
        }
        if (type.includes("asset")) {
            return "o_hierarchy_badge_asset";
        }
        if (type.includes("liability")) {
            return "o_hierarchy_badge_liability";
        }
        if (type.includes("equity")) {
            return "o_hierarchy_badge_equity";
        }
        if (type.includes("income")) {
            return "o_hierarchy_badge_income";
        }
        if (type.includes("expense")) {
            return "o_hierarchy_badge_expense";
        }
        return "o_hierarchy_badge_default";
    }
}

registry.category("actions").add("account_hierarchy_client_action", AccountHierarchyClient);
