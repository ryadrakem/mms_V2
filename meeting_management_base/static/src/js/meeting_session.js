/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@smartdz/owl";
import { loadJS } from "@web/core/assets";
import VoicePVRecorder from './voice_pv_recorder';

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
    this.agendaTimers = {};
    this.printAttendanceSheet = this.printAttendanceSheet.bind(this);
    this.addAttendanceLine = this.addAttendanceLine.bind(this);
    this.removeAttendanceLine = this.removeAttendanceLine.bind(this);

    this.state = useState({
      loading: true,
      jitsiLoaded: false,
      jitsiAPI: null,
      error: null,
      attendanceLines: [],

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
        use_vc: false,
        is_action_assigner: false,
        can_edit_agenda: false,
        can_edit_summary: false,
        planification_id: null,
        project_id: null,
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
        use_agenda_timer: true,  // ⭐ AJOUT: Activer les timers par défaut
      },

      localParticipantId: null,
      activeParticipants: 0,
      waitingParticipants: [],
      meetingDuration: "00:00:00",
      activeMainTab: 'video',
      notes: "",
      actions: [],
      availableAssignees: [],
      availableProjects: [],
      formattedDate: "",
      formattedJoinTime: "",
      sessionDuration: 0,
      meetingTypeName: "",
      jitsiRoomId: null,
      pv: "",
      jitsiInitialized: false,
      pipManuallyClosed: false, // Track if user closed the PiP with X button

      agendaItems: [],
      draggedAgendaId: null,
      editingAgendaId: null,
      newAgendaName: "",
    });

    this.sessionId = null;
    this.planificationId = null;
    this.meetingId = null;
    this.durationInterval = null;
    this.statusInterval = null;
    this.startTime = null;
    this._updateTimeout = null;
    this.jitsiApi = null;
    this.voiceRecorder = null;

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
    this.onTabChange = this.onTabChange.bind(this);
    this.loadPvTemplate = this.loadPvTemplate.bind(this);
    this.startBlankPv = this.startBlankPv.bind(this);
    this.generatePvTemplate = this.generatePvTemplate.bind(this);
    this.closeVideoPip = this.closeVideoPip.bind(this);
    this.showVideoPip = this.showVideoPip.bind(this);
    this._initializeVoiceRecorder = this._initializeVoiceRecorder.bind(this);
    this._initializeVoiceRecorderOnPVTab = this._initializeVoiceRecorderOnPVTab.bind(this);
    this.downloadDocument = this.downloadDocument.bind(this);
    this.addAgendaItem = this.addAgendaItem.bind(this);
    this.deleteAgendaItem = this.deleteAgendaItem.bind(this);
    this.updateAgendaItem = this.updateAgendaItem.bind(this);
    this.startEditAgenda = this.startEditAgenda.bind(this);
    this.saveAgendaEdit = this.saveAgendaEdit.bind(this);
    this.cancelAgendaEdit = this.cancelAgendaEdit.bind(this);
    this.onAgendaDragStart = this.onAgendaDragStart.bind(this);
    this.onAgendaDragOver = this.onAgendaDragOver.bind(this);
    this.onAgendaDrop = this.onAgendaDrop.bind(this);
    this.onAgendaDragEnd = this.onAgendaDragEnd.bind(this);
    this.startAgendaTimer = this.startAgendaTimer.bind(this);
    this.pauseAgendaTimer = this.pauseAgendaTimer.bind(this);
    this.stopAgendaTimer = this.stopAgendaTimer.bind(this);
    this.resetAgendaTimer = this.resetAgendaTimer.bind(this);
    this.formatTime = this.formatTime.bind(this);
    this.getTimerStateClass = this.getTimerStateClass.bind(this);
    this.getTimerStateIcon = this.getTimerStateIcon.bind(this);
    this.getStatusLabel = this.getStatusLabel.bind(this);

    // Expose global functions so Owl can resolve them via ctx in the template
    this.parseInt = parseInt;
    this.Math = Math;

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
      await this.loadAvailableProjects();
      await this.loadPlanificationDocuments();
      await this.loadAgendaItems();
    });

    onMounted(async () => {
      if (!this.state.error && this.meetingId && this.state.session.state !== 'done' && this.state.session.use_vc) {
        await this.initializeJitsi();
        this.startDurationTimer();
      }

      this.statusInterval = setInterval(async () => {
        await this.refreshParticipantStatus();
      }, 10000);

      await this.refreshParticipantStatus();

      // Initialize PiP drag functionality
      this.initializePipDrag();

      this.initializeRunningTimers();
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
      if (this.voiceRecorder) {
        try {
          if (this.voiceRecorder.isRecording) {
            this.voiceRecorder.stopRecording();
          }
        } catch (e) {
          console.warn('Error cleaning up voice recorder:', e);
        }
      }
      // Cleanup PiP drag functionality
      if (this._cleanupPipDrag) {
        this._cleanupPipDrag();
      }

      Object.keys(this.agendaTimers).forEach(agendaId => {
        if (this.agendaTimers[agendaId]?.interval) {
          clearInterval(this.agendaTimers[agendaId].interval);
        }
      });
    });
  }
  // ================== AGENDA MANAGEMENT ==================
  async loadAgendaItems() {
    try {
      const agendas = await this.orm.searchRead(
        'dw.agenda',
        [['session_id', '=', this.sessionId]],
        ['id', 'name', 'sequence', 'duration_minutes', 'timer_state',
         'elapsed_seconds', 'timer_start_time', 'timer_pause_time'],
        { order: 'sequence, id' }
      );

      this.state.agendaItems = agendas;
      this.state.session.subject_order = agendas;
    } catch (error) {
      console.error('Failed to load agenda items:', error);
      this.notification.add('Failed to load agenda', { type: 'danger' });
    }
  }

  async addAgendaItem() {
    if (!this.state.newAgendaName.trim()) {
      this.notification.add('Please enter an agenda item name', { type: 'warning' });
      return;
    }

    try {
      const maxSequence = this.state.agendaItems.length > 0
        ? Math.max(...this.state.agendaItems.map(a => a.sequence || 0))
        : 0;

      const newId = await this.orm.create('dw.agenda', [{
        name: this.state.newAgendaName,
        session_id: this.sessionId,
        meeting_id: this.meetingId,
        planification_id: this.planificationId,
        sequence: maxSequence + 10,
        duration_minutes: 15,
        timer_state: 'not_started',
      }]);

      await this.loadAgendaItems();
      this.state.newAgendaName = "";
      this.notification.add('Agenda item added', { type: 'success' });
    } catch (error) {
      console.error('Failed to add agenda item:', error);
      this.notification.add('Failed to add agenda item', { type: 'danger' });
    }
  }

  async deleteAgendaItem(agendaId) {
    const confirmed = confirm('Delete this agenda item?');
    if (!confirmed) return;

    try {
      await this.orm.unlink('dw.agenda', [agendaId]);

      // Stop timer if running
      if (this.agendaTimers[agendaId]) {
        clearInterval(this.agendaTimers[agendaId].interval);
        delete this.agendaTimers[agendaId];
      }

      await this.loadAgendaItems();
      this.notification.add('Agenda item deleted', { type: 'success' });
    } catch (error) {
      console.error('Failed to delete agenda item:', error);
      this.notification.add('Failed to delete agenda item', { type: 'danger' });
    }
  }

  async updateAgendaItem(agendaId, field, value) {
    try {
      await this.orm.write('dw.agenda', [agendaId], { [field]: value });

      const item = this.state.agendaItems.find(a => a.id === agendaId);
      if (item) {
        item[field] = value;
      }

      if (this._updateTimeout) clearTimeout(this._updateTimeout);
      this._updateTimeout = setTimeout(() => {
        this.notification.add('Agenda updated', { type: 'success', timeout: 1000 });
      }, 500);
    } catch (error) {
      console.error('Failed to update agenda item:', error);
      this.notification.add('Failed to update agenda', { type: 'danger' });
    }
  }

  startEditAgenda(agendaId) {
    this.state.editingAgendaId = agendaId;
  }

  async saveAgendaEdit(agendaId) {
    const item = this.state.agendaItems.find(a => a.id === agendaId);
    if (item && item.name.trim()) {
      await this.updateAgendaItem(agendaId, 'name', item.name);
      this.state.editingAgendaId = null;
    }
  }

  cancelAgendaEdit() {
    this.state.editingAgendaId = null;
    this.loadAgendaItems(); // Reload to reset changes
  }

  // Drag and Drop for reordering
  onAgendaDragStart(ev, agendaId) {
    this.state.draggedAgendaId = agendaId;
    ev.dataTransfer.effectAllowed = 'move';
  }

  onAgendaDragOver(ev) {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
  }

  async onAgendaDrop(ev, targetAgendaId) {
    ev.preventDefault();

    if (this.state.draggedAgendaId === targetAgendaId) return;

    try {
      const items = [...this.state.agendaItems];
      const draggedIndex = items.findIndex(a => a.id === this.state.draggedAgendaId);
      const targetIndex = items.findIndex(a => a.id === targetAgendaId);

      if (draggedIndex === -1 || targetIndex === -1) return;

      // Remove dragged item
      const [draggedItem] = items.splice(draggedIndex, 1);

      // Insert at new position
      items.splice(targetIndex, 0, draggedItem);

      // Update sequences
      const updates = items.map((item, index) => ({
        id: item.id,
        sequence: (index + 1) * 10
      }));

      for (const update of updates) {
        await this.orm.write('dw.agenda', [update.id], { sequence: update.sequence });
      }

      await this.loadAgendaItems();
      this.notification.add('Agenda reordered', { type: 'success' });
    } catch (error) {
      console.error('Failed to reorder agenda:', error);
      this.notification.add('Failed to reorder agenda', { type: 'danger' });
    }
  }

  onAgendaDragEnd() {
    this.state.draggedAgendaId = null;
  }

  // ================== AGENDA TIMERS ==================

  async startAgendaTimer(agendaId) {
    try {
      await this.orm.call('dw.agenda', 'action_start_timer', [agendaId]);
      await this.loadAgendaItems();
      this.startAgendaTimerUI(agendaId);
    } catch (error) {
      console.error('Failed to start timer:', error);
      this.notification.add('Failed to start timer', { type: 'danger' });
    }
  }

  async pauseAgendaTimer(agendaId) {
    try {
      await this.orm.call('dw.agenda', 'action_pause_timer', [agendaId]);
      await this.loadAgendaItems();
      this.pauseAgendaTimerUI(agendaId);
    } catch (error) {
      console.error('Failed to pause timer:', error);
      this.notification.add('Failed to pause timer', { type: 'danger' });
    }
  }

  async stopAgendaTimer(agendaId) {
    try {
      await this.orm.call('dw.agenda', 'action_stop_timer', [agendaId]);
      await this.loadAgendaItems();
      this.stopAgendaTimerUI(agendaId);
    } catch (error) {
      console.error('Failed to stop timer:', error);
      this.notification.add('Failed to stop timer', { type: 'danger' });
    }
  }

  async resetAgendaTimer(agendaId) {
    try {
      await this.orm.call('dw.agenda', 'action_reset_timer', [agendaId]);
      await this.loadAgendaItems();
      this.resetAgendaTimerUI(agendaId);
    } catch (error) {
      console.error('Failed to reset timer:', error);
      this.notification.add('Failed to reset timer', { type: 'danger' });
    }
  }

  // ---------- UI TIMER MANAGEMENT ----------

  initializeRunningTimers() {
    // ⭐ AJOUT: Ne démarrer les timers que si use_agenda_timer est activé
    if (!this.state.session.use_agenda_timer) {
      console.log('⏱️ Agenda timers disabled - skipping initialization');
      return;
    }

    // Start UI timers for any agenda items that are currently running
    this.state.agendaItems.forEach(item => {
      if (item.timer_state === 'running') {
        this.startAgendaTimerUI(item.id);
      }
    });
  }

  startAgendaTimerUI(agendaId) {
    const item = this.state.agendaItems.find(i => i.id === agendaId);
    if (!item) return;

    // Clear existing timer if any
    if (this.agendaTimers[agendaId]) {
      clearInterval(this.agendaTimers[agendaId].interval);
    }

    this.agendaTimers[agendaId] = {
      startTime: Date.now() / 1000 - (item.elapsed_seconds || 0),
      interval: setInterval(() => this.updateAgendaTimerUI(agendaId), 1000)
    };
  }

  pauseAgendaTimerUI(agendaId) {
    if (this.agendaTimers[agendaId]) {
      clearInterval(this.agendaTimers[agendaId].interval);
    }
  }

  stopAgendaTimerUI(agendaId) {
    if (this.agendaTimers[agendaId]) {
      clearInterval(this.agendaTimers[agendaId].interval);
      delete this.agendaTimers[agendaId];
    }
  }

  resetAgendaTimerUI(agendaId) {
    this.stopAgendaTimerUI(agendaId);

    const elapsedEl = document.querySelector(`[data-agenda-elapsed="${agendaId}"]`);
    const remainingEl = document.querySelector(`[data-agenda-remaining="${agendaId}"]`);
    const progressEl = document.querySelector(`[data-agenda-progress="${agendaId}"]`);

    if (elapsedEl) elapsedEl.textContent = '00:00';
    if (remainingEl) remainingEl.textContent = '00:00';
    if (progressEl) {
      progressEl.style.width = '0%';
      progressEl.classList.remove('overtime');
    }
  }

  updateAgendaTimerUI(agendaId) {
    const item = this.state.agendaItems.find(i => i.id === agendaId);
    if (!item || !this.agendaTimers[agendaId]) return;

    const now = Date.now() / 1000;
    const elapsed = now - this.agendaTimers[agendaId].startTime;
    const totalSeconds = item.duration_minutes * 60;
    const remaining = Math.max(0, totalSeconds - elapsed);
    const progress = Math.min(100, (elapsed / totalSeconds) * 100);

    const elapsedEl = document.querySelector(`[data-agenda-elapsed="${agendaId}"]`);
    const remainingEl = document.querySelector(`[data-agenda-remaining="${agendaId}"]`);
    const progressEl = document.querySelector(`[data-agenda-progress="${agendaId}"]`);

    if (elapsedEl) elapsedEl.textContent = this.formatTime(elapsed);
    if (remainingEl) remainingEl.textContent = this.formatTime(remaining);
    if (progressEl) {
      progressEl.style.width = `${progress}%`;

      // Add overtime class if over time
      if (elapsed > totalSeconds) {
        progressEl.classList.add('overtime');

        // Notify once when entering overtime
        if (item.timer_state !== 'overtime') {
          item.timer_state = 'overtime';
          this.notification.add(
            `Agenda "${item.name}" is in overtime!`,
            { type: 'warning', sticky: true }
          );
        }
      }
    }
  }

  formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  getTimerStateClass(state) {
    const stateClasses = {
      'not_started': 'timer-not-started',
      'running': 'timer-running',
      'paused': 'timer-paused',
      'completed': 'timer-completed',
      'overtime': 'timer-overtime',
    };
    return stateClasses[state] || '';
  }

  getTimerStateIcon(state) {
    const icons = {
      'not_started': 'fa-clock-o',
      'running': 'fa-play-circle',
      'paused': 'fa-pause-circle',
      'completed': 'fa-check-circle',
      'overtime': 'fa-exclamation-circle',
    };
    return icons[state] || 'fa-clock-o';
  }


  // ================== MÉTHODES DE CLASSE (EN DEHORS DE setup()) ==================
    /**
    méthode d'impression feuille de presence
    */
    async saveAttendanceState() {
        if (!this.sessionId) {
            console.warn("⚠️ Impossible de sauvegarder : pas de session ID");
            return;
        }

        try {
            // Filtrer uniquement les lignes manuelles (isEditable: true)
            const manualLines = this.state.attendanceLines.filter(line => line.isEditable);

            // Sauvegarder dans la base de données
            await this.orm.write(
                'dw.meeting.session',
                [this.sessionId],
                {
                    attendance_lines_json: JSON.stringify(manualLines)
                }
            );

            console.log("💾 État feuille de présence sauvegardé:", manualLines.length, "ligne(s) manuelle(s)");
        } catch (error) {
            console.error("❌ Erreur lors de la sauvegarde de la feuille de présence:", error);
        }
    }
    async loadAttendanceLines() {
        try {
            const lines = [];

            // Charger les participants existants
            if (this.state.session.participants?.length) {
                this.state.session.participants.forEach(participant => {
                    lines.push({
                        id: participant.id,
                        name: participant.name,
                        quality: '',
                        isEditable: false,
                        isParticipant: true
                    });
                });
            }

            // Charger les lignes manuelles sauvegardées
            if (this.sessionId) {
                const session = await this.orm.read(
                    'dw.meeting.session',
                    [this.sessionId],
                    ['attendance_lines_json']
                );

                if (session[0]?.attendance_lines_json) {
                    try {
                        const manualLines = JSON.parse(session[0].attendance_lines_json);
                        manualLines.forEach(line => {
                            if (line.isEditable) {
                                lines.push(line);
                            }
                        });
                    } catch (e) {
                        console.warn('Erreur parsing JSON des lignes:', e);
                    }
                }
            }

            this.state.attendanceLines = lines;
            console.log("✅ Lignes de présence chargées:", lines.length);
        } catch (error) {
            console.error("❌ Erreur chargement lignes de présence:", error);
            this.state.attendanceLines = [];
        }
    }

    async addAttendanceLine() {  // ✅ IMPORTANT: Ajouter "async"
        // Ajouter la nouvelle ligne dans le state
        this.state.attendanceLines.push({
            id: null,
            name: '',
            quality: '',
            isEditable: true,
            isParticipant: false
        });

        // ✅ NOUVEAU: Sauvegarder immédiatement l'état
        await this.saveAttendanceState();

        // Notification utilisateur
        this.notification.add("Ligne ajoutée", {
            type: "success",
        });

        // Auto-scroll vers le bas
        setTimeout(() => {
            const container = document.querySelector('.attendance-table-container');
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }, 100);
    }

    async removeAttendanceLine(index) {  // ✅ IMPORTANT: Ajouter "async"
        // Demander confirmation
        const confirmed = confirm("Supprimer cette ligne ?");
        if (!confirmed) return;

        // Supprimer la ligne du state
        this.state.attendanceLines.splice(index, 1);

        // ✅ NOUVEAU: Sauvegarder immédiatement l'état
        await this.saveAttendanceState();

        // Notification utilisateur
        this.notification.add("Ligne supprimée", {
            type: "success",
        });
    }

    async printAttendanceSheet() {
        try {
            if (!this.sessionId) {
                throw new Error("Aucune session ID disponible");
            }

            // ✅ Sauvegarder TOUTES les lignes visibles
            const allVisibleLines = this.state.attendanceLines.map(line => ({
                name: line.name,
                quality: line.quality || '',
                isEditable: line.isEditable,
                isParticipant: line.isParticipant,
                id: line.id || null
            }));

            await this.orm.write('dw.meeting.session', [this.sessionId], {
                attendance_lines_json: JSON.stringify(allVisibleLines)
            });

            // Générer PDF
            await this.actionService.doAction({
                type: 'ir.actions.report',
                report_type: 'qweb-pdf',
                report_name: 'meeting_management_base.report_attendance_sheet_document',
                context: { active_id: this.sessionId, active_ids: [this.sessionId] }
            });

            this.notification.add("Feuille générée", { type: "success" });
        } catch (error) {
            console.error("Erreur:", error);
            this.notification.add("Erreur génération", { type: "danger" });
        }
    }

  /**
   * Initialize voice recorder for PV editing
   * This is now called when PV tab becomes active, not on component mount
   */
    async _initializeVoiceRecorder() {
      try {
        console.log('🎤 Attempting to initialize voice recorder...');

        let pvTextarea = null;
        let retries = 0;
        const maxRetries = 30; // 3 seconds total (100ms intervals)

        // Wait for the pv-textarea to be in the DOM
        while (!pvTextarea && retries < maxRetries) {
          pvTextarea = document.querySelector('.pv-textarea');
          if (!pvTextarea) {
            await new Promise(resolve => setTimeout(resolve, 100));
            retries++;
          }
        }

        if (!pvTextarea) {
          console.warn('⚠️ PV textarea not found after retries');
          console.warn('Voice recorder will not be available for this session');
          return;
        }

        console.log('✅ PV textarea found, initializing voice recorder...');

        // Créer une callback pour mettre à jour state.pv
        const onTextUpdate = (newText) => {
          this.state.pv = newText;
          console.log('📝 Updated state.pv:', newText.substring(0, 50) + '...');
        };

        // Instantiate avec la callback
        this.voiceRecorder = new VoicePVRecorder(
          pvTextarea,
          this.meetingId,
          this.notification,
          onTextUpdate  // ← PASSER LA CALLBACK
        );

        this.voiceRecorder.initializeControls(pvTextarea.parentNode);
        console.log('✅ Voice recorder initialized for PV');

      } catch (error) {
        console.warn('⚠️ Voice recorder initialization failed (non-critical):', error);
      }
    }

  /**
   * Initialize voice recorder when PV tab becomes active
   * Call this from onTabChange when activeMainTab === 'pv'
   */
  _initializeVoiceRecorderOnPVTab() {
    if (!this.voiceRecorder && this.state.session.is_pv) {
      console.log('🎤 Initializing voice recorder for PV tab...');
      this._initializeVoiceRecorder();
    }
  }

  /**
   * Check browser support for voice features
   */
  _checkVoiceSupport() {
    const hasSpeechAPI = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
    const hasMediaRecorder = !!(window.MediaRecorder);
    const hasGetUserMedia = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

    return {
      speechAPI: hasSpeechAPI,
      mediaRecorder: hasMediaRecorder,
      microphone: hasGetUserMedia,
      supported: hasSpeechAPI || (hasMediaRecorder && hasGetUserMedia)
    };
  }

  // ================== DATETIME HELPERS ==================

  formatOdooDatetimeUTC(dateLike) {
    const d = dateLike instanceof Date ? dateLike : new Date(dateLike);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
  }

  parseOdooDatetimeToDate(s) {
    if (!s) return null;
    if (typeof s !== "string") return new Date(s);
    if (s.includes("T")) {
      return new Date(s);
    }
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
    if (m) {
      const [_, Y, M, D, h, mi, sec] = m;
      return new Date(Date.UTC(+Y, +M - 1, +D, +h, +mi, +sec));
    }
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

  // ================== DATA LOADING ==================

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
          "use_vc",
          "is_action_assigner",
          "can_edit_agenda",
          "can_edit_summary",
          "planification_id",
          "project_id",
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
          "has_remote_participants",
          "use_agenda_timer"  // ⭐ AJOUT: Charger le champ use_agenda_timer
        ]
      );

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
        use_vc: sessionData.use_vc || false,
        is_action_assigner: sessionData.is_action_assigner || false,
        can_edit_agenda: sessionData.can_edit_agenda || false,
        can_edit_summary: sessionData.can_edit_summary || false,
        planification_id: this.planificationId,
        project_id: Array.isArray(sessionData.project_id)
            ? sessionData.project_id[0]
            : sessionData.project_id || null,
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
        use_agenda_timer: sessionData.use_agenda_timer !== undefined ? sessionData.use_agenda_timer : true,  // ⭐ AJOUT: Récupérer use_agenda_timer du serveur
        documents: [],
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
      }

              // ✅ CHANGÉ: Charger l'agenda depuis le SESSION d'abord, sinon depuis le MEETING
        console.log('📋 Chargement de l\'agenda...');
        let agendaIds = sessionData.subject_order || [];

        // Si la session n'a pas d'agenda, charger depuis le meeting
        if (!agendaIds || agendaIds.length === 0) {
          console.warn('⚠️ Pas d\'agenda dans la session, chargement depuis le meeting...');
          const meetingData = await this.orm.read(
            "dw.meeting",
            [this.meetingId],
            ["subject_order"]
          );
          if (meetingData && meetingData.length > 0 && meetingData[0].subject_order) {
            agendaIds = meetingData[0].subject_order;
            console.log('✅ Agenda trouvé dans le meeting:', agendaIds);
          }
        }

        // Charger les détails de l'agenda
        if (agendaIds && agendaIds.length > 0) {
          try {
            const subject_orderRecords = await this.orm.read(
              'dw.agenda',
              agendaIds,
              ['id', 'name']
            );
            this.state.session.subject_order = subject_orderRecords;
            console.log('✅ Agenda chargé avec succès:', subject_orderRecords.length, 'items');
          } catch (error) {
            console.warn('⚠️ Erreur lors du chargement de l\'agenda:', error);
            this.state.session.subject_order = [];
          }
        } else {
          console.log('ℹ️ Aucun agenda disponible');
          this.state.session.subject_order = [];
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
        ["jitsi_room_id", "pv"]
      );
      if (meetings && meetings.length > 0) {
        this.state.jitsiRoomId = meetings[0].jitsi_room_id;
        this.state.pv = meetings[0].pv || "";
      }
      await this.loadAttendanceLines();
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
      'paused': 'In Pause',
      'absent': 'Absent',
      'excused': 'Excused',
      'default': 'Awaiting'
    };
    return labels[status] || 'Unknown';
  }

  getPriorityLabel(priority) {
    const labels = {
      '0': 'Normal',
      '1': 'Low',
      '2': 'High',
      '3': 'Urgent'
    };
    return labels[priority] || 'Normal';
  }

  async loadActions() {
    try {
      const actions = await this.orm.searchRead(
        "dw.actions",
        [["session_id", "=", this.sessionId]],
        ["name", "assignee", "dead_line", "priority", "status", "meeting_id", "description", "project_id"]
      );

      this.state.actions = actions.map(a => ({
        ...a,
        assignee_id: a.assignee ? (Array.isArray(a.assignee) ? a.assignee[0] : a.assignee) : "",
        project_id: a.project_id ? (Array.isArray(a.project_id) ? a.project_id[0] : a.project_id) : (this.state.session.project_id || ""),
        priority: a.priority || '0',
      }));
    } catch (error) {
      console.error("Failed to load actions:", error);
    }
  }

  async loadAvailableAssignees() {
    try {
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

    async loadAvailableProjects() {
      try {

        const currentUserId = this.state.session.user_id;

        if (!currentUserId) {
            console.warn("⚠️ No user ID available");
            this.state.availableProjects = [];
            return;
        }

        const projects = await this.orm.searchRead(
          "dw.project",
          [["users_allowed_to_see", "in", [currentUserId]]],
          ["name"]
        );
        console.log("projects:", projects);

        this.state.availableProjects = projects.map(p => ({
          id: p.id,
          name: p.name
        }));
        console.log("Loaded projects:", this.state.availableProjects);
      } catch (error) {
        console.error("Failed to load projects:", error);
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
      // **FIX: Wait for the container to be rendered in the DOM**
      let container = null;
      let retries = 0;
      const maxRetries = 20; // 2 seconds with 100ms intervals

      // Ensure display_camera is true so container is rendered
      if (!this.state.session.display_camera) {
        this.state.session.display_camera = true;
      }

      // Poll for container availability
      while (!container && retries < maxRetries) {
        container = document.getElementById("jitsi-meet-container");
        if (!container) {
          await new Promise(resolve => setTimeout(resolve, 100));
          retries++;
        }
      }

      if (!container) {
        throw new Error(
          `Jitsi container not found after ${maxRetries * 100}ms. ` +
          "Ensure video-conference-container and jitsi-meet-container exist in template."
        );
      }

      const tokenData = await this.rpcCall("/meeting/jitsi/token", {
        meeting_id: this.meetingId,
        session_id: this.sessionId,
      });

      if (!tokenData || !tokenData.success) {
        throw new Error(tokenData?.error || "Authentication failed");
      }

      const { domain, room_name, token: jwt, is_moderator } = tokenData;

      console.log("🎥 Initializing Jitsi:", { domain, room_name, is_moderator });

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
          disableReactions: true,
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

      // Set initial CSS class for video container
      setTimeout(() => {
        const videoContainer = document.querySelector('.video-conference-container');
        if (videoContainer) {
            if (this.state.activeMainTab === 'video') {
                videoContainer.classList.add('main-mode');
            }
        }
      }, 100);

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

  onTabChange(tabName) {
    this.state.activeMainTab = tabName;

    // Initialize voice recorder when switching to PV tab
    if (tabName === 'pv' && this.state.session.is_pv) {
      this._initializeVoiceRecorderOnPVTab();
    }

    const videoContainer = document.querySelector('.video-conference-container');

    if (!videoContainer) return;

    if (tabName === 'video') {
        // Show video in main view
        videoContainer.classList.remove('pip-mode');
        videoContainer.classList.add('main-mode');
        this.state.showVideoPip = false;
        // Reset the manually closed flag when user goes to video tab
        this.state.pipManuallyClosed = false;
    } else if (this.state.session.display_camera && !this.state.pipManuallyClosed) {
        // Show video in PiP mode only if camera is enabled and user didn't manually close it
        videoContainer.classList.remove('main-mode');
        videoContainer.classList.add('pip-mode');
        this.state.showVideoPip = true;
    } else {
        // Hide video completely
        videoContainer.classList.remove('main-mode', 'pip-mode');
        this.state.showVideoPip = false;
    }
  }

  showVideoPip() {
    this.state.showVideoPip = true;
    const videoContainer = document.querySelector('.video-conference-container');
    if (videoContainer && this.state.activeMainTab !== 'video') {
        videoContainer.classList.add('pip-mode');
        videoContainer.classList.remove('main-mode');
    }
  }

  closeVideoPip() {
    // Hide PiP but keep camera available on video tab
    this.state.showVideoPip = false;
    this.state.pipManuallyClosed = true; // Mark that user manually closed the PiP

    const videoContainer = document.querySelector('.video-conference-container');
    if (videoContainer) {
        // Remove PiP mode - video will show in main mode when user switches to video tab
        videoContainer.classList.remove('pip-mode');
    }

    // Note: We keep display_camera as true so video remains available on video tab
    // The pipManuallyClosed flag prevents PiP from reappearing on other tabs
  }

  /**
   * Initialize drag and resize functionality for PiP mode
   */
  initializePipDrag() {
    const videoContainer = document.querySelector('.video-conference-container');
    if (!videoContainer) return;

    // Drag variables
    let isDragging = false;
    let isResizing = false;
    let currentX, currentY;
    let initialX, initialY;
    let startWidth, startHeight;
    let startMouseX, startMouseY;

    // Calculate size limits based on viewport (30% to 100%)
    const getMinSize = () => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      // 30% of viewport, maintaining 16:9 aspect ratio
      const minWidth = Math.max(vw * 0.30, 320); // At least 320px for clarity
      const minHeight = minWidth / (16/9);
      return { width: minWidth, height: minHeight };
    };

    const getMaxSize = () => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      // 100% of viewport (with some padding)
      const maxWidth = vw - 40; // 20px padding on each side
      const maxHeight = vh - 100; // Space for header and some padding
      return { width: maxWidth, height: maxHeight };
    };

    const dragStart = (e) => {
      // Only allow dragging in PiP mode
      if (!videoContainer.classList.contains('pip-mode')) return;

      // Check if clicking on resize handle (bottom-right 30px area for easier grabbing)
      const rect = videoContainer.getBoundingClientRect();
      const isResizeHandle = (
        e.clientX > rect.right - 30 &&
        e.clientY > rect.bottom - 30
      );

      // Prevent dragging if clicking on buttons
      if (e.target.closest('button')) return;

      if (isResizeHandle) {
        isResizing = true;
        startWidth = videoContainer.offsetWidth;
        startHeight = videoContainer.offsetHeight;
        startMouseX = e.clientX;
        startMouseY = e.clientY;
        videoContainer.style.cursor = 'se-resize';
      } else {
        isDragging = true;

        if (e.type === 'touchstart') {
          initialX = e.touches[0].clientX - (videoContainer._xOffset || 0);
          initialY = e.touches[0].clientY - (videoContainer._yOffset || 0);
        } else {
          initialX = e.clientX - (videoContainer._xOffset || 0);
          initialY = e.clientY - (videoContainer._yOffset || 0);
        }

        videoContainer.style.cursor = 'grabbing';
      }
    };

    const drag = (e) => {
      e.preventDefault();

      if (isResizing) {
        const deltaX = e.clientX - startMouseX;
        const deltaY = e.clientY - startMouseY;

        const minSize = getMinSize();
        const maxSize = getMaxSize();

        let newWidth = startWidth + deltaX;
        let newHeight = startHeight + deltaY;

        // Maintain aspect ratio (16:9)
        const aspectRatio = 16 / 9;
        if (Math.abs(deltaX) > Math.abs(deltaY)) {
          newHeight = newWidth / aspectRatio;
        } else {
          newWidth = newHeight * aspectRatio;
        }

        // Apply size constraints
        newWidth = Math.max(minSize.width, Math.min(maxSize.width, newWidth));
        newHeight = Math.max(minSize.height, Math.min(maxSize.height, newHeight));

        // Ensure aspect ratio is maintained after constraints
        const constrainedHeight = newWidth / aspectRatio;
        if (constrainedHeight <= maxSize.height) {
          newHeight = constrainedHeight;
        } else {
          newWidth = newHeight * aspectRatio;
        }

        videoContainer.style.width = newWidth + 'px';
        videoContainer.style.height = newHeight + 'px';

      } else if (isDragging) {
        if (e.type === 'touchmove') {
          currentX = e.touches[0].clientX - initialX;
          currentY = e.touches[0].clientY - initialY;
        } else {
          currentX = e.clientX - initialX;
          currentY = e.clientY - initialY;
        }

        videoContainer._xOffset = currentX;
        videoContainer._yOffset = currentY;

        // Apply transform
        videoContainer.style.transform = `translate(${currentX}px, ${currentY}px)`;
      }
    };

    const dragEnd = () => {
      if (isResizing) {
        isResizing = false;
        updateCursor();
      }
      if (isDragging) {
        isDragging = false;
        videoContainer.style.cursor = 'grab';
      }
    };

    const updateCursorOnMove = (e) => {
      if (!videoContainer.classList.contains('pip-mode')) return;
      if (isDragging || isResizing) return;

      const rect = videoContainer.getBoundingClientRect();
      const isResizeHandle = (
        e.clientX > rect.right - 30 &&
        e.clientY > rect.bottom - 30
      );

      if (isResizeHandle) {
        videoContainer.style.cursor = 'se-resize';
      } else {
        videoContainer.style.cursor = 'grab';
      }
    };

    // Add event listeners
    videoContainer.addEventListener('mousedown', dragStart);
    videoContainer.addEventListener('mousemove', updateCursorOnMove);
    document.addEventListener('mousemove', drag);
    document.addEventListener('mouseup', dragEnd);

    // Touch events for mobile
    videoContainer.addEventListener('touchstart', dragStart, { passive: false });
    document.addEventListener('touchmove', drag, { passive: false });
    document.addEventListener('touchend', dragEnd);

    // Set cursor style for PiP mode
    const updateCursor = () => {
      if (videoContainer.classList.contains('pip-mode')) {
        videoContainer.style.cursor = 'grab';
      } else {
        videoContainer.style.cursor = '';
        videoContainer.style.transform = '';
        videoContainer.style.width = '';
        videoContainer.style.height = '';
        videoContainer._xOffset = 0;
        videoContainer._yOffset = 0;
      }
    };

    // Watch for class changes
    const observer = new MutationObserver(updateCursor);
    observer.observe(videoContainer, { attributes: true, attributeFilter: ['class'] });

    // Store cleanup function
    this._cleanupPipDrag = () => {
      videoContainer.removeEventListener('mousedown', dragStart);
      videoContainer.removeEventListener('mousemove', updateCursorOnMove);
      document.removeEventListener('mousemove', drag);
      document.removeEventListener('mouseup', dragEnd);
      videoContainer.removeEventListener('touchstart', dragStart);
      document.removeEventListener('touchmove', drag);
      document.removeEventListener('touchend', dragEnd);
      observer.disconnect();
    };
  }

  pauseJitsi() {
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
    if (this.jitsiApi && !this.state.jitsiLoaded) {
      this.state.jitsiLoaded = true;
      this.resumeJitsi();
    }
  }

  cleanupJitsi() {
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
    if (this.state.session.participant_ids?.length > 0) {
      try {
        const participantRecords = await this.orm.read(
          'dw.participant',
          this.state.session.participant_ids,
          ['id', 'name', 'attendance_status']
        );

        this.state.session.participants = participantRecords;

      } catch (error) {
        console.error("❌ Error refreshing participant status:", error);
      }
    } else {
      console.log("⚠️ No participant IDs to refresh");
    }
  }

  startDurationTimer() {
    const parsedStart = this.parseOdooDatetimeToDate(this.state.session.actual_start_datetime);
    if (parsedStart) {
      this.startTime = parsedStart.getTime();
    } else {
      this.startTime = Date.now();
    }
    this.durationInterval = setInterval(() => {
      const elapsed = Date.now() - this.startTime;
      const seconds = Math.floor(elapsed / 1000);
      const minutes = Math.floor(seconds / 60);
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

  // ================== UI TOGGLES ==================

  toggleNotes() {
    this.onTabChange(this.state.activeMainTab === 'notes' ? 'video' : 'notes');
  }

  toggleActions() {
    this.onTabChange(this.state.activeMainTab === 'actions' ? 'video' : 'actions');
  }

  toggleAgenda() {
    this.onTabChange(this.state.activeMainTab === 'agenda' ? 'video' : 'agenda');
  }

  async toggleCamera() {
    this.state.session.display_camera = !this.state.session.display_camera;

    // If user is turning camera on, reset the manually closed flag
    if (this.state.session.display_camera) {
      this.state.pipManuallyClosed = false;
    }

    await this.orm.write("dw.meeting.session", [this.sessionId], {
      display_camera: this.state.session.display_camera,
    });
  }

  // ================== SAVE OPERATIONS ==================

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

  // ================== PV TEMPLATE METHODS ==================

  async loadPvTemplate() {
    try {
      // Generate template from backend
      await this.generatePvTemplate();
    } catch (error) {
      console.error("Failed to load PV template:", error);
      this.notification.add("Failed to load PV template", {
        type: "danger",
      });
    }
  }

  async generatePvTemplate() {
    // Load PV template from backend instead of using prototype
    try {
      if (!this.meetingId) {
        throw new Error("No meeting ID available");
      }

      // Call backend to generate template
      await this.orm.call(
        'dw.meeting',
        'action_generate_pv_template',
        [this.meetingId]
      );

      // Reload PV content
      const meetings = await this.orm.read(
        "dw.meeting",
        [this.meetingId],
        ["pv"]
      );

      if (meetings && meetings.length > 0) {
        this.state.pv = meetings[0].pv || "";
      }

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

  // ================== ACTIONS ==================

  async addNewAction() {
    try {
      const newActionId = await this.orm.create("dw.actions", [{
        name: "New Action",
        session_id: this.sessionId,
        meeting_id: this.meetingId,
        project_id: this.state.session.project_id,
        status: "todo",
        priority: "0",
      }]);

      this.state.actions.push({
        id: newActionId[0],
        name: "New Action",
        assignee_id: "",
        dead_line: "",
        priority: "0",
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

      if (action.project_id) {
        const projectId = typeof action.project_id === 'string'
            ? parseInt(action.project_id, 10)
            : action.project_id;
        if (!isNaN(projectId) && projectId > 0) {
            updateData.project_id = projectId;
        }
      } else {
          updateData.project_id = false;
      }

      if (action.assignee_id) {
        const assigneeId = typeof action.assignee_id === 'string'
          ? parseInt(action.assignee_id, 10)
          : action.assignee_id;

        if (!isNaN(assigneeId) && assigneeId > 0) {
          updateData.assignee = assigneeId;
        }
      } else {
        updateData.assignee = false;
      }

      if (action.dead_line) {
        updateData.dead_line = action.dead_line;
      }

      console.log("Updating action with data:", updateData);

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

  // ================== MEETING CONTROL ==================

async leaveMeeting() {
  const confirmed = confirm("Are you sure you want to leave this meeting?");
  if (confirmed) {
    try {
      // Find current participant based on current user
      const currentUserId = this.state.session.user_id;
      console.log("currentUserId:", currentUserId);
      const currentParticipant = this.state.session.participant_id;
      console.log("currentParticipant:", currentParticipant);
      if (currentParticipant) {
        // Update attendance status to 'pause'
        await this.orm.write(
          'dw.participant',
          [currentParticipant],
          { attendance_status: 'pause' }
        );

        // Read back the updated status to verify
        const updatedParticipant = await this.orm.read(
          'dw.participant',
          [currentParticipant],
          ['attendance_status']
        );

        console.log("✅ Updated attendance_status:", updatedParticipant[0].attendance_status);
      }

      // Leave the meeting
      if (this.jitsiApi) {
        this.jitsiApi.executeCommand("hangup");
      } else {
        this.goBack();
      }
    } catch (error) {
      console.error("❌ Error updating attendance status:", error);
      // Still leave the meeting even if status update fails
      if (this.jitsiApi) {
        this.jitsiApi.executeCommand("hangup");
      } else {
        this.goBack();
      }
    }
  }
}

    // ADD THE downloadDocument METHOD HERE
    downloadDocument(doc) {
      try {
        if (!doc.attachments) {
          console.warn("⚠️ No attachment data for:", doc.name);
          return;
        }

        // Convert base64 to blob and download
        const byteCharacters = atob(doc.attachments);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);

        // Try to determine mimetype from file extension
        const extension = doc.name.split('.').pop().toLowerCase();
        const mimetypes = {
          'pdf': 'application/pdf',
          'doc': 'application/msword',
          'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'xls': 'application/vnd.ms-excel',
          'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'ppt': 'application/vnd.ms-powerpoint',
          'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
          'jpg': 'image/jpeg',
          'jpeg': 'image/jpeg',
          'png': 'image/png',
          'gif': 'image/gif',
          'txt': 'text/plain',
          'zip': 'application/zip',
        };

        const mimetype = mimetypes[extension] || 'application/octet-stream';
        const blob = new Blob([byteArray], { type: mimetype });

        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.name;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        console.log("✅ Document downloaded:", doc.name);
      } catch (error) {
        console.error("❌ Error downloading document:", error);
      }
    }

    async loadPlanificationDocuments() {
      if (this.planificationId) {
        try {
          const planification = await this.orm.read(
            'dw.planification.meeting',
            [this.planificationId],
            ['document_ids']
          );

          if (planification[0]?.document_ids?.length > 0) {
            const documents = await this.orm.read(
              'dw.meeting.document',
              planification[0].document_ids,
              ['id', 'name', 'attachments']
            );

            this.state.session.documents = documents;
            console.log("📄 Loaded documents:", documents);
          } else {
            this.state.session.documents = [];
          }
        } catch (error) {
          console.error("❌ Error loading documents:", error);
          this.state.session.documents = [];
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
      const durationHours = h + m / 60 + s / 3600;

      const sessionIds = await this.orm.search("dw.meeting.session", [
        ["planification_id", "=", this.planificationId]
      ]);

      if (sessionIds.length > 0) {
        await this.orm.write("dw.meeting.session", sessionIds, {
          state: "done",
          is_connected: false,
          actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
          actual_duration: durationHours,
        });
      }

      if (this.planificationId) {
        await this.orm.write("dw.planification.meeting", [this.planificationId], {
          state: "done",
          actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
          actual_duration: durationHours,
        });
      }

      if (this.meetingId) {
        await this.orm.write("dw.meeting", [this.meetingId], {
          state: "done",
          actual_end_datetime: this.formatOdooDatetimeUTC(new Date()),
          actual_duration: durationHours,
        });
      }

      const api = this.jitsiApi;
      if (api && typeof api.executeCommand === "function") {
        try {
          const participants = api.getParticipantsInfo() || [];
          for (const participant of participants) {
            if (participant.participantId !== this.state.localParticipantId) {
              api.executeCommand("kickParticipant", participant.participantId);
            }
          }
        } catch (e) {
          console.warn("Error kicking participants:", e);
        }
      }

      this.notification.add("Meeting ended successfully", {
        type: "success",
      });

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