/** @odoo-module **/
import { Component, useState } from "@smartdz/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MeetingHomeDashboard extends Component {
    static template = "meeting_management_base.MeetingHomeDashboard";

    setup() {
        this.actionService = useService("action");

        // État local pour toutes les stats
        this.state = useState({
            planned_count: 0,
            in_progress_count: 0,
            action_todo_count: 0,
        });

        // Charger les stats au démarrage
        this.loadCounts();
    }

    async loadCounts() {
        try {
            // Réunions planifiées
            const meeting_planned = await this.env.services.orm.searchCount(
                "dw.planification.meeting",
                [["state", "=", "planned"]]
            );
            this.state.planned_count = meeting_planned;

            // Réunions en cours
            const meeting_inProgress = await this.env.services.orm.searchCount(
                "dw.meeting",
                [["state", "=", ["in_progress", "paused"]]]
            );
            this.state.in_progress_count = meeting_inProgress;

            // Actions à faire
            const action_todo = await this.env.services.orm.searchCount(
                "dw.dw.actions",
                [["state", "=", "to_do"]]
            );
            this.state.action_todo_count = action_todo;
        } catch (error) {
            console.error("Erreur lors du chargement du compteur:", error);
        }
    }

    async openMenuAction(xmlId, event) {
        try {
            // Empêcher la propagation de l'événement
            if (event) {
                event.stopPropagation();
            }

            await this.actionService.doAction(xmlId);
        } catch (error) {
            console.error("Error opening action:", error);
        }
    }
}

registry.category("actions").add(
    "meeting_management_base.meeting_home_dashboard_action",
    MeetingHomeDashboard
);