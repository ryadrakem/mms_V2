/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@smartdz/owl";
import { loadJS } from "@web/core/assets";

export class MeetingSessionView extends Component {
  static template = "meeting_management_base.MeetingSessionView";
  static props = {
    action: { type: Object, optional: true },
    sessionId: { type: Number, optional: true },
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
      jitsiLoaded: false,
      jitsiAPI: null,
      error: null,

      session: {
        id: null,
        name: "",
        meeting_id: null,
        user_id: null,
        participant_id: null,
        personal_actions_ids: [],
        personal_notes: "",
        requirements: "",
        view_state: {},
        join_datetime: null,
        actual_end_datetime: null,
        duration: 0,
        is_connected: false,
        is_host: false,
        is_pv: false,
        can_edit_agenda: false,
        can_edit_summary: false,
        planification_id: null,
        objet: "",
        meeting_type_id: null,
        subject_order: [],
        planned_start_datetime: null,
        planned_end_time: null,
        participant_ids: [],
        participants: [],
        state: "in_progress",
        actual_start_datetime: null,
        display_camera: false,
        actual_duration: false,
        has_remote_participants: false,
      },

      localParticipantId: null,
      activeParticipants: 0,
      waitingParticipants: [],
      meetingDuration: "00:00:00",
      activeMainTab: 'video', // Default to video tab
      notes: "",
      actions: [],
      availableAssignees: [],
      formattedDate: "",
      formattedJoinTime: "",
      sessionDuration: 0,
      meetingTypeName: "",
      jitsiRoomId: null,
      pv: "",
      jitsiInitialized: false,
      showVideoPip: false,
    });

    this.sessionId = null;
    this.planificationId = null;
    this.meetingId = null;
    this.durationInterval = null;
    this.statusInterval = null;
    this.startTime = null;
    this._updateTimeout = null;
    this.jitsiApi = null; // Store Jitsi API instance

    // Bind methods
    this.goBack = this.goBack.bind(this);
    this.toggleNotes = this.toggleNotes.bind(this);
    this.toggleActions = this.toggleActions.bind(this);
    this.toggleCamera = this.toggleCamera.bind(this);
    this.toggleAgenda = this.toggleAgenda.bind(this);
    this.saveNotes = this.saveNotes.bind(this);
    this.savePv = this.savePv.bind(this);
    this.addNewAction = this.addNewAction.bind(this);
    this.updateAction = this.updateAction.bind(this);
    this.deleteAction = this.deleteAction.bind(this);
    this.admitParticipant = this.admitParticipant.bind(this);
    this.rejectParticipant = this.rejectParticipant.bind(this);
    this.leaveMeeting = this.leaveMeeting.bind(this);
    this.endMeeting = this.endMeeting.bind(this);
    this.retryConnection = this.retryConnection.bind(this);
    this.onTabChange = this.onTabChange.bind(this); // New method for tab changes

    this.loadPvTemplate = this.loadPvTemplate.bind(this);
    this.startBlankPv = this.startBlankPv.bind(this);
    this.generatePvTemplate = this.generatePvTemplate.bind(this);

    this.moveJitsiToSidebar = this.moveJitsiToSidebar.bind(this);
    this.moveJitsiToMain = this.moveJitsiToMain.bind(this);
    this.closeVideoPip = this.closeVideoPip.bind(this);
    this.showVideoPip = this.showVideoPip.bind(this);


    onWillStart(async () => {
      const context = this.props.action?.context || {};
      this.sessionId = context.active_id || context.default_session_id;
      this.planificationId = context.default_planification_id;

      if (!this.sessionId) {
        this.state.error = "No session ID provided";
        this.state.loading = false;
        return;
      }

      try {
        await loadJS("https://meet.jit.si/external_api.js");
      } catch (error) {
        console.error("Failed to load Jitsi API:", error);
      }

      await this.loadSessionData();
      await this.loadActions();
      await this.loadAvailableAssignees();
    });

    onMounted(async () => {
      if (!this.state.error && this.meetingId) {
        await this.initializeJitsi();
        this.startDurationTimer();
      }
  this.statusInterval = setInterval(async () => {
    await this.refreshParticipantStatus();
  }, 10000); // 10 seconds

  // Also call it once immediately to get initial status
  await this.refreshParticipantStatus();
    });

    onWillUnmount(() => {
      this.cleanupJitsi();
      if (this.durationInterval) {
        clearInterval(this.durationInterval);
      }
      if (this._updateTimeout) {
        clearTimeout(this._updateTimeout);
      }
      if (this.statusInterval) {
      clearInterval(this.statusInterval);
      }
    });
  }

  // -------------------- Helper methods for datetime handling --------------------
  // Format a JS Date (or parseable value) to Odoo DB string "YYYY-MM-DD HH:MM:SS" using UTC
  formatOdooDatetimeUTC(dateLike) {
    const d = dateLike instanceof Date ? dateLike : new Date(dateLike);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
  }

  // Parse server datetime into JS Date
  // Accepts ISO strings with 'T' or Odoo DB format 'YYYY-MM-DD HH:MM:SS'
  parseOdooDatetimeToDate(s) {
    if (!s) return null;
    if (typeof s !== "string") return new Date(s);
    // If it contains 'T' assume ISO
    if (s.includes("T")) {
      return new Date(s);
    }
    // Match DB format
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
    if (m) {
      const [_, Y, M, D, h, mi, sec] = m;
      // Treat DB values as UTC to avoid timezone 'Z' issues — change if your server uses local time
      return new Date(Date.UTC(+Y, +M - 1, +D, +h, +mi, +sec));
    }
    // Fallback to Date constructor
    return new Date(s);
  }

  async rpcCall(route, params) {
    const response = await fetch(route, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        params: params,
      }),
    });
    const data = await response.json();

    if (data.error) {
      throw new Error(data.error.message || data.error.data?.message || "RPC Error");
    }

    return data.result;
  }

  async loadSessionData() {
    try {
      const sessions = await this.orm.read(
        "dw.meeting.session",
        [this.sessionId],
        [
          "name",
          "meeting_id",
          "user_id",
          "participant_id",
          "personal_actions_ids",
          "personal_notes",
          "requirements",
          "view_state",
          "join_datetime",
          "actual_end_datetime",
          "duration",
          "is_connected",
          "is_host",
          "is_pv",
          "can_edit_agenda",
          "can_edit_summary",
          "planification_id",
          "objet",
          "meeting_type_id",
          "subject_order",
          "planned_start_datetime",
          "planned_end_time",
          "participant_ids",
          "state",
          "actual_start_datetime",
          "display_camera",
          "actual_duration",
          "has_remote_participants"
        ]
      );
      console.log("Loaded session_id:", this.sessionId);
      console.log("Loaded session data:", sessions);

      if (!sessions || sessions.length === 0) {
        throw new Error("Session not found");
      }

      const sessionData = sessions[0];

      this.meetingId = Array.isArray(sessionData.meeting_id)
        ? sessionData.meeting_id[0]
        : sessionData.meeting_id;

      this.planificationId = Array.isArray(sessionData.planification_id)
        ? sessionData.planification_id[0]
        : sessionData.planification_id;

      this.state.session = {
        id: sessionData.id,
        name: sessionData.name || "",
        meeting_id: this.meetingId,
        user_id: Array.isArray(sessionData.user_id)
          ? sessionData.user_id[0]
          : sessionData.user_id || null,
        participant_id: Array.isArray(sessionData.participant_id)
          ? sessionData.participant_id[0]
          : sessionData.participant_id || null,
        personal_actions_ids: sessionData.personal_actions_ids || [],
        personal_notes: sessionData.personal_notes || "",
        requirements: sessionData.requirements || "",
        view_state: sessionData.view_state || {},
        join_datetime: sessionData.join_datetime || null,
        actual_end_datetime: sessionData.actual_end_datetime || null,
        duration: sessionData.duration || 0,
        is_connected: sessionData.is_connected || false,
        is_host: sessionData.is_host || false,
        is_pv: sessionData.is_pv || false,
        can_edit_agenda: sessionData.can_edit_agenda || false,
        can_edit_summary: sessionData.can_edit_summary || false,
        planification_id: this.planificationId,
        objet: sessionData.objet || "",
        meeting_type_id: Array.isArray(sessionData.meeting_type_id)
          ? sessionData.meeting_type_id[0]
          : sessionData.meeting_type_id || null,
        subject_order: sessionData.subject_order || [],
        planned_start_datetime: sessionData.planned_start_datetime || null,
        planned_end_time: sessionData.planned_end_time || null,
        participant_ids: sessionData.participant_ids || [],
        state: sessionData.state || "in_progress",
        actual_start_datetime: sessionData.actual_start_datetime || null,
        display_camera: sessionData.display_camera || false,
        actual_duration: sessionData.actual_duration || null,
        has_remote_participants: sessionData.has_remote_participants || false,
      };

      this.state.session.display_camera = this.state.session.has_remote_participants ? true : this.state.session.display_camera;

      if (sessionData.participant_ids && sessionData.participant_ids.length > 0) {
        const participantRecords = await this.orm.read(
          'dw.participant',
          sessionData.participant_ids,
          ['id', 'name', 'attendance_status']
        );
        this.state.session.participants = participantRecords;
        this.state.session.participant_ids = participantRecords.map(p => p.id);
        console.log("Loaded participants:", this.state.session.participants);
        console.log("Loaded participant_ids:", this.state.session.participant_ids);
      }

      if (sessionData.subject_order && sessionData.subject_order.length > 0) {
        const subject_orderRecords = await this.orm.read(
          'dw.agenda',
          sessionData.subject_order,
          ['name']
        );
        this.state.session.subject_order = subject_orderRecords;
        this.state.session.subject_order_names = subject_orderRecords.map(p => p.id);
      }

      if (sessionData.planned_start_datetime) {
        const date = new Date(sessionData.planned_start_datetime);
        this.state.formattedDate = date.toLocaleDateString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
      }

      if (sessionData.join_datetime) {
        const joinDate = new Date(sessionData.join_datetime);
        this.state.formattedJoinTime = joinDate.toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        });
      }

      if (this.state.session.meeting_type_id) {
        const meetingTypes = await this.orm.read(
          "dw.meeting.type",
          [this.state.session.meeting_type_id],
          ["name"]
        );
        if (meetingTypes && meetingTypes.length > 0) {
          this.state.meetingTypeName = meetingTypes[0].name;
        }
      }

      this.state.sessionDuration = sessionData.duration || 0;

      this.state.notes = sessionData.personal_notes || "";

      const meetings = await this.orm.read(
        "dw.meeting",
        [this.meetingId],
        ["jitsi_room_id"]
      );
      if (meetings && meetings.length > 0) {
        this.state.jitsiRoomId = meetings[0].jitsi_room_id;
      }
      if (this.meetingId) {
        const meetings = await this.orm.read(
                  "dw.meeting",
                  [this.meetingId],
                  ["pv"]
                );
        if (meetings && meetings.length > 0) {
          this.state.pv = meetings[0].pv || "";
        }
      }

      this.state.loading = false;
    } catch (error) {
      console.error("Failed to load session data:", error);
      this.state.error = "Failed to load session data";
      this.state.loading = false;
      this.notification.add("Failed to load meeting session", {
        type: "danger",
      });
    }
  }

  getStatusLabel(status) {
        const labels = {
            'present': 'Present',
            'late': 'Late',
            'absent': 'Absent',
            'excused': 'Excused',
            'default': 'Awaiting'
        };
        return labels[status] || 'Unknown';
  }

  async loadActions() {
    try {
      const actions = await this.orm.searchRead(
        "dw.actions",
        [["session_id", "=", this.sessionId]],
        ["name", "assignee", "dead_line", "priority", "status", "meeting_id", "description"]
      );

      this.state.actions = actions.map(a => ({
        ...a,
        assignee_id: a.assignee ? (Array.isArray(a.assignee) ? a.assignee[0] : a.assignee) : "",
      }));
    } catch (error) {
      console.error("Failed to load actions:", error);
    }
  }

  async loadAvailableAssignees() {
    try {
      // Get all participants from the meeting
      if (this.state.session.participant_ids && this.state.session.participant_ids.length > 0) {
        const participants = await this.orm.read(
          "dw.participant",
          this.state.session.participant_ids,
          ["name", "user_id"]
        );

        this.state.availableAssignees = participants
          .filter(p => p.user_id)
          .map(p => ({
            id: Array.isArray(p.user_id) ? p.user_id[0] : p.user_id,
            name: p.name
          }));
      }
    } catch (error) {
      console.error("Failed to load assignees:", error);
    }
  }

  async initializeJitsi() {
    // Prevent multiple initializations
    if (this.jitsiApi && this.state.jitsiInitialized) {
      this.state.jitsiLoaded = true;
      this.resumeJitsi();
      return;
    }

    if (!window.JitsiMeetExternalAPI) {
      this.state.error = "Jitsi API not loaded";
      return;
    }

    try {
      const tokenData = await this.rpcCall("/meeting/jitsi/token", {
        meeting_id: this.meetingId,
        session_id: this.sessionId,
      });

      if (!tokenData || !tokenData.success) {
        throw new Error(tokenData?.error || "Authentication failed");
      }

      const { domain, room_name, token: jwt, is_moderator } = tokenData;

      console.log("🎥 Initializing Jitsi:", { domain, room_name, is_moderator });

      const container = document.getElementById("jitsi-meet-container");
      if (!container) {
        throw new Error("Jitsi container not found");
      }

      // Clear container only if not already initialized
      if (!this.state.jitsiInitialized) {
        container.innerHTML = "";
      }

      const options = {
        roomName: room_name,
        width: "100%",
        height: "100%",
        parentNode: container,
        jwt: jwt,
        configOverwrite: {
          prejoinPageEnabled: false,
          startWithAudioMuted: false,
          startWithVideoMuted: false,
          enableUserRolesBasedOnToken: true,
        },
        interfaceConfigOverwrite: {
          SHOW_JITSI_WATERMARK: false,
          TOOLBAR_ALWAYS_VISIBLE: false,
          DEFAULT_BACKGROUND: "#474747",
        },
        userInfo: {
          displayName: tokenData.user_name,
          email: tokenData.user_email,
        },
      };

      this.jitsiApi = new JitsiMeetExternalAPI(domain, options);
      this.state.jitsiAPI = this.jitsiApi;
      this.state.jitsiInitialized = true;
      this.setupJitsiEvents();

      this.notification.add("Connecting to video conference...", {
        type: "info",
      });
    } catch (error) {
      console.error("Failed to initialize Jitsi:", error);
      this.state.error = error.message || "Failed to connect";
      this.notification.add("Failed to connect to video conference", {
        type: "danger",
      });
    }
  }

  setupJitsiEvents() {
    const api = this.jitsiApi;
    if (!api) return;

    api.addEventListener("videoConferenceJoined", (event) => {
      console.log("✅ Joined conference");
      this.state.localParticipantId = event.id;
      this.state.jitsiLoaded = true;
      this.state.loading = false;
      this.state.error = null;

      // Update session join time (format to Odoo DB format)
      try {
        this.orm.write("dw.meeting.session", [this.sessionId], {
          is_connected: true,
          join_datetime: this.formatOdooDatetimeUTC(new Date()),
        });
      } catch (e) {
        console.warn('Failed to write join_datetime:', e);
      }

      this.notification.add("Connected to video conference", {
        type: "success",
      });
      this.refreshParticipants();
    });

    api.addEventListener("participantJoined", () => {
      this.state.activeParticipants++;
      this.refreshParticipants();
    });

    api.addEventListener("participantLeft", () => {
      this.state.activeParticipants = Math.max(0, this.state.activeParticipants - 1);
      this.refreshParticipants();
    });

    api.addEventListener("knockingParticipant", (participant) => {
      console.log("🚪 Participant waiting:", participant);
      const p = participant.participant || participant;
      const id = p.id || p.participantId;
      const name = p.name || p.displayName || "Guest";

      if (!this.state.waitingParticipants.find((x) => x.id === id)) {
        this.state.waitingParticipants.push({ id, name });
      }

      if (this.state.session.is_host) {
        this.notification.add(`${name} is waiting to join`, {
          type: "info",
        });
      }
    });

    api.addEventListener("videoConferenceLeft", () => {
      console.log("👋 Left conference");
      // Update session leave time (format to Odoo DB format)
      try {
        this.orm.write("dw.meeting.session", [this.sessionId], {
          is_connected: false,
          actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
        });
      } catch (e) {
        console.warn('Failed to write actual_end_datetime:', e);
      }
      this.goBack();
    });

    api.addEventListener("videoConferenceJoinFailed", (error) => {
      console.error("❌ Join failed:", error);
      this.state.error = "Failed to join video conference";
    });
  }

  // New method to handle tab changes
    onTabChange(tabName) {
        const previousTab = this.state.activeMainTab;
        this.state.activeMainTab = tabName;

        // If switching away from video tab to another tab, automatically show video in sidebar
        if (previousTab === 'video' && tabName !== 'video') {
            this.state.showVideoPip = true;
            // Move Jitsi to sidebar after a short delay to ensure DOM is ready
            setTimeout(() => this.moveJitsiToSidebar(), 100);
        }

        // If switching to video tab, hide sidebar and move Jitsi back to main
        if (tabName === 'video') {
            this.state.showVideoPip = false;
            setTimeout(() => this.moveJitsiToMain(), 100);
        }
    }

    // Method to move Jitsi iframe to sidebar
    moveJitsiToSidebar() {
        const jitsiContainer = document.getElementById('jitsi-meet-container');
        const sidebarContainer = document.getElementById('jitsi-sidebar-container');

        if (jitsiContainer && sidebarContainer && jitsiContainer.firstChild) {
            // Move the iframe from main container to sidebar
            while (jitsiContainer.firstChild) {
                sidebarContainer.appendChild(jitsiContainer.firstChild);
            }
        }
    }

