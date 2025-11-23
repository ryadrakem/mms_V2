/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@smartdz/owl";
import { loadJS } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";

export class MeetingView extends Component {
  static template = "meeting_management_base.MeetingView";
  static props = {
    action: { type: Object, optional: true },
    meetingId: { type: Number, optional: true },
    actionId: { type: Number, optional: true },
    updateActionState: { type: Function, optional: true },
    className: { type: String, optional: true },
    globalState: { type: Object, optional: true },
  };

  setup() {
    this.env = this.props.action?.env || this.env;
    this.orm = this.env.services.orm;
    this.actionService = this.env.services.action;
    this.notification = this.env.services.notification;
    this.state = useState({
      loading: true,
      error: null,

      meeting: {
        name: "",
        actual_end_datetime: null,
        duration: 0,
        planification_id: null,
        objet: "",
        meeting_type_id: null,
        subject_order: [],
        planned_start_datetime: null,
        planned_end_time: null,
        participant_ids: [],
        participants: [],
        state: "draft",
        actual_start_datetime: null,
        display_camera: false,
        actual_duration: false,
        is_external: false,
        client_ids: [],
        location_id: null,
        room_id: null,
        pv: "",
      },

      activeMainTab: 'agenda',
      formattedDuration: '00:00',
      currentUserSessionId: null,
      isCurrentUserParticipant: false,
    });

    this.planificationId = null;
    this.meetingId = null;
    this.userId = null;

    // Bind methods
    this.goBack = this.goBack.bind(this);
    this.openMySession = this.openMySession.bind(this);
    this.toggleNotes = this.toggleNotes.bind(this);
    this.toggleActions = this.toggleActions.bind(this);
    this.toggleAgenda = this.toggleAgenda.bind(this);
    this.leaveMeeting = this.leaveMeeting.bind(this);

    onWillStart(async () => {
      const context = this.props.action?.context || {};
      this.meetingId = context.active_id;
      this.planificationId = context.default_planification_id;
      this.userId = context.uid;

      if (!this.meetingId) {
        this.state.error = "No Meeting ID provided";
        this.state.loading = false;
        return;
      }
      await this.loadMeetingData();


    });
  }

  async loadMeetingData() {
    try {

      const meetings = await this.orm.read(
        "dw.meeting",
        [this.meetingId],
        [
          "name",
          "actual_end_datetime",
          "duration",
          "planification_id",
          "objet",
          "meeting_type_id",
          "subject_order",
          "planned_start_datetime",
          "planned_end_time",
          "participant_ids",
          "state",
          "actual_start_datetime",
          "actual_duration",
          "is_external",
          "client_ids",
          "location_id",
          "room_id",
          "pv",
        ]
      );
      console.log("Loaded meeting data:", meetings);

      if (!meetings || meetings.length === 0) {
        throw new Error("Meeting not found");
      }

      const meetingData = meetings[0];

      this.meetingId = Array.isArray(meetingData.meeting_id)
        ? meetingData.meeting_id[0]
        : meetingData.meeting_id;

      this.planificationId = Array.isArray(meetingData.planification_id)
        ? meetingData.planification_id[0]
        : meetingData.planification_id;

      this.state.meeting = {
        id: this.meetingId,
        name: meetingData.name || "",
        actual_end_datetime: meetingData.actual_end_datetime || null,
        duration: meetingData.duration || 0,
        planification_id: this.planificationId,
        objet: meetingData.objet || "",
        meeting_type_id: meetingData.meeting_type_id || null,
        subject_order: meetingData.subject_order || [],
        planned_start_datetime: meetingData.planned_start_datetime || null,
        planned_end_time: meetingData.planned_end_time || null,
        participant_ids: meetingData.participant_ids || [],
        state: meetingData.state || "done",
        actual_start_datetime: meetingData.actual_start_datetime || null,
        actual_duration: meetingData.actual_duration || null,
        is_external: meetingData.is_external || false,
        client_ids: meetingData.client_ids || false,
        location_id: meetingData.location_id || null,
        room_id: meetingData.room_id || null,
        pv: meetingData.pv || "",
      };

      if (meetingData.participant_ids && meetingData.participant_ids.length > 0) {
        const participantRecords = await this.orm.read(
          'dw.participant',
          meetingData.participant_ids,
          ['id', 'name', 'user_id']
        );
        this.state.meeting.participants = participantRecords;
        this.state.meeting.participant_ids = participantRecords.map(p => p.id);

        const currentUserId = this.userId || null;
        console.log("Current user ID:", currentUserId);
        const currentUserParticipant = participantRecords.find(p => {
          const userId = Array.isArray(p.user_id) ? p.user_id[0] : p.user_id;
          return userId === currentUserId;
        });
        console.log("Current user participant record:", currentUserParticipant);
        if (currentUserParticipant) {
          this.state.isCurrentUserParticipant = true;

          // Search for the user's session
          const sessions = await this.orm.searchRead(
            'dw.meeting.session',
            [['participant_id', '=', currentUserParticipant.id]],
            ['id'],
          );
          console.log("Current user sessions found:", sessions);

          if (sessions && sessions.length > 0) {
            this.state.currentUserSessionId = sessions[0].id;
          }
        }
      }

      if (meetingData.subject_order && meetingData.subject_order.length > 0) {
        const subject_orderRecords = await this.orm.read(
          'dw.agenda',
          meetingData.subject_order,
          ['name']
        );
        this.state.meeting.subject_order = subject_orderRecords;
        this.state.meeting.subject_order_names = subject_orderRecords.map(p => p.id);
      }
        const d = this.state.meeting.actual_duration;
        if (d != null) {
            const h = Math.floor(d);
            const m = Math.round((d - h) * 60);

            this.state.formattedDuration = `${h.toString().padStart(2, '0')}:${m
                .toString()
                .padStart(2, '0')}`;
        }


      this.state.loading = false;
    } catch (error) {
      console.error("Failed to load Meeting data:", error);
      this.state.error = "Failed to load Meeting data";
      this.state.loading = false;
      this.notification.add("Failed to load meeting Meeting", {
        type: "danger",
      });
    }
  }

    toggleNotes() {
        this.state.activeMainTab = this.state.activeMainTab === 'notes' ? 'video' : 'notes';
    }

    toggleActions() {
    this.state.activeMainTab = this.state.activeMainTab === 'actions' ? 'video' : 'actions';
    }

    toggleAgenda() {
    this.state.activeMainTab = this.state.activeMainTab === 'actions' ? 'video' : 'actions';
    }

    async openMySession() {
      console.log("Opening session for current user:", this.state.currentUserSessionId);
      try {
          if (!this.state.currentUserSessionId) {
            this.notification.add("No session found for current user", {
              type: "warning",
            });
            return;
          }

            // Get the session details
          const sessions = await this.orm.read(
            'dw.meeting.session',
            [this.state.currentUserSessionId],
            ['id', 'user_id']
          );

          if (!sessions || sessions.length === 0) {
            this.notification.add("Session not found", {
              type: "warning",
            });
            return;
          }

          const session = sessions[0];
          const userId = Array.isArray(session.user_id) ? session.user_id[0] : session.user_id;
          const userName = Array.isArray(session.user_id) ? session.user_id[1] : '';

          await this.actionService.doAction({
            type: "ir.actions.client",
            name: `Meeting: ${this.state.meeting.name}-${userName}`,
            tag: 'meeting_session_view_action',
            params: {
              planification_id: this.planificationId,
            },
            context: {
              active_id: this.state.currentUserSessionId,
              default_session_id: this.state.currentUserSessionId,
              default_planification_id: this.planificationId,
              default_pv: this.state.meeting.pv,
            },
          });
      } catch (error) {
          console.error("Failed to open session:", error);
          this.notification.add("Failed to open session", {
            type: "danger",
          });
      }
  }

  async leaveMeeting() {
        this.goBack();
  }

  async goBack() {
    try {
      if (this.planificationId) {
        await this.actionService.doAction({
          type: "ir.actions.act_window",
          res_model: "dw.planification.meeting",
          res_id: this.planificationId,
          views: [[false, "form"]],
          target: "current",
        });
      } else {
        window.history.back();
      }
    } catch (error) {
      console.error("Failed to navigate back:", error);
      window.history.back();
    }
  }
}

registry.category("actions").add("meetin_view_action", MeetingView);