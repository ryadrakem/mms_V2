/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState } from "@smartdz/owl";
import { useService } from "@web/core/utils/hooks";

export class MeetingSummaryGenerator extends Component {
  static template = "meeting_management_base.MeetingSummaryGenerator";
  static props = {
    action: { type: Object, optional: true },
  };

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.notification = useService("notification");

    this.state = useState({
      loading: false,
      generating: false,
      summary: null,
      error: null,
      meetingId: this.props.action?.params?.meeting_id,
      meetingName: this.props.action?.params?.meeting_name,
    });
  }

  async generateSummary() {
    this.state.generating = true;
    this.state.error = null;

    try {
      const response = await fetch("/meeting/generate_summary", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          method: "call",
          params: {
            meeting_id: this.state.meetingId,
          },
        }),
      });

      const data = await response.json();

      if (data.error || !data.result?.success) {
        throw new Error(data.error?.message || data.result?.error || "Failed to generate summary");
      }

      this.state.summary = data.result.summary_data;

      this.notification.add("Summary generated successfully! Opening summary form...", {
        type: "success",
      });

      // Open the summary form
      setTimeout(() => {
        this.action.doAction({
          type: "ir.actions.act_window",
          res_model: "dw.meeting.summary",
          res_id: data.result.summary_id,
          views: [[false, "form"]],
          target: "current",
        });
      }, 1000);
    } catch (error) {
      console.error("Failed to generate summary:", error);
      this.state.error = error.message;
      this.notification.add("Failed to generate summary: " + error.message, {
        type: "danger",
      });
    } finally {
      this.state.generating = false;
    }
  }

  cancel() {
    this.action.doAction({ type: "ir.actions.act_window_close" });
  }
}

registry.category("actions").add("generate_meeting_summary", MeetingSummaryGenerator);