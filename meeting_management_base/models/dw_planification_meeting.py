from smartdz import models, fields, api, _
from smartdz.exceptions import ValidationError, UserError
from datetime import timedelta, datetime
import logging
import pytz

_logger = logging.getLogger(__name__)

class DwMeetingDocument(models.Model):
    _name = 'dw.meeting.document'
    _description = 'Meeting Documents'

    name = fields.Char(string='Document name', required=True)
    meeting_id = fields.Many2one(
        'dw.planification.meeting',
        string='Meeting',
        ondelete='cascade',
        required=True,
    )
    attachments = fields.Binary(string='Attachments',required=True)

class DwAgenda(models.Model):
    _name = 'dw.agenda'
    _description = 'Agenda'
    _order = 'sequence, id'

    name = fields.Char(string='Ordre du jour', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    planification_id = fields.Many2one('dw.planification.meeting', string='Planification Meeting')
    meeting_id = fields.Many2one('dw.meeting', string='Meeting')
    session_id = fields.Many2one('dw.meeting.session', string='session')
    # Timer fields - NOUVEAUX CHAMPS
    duration_minutes = fields.Integer(
        string='Duration (minutes)',
        default=15,
        help='Durée prévue pour cet ordre du jour en minutes'
    )
    timer_state = fields.Selection([
        ('not_started', 'Not Started'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('overtime', 'Overtime')
    ], string='Timer State', default='not_started', tracking=True)

    timer_start_time = fields.Datetime(string='Timer Start Time')
    timer_pause_time = fields.Datetime(string='Timer Pause Time')
    timer_end_time = fields.Datetime(string='Timer End Time')
    elapsed_seconds = fields.Integer(string='Elapsed Seconds', default=0)
    remaining_seconds = fields.Integer(
        string='Remaining Seconds',
        compute='_compute_remaining_seconds',
        store=False
    )

    @api.depends('duration_minutes', 'elapsed_seconds')
    def _compute_remaining_seconds(self):
        """Calculate remaining time in seconds"""
        for record in self:
            total_seconds = record.duration_minutes * 60
            record.remaining_seconds = max(0, total_seconds - record.elapsed_seconds)

    def action_start_timer(self):
        """Start or resume the timer"""
        self.ensure_one()
        now = fields.Datetime.now()

        if self.timer_state == 'not_started':
            self.write({
                'timer_state': 'running',
                'timer_start_time': now,
                'elapsed_seconds': 0
            })
            _logger.info(f"Timer started for agenda item: {self.name}")

        elif self.timer_state == 'paused':
            if self.timer_pause_time:
                pause_duration = (now - self.timer_pause_time).total_seconds()
                adjusted_start = self.timer_start_time + timedelta(seconds=pause_duration)
                self.write({
                    'timer_state': 'running',
                    'timer_start_time': adjusted_start,
                    'timer_pause_time': False
                })
            _logger.info(f"Timer resumed for agenda item: {self.name}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Timer Started'),
                'message': _('Timer started for: %s') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_pause_timer(self):
        """Pause the timer"""
        self.ensure_one()

        if self.timer_state == 'running':
            now = fields.Datetime.now()
            if self.timer_start_time:
                elapsed = (now - self.timer_start_time).total_seconds()
                self.write({
                    'timer_state': 'paused',
                    'timer_pause_time': now,
                    'elapsed_seconds': int(elapsed)
                })
            _logger.info(f"Timer paused for agenda item: {self.name}")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Timer Paused'),
                    'message': _('Timer paused for: %s') % self.name,
                    'type': 'info',
                    'sticky': False,
                }
            }

    def action_stop_timer(self):
        """Stop the timer and mark as completed"""
        self.ensure_one()
        now = fields.Datetime.now()

        if self.timer_state in ['running', 'paused', 'overtime']:
            if self.timer_state == 'running' and self.timer_start_time:
                elapsed = (now - self.timer_start_time).total_seconds()
                self.elapsed_seconds = int(elapsed)

            self.write({
                'timer_state': 'completed',
                'timer_end_time': now
            })
            _logger.info(f"Timer stopped for agenda item: {self.name}")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Timer Completed'),
                    'message': _('Timer completed for: %s') % self.name,
                    'type': 'success',
                    'sticky': False,
                }
            }

    def action_reset_timer(self):
        """Reset the timer to initial state"""
        self.ensure_one()
        self.write({
            'timer_state': 'not_started',
            'timer_start_time': False,
            'timer_pause_time': False,
            'timer_end_time': False,
            'elapsed_seconds': 0
        })
        _logger.info(f"Timer reset for agenda item: {self.name}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Timer Reset'),
                'message': _('Timer reset for: %s') % self.name,
                'type': 'info',
                'sticky': False,
            }
        }

    @api.model
    def get_timer_data(self, agenda_id):
        """Get current timer data for real-time updates"""
        record = self.browse(agenda_id)
        if not record.exists():
            return {}

        now = fields.Datetime.now()
        elapsed_seconds = 0

        if record.timer_state == 'running' and record.timer_start_time:
            elapsed_seconds = int((now - record.timer_start_time).total_seconds())
        elif record.timer_state in ['paused', 'completed', 'overtime']:
            elapsed_seconds = record.elapsed_seconds

        total_seconds = record.duration_minutes * 60
        remaining_seconds = max(0, total_seconds - elapsed_seconds)

        return {
            'id': record.id,
            'name': record.name,
            'duration_minutes': record.duration_minutes,
            'timer_state': record.timer_state,
            'elapsed_seconds': elapsed_seconds,
            'remaining_seconds': remaining_seconds,
            'is_overtime': elapsed_seconds > total_seconds
        }

    @api.model
    def check_overtime_and_notify(self):
        """Vérifier les agendas en overtime et envoyer des notifications"""
        now = fields.Datetime.now()
        overtime_agendas = self.search([
            ('timer_state', '=', 'running'),
            ('timer_start_time', '!=', False)
        ])

        for agenda in overtime_agendas:
            if agenda.timer_start_time:
                elapsed = (now - agenda.timer_start_time).total_seconds()
                if elapsed > agenda.duration_minutes * 60:
                    # Marquer comme overtime
                    agenda.write({'timer_state': 'overtime'})
                    # Notification (vous pouvez étendre avec des bus.bus pour les popups)
                    _logger.info(f"Agenda '{agenda.name}' is in overtime!")
                    # Ici, vous pouvez ajouter une notification via bus.bus ou chatter


class DwPlanificationMeeting(models.Model):
    _name = 'dw.planification.meeting'
    _description = 'Planification Meeting'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Title', tracking=True, required=True)
    objet = fields.Char(string='Objet')
    is_external = fields.Boolean(string='External', help="If the meeting implies external participants")
    is_off_site = fields.Boolean(string='Off Site', help="If the meeting location is outside the company")
    use_agenda_timer = fields.Boolean(
        string='Use Agenda Timer',
        default=True,
        tracking=True,
        help='Enable timer for each agenda item during the meeting'
    )
    is_presence_constraint = fields.Boolean(string='Presence Constraint', help="Keeps the meeting from starting if a required member did not accept the invitation or if the minimum number of attendees is not reached")
    meeting_type_id = fields.Many2one('dw.meeting.type', string='Meeting Type')
    # subject_order = fields.Html(string='Agenda')
    subject_order = fields.One2many('dw.agenda', 'planification_id', string='Agenda')
    client_ids = fields.Many2many('res.partner', string='Client', domain=[('is_company', '=', True)])
    planned_start_datetime = fields.Datetime(string='Start Date & Time', required=True, tracking=True)
    actual_start_datetime = fields.Datetime(string='Actual Start Date & Time', tracking=True)
    tolerated_late = fields.Integer(string="Tolerated Late (minutes)", help="In minutes")
    tolerated_limit = fields.Datetime(string="Tolerated Limit", compute="_compute_tolerated_limit", store=True)

    planned_end_time = fields.Datetime(string='End Time', compute='_compute_end_time', store=True)
    actual_end_datetime = fields.Datetime(string='Actual End Date & Time', store=True)
    location_id = fields.Many2one('dw.location', string='Location')
    room_id = fields.Many2one('dw.room', string='Room')
    participant_ids = fields.One2many('dw.participant','meeting_planification_id', string='Participants', store=True)
    duration = fields.Float(string='Duration (H)', store=True, required=True, default=1.0)
    actual_duration = fields.Float(string='Duration (hours)', default=1.0, tracking=True)

    # specific to planification
    equipment_ids = fields.Many2many('dw.equipment', string='Equipements')
    meeting_id = fields.Many2one('dw.meeting', string='Meetings', ondelete='cascade')
    project_id = fields.Many2one('dw.project', string='Project', domain=lambda self: self._get_allowed_projects_domain())
    use_the_chat_room = fields.Boolean(string='Use the chat room', default=False)
    display_camera = fields.Boolean(string='Display the cameras in the meeting', default=False)
    is_current_user_host = fields.Boolean(string="Is Current User Host", compute="_compute_is_current_user_host", store=False)
    is_current_user_participant = fields.Boolean(string="Is Current User Participant", compute="_compute_is_current_user_participant")
    calendar_event_id = fields.Many2one('calendar.event', string='Calendar Event', readonly=True, copy=False)
    sync_with_calendar = fields.Boolean(string='Sync with Calendar', default=True, help='Create the event in your calendar')
    use_vc = fields.Boolean(string='Video Conference', default=True, help='If ticked, a video conference page will be available during the meeting')
    has_pv = fields.Boolean(string='PV', default=True, help='If the meeting implies the redaction of an offical report')
    times_postponed = fields.Integer(string='Times Postponed')

    use_quorum_percentage = fields.Boolean(
        string="Use Quorum Percentage",
        default=True,
        help="Enable to use a percentage quorum. Disable to use a fixed number."
    )

    quorum_number = fields.Integer(
        string="Quorum (Number)",
        help="Minimum number of participants who must accept."
    )

    quorum = fields.Integer(string='Quorum (%)', default=50, help="Minimum percentage of participants who must accept.")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    unique_participant_ids = fields.Many2many(
        'dw.participant',
        string="Unique Participants",
        compute="_compute_unique_participants",
        store=True
    )

    @api.onchange('participant_ids', 'permanent_members_id')
    @api.depends('participant_ids', 'participant_ids.user_id')
    def _compute_unique_participants(self):
        for rec in self:
            seen_users = set()
            unique_participants = self.env['dw.participant']
            for p in rec.participant_ids:
                if p.user_id and p.user_id.id not in seen_users:
                    seen_users.add(p.user_id.id)
                    unique_participants |= p
            rec.unique_participant_ids = unique_participants

    pv_writer_id2 = fields.Many2one(
        'dw.participant',
        string='PV Writer',
        store=True,
        tracking=True
    )

    pv_writer_id = fields.Many2one(
        'res.users',
        string='PV Writer',
        tracking=True
    )

    host_id = fields.Many2one(
        'dw.participant',
        store=True,
        tracking=True,
    )

    permanent_members_id = fields.Many2one(
        'dw.permanent.members',
        string='Permanent Members Group'
    )

    has_remote_participants = fields.Boolean(
        string='Has Remote Participants',
        compute='_compute_has_remote_participants',
        store=True
    )
    is_send_email = fields.Boolean(string='Send Email Invitations', default=True, help='Do you wish to send email invitations to the participants')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('planned', 'Planned'),
        ('started', 'Started'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    document_ids = fields.One2many(
        'dw.meeting.document',
        'meeting_id',
        string='Documents'
    )

    @api.onchange('pv_writer_id2')
    def _compute_set_pv_writer(self):
        for rec in self:
            rec.participant_ids.write({'is_pv': False})
            if rec.pv_writer_id2:
                rec.pv_writer_id2.is_pv = True


    @api.onchange('permanent_members_id')
    def _compute_participant_ids_from_permanent(self):
        for rec in self:
            if not rec.permanent_members_id:
                rec.participant_ids = [(5, 0, 0)]
                continue

            new_participants = [(5, 0, 0)]

            for participant in rec.permanent_members_id.participant_ids:
                new_participants.append((0, 0, {
                    'name': participant.name,
                    'employee_id': participant.employee_id.id,
                    'role_id': participant.role_id.id,
                    'department': participant.department.id,
                    'job': participant.job.id,
                    'is_external': participant.is_external,
                    'is_action_assigner': participant.is_action_assigner,
                    'is_presence_required': participant.is_presence_required,
                    'is_remote': participant.is_remote,
                }))

            rec.participant_ids = new_participants

    @api.model
    def _get_allowed_projects_domain(self):
        return [
            ('status', 'not in', ['cancelled', 'done']),
            ('users_allowed_to_see', 'in', [self.env.user.id])
        ]

    @api.depends("actual_start_datetime", "tolerated_late")
    def _compute_tolerated_limit(self):
        for rec in self:
            if rec.actual_start_datetime and rec.tolerated_late is not None:
                rec.tolerated_limit = rec.actual_start_datetime + timedelta(minutes=rec.tolerated_late)
            else:
                rec.tolerated_limit = False

    @api.depends('participant_ids', 'participant_ids.is_remote')
    def _compute_has_remote_participants(self):
        """Check if meeting has any remote participants"""
        for meeting in self:
            meeting.has_remote_participants = any(meeting.participant_ids.mapped('is_remote'))

    @api.depends('participant_ids.is_host')
    def _compute_is_current_user_host(self):
        for rec in self:
            participant = rec.participant_ids.filtered(lambda p: p.user_id == self.env.user)
            rec.is_current_user_host = any(participant.mapped('is_host'))

    def _compute_is_current_user_participant(self):
        for rec in self:
            user = self.env.user

            # find participant linked to this user
            participant = rec.participant_ids.filtered(
                lambda p: p.user_id.id == user.id
            )

            # true if participant found
            rec.is_current_user_participant = bool(participant)

    @api.constrains('planned_start_datetime')
    def _check_start_datetime(self):
        for record in self:
            if record.planned_start_datetime and record.planned_start_datetime < fields.Datetime.now():
                raise ValidationError(_("You cannot set a reservation date in the past."))

    @api.onchange('location_id')
    def _onchange_location_clear_room(self):
        """Clear room field when location changes"""
        if self.room_id:
            self.room_id = False

    @api.onchange('is_off_site')
    def _onchange_location_id(self):
        for rec in self:
            if rec.location_id:
                rec.location_id = False
            if rec.room_id:
                rec.room_id = False

    @api.depends('planned_start_datetime', 'duration')
    def _compute_end_time(self):
        for rec in self:
            if rec.planned_start_datetime and rec.duration:
                rec.planned_end_time = rec.planned_start_datetime + timedelta(hours=rec.duration)
            else:
                rec.planned_end_time = False

    def _format_time_for_user(self, dt):
        """
        Convert a UTC datetime to the current user's timezone string.
        Fixes the 'Time - 1' display issue in error messages.
        """
        if not dt:
            return ""

        # Get user's timezone or default to UTC
        user_tz_str = self.env.user.tz or 'UTC'
        try:
            user_tz = pytz.timezone(user_tz_str)
            # Odoo datetimes are naive UTC, localize them then convert
            utc_dt = pytz.utc.localize(dt)
            local_dt = utc_dt.astimezone(user_tz)
            return local_dt.strftime('%d/%m/%Y %H:%M')
        except Exception:
            # Fallback if timezone conversion fails
            return dt.strftime('%d/%m/%Y %H:%M')

    @api.constrains('planned_start_datetime', 'planned_end_time', 'room_id', 'equipment_ids')
    def _check_availability(self):
        """
        Check availability considering ACTUAL meeting times and PLANNED bookings.
        Validates time slots while allowing future bookings even if room is currently busy.
        """
        for rec in self:
            if not rec.planned_start_datetime or not rec.planned_end_time:
                continue

            #  Check room availability
            if rec.room_id:

                # --- Check for ACTUAL ONGOING meetings ---
                ongoing_meetings = self.env['dw.meeting'].search([
                    ('room_id', '=', rec.room_id.id),
                    ('state', '=', 'in_progress'),
                    # Optimization: Ignore meetings that started AFTER our requested slot ends
                    ('actual_start_datetime', '<', rec.planned_end_time),
                ])

                for ongoing in ongoing_meetings:
                    # Calculate effective end time
                    if ongoing.actual_end_datetime:
                        ongoing_end = ongoing.actual_end_datetime
                    else:
                        # If running, assume: Start + Duration + 15min Buffer
                        duration_hours = ongoing.duration if ongoing.duration > 0 else 1.0
                        ongoing_end = ongoing.actual_start_datetime + timedelta(hours=duration_hours) + timedelta(
                            minutes=15)

                    # Strict Overlap Check: (StartA < EndB) and (EndA > StartB)
                    if rec.planned_start_datetime < ongoing_end and rec.planned_end_time > ongoing.actual_start_datetime:
                        start_str = self._format_time_for_user(ongoing.actual_start_datetime)
                        end_str = self._format_time_for_user(ongoing_end)

                        raise ValidationError(
                            f"❌ Room '{rec.room_id.name}' is currently occupied.\n\n"
                            f"🔴 Current meeting: {ongoing.name}\n"
                            f"⏰ Occupied from: {start_str}\n"
                            f"⌛ Estimated end: {end_str}\n"
                            f"💡 Your meeting starts: {self._format_time_for_user(rec.planned_start_datetime)}\n\n"
                            f"Please choose a later time."
                        )

                # --- B. Check for PLANNED meetings ---
                overlapping_planned = self.search([
                    ('id', '!=', rec.id),
                    ('room_id', '=', rec.room_id.id),
                    ('state', 'in', ['planned', 'confirmed']),
                    ('planned_start_datetime', '<', rec.planned_end_time),
                    ('planned_end_time', '>', rec.planned_start_datetime),
                    ('meeting_id', '=', False),  # Not yet started
                ], limit=1)

                if overlapping_planned:
                    start_str = self._format_time_for_user(overlapping_planned.planned_start_datetime)
                    end_str = self._format_time_for_user(overlapping_planned.planned_end_time)

                    raise ValidationError(
                        f"📅 Room '{rec.room_id.name}' is already booked.\n\n"
                        f"📌 Conflict: {overlapping_planned.name}\n"
                        f"⏰ Time slot: {start_str} - {end_str}\n\n"
                        f"Please choose a different time."
                    )

            # 2. Check equipment availability
            for equipment in rec.equipment_ids:
                overlapping_equipments = self.search([
                    ('id', '!=', rec.id),
                    ('equipment_ids', 'in', equipment.id),
                    ('state', 'in', ['planned', 'confirmed']),
                    ('planned_start_datetime', '<', rec.planned_end_time),
                    ('planned_end_time', '>', rec.planned_start_datetime),
                ], limit=1)

                if overlapping_equipments:
                    raise ValidationError(
                        f"Equipment '{equipment.name}' is already reserved for this time period."
                    )
    def action_plan(self):
        for rec in self:
            rec.state = 'planned'

            if rec.sync_with_calendar and not rec.calendar_event_id:
                rec._create_calendar_event()

            # Create room reservation
            if rec.room_id:
                self.env['dw.reservations'].create({
                    'name': f"Salle: {rec.room_id.name}",
                    'start_time': rec.planned_start_datetime,
                    'planned_end_time': rec.planned_end_time,
                    'room_id': rec.room_id.id,
                    'meeting_plannification_id': rec.id,
                })

            for equipment in rec.equipment_ids:
                self.env['dw.reservations'].create({
                    'name': f"Équipement: {equipment.name}",
                    'start_time': rec.planned_start_datetime,
                    'planned_end_time': rec.planned_end_time,
                    'equipment_ids': [(4, equipment.id)],
                    'meeting_plannification_id': rec.id,
                })

            # Generate access tokens for all participants
            for participant in rec.participant_ids:
                if not participant.access_token:
                    participant._generate_access_token()

            # Get the secure email template
            template = self.env.ref('meeting_management_base.email_template_meeting_invitation_secure',
                                    raise_if_not_found=False)

            if template and self.is_send_email:
                # Send individual email to each participant
                for participant in rec.participant_ids:
                    participant_email = None
                    if participant.partner_id and participant.partner_id.email:
                        participant_email = participant.partner_id.email
                    elif participant.employee_id and participant.employee_id.work_email:
                        participant_email = participant.employee_id.work_email

                    if participant_email:
                        try:
                            template.send_mail(
                                participant.id,  # Send to participant record
                                force_send=True,
                                email_values={
                                    'email_to': participant_email,
                                    'recipient_ids': []  # Clear default recipients
                                }
                            )
                            _logger.info(f"Invitation sent to {participant.name} ({participant_email})")
                        except Exception as e:
                            _logger.error(f"Failed to send invitation to {participant.name}: {str(e)}")
                    else:
                        _logger.warning(f"No email address found for participant {participant.name}")
            else:
                _logger.warning("Email template 'email_template_meeting_invitation_secure' not found!")

    def create_meeting_and_sessions(self):
        self.ensure_one()

        participants = self.participant_ids
        total = len(participants)
        accepted = len(participants.filtered(lambda p: p.invitation_status == 'accepted'))

        if total > 0 and self.is_presence_constraint:
            if self.use_quorum_percentage:
                if not self.quorum:
                    raise ValidationError("⚠️ Please set the quorum percentage.")
                required = (total * self.quorum) / 100.0
                display_required = f"{self.quorum}% ({int(required) if required.is_integer() else round(required, 1)})"
            else:
                if not self.quorum_number:
                    raise ValidationError("⚠️ Please set the quorum number.")
                required = self.quorum_number
                display_required = f"{self.quorum_number} participants"

            if accepted < required:
                raise ValidationError(
                    "⚠️ Cannot start the meeting.\n\n"
                    f"Quorum not reached: {accepted}/{total} participants accepted.\n"
                    f"Required: {display_required}."
                )

        missing_required = participants.filtered(
            lambda p: p.is_presence_required and p.invitation_status != 'accepted'
        )
        if missing_required and self.is_presence_constraint:
            names = ", ".join(missing_required.mapped("name"))
            raise ValidationError(
                "⚠️ Cannot start the meeting.\n\n"
                "The following required participants have not accepted the invitation:\n"
                f"- {names}\n\n"
                "Please wait for their confirmation before starting the meeting."
            )

        # Check for overrun conflicts before creating meeting
        if self.room_id and self._handle_meeting_overrun(ignore_time_window=True):
            self.env.cr.commit()
            raise ValidationError(
                "⚠️ Cannot start meeting - room is still occupied.\n\n"
                "The previous meeting is still in progress.\n"
                "Notifications have been sent to both meeting hosts.\n\n"
                "Please wait a few minutes and try again."
            )

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 1: Copier les agendas pour le MEETING
        # ═══════════════════════════════════════════════════════════════════
        meeting_agendas = []
        for agenda in self.subject_order.sorted('sequence'):
            meeting_agenda = self.env['dw.agenda'].create({
                'name': agenda.name,
                'sequence': agenda.sequence,
                'duration_minutes': agenda.duration_minutes,
                # planification_id reste vide pour les agendas du meeting
                # meeting_id sera assigné après la création du meeting
            })
            meeting_agendas.append(meeting_agenda.id)

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 2: Créer le MEETING avec les agendas copiés
        # ═══════════════════════════════════════════════════════════════════
        self.actual_start_datetime = fields.Datetime.now()
        meeting = self.env['dw.meeting'].create({
            'name': self.name,
            'planned_start_datetime': self.planned_start_datetime,
            'duration': self.duration,
            'subject_order': [(6, 0, meeting_agendas)],  # Utiliser les agendas copiés
            'planification_id': self.id,
            'form_planification': True,
            'actual_start_datetime': fields.Datetime.now(),
            'participant_ids': [(6, 0, self.participant_ids.ids)],
            'objet': self.objet,
            'meeting_type_id': self.meeting_type_id.id,
            'client_ids': [(6, 0, self.client_ids.ids)],
            'room_id': self.room_id.id if self.room_id else False,
            'location_id': self.location_id.id if self.location_id else False,
            'is_external': self.is_external,
            'project_id': self.project_id.id,
            'state': 'in_progress',
        })

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 3: Mettre à jour les agendas du meeting avec meeting_id
        # ═══════════════════════════════════════════════════════════════════
        self.env['dw.agenda'].browse(meeting_agendas).write({
            'meeting_id': meeting.id
        })

        self.write({
            'state': 'started',
            'meeting_id': meeting.id,
        })

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 4: Créer les SESSIONS avec des agendas copiés pour chacune
        # ═══════════════════════════════════════════════════════════════════
        Session = self.env['dw.meeting.session']
        user_session = False

        for participant in self.participant_ids:
            if participant.user_id:
                # ────────────────────────────────────────────────────────────
                # Copier les agendas pour CETTE SESSION spécifique
                # ────────────────────────────────────────────────────────────
                session_agendas = []
                for agenda in self.subject_order.sorted('sequence'):
                    session_agenda = self.env['dw.agenda'].create({
                        'name': agenda.name,
                        'sequence': agenda.sequence,
                        'duration_minutes': agenda.duration_minutes,
                        # session_id sera assigné après la création de la session
                    })
                    session_agendas.append(session_agenda.id)

                # ────────────────────────────────────────────────────────────
                # Créer la session avec les agendas copiés
                # ────────────────────────────────────────────────────────────
                session = Session.create({
                    'name': f"Session {meeting.name}, {participant.name}",
                    'meeting_id': meeting.id,
                    'user_id': participant.user_id.id,
                    'participant_id': participant.id,
                    'planification_id': self.id,
                    'is_host': participant.is_host,
                    'is_pv': participant.is_pv,
                    'use_vc': self.use_vc,
                    'is_action_assigner': participant.is_action_assigner,
                    'actual_start_datetime': fields.Datetime.now(),
                    'display_camera': self.display_camera,
                    'subject_order': [(6, 0, session_agendas)],  # Agendas copiés
                    'project_id': self.project_id.id,
                })

                # ────────────────────────────────────────────────────────────
                # Mettre à jour les agendas de cette session avec session_id
                # ────────────────────────────────────────────────────────────
                self.env['dw.agenda'].browse(session_agendas).write({
                    'session_id': session.id
                })

                if participant.user_id.id == self.env.user.id:
                    user_session = session

        if user_session:
            return self.action_join()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Meeting',
            'res_model': 'dw.meeting',
            'view_mode': 'form',
            'res_id': meeting.id,
            'target': 'current',
        }

    def action_postpone(self):
        self.ensure_one()
        template = self.env.ref('meeting_management_base.email_template_meeting_postponed_secure',
                                raise_if_not_found=False)

        if template and self.is_send_email:
            # Send individual email to each participant
            for participant in self.participant_ids:
                participant_email = None
                if participant.partner_id and participant.partner_id.email:
                    participant_email = participant.partner_id.email
                elif participant.employee_id and participant.employee_id.work_email:
                    participant_email = participant.employee_id.work_email

                if participant_email:
                    try:
                        template.send_mail(
                            participant.id,  # Send to participant record
                            force_send=True,
                            email_values={
                                'email_to': participant_email,
                                'recipient_ids': []  # Clear default recipients
                            }
                        )
                        _logger.info(f"Invitation sent to {participant.name} ({participant_email})")
                    except Exception as e:
                        _logger.error(f"Failed to send invitation to {participant.name}: {str(e)}")
                else:
                    _logger.warning(f"No email address found for participant {participant.name}")
        else:
            _logger.warning("Email template 'email_template_meeting_invitation_secure' not found!")

        return {
            'name': 'Postpone Meeting',
            'type': 'ir.actions.act_window',
            'res_model': 'dw.meeting.postpone.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_meeting_id': self.id,
                # 'default_participant_ids': self.participant_ids.ids,
            }
        }


    def _delete_reservations(self):
        """Delete all reservations when meeting is cancelled or done"""
        self.ensure_one()
        reservations = self.env['dw.reservations'].search([
            ('meeting_plannification_id', '=', self.id)
        ])
        if reservations:
            reservations.unlink()
            _logger.info(f"Deleted {len(reservations)} reservations for meeting {self.name}")

    def open_meeting(self):
        self.ensure_one()
        Meeting = self.env['dw.meeting']
        meeting = Meeting.search([('planification_id', '=', self.id)], limit=1)
        return {
            'type': 'ir.actions.client',
            'name': f'Meeting: {meeting.name}',
            'tag': 'meetin_view_action',
            'context': {
                'active_id': meeting.id,
                'default_planification_id': self.id,
            },
        }

    def action_join(self):
        self.ensure_one()
        Session = self.env['dw.meeting.session']
        user_session = False
        Meeting = self.env['dw.meeting']

        # find meeting linked to this planification
        meeting = Meeting.search([('planification_id', '=', self.id)], limit=1)

        for participant in self.participant_ids:
            if participant.user_id:
                session = Session.search([('meeting_id', '=', meeting.id), ('participant_id', '=', participant.id),
                                          ('user_id', '=', participant.user_id.id)], limit=1)

                if participant.user_id.id == self.env.user.id:
                    user_session = session

        if user_session:
            user_session.participant_id.attendance_status = "present"

            if not user_session.flag_attendance:
                now = fields.Datetime.now()
                user_session.join_time = now
                if self.actual_start_datetime and self.tolerated_late:
                    tolerated_limit = self.actual_start_datetime + timedelta(minutes=self.tolerated_late)
                    if now <= tolerated_limit:
                        user_session.participant_id.is_late = False
                    else:
                        user_session.participant_id.is_late = True

                elif self.actual_start_datetime and self.tolerated_late == 0:
                    if now <= self.actual_start_datetime + timedelta(minutes=1):
                        user_session.participant_id.is_late = False
                    else:
                        user_session.participant_id.is_late = True
                user_session.flag_attendance = True

        return {
            'type': 'ir.actions.client',
            'name': f'Meeting: {meeting.name}-{user_session.user_id.name}',
            'tag': 'meeting_session_view_action',
            'params': {
                'planification_id': self.id,
            },
            'context': {
                'active_id': user_session.id,
                'default_session_id': user_session.id,
                'default_planification_id': self.id,
                'default_pv': meeting.pv,
            },
        }

    """
    # TODO : we have to check about this create for the calendar integration suggested by claude.
    """

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            group_id = vals.get('permanent_members_id')
            group = self.env['dw.permanent.members'].browse(group_id)
            meeting_type_id = vals.get('meeting_type_id')
            if group_id:
                meeting_type_id = self.env['dw.meeting.type'].browse(meeting_type_id)
                if not meeting_type_id.is_corporate:
                    participants = []
                    for participant in group.participant_ids:
                        participants.append((0, 0, {
                            'name': participant.name,
                            'employee_id': participant.employee_id.id if participant.employee_id else False,
                            'role_id': participant.role_id.id if participant.role_id else False,
                            'department': participant.department.id if participant.department else False,
                            'job': participant.job.id if participant.job else False,
                            'is_external': participant.is_external,
                            'is_action_assigner': participant.is_action_assigner,
                            'is_presence_required': participant.is_presence_required,
                            'is_remote': participant.is_remote,
                            'partner_id': participant.partner_id.id if participant.partner_id else False,
                        }))
                    vals['participant_ids'] = participants

        return super().create(vals_list)


    def write(self, vals):
        result = super().write(vals)

        if 'pv_writer_id2' in vals:
            for rec in self:
                rec.participant_ids.write({'is_pv': False})

                if rec.pv_writer_id2:
                    rec.pv_writer_id2.write({'is_pv': True})

        if 'state' in vals and vals['state'] in ['planned']:
            for record in self:
                if record.sync_with_calendar and not record.calendar_event_id:
                    record._create_calendar_event()

        # Si des champs liés à la date/heure sont modifiés, mettre à jour le calendrier
        calendar_fields = ['name', 'planned_start_datetime', 'duration', 'planned_end_time', 'location_id',
                           'room_id', 'subject_order', 'participant_ids']

        if any(field in vals for field in calendar_fields):
            for record in self:
                if record.sync_with_calendar and record.calendar_event_id:
                    record._update_calendar_event()

        if 'permanent_members_id' in vals:
            for rec in self:
                if rec.permanent_members_id:
                    rec.participant_ids.unlink()

                    participants = []
                    for participant in rec.permanent_members_id.participant_ids:
                        participants.append((0, 0, {
                            'name': participant.name,
                            'employee_id': participant.employee_id.id if participant.employee_id else False,
                            'role_id': participant.role_id.id if participant.role_id else False,
                            'department': participant.department.id if participant.department else False,
                            'job': participant.job.id if participant.job else False,
                            'is_external': participant.is_external,
                            'is_action_assigner': participant.is_action_assigner,
                            'is_presence_required': participant.is_presence_required,
                            'is_remote': participant.is_remote,
                            'partner_id': participant.partner_id.id if participant.partner_id else False,
                        }))

                    rec.participant_ids = participants
                else:
                    rec.participant_ids.unlink()

        return result

    def unlink(self):
        """Prevent deletion if meeting has been created or if in certain states"""
        for record in self:
            # Check if meeting has been created from this planification
            if record.meeting_id:
                raise UserError(_(
                    'Cannot delete planification "%s" because a meeting has already been created from it. '
                    'You can cancel the meeting instead.'
                ) % record.name)

            # Check if there are confirmed reservations
            if record.state in ['planned', 'confirmed', 'started', 'done']:
                raise UserError(_(
                    'Cannot delete planification "%s" in state "%s". '
                ) % (record.name, record.state))

            # Delete associated calendar event if exists
            if record.calendar_event_id:
                record.calendar_event_id.unlink()

        return super().unlink()

    def _create_calendar_event(self):
        """Créer un événement dans le calendrier"""
        self.ensure_one()

        if not self.planned_start_datetime:
            return

        # Préparer la description
        description_parts = []
        if self.objet:
            description_parts.append(f"Objet: {self.objet}")
        if self.subject_order:
            description_parts.append(f"\n\nAgenda:\n{self.subject_order}")
        if self.room_id:
            description_parts.append(f"\n\nSalle: {self.room_id.name}")
        if self.location_id:
            description_parts.append(f"Lieu: {self.location_id.name}")

        description = '\n'.join(description_parts) if description_parts else ''

        # Récupérer les participants
        partner_ids = self._get_calendar_partners()

        # Localisation
        location = ''
        if self.room_id:
            location = self.room_id.name
            if self.location_id:
                location += f" - {self.location_id.name}"
        elif self.location_id:
            location = self.location_id.name

        # Créer l'événement calendrier
        calendar_vals = {
            'name': self.name or 'Réunion',
            'start': self.planned_start_datetime,
            'stop': self.planned_end_time or self.planned_start_datetime,
            'duration': self.duration,
            'description': description,
            'location': location,
            'partner_ids': [(6, 0, partner_ids)],
            'user_id': self.env.user.id,
            'privacy': 'public',
            'show_as': 'busy',
            'active': True,
        }

        try:
            calendar_event = self.env['calendar.event'].create(calendar_vals)
            self.calendar_event_id = calendar_event.id

            _logger.info(f"Événement calendrier créé (ID: {calendar_event.id}) pour la planification {self.name}")

            # Message dans le chatter
            self.message_post(
                body=_("Calendar event created: <a href='#' data-oe-model='calendar.event' data-oe-id='%s'>%s</a>") %
                     (calendar_event.id, calendar_event.name)
            )

        except Exception as e:
            _logger.error(f"Erreur lors de la création de l'événement calendrier: {str(e)}")
            raise ValidationError(_(f"Failed to create calendar event: {str(e)}"))

    def _update_calendar_event(self):
        """Mettre à jour l'événement dans le calendrier"""
        self.ensure_one()

        if not self.calendar_event_id:
            return

        description_parts = []
        if self.objet:
            description_parts.append(f"Objet: {self.objet}")
        if self.subject_order:
            description_parts.append(f"\n\nAgenda:\n{self.subject_order}")
        if self.room_id:
            description_parts.append(f"\n\nSalle: {self.room_id.name}")
        if self.location_id:
            description_parts.append(f"Lieu: {self.location_id.name}")

        description = '\n'.join(description_parts) if description_parts else ''

        partner_ids = self._get_calendar_partners()

        location = ''
        if self.room_id:
            location = self.room_id.name
            if self.location_id:
                location += f" - {self.location_id.name}"
        elif self.location_id:
            location = self.location_id.name

        update_vals = {
            'name': self.name or 'Réunion',
            'start': self.planned_start_datetime,
            'stop': self.planned_end_time or self.planned_start_datetime,
            'duration': self.duration,
            'description': description,
            'location': location,
            'partner_ids': [(6, 0, partner_ids)],
        }

        try:
            self.calendar_event_id.write(update_vals)
            _logger.info(f"Événement calendrier mis à jour (ID: {self.calendar_event_id.id})")
        except Exception as e:
            _logger.error(f"Erreur lors de la mise à jour de l'événement calendrier: {str(e)}")

    def _get_calendar_partners(self):
        """Récupérer les IDs des partners pour le calendrier"""
        partner_ids = []

        for participant in self.participant_ids:
            if participant.partner_id:
                partner_ids.append(participant.partner_id.id)
            elif participant.employee_id and participant.employee_id.user_id:
                partner_ids.append(participant.employee_id.user_id.partner_id.id)

        # Ajouter l'utilisateur créateur s'il n'est pas déjà dans la liste
        if self.env.user.partner_id.id not in partner_ids:
            partner_ids.append(self.env.user.partner_id.id)

        return partner_ids

    def action_done(self):
        for rec in self:
            rec._delete_reservations()  # Add this line
            rec.state = 'done'

    def action_confirm(self):
        for rec in self:
            host_count = self.participant_ids.filtered(lambda p: p.is_host == True)
            if not host_count:
                raise ValidationError(
                    _("At least one participant must be designated as host before starting the meeting.")
                )
            if not rec.participant_ids:
                raise ValidationError(_("You cannot confirm a planification without any participant."))

            if rec.has_pv:
                pv_participants = rec.participant_ids.filtered(lambda p: p.is_pv)

                if not pv_participants:
                    raise ValidationError(
                        _("A PV has been requested, but no participant has the PV role.")
                    )

                if len(pv_participants) > 1:
                    raise ValidationError(
                        _("Only one participant may be designated as PV.")
                    )
            rec.state = 'confirmed'

    def action_cancel(self):
        for rec in self:
            if rec.calendar_event_id:
                rec.calendar_event_id.unlink()
            rec._delete_reservations()
            rec.state = 'cancelled'

            template = self.env.ref('meeting_management_base.email_template_meeting_cancellation_secure',
                                    raise_if_not_found=False)

            if rec.state == "planned" and template and self.is_send_email:
                # Send individual email to each participant
                for participant in rec.participant_ids:
                    participant_email = None
                    if participant.partner_id and participant.partner_id.email:
                        participant_email = participant.partner_id.email
                    elif participant.employee_id and participant.employee_id.work_email:
                        participant_email = participant.employee_id.work_email

                    if participant_email:
                        try:
                            template.send_mail(
                                participant.id,  # Send to participant record
                                force_send=True,
                                email_values={
                                    'email_to': participant_email,
                                    'recipient_ids': []  # Clear default recipients
                                }
                            )
                            _logger.info(f"Invitation sent to {participant.name} ({participant_email})")
                        except Exception as e:
                            _logger.error(f"Failed to send invitation to {participant.name}: {str(e)}")
                    else:
                        _logger.warning(f"No email address found for participant {participant.name}")
            else:
                _logger.warning("Email template 'email_template_meeting_invitation_secure' not found!")

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'

    @api.model
    def get_dashboard_kpis(self):
        """Get KPI data for dashboard - using actual meeting data"""
        now = fields.Datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Upcoming meetings from planifications
        upcoming_count = self.search_count([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ])

        # Today's meetings - use actual meetings if available
        Meeting = self.env['dw.meeting']
        today_actual_meetings = Meeting.search([
            ('actual_start_datetime', '>=', today_start),
            ('actual_start_datetime', '<', today_end),
            ('state', 'in', ['in_progress', 'done'])
        ])

        # Fall back to planned if no actual meetings
        if not today_actual_meetings:
            today_meetings = self.search([
                ('planned_start_datetime', '>=', today_start),
                ('planned_start_datetime', '<', today_end),
                ('state', 'not in', ['cancelled', 'draft'])
            ])
            today_count = len(today_meetings)
            today_hours = sum(today_meetings.mapped('duration'))
        else:
            today_count = len(today_actual_meetings)
            today_hours = sum(today_actual_meetings.mapped('actual_duration') or [0])

        # Available rooms
        all_rooms = self.env['dw.room'].search([])
        rooms_free = sum(1 for room in all_rooms if room.status == 'free')

        # Total unique participants in upcoming meetings
        upcoming_meetings = self.search([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ])

        unique_participants = set()
        for meeting in upcoming_meetings:
            for participant in meeting.participant_ids:
                if participant.employee_id:
                    unique_participants.add(participant.employee_id.id)
                elif participant.partner_id:
                    unique_participants.add(participant.partner_id.id)
                else:
                    unique_participants.add(participant.id)

        total_participants = len(unique_participants)

        # Calculate trend
        last_week_start = now - timedelta(days=7)
        last_week_count = self.search_count([
            ('planned_start_datetime', '>=', last_week_start),
            ('planned_start_datetime', '<', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ])

        trend = None
        if last_week_count > 0:
            trend = round(((upcoming_count - last_week_count) / last_week_count) * 100, 1)

        return {
            'upcoming': upcoming_count,
            'today': today_count,
            'today_hours': round(today_hours, 1),
            'rooms_free': rooms_free,
            'total_participants': total_participants,
            'upcoming_trend': trend
        }

    @api.model
    def get_upcoming_meetings(self, limit=20):
        """Get upcoming planification meetings with proper timezone handling"""
        now = fields.Datetime.now()
        meetings = self.search([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ], limit=limit, order='planned_start_datetime asc')

        result = []
        user_tz = self.env.user.tz or 'UTC'
        tz = pytz.timezone(user_tz)

        for meeting in meetings:
            # Get organizer
            organizer_name = 'Unknown'
            host_participant = meeting.participant_ids.filtered(lambda p: p.is_host)
            if host_participant:
                organizer_name = host_participant[0].name
            elif meeting.create_uid:
                organizer_name = meeting.create_uid.name

            # Convert UTC to user timezone
            if meeting.planned_start_datetime:
                utc_dt = pytz.UTC.localize(meeting.planned_start_datetime)
                user_dt = utc_dt.astimezone(tz)
                formatted_date = user_dt.strftime('%a, %b %d, %I:%M %p')
                # Return ISO format in user timezone for JavaScript
                iso_in_user_tz = user_dt.isoformat()
            else:
                formatted_date = ''
                iso_in_user_tz = None

            # Determine priority
            priority = 'normal'
            if meeting.duration > 2:
                priority = 'high'
            time_to_start = (meeting.planned_start_datetime - now).total_seconds() / 3600
            if time_to_start < 1:
                priority = 'urgent'

            # Count unique participants
            unique_participants = set()
            for participant in meeting.participant_ids:
                if participant.employee_id:
                    unique_participants.add(participant.employee_id.id)
                elif participant.partner_id:
                    unique_participants.add(participant.partner_id.id)
                else:
                    unique_participants.add(participant.id)

            result.append({
                'id': meeting.id,
                'name': meeting.name or 'Untitled Meeting',
                'planned_start_datetime': iso_in_user_tz,
                'formatted_date': formatted_date,
                'duration': meeting.duration,
                'room_name': meeting.room_id.name if meeting.room_id else None,
                'organizer_name': organizer_name,
                'participant_count': len(unique_participants),
                'state': meeting.state,
                'priority': priority,
                'is_recurring': False,
            })

        return result

    @api.model
    def quick_create_meeting(self, payload):
        """Quick create with proper timezone handling"""
        if not payload.get('name'):
            raise ValidationError("Meeting title is required")

        if not payload.get('planned_start_datetime'):
            raise ValidationError("Start date and time is required")

        # Parse the datetime string - it's already in UTC format from frontend
        start_dt_str = payload['planned_start_datetime']

        # Parse datetime string (format: "YYYY-MM-DD HH:MM:SS")
        try:
            start_dt = fields.Datetime.to_datetime(start_dt_str)
        except:
            raise ValidationError("Invalid datetime format")

        duration = float(payload.get('duration', 1))
        end_dt = start_dt + timedelta(hours=duration)

        # Validate room availability
        room_id = payload.get('room_id')
        if room_id:
            overlapping = self.search([
                ('room_id', '=', room_id),
                ('state', 'not in', ['cancelled', 'done', 'draft']),
                '|',
                '&', ('planned_start_datetime', '<=', start_dt),
                ('planned_end_time', '>', start_dt),
                '&', ('planned_start_datetime', '<', end_dt),
                ('planned_end_time', '>=', end_dt),
            ], limit=1)

            if overlapping:
                raise ValidationError("Room is already booked for this time period")

        # Create meeting
        meeting = self.create({
            'name': payload['name'],
            'planned_start_datetime': start_dt,
            'duration': duration,
            'room_id': room_id or False,
            'state': 'draft',  # Changed from draft to planned
        })

        return {'id': meeting.id, 'name': meeting.name}

    @api.model
    def get_week_stats(self):
        """Get current week statistics using actual meeting data"""
        now = fields.Datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        # Try to get actual completed meetings first
        Meeting = self.env['dw.meeting']
        actual_meetings = Meeting.search([
            ('actual_start_datetime', '>=', week_start),
            ('actual_start_datetime', '<', week_end),
            ('state', 'in', ['in_progress', 'done'])
        ])

        if actual_meetings:
            total = len(actual_meetings)
            hours = sum(actual_meetings.mapped('actual_duration') or [0])
            avg_duration = round((hours / total * 60) if total > 0 else 0, 1)
        else:
            # Fall back to planned meetings
            week_meetings = self.search([
                ('planned_start_datetime', '>=', week_start),
                ('planned_start_datetime', '<', week_end),
                ('state', 'not in', ['cancelled', 'draft'])
            ])
            total = len(week_meetings)
            hours = sum(week_meetings.mapped('duration'))
            avg_duration = round((hours / total * 60) if total > 0 else 0, 1)

        return {
            'total': total,
            'hours': round(hours, 1),
            'avg_duration': avg_duration
        }

    @api.model
    def get_activity_feed(self, limit=15):
        """Get recent activity feed"""
        # Get recent meetings with activities
        recent_meetings = self.search([], limit=limit, order='write_date desc')

        feed = []
        for meeting in recent_meetings:
            activity_type = 'created'
            if meeting.state == 'cancelled':
                activity_type = 'cancelled'
            elif meeting.write_date and meeting.create_date and meeting.write_date != meeting.create_date:
                activity_type = 'updated'

            author = meeting.create_uid.name if meeting.create_uid else 'System'
            time_ago = self._format_time_ago(meeting.write_date or meeting.create_date)

            feed.append({
                'id': meeting.id,
                'title': f"{meeting.name or 'Meeting'} - {meeting.state.replace('_', ' ').title()}",
                'author': author,
                'time': time_ago,
                'type': activity_type,
            })

        return feed


    @api.model
    def get_analytics_data(self):
        """Get analytics data using actual meetings when available"""
        now = fields.Datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        Meeting = self.env['dw.meeting']

        # Meetings per day (last 7 days) - use actual meetings
        daily_meetings = []
        for i in range(7):
            day_start = week_start + timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            # Count actual meetings first
            actual_count = Meeting.search_count([
                ('actual_start_datetime', '>=', day_start),
                ('actual_start_datetime', '<', day_end),
                ('state', 'in', ['in_progress', 'done'])
            ])

            # If no actual meetings, count planned ones
            if actual_count == 0:
                actual_count = self.search_count([
                    ('planned_start_datetime', '>=', day_start),
                    ('planned_start_datetime', '<', day_end),
                    ('state', 'not in', ['cancelled', 'draft'])
                ])

            daily_meetings.append(actual_count)

        # Duration distribution - use actual meetings
        actual_meetings = Meeting.search([
            ('actual_start_datetime', '>=', week_start),
            ('state', 'in', ['in_progress', 'done'])
        ])

        if not actual_meetings:
            actual_meetings = self.search([
                ('planned_start_datetime', '>=', week_start),
                ('state', 'not in', ['cancelled', 'draft'])
            ])
            use_field = 'duration'
        else:
            use_field = 'actual_duration'

        duration_dist = {
            'under_30': 0,
            '30_to_60': 0,
            '60_to_120': 0,
            'over_120': 0
        }

        for meeting in actual_meetings:
            duration_hours = getattr(meeting, use_field, 0) or 0
            duration_minutes = duration_hours * 60

            if duration_minutes < 30:
                duration_dist['under_30'] += 1
            elif duration_minutes < 60:
                duration_dist['30_to_60'] += 1
            elif duration_minutes < 120:
                duration_dist['60_to_120'] += 1
            else:
                duration_dist['over_120'] += 1

        total = sum(duration_dist.values()) or 1
        duration_percentages = {k: round((v / total) * 100, 1) for k, v in duration_dist.items()}

        # Room utilization
        all_rooms = self.env['dw.room'].search([])
        total_rooms = len(all_rooms)
        occupied_rooms = sum(1 for room in all_rooms if room.status != 'free')
        utilization = round((occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0, 1)

        # Participant trends (last 7 days)
        participant_trends = []
        for i in range(7):
            day_start = week_start + timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            # Use actual meetings
            day_meetings = Meeting.search([
                ('actual_start_datetime', '>=', day_start),
                ('actual_start_datetime', '<', day_end),
                ('state', 'in', ['in_progress', 'done'])
            ])

            if not day_meetings:
                day_meetings = self.search([
                    ('planned_start_datetime', '>=', day_start),
                    ('planned_start_datetime', '<', day_end),
                    ('state', 'not in', ['cancelled', 'draft'])
                ])

            avg_participants = round(
                sum(len(m.participant_ids) for m in day_meetings) / len(day_meetings)
            ) if day_meetings else 0
            participant_trends.append(avg_participants)

        return {
            'daily_meetings': daily_meetings,
            'duration_distribution': duration_percentages,
            'room_utilization': utilization,
            'participant_trends': participant_trends
        }

    def _format_time_ago(self, dt):
        """Format datetime to 'time ago' string"""
        if not dt:
            return 'Unknown'

        now = datetime.now()
        diff = now - dt

        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

    def _handle_meeting_overrun(self, ignore_time_window=False):
        """
        Handle the case where a previous meeting is still running.
        :param ignore_time_window: If True, checks room status regardless of planned time (for manual start).
        """
        self.ensure_one()

        if self.state not in ['planned', 'confirmed']:
            return False

        now = fields.Datetime.now()

        _logger.info(f"🔍 CHECKING OVERRUN: {self.name} (Planned: {self.planned_start_datetime})")

        #  TIME WINDOW CHECK
        if not ignore_time_window:
            time_until_start = (self.planned_start_datetime - now).total_seconds() / 60
            _logger.info(f"   ⏱️ Minutes until start: {time_until_start}")

            if time_until_start > 30 or time_until_start < -240:
                _logger.info("   ❌ Stopped: Outside time window (+30 to -240 mins)")
                return False

        # ROOM OCCUPANCY CHECK
        ongoing_meeting = self.env['dw.meeting'].search([
            ('room_id', '=', self.room_id.id),
            ('state', '=', 'in_progress'),
            ('actual_start_datetime', '<', now),
            '|',
            ('actual_end_datetime', '=', False),
            ('actual_end_datetime', '>', now)
        ], limit=1)

        if ongoing_meeting:
            _logger.info(f"   ✅ CONFLICT FOUND with: {ongoing_meeting.name}")
            self._send_in_app_notifications(ongoing_meeting)
            return True

        _logger.info("   🟢 No conflict found.")
        return False

    def _send_in_app_notifications(self, ongoing_meeting):
        """
        Send in-app notifications.
        - Ongoing Meeting: Host ONLY.
        - Waiting Meeting: All Participants (Host gets specific message, others get general).
        """
        self.ensure_one()

        # Get hosts
        ongoing_host = ongoing_meeting.participant_ids.filtered(lambda p: p.is_host)[:1]
        waiting_host = self.participant_ids.filtered(lambda p: p.is_host)[:1]

        # Calculate times
        if ongoing_meeting.actual_end_datetime:
            estimated_end = ongoing_meeting.actual_end_datetime
        else:
            estimated_end = ongoing_meeting.actual_start_datetime + timedelta(
                hours=ongoing_meeting.duration if ongoing_meeting.duration > 0 else 1.0
            )
        estimated_end_str = estimated_end.strftime('%H:%M')
        current_time = fields.Datetime.now().strftime('%H:%M')

        if ongoing_host and ongoing_host.user_id:
            try:
                self._send_notification_to_user(
                    user=ongoing_host.user_id,
                    title='⚠️ URGENT: Meeting Overrun!',
                    message=f'Your meeting is overrunning! Next meeting is waiting.',
                    notification_type='warning',
                    sticky=True
                )

                # Inbox Message
                ongoing_meeting.message_post(
                    body=f"""
                        <div style="background-color:#fff3cd; padding:15px; border-left: 5px solid #ffc107;">
                            <h3 style="color:#856404; margin-top:0;">⚠️ YOUR MEETING IS OVERRUNNING!</h3>
                            <p><strong>Scheduled End:</strong> {ongoing_meeting.planned_end_time.strftime('%H:%M')}</p>
                            <p style="color:#856404;"><strong>🔴 NEXT MEETING WAITING:</strong> {self.name}</p>
                            <p>Please wrap up immediately.</p>
                        </div>
                    """,
                    subject='⚠️ URGENT: Meeting Overrun Alert',
                    message_type='notification',
                    partner_ids=[ongoing_host.user_id.partner_id.id],
                    subtype_xmlid='mail.mt_comment',
                )
            except Exception as e:
                _logger.error(f"❌ Failed to notify ongoing host: {e}")


        if waiting_host and waiting_host.user_id:
            try:
                self._send_notification_to_user(
                    user=waiting_host.user_id,
                    title='⏰ Room Delay',
                    message=f'Room {self.room_id.name} occupied. Est delay: 15-30 min.',
                    notification_type='info',
                    sticky=True
                )

                self.message_post(
                    body=f"""
                        <div style="background-color:#d1ecf1; padding:15px; border-left: 5px solid #17a2b8;">
                            <h3 style="color:#0c5460; margin-top:0;">⏰ ROOM DELAY NOTIFICATION</h3>
                            <p><strong>Room:</strong> {self.room_id.name}</p>
                            <p><strong>Occupied By:</strong> {ongoing_meeting.name}</p>
                            <p><strong>Est. Available:</strong> {estimated_end_str}</p>
                        </div>
                    """,
                    subject='⏰ Room Delay Notification',
                    message_type='notification',
                    partner_ids=[waiting_host.user_id.partner_id.id],
                    subtype_xmlid='mail.mt_comment',
                )
            except Exception as e:
                _logger.error(f"❌ Failed to notify waiting host: {e}")


        other_participants = self.participant_ids.filtered(
            lambda p: p.user_id and not p.is_host
        )

        if other_participants:
            # Send Popups
            for participant in other_participants:
                try:
                    self._send_notification_to_user(
                        user=participant.user_id,
                        title='📢 Meeting Delayed',
                        message=f'"{self.name}" delayed. Room occupied.',
                        notification_type='danger',
                        sticky=True
                    )
                except Exception as e:
                    _logger.error(f"Failed to popup {participant.name}: {e}")

            partner_ids = [p.user_id.partner_id.id for p in other_participants]
            try:
                self.message_post(
                    body=f"""
                        <div style="background-color:#f8d7da; padding:15px; border-left: 5px solid #dc3545;">
                            <h3 style="color:#721c24; margin-top:0;">📢 MEETING DELAYED</h3>
                            <p><strong>Meeting:</strong> {self.name}</p>
                            <p><strong>Reason:</strong> Room {self.room_id.name} is still occupied.</p>
                            <p><strong>Delay:</strong> Approx 15-30 minutes.</p>
                        </div>
                    """,
                    subject='📢 Meeting Delay Notification',
                    message_type='notification',
                    partner_ids=partner_ids,
                    subtype_xmlid='mail.mt_comment',
                )
            except Exception as e:
                _logger.error(f"❌ Failed to notify participants: {e}")

    def _send_notification_to_user(self, user, title, message, notification_type='info', sticky=False):
        """
        Send browser notification (toast popup)
        """
        try:
            partner = user.partner_id
            payload = {
                'type': notification_type,
                'title': title,
                'message': message,
                'sticky': sticky,
            }
            # Odoo 18 Bus Call
            self.env['bus.bus']._sendone(partner, 'simple_notification', payload)
            _logger.info(f"   🚀 POPUP SENT to {user.name}")

        except Exception as e:
            _logger.error(f"   ❌ FAILED to send popup: {e}")

    @api.model
    def _cron_check_overruns(self):
        """
        Scheduled action to check for meetings that should have started
        but room is occupied (run every 5 minutes)
        """
        now = fields.Datetime.now()
        waiting_meetings = self.search([
            ('state', '=', 'planned'),
            ('planned_start_datetime', '>=', now - timedelta(minutes=15)),
            ('planned_start_datetime', '<=', now + timedelta(minutes=5)),
            ('room_id', '!=', False),
        ])

        for meeting in waiting_meetings:
            try:
                meeting._handle_meeting_overrun(ignore_time_window=False)
            except Exception as e:
                _logger.error(f"Error checking overrun for meeting {meeting.id}: {e}")