// Method to move Jitsi iframe back to main container
    moveJitsiToMain() {
        const jitsiContainer = document.getElementById('jitsi-meet-container');
        const sidebarContainer = document.getElementById('jitsi-sidebar-container');

        if (jitsiContainer && sidebarContainer && sidebarContainer.firstChild) {
            // Move the iframe from sidebar back to main container
            while (sidebarContainer.firstChild) {
                jitsiContainer.appendChild(sidebarContainer.firstChild);
            }
        }
    }

  pauseJitsi() {
    // Instead of destroying Jitsi, just mute audio/video when switching tabs
    if (this.jitsiApi) {
      try {
        this.jitsiApi.executeCommand('toggleAudio', false);
        this.jitsiApi.executeCommand('toggleVideo', false);
      } catch (e) {
        console.warn('Could not pause Jitsi:', e);
      }
    }
  }

  resumeJitsi() {
    // Resume audio/video when returning to video tab
    if (this.jitsiApi) {
      try {
        this.jitsiApi.executeCommand('toggleAudio', true);
        this.jitsiApi.executeCommand('toggleVideo', true);
      } catch (e) {
        console.warn('Could not resume Jitsi:', e);
      }
    }
  }

  reconnectJitsi() {
    // Re-establish connection if needed
    if (this.jitsiApi && !this.state.jitsiLoaded) {
      this.state.jitsiLoaded = true;
      this.resumeJitsi();
    }
  }

  cleanupJitsi() {
    // Only destroy Jitsi when component is completely unmounted
    if (this.jitsiApi) {
      try {
        this.jitsiApi.dispose();
      } catch (e) {
        console.warn('Error disposing Jitsi:', e);
      }
      this.jitsiApi = null;
    }
    this.state.jitsiInitialized = false;
    this.state.jitsiLoaded = false;
  }

  refreshParticipants() {
    const api = this.jitsiApi;
    if (!api || typeof api.getParticipantsInfo !== "function") return;

    try {
      const participants = api.getParticipantsInfo() || [];
      this.state.activeParticipants = participants.length;
    } catch (e) {
      console.warn("Failed to refresh participants:", e);
    }
  }

  admitParticipant(participantId) {
    if (!this.state.session.is_host) {
      this.notification.add("Only hosts can admit participants", {
        type: "warning",
      });
      return;
    }

    const api = this.jitsiApi;
    if (api && typeof api.executeCommand === "function") {
      try {
        api.executeCommand("answerKnockingParticipant", participantId, true);
        this.state.waitingParticipants = this.state.waitingParticipants.filter(
          (p) => p.id !== participantId
        );
        this.notification.add("Participant admitted", { type: "success" });
      } catch (e) {
        console.error("Failed to admit participant:", e);
      }
    }
  }

  rejectParticipant(participantId) {
    if (!this.state.session.is_host) return;

    const api = this.jitsiApi;
    if (api && typeof api.executeCommand === "function") {
      try {
        api.executeCommand("answerKnockingParticipant", participantId, false);
        this.state.waitingParticipants = this.state.waitingParticipants.filter(
          (p) => p.id !== participantId
        );
      } catch (e) {
        console.error("Failed to reject participant:", e);
      }
    }
  }

async refreshParticipantStatus() {
  console.log("🔄 Refreshing participant status...");
  console.log("Participant IDs:", this.state.session.participant_ids);

  if (this.state.session.participant_ids?.length > 0) {
    try {
      const participantRecords = await this.orm.read(
        'dw.participant',
        this.state.session.participant_ids,
        ['id', 'name', 'attendance_status']
      );

      console.log("✅ Fetched participant records:", participantRecords);

      // Update participants while preserving reactivity
      this.state.session.participants = participantRecords;
      console.log("✅ Updated state.session.participants");

    } catch (error) {
      console.error("❌ Error refreshing participant status:", error);
    }
  } else {
    console.log("⚠️ No participant IDs to refresh");
  }
}

  startDurationTimer() {
    // Use robust parsing helper instead of appending 'Z'
    const parsedStart = this.parseOdooDatetimeToDate(this.state.session.actual_start_datetime);
    if (parsedStart) {
      this.startTime = parsedStart.getTime();
    } else {
      this.startTime = Date.now();
    }
    console.log("Meeting started at:", new Date(this.startTime).toISOString());
    this.durationInterval = setInterval(() => {
      const elapsed = Date.now() - this.startTime;
      console.log("Elapsed time (ms):", elapsed);
      const seconds = Math.floor(elapsed / 1000);
      console.log("Elapsed time (s):", seconds);
      const minutes = Math.floor(seconds / 60);
      console.log("Elapsed time (min):", minutes);
      const hours = Math.floor(minutes / 60);

      this.state.meetingDuration =
        `${String(hours).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    }, 1000);
  }

  stopDurationTimer() {
    if (this.durationInterval) {
        clearInterval(this.durationInterval);
        this.durationInterval = null;
    }
  }

  toggleNotes() {
    this.onTabChange(this.state.activeMainTab === 'notes' ? 'video' : 'notes');
  }

  toggleActions() {
    this.onTabChange(this.state.activeMainTab === 'actions' ? 'video' : 'actions');
  }

  toggleAgenda() {
    this.onTabChange(this.state.activeMainTab === 'agenda' ? 'video' : 'agenda');
  }

  showVideoPip() {
        this.state.showVideoPip = true;
        setTimeout(() => this.moveJitsiToSidebar(), 100);
  }

  closeVideoPip() {
        this.state.showVideoPip = false;
  }

  async toggleCamera() {
    this.state.session.display_camera = !this.state.session.display_camera;

    await this.orm.write("dw.meeting.session", [this.sessionId], {
        display_camera: this.state.session.display_camera,
    });
  }

  async saveNotes() {
    try {
      await this.orm.write("dw.meeting.session", [this.sessionId], {
        personal_notes: this.state.notes,
      });
      this.notification.add("Notes saved successfully", {
        type: "success",
      });
    } catch (error) {
      console.error("Failed to save notes:", error);
      this.notification.add("Failed to save notes", {
        type: "danger",
      });
    }
  }

  async savePv() {
    try {
      if (!this.meetingId) {
        throw new Error("No meeting ID available");
      }

      await this.orm.write("dw.meeting", [this.meetingId], {
        pv: this.state.pv,
      });

      console.log("Saved PV:", this.state.pv);
      this.notification.add("PV saved successfully", {
        type: "success",
      });
    } catch (error) {
      console.error("Failed to save PV:", error);
      this.notification.add("Failed to save PV", {
        type: "danger",
      });
    }
  }

  async loadPvTemplate() {
    try {
      // Generate PV template with meeting data
      const template = this.generatePvTemplate();
      this.state.pv = template;

      this.notification.add("PV template loaded", {
        type: "success",
      });
    } catch (error) {
      console.error("Failed to load PV template:", error);
      this.notification.add("Failed to load PV template", {
        type: "danger",
      });
    }
  }

  generatePvTemplate() {
    const meetingDate = this.state.session.actual_start_datetime
      ? new Date(this.state.session.actual_start_datetime).toLocaleDateString('fr-FR', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric'
        })
      : new Date().toLocaleDateString('fr-FR', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric'
        });

    const meetingTime = this.state.session.actual_start_datetime
      ? new Date(this.state.session.actual_start_datetime).toLocaleTimeString('fr-FR', {
          hour: '2-digit',
          minute: '2-digit'
        })
      : new Date().toLocaleTimeString('fr-FR', {
          hour: '2-digit',
          minute: '2-digit'
        });

    const participants = this.state.session.participants || [];
    const participantsList = participants.map(p => `  - ${p.name}`).join('\n');

    const agendaItems = this.state.session.subject_order || [];
    const agendaList = agendaItems.map((item, index) =>
      `${index + 1}. ${item.name}${item.description ? '\n   ' + item.description : ''}`
    ).join('\n');

    const actions = this.state.actions || [];
    const actionsList = actions.map((action, index) => {
      const assignee = this.state.availableAssignees.find(a => a.id === action.assignee_id);
      const assigneeName = assignee ? assignee.name : 'Non assigné';
      const deadline = action.dead_line ? ` (échéance: ${action.dead_line})` : '';
      return `${index + 1}. ${action.name} - Assigné à: ${assigneeName}${deadline}`;
    }).join('\n');

    return `PROCÈS-VERBAL DE RÉUNION

═══════════════════════════════════════════════════════════════

INFORMATIONS GÉNÉRALES
═══════════════════════════════════════════════════════════════

Titre de la réunion : ${this.state.session.name || '[Titre de la réunion]'}
Objet : ${this.state.session.objet || '[Objet de la réunion]'}
Date : ${meetingDate}
Heure de début : ${meetingTime}
Durée prévue : ${this.state.sessionDuration || 0} heures
Type de réunion : ${this.state.meetingTypeName || '[Type]'}


PARTICIPANTS
═══════════════════════════════════════════════════════════════

Présents (${participants.length}) :
${participantsList || '  [Liste des participants]'}

Absents :
  [À compléter]

Invités :
  [À compléter]


ORDRE DU JOUR
═══════════════════════════════════════════════════════════════

${agendaList || '[Points à l\'ordre du jour]'}


DÉROULEMENT DE LA RÉUNION
═══════════════════════════════════════════════════════════════

1. OUVERTURE DE LA SÉANCE
   [À compléter]

2. POINTS DISCUTÉS
   ${agendaItems.length > 0 ? agendaItems.map(item => `
   ${item.name}
   ───────────────────────────────────────────────────────────
   Discussion :
   [À compléter]

   `).join('') : '[À compléter]'}

3. DÉCISIONS PRISES
   [À compléter]


ACTIONS À ENTREPRENDRE
═══════════════════════════════════════════════════════════════

${actionsList || '[Actions à entreprendre]'}


PROCHAINES ÉTAPES
═══════════════════════════════════════════════════════════════

[À compléter]


PROCHAINE RÉUNION
═══════════════════════════════════════════════════════════════

Date : [À définir]
Lieu : [À définir]
Ordre du jour : [À définir]


CLÔTURE
═══════════════════════════════════════════════════════════════

Heure de clôture : ${this.state.meetingDuration || '[Heure de fin]'}

Le présent procès-verbal a été rédigé par [Nom] et sera diffusé à l'ensemble des participants.


Signatures :
  Président de séance : ________________
  Secrétaire de séance : ________________


═══════════════════════════════════════════════════════════════
Document généré le ${new Date().toLocaleString('fr-FR')}
═══════════════════════════════════════════════════════════════`;
  }

  async startBlankPv() {
    const confirmed = this.state.pv
      ? confirm("Cela effacera le contenu actuel du PV. Continuer ?")
      : true;

    if (confirmed) {
        const meetings = await this.orm.read(
                  "dw.meeting",
                  [this.meetingId],
                  ["pv"]
                );
        if (meetings && meetings.length > 0) {
          this.state.pv = meetings[0].pv || "";
        }
    }
  }

  async addNewAction() {
    try {
      const newActionId = await this.orm.create("dw.actions", [{
        name: "New Action",
        session_id: this.sessionId,
        meeting_id: this.meetingId,
        status: "todo",
        priority: "medium",
      }]);

      this.state.actions.push({
        id: newActionId[0],
        name: "New Action",
        assignee_id: "",
        dead_line: "",
        priority: "medium",
        status: "todo",
        description: "",
      });

      this.notification.add("Action item created", { type: "success" });
    } catch (error) {
      console.error("Failed to create action:", error);
      this.notification.add("Failed to create action", { type: "danger" });
    }
  }

  async updateAction(action) {
    if (!action.id) return;

    try {
      const updateData = {
        name: action.name,
        status: action.status,
        priority: action.priority,
      };

      if (action.assignee_id) {
        updateData.assignee = action.assignee_id;
      }
      if (action.dead_line) {
        updateData.dead_line = action.dead_line;
      }

      await this.orm.write("dw.actions", [action.id], updateData);

      if (this._updateTimeout) clearTimeout(this._updateTimeout);
      this._updateTimeout = setTimeout(() => {
        this.notification.add("Action updated", {
          type: "success",
          timeout: 1000
        });
      }, 500);
    } catch (error) {
      console.error("Failed to update action:", error);
      this.notification.add("Failed to update action", { type: "danger" });
    }
  }

  async deleteAction(action) {
    if (!action.id) return;

    const confirmed = confirm("Delete this action item?");
    if (!confirmed) return;

    try {
      await this.orm.unlink("dw.actions", [action.id]);
      this.state.actions = this.state.actions.filter(a => a.id !== action.id);
      this.notification.add("Action deleted", { type: "success" });
    } catch (error) {
      console.error("Failed to delete action:", error);
      this.notification.add("Failed to delete action", { type: "danger" });
    }
  }

  async leaveMeeting() {
    const confirmed = confirm("Are you sure you want to leave this meeting?");
    if (confirmed) {
      if (this.jitsiApi) {
        this.jitsiApi.executeCommand("hangup");
      } else {
        this.goBack();
      }
    }
  }

  async endMeeting() {
    if (!this.state.session.is_host) {
      this.notification.add("Only hosts can end the meeting", {
        type: "warning",
      });
      return;
    }

    const confirmed = confirm(
      "Are you sure you want to end this meeting for all participants? This action cannot be undone."
    );

    if (!confirmed) return;

    try {
      this.stopDurationTimer();

      const durationStr = this.state.meetingDuration;
      const [h, m, s] = durationStr.split(":").map(Number);
      const durationHours = h + m/60 + s/3600;

//      // 1. Update session state to 'done'
//      await this.orm.write("dw.meeting.session", [this.sessionId], {
//        state: "done",
//        is_connected: false,
//        actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
//        actual_duration: durationHours,
//      });
        // 1. Get all session IDs for this planification
        const sessionIds = await this.orm.search("dw.meeting.session", [
            ["planification_id", "=", this.planificationId]
        ]);

        // 2. Write to all found sessions
        if (sessionIds.length > 0) {
            await this.orm.write("dw.meeting.session", sessionIds, {
                state: "done",
                is_connected: false,
                actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
                actual_duration: durationHours,
            });
        }

      // 2. Update planification state to 'done'
      if (this.planificationId) {
        await this.orm.write("dw.planification.meeting", [this.planificationId], {
          state: "done",
          actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
          actual_duration: durationHours,
        });
      }

      // 3. Update meeting state to 'done'
      if (this.meetingId) {
        await this.orm.write("dw.meeting", [this.meetingId], {
          state: "done",
          actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
          actual_duration: durationHours,
        });
      }

      // 4. Kick all participants from Jitsi
      const api = this.jitsiApi;
      if (api && typeof api.executeCommand === "function") {
        try {
          // Get all participants
          const participants = api.getParticipantsInfo() || [];

          // Kick each participant
          for (const participant of participants) {
            if (participant.participantId !== this.state.localParticipantId) {
              api.executeCommand("kickParticipant", participant.participantId);
            }
          }
        } catch (e) {
          console.warn("Error kicking participants:", e);
        }
      }

      // 5. Show success notification
      this.notification.add("Meeting ended successfully", {
        type: "success",
      });

      // 6. Wait a moment for notifications to show, then leave
      setTimeout(() => {
        if (this.jitsiApi) {
          this.jitsiApi.executeCommand("hangup");
        } else {
          this.goBack();
        }
      }, 1500);

    } catch (error) {
      console.error("Failed to end meeting:", error);
      this.notification.add("Failed to end meeting. Please try again.", {
        type: "danger",
      });
    }
  }

  async retryConnection() {
    this.state.error = null;
    this.cleanupJitsi();
    await this.initializeJitsi();
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

registry.category("actions").add("meeting_session_view_action", MeetingSessionView);