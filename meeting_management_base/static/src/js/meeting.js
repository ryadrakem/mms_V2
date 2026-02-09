/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef, markup } from "@smartdz/owl";
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

    // Use useRef for proper OWL reference handling
    this.pvEditorRef = useRef("pvEditor");
    // NEW: Reference for the hidden file input
    this.signedPvUploadRef = useRef("signedPvUpload");

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
        pv_status: "draft",
        pv_can_edit: false,
        pv_signed_document: null,
        pv_signed_document_name: null,
      },

      activeMainTab: 'agenda',
      formattedDuration: '00:00',
      currentUserSessionId: null,
      isCurrentUserParticipant: false,
      pvEditing: false,
      selectedFile: null,
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

    // PV-related methods
    this.generatePvTemplate = this.generatePvTemplate.bind(this);
    this.downloadPvWord = this.downloadPvWord.bind(this);
    this.downloadPvPdf = this.downloadPvPdf.bind(this);
    this.sendPvEmails = this.sendPvEmails.bind(this);
    this.setPvFinal = this.setPvFinal.bind(this);
    this.handleFileSelect = this.handleFileSelect.bind(this);
    this.uploadSignedPv = this.uploadSignedPv.bind(this);
    this.savePv = this.savePv.bind(this);
    this.togglePvEdit = this.togglePvEdit.bind(this);
    this.onPvInput = this.onPvInput.bind(this);
    // NEW: Bind the trigger method
    this.triggerFileUpload = this.triggerFileUpload.bind(this);

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

    onMounted(() => {
      // Set innerHTML when component mounts if in edit mode
      this.updatePvEditor();
    });

    onWillUnmount(() => {
      // Cleanup if needed
    });
  }

  // NEW: Safely trigger the hidden file input click
  triggerFileUpload() {
    if (this.signedPvUploadRef.el) {
        this.signedPvUploadRef.el.click();
    }
  }

  updatePvEditor() {
    // Update editor content when switching to edit mode
    if (this.state.pvEditing && this.pvEditorRef.el) {
      this.pvEditorRef.el.innerHTML = this.state.meeting.pv || '';
    }
  }

  onUploadClick() {
    document.getElementById('signed-pv-upload').click();
  }

  onDownloadClick() {
    const model = "dw.meeting";
    const fieldName = "pv_signed_document";
    const fileName = this.state.meeting.pv_signed_document_name;

    const url = `/web/content/${model}/${this.meetingId}/${fieldName}?download=true&filename=${encodeURIComponent(fileName)}`;
    window.open(url, "_blank");
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
          "pv_status",
          "pv_can_edit",
          "pv_signed_document",
          "pv_signed_document_name",
        ]
      );
      console.log("Loaded meeting data:", meetings);

      if (!meetings || meetings.length === 0) {
        throw new Error("Meeting not found");
      }

      const meetingData = meetings[0];

      this.meetingId = meetingData.id;

      this.planificationId = Array.isArray(meetingData.planification_id)
        ? meetingData.planification_id[0]
        : meetingData.planification_id;

      // ✅ FIX: Convert PV HTML to markup for safe rendering
      const pvContent = meetingData.pv || "";

      this.state.meeting = {
        id: this.meetingId,
        name: meetingData.name || "",
        actual_end_datetime: meetingData.actual_end_datetime || null,
        duration: meetingData.duration || 0,
        planification_id: this.planificationId,
        objet: meetingData.objet || "",
        meeting_type_id: Array.isArray(meetingData.meeting_type_id)
            ? meetingData.meeting_type_id[1]
            : null,
        subject_order: meetingData.subject_order || [],
        planned_start_datetime: meetingData.planned_start_datetime || null,
        planned_end_time: meetingData.planned_end_time || null,
        participant_ids: meetingData.participant_ids || [],
        state: meetingData.state || "done",
        actual_start_datetime: meetingData.actual_start_datetime || null,
        actual_duration: meetingData.actual_duration || null,
        is_external: meetingData.is_external || false,
        client_ids: meetingData.client_ids || false,
        location_id: Array.isArray(meetingData.location_id)
          ? meetingData.location_id[1]
          : null,
        room_id: Array.isArray(meetingData.room_id)
          ? meetingData.room_id[1]
          : null,
        pv: markup(pvContent),  // ✅ FIX: Mark as safe HTML
        pv_status: meetingData.pv_status || "draft",
        pv_can_edit: meetingData.pv_can_edit || false,
        pv_signed_document: meetingData.pv_signed_document || null,
        pv_signed_document_name: meetingData.pv_signed_document_name || null,
      };

      if (meetingData.participant_ids && meetingData.participant_ids.length > 0) {
        const participantRecords = await this.orm.read(
          'dw.participant',
          meetingData.participant_ids,
          ['id', 'name', 'user_id', 'attendance_status','is_late']
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

    getStatusLabel(status) {
        const labels = {
            'present': 'Present',
            'pause': 'In Pause',
            'absent': 'Absent',
            'excused': 'Excused',
            'default': 'Awaiting'
        };
        return labels[status] || 'Unknown';
  }

    getPvStatusLabel(status) {
        const labels = {
            'draft': 'Brouillon',
            'final': 'Final',
            'signed': 'Signé'
        };
        return labels[status] || 'Brouillon';
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

    togglePvEdit() {
        if (this.state.meeting.pv_can_edit) {
            this.state.pvEditing = !this.state.pvEditing;
            // Update editor content after state change
            setTimeout(() => this.updatePvEditor(), 50);
        }
    }

    onPvInput(ev) {
        // Get the inner HTML without HTML encoding issues
        this.state.meeting.pv = ev.target.innerHTML;
    }

    // ================== PV MANAGEMENT METHODS ==================

    async generatePvTemplate() {
        try {
            // FIXED: Pass meeting ID as array in second argument
            const result = await this.orm.call(
                'dw.meeting',
                'action_generate_pv_template',
                [[this.meetingId]]  // Pass as array of IDs
            );

            // Reload meeting data to get the generated PV
            await this.loadMeetingData();

            this.notification.add("PV template generated successfully", {
                type: "success",
            });
        } catch (error) {
            console.error("Failed to generate PV template:", error);
            this.notification.add("Failed to generate PV template", {
                type: "danger",
            });
        }
    }

    async savePv() {
        try {
            // ✅ FIX: Extract plain HTML string from markup before saving
            const pvHtml = typeof this.state.meeting.pv === 'string'
                ? this.state.meeting.pv
                : this.state.meeting.pv.toString();

            await this.orm.write("dw.meeting", [this.meetingId], {
                pv: pvHtml,
            });

            this.notification.add("PV saved successfully", {
                type: "success",
            });

            this.state.pvEditing = false;
        } catch (error) {
            console.error("Failed to save PV:", error);
            this.notification.add("Failed to save PV", {
                type: "danger",
            });
        }
    }

    async downloadPvWord() {
        try {
            // FIXED: Pass meeting ID as array in second argument
            const result = await this.orm.call(
                'dw.meeting',
                'action_download_pv_word',
                [[this.meetingId]]  // Pass as array of IDs
            );

            if (result && result.url) {
                window.open(result.url, '_blank');
            }

            this.notification.add("PV Word document generated", {
                type: "success",
            });
        } catch (error) {
            console.error("Failed to download Word PV:", error);
            this.notification.add("Failed to download Word document", {
                type: "danger",
            });
        }
    }

    async downloadPvPdf() {
        try {
            // FIXED: Pass meeting ID as array in second argument
            const result = await this.orm.call(
                'dw.meeting',
                'action_download_pv_pdf',
                [[this.meetingId]]  // Pass as array of IDs
            );

            if (result && result.url) {
                window.open(result.url, '_blank');
            }

            this.notification.add("PV PDF generated", {
                type: "success",
            });
        } catch (error) {
            console.error("Failed to download PDF PV:", error);
            this.notification.add("Failed to download PDF", {
                type: "danger",
            });
        }
    }

    async sendPvEmails() {
        const confirmed = confirm(
            "Are you sure you want to send the PV to all participants via email?"
        );

        if (!confirmed) return;

        try {
            // FIXED: Pass meeting ID as array in second argument
            await this.orm.call(
                'dw.meeting',
                'action_send_pv_emails',
                [[this.meetingId]]  // Pass as array of IDs
            );

            this.notification.add("PV sent to all participants successfully", {
                type: "success",
            });
        } catch (error) {
            console.error("Failed to send PV emails:", error);
            this.notification.add("Failed to send PV emails", {
                type: "danger",
            });
        }
    }

    async setPvFinal() {
        const confirmed = confirm(
            "Are you sure you want to set the PV status to Final? This will lock the PV from further editing by non-hosts."
        );

        if (!confirmed) return;

        try {
            // FIXED: Pass meeting ID as array in second argument
            await this.orm.call(
                'dw.meeting',
                'action_set_pv_final',
                [[this.meetingId]]  // Pass as array of IDs
            );

            // Reload meeting data to get updated status
            await this.loadMeetingData();

            this.notification.add("PV status set to Final", {
                type: "success",
            });
        } catch (error) {
            console.error("Failed to set PV final:", error);
            this.notification.add("Failed to set PV final", {
                type: "danger",
            });
        }
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.state.selectedFile = file;
            this.state.meeting.pv_signed_document_name = file.name;
        }
    }

    async uploadSignedPv() {
        try {
            if (!this.state.selectedFile) {
                this.notification.add("Please select a file first", {
                    type: "warning",
                });
                return;
            }

            // Convert file to base64
            const reader = new FileReader();
            reader.onload = async (e) => {
                const base64Data = e.target.result.split(',')[1];

                try {
                    // Upload the file
                    await this.orm.write("dw.meeting", [this.meetingId], {
                        pv_signed_document: base64Data,
                        pv_signed_document_name: this.state.selectedFile.name,
                        pv_status: 'signed',
                        state: 'done',
                    });

                    // Reload meeting data
                    await this.loadMeetingData();

                    this.notification.add("Signed PV uploaded and meeting closed", {
                        type: "success",
                    });

                    this.state.selectedFile = null;
                } catch (error) {
                    console.error("Failed to upload signed PV:", error);
                    this.notification.add("Failed to upload signed PV", {
                        type: "danger",
                    });
                }
            };

            reader.readAsDataURL(this.state.selectedFile);
        } catch (error) {
            console.error("Failed to upload signed PV:", error);
            this.notification.add("Failed to upload signed PV", {
                type: "danger",
            });
        }
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
              display_camera: false,
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