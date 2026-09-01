/** @odoo-module */

import { Dropdown as CoreDropdown } from "@web/core/dropdown/dropdown";
import { Component } from "@odoo/owl";

/**
 * Adapter for the pre-19 Dropdown API used by the report templates.
 *
 * Odoo 19 renders the default slot as the target and the named ``content``
 * slot as the menu.  Older report templates instead provide a ``toggler``
 * slot and use the default slot for menu items.  Keeping that translation in
 * one component makes all report filters follow the current core behaviour.
 */
export class LegacyDropdown extends Component {
    static template = "account_reports.LegacyDropdown";
    static components = { CoreDropdown };
    static props = {
        togglerClass: { type: String, optional: true },
        showCaret: { type: Boolean, optional: true },
        class: { type: String, optional: true },
        position: { type: String, optional: true },
        menuClass: { type: [String, Object], optional: true },
        listRendererClass: { type: String, optional: true },
        disabled: { type: Boolean, optional: true },
        beforeOpen: { type: Function, optional: true },
        slots: {
            type: Object,
            shape: {
                toggler: { optional: true },
                default: { optional: true },
            },
        },
    };

    get togglerClasses() {
        return [
            this.props.togglerClass,
            this.props.class,
            this.props.showCaret ? "" : "o-dropdown--no-caret",
        ].filter(Boolean).join(" ");
    }

    get menuClasses() {
        return this.props.menuClass || this.props.listRendererClass || "";
    }
}

