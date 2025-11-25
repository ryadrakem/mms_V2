from smartdz import models, fields, api, _
from smartdz.exceptions import ValidationError, UserError
from datetime import timedelta, datetime
import logging

_logger = logging.getLogger(__name__)


class DwAgenda(models.Model):
    _name = 'dw.agenda'
    _description = 'Agenda'

    name = fields.Char(string='Ordre du jour', required=True)
    planification_id = fields.Many2one('dw.planification.meeting', string='Planification Meeting')
    meeting_id = fields.Many2one('dw.meeting', string='Meeting')
    session_id = fields.Many2one('dw.meeting.session', string='session')


class DwPlanificationMeeting(models.Model):
    _name = 'dw.planification.meeting'
    _description = 'Planification Meeting'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Title', tracking=True, required=True)
    objet = fields.Char(string='Objet')
    is_external = fields.Boolean(string='External')
    is_off_site = fields.Boolean(string='Off Site')
    meeting_type_id = fields.Many2one('dw.meeting.type', string='Meeting Type')
    # subject_order = fields.Html(string='Agenda')
    subject_order = fields.One2many('dw.agenda', 'planification_id', string='Agenda')
    client_ids = fields.Many2many('res.partner', string='Client', domain=[('is_company', '=', True)])
    planned_start_datetime = fields.Datetime(string='Start Date & Time', required=True, tracking=True)
    actual_start_datetime = fields.Datetime(string='Actual Start Date & Time', tracking=True)
    planned_end_time = fields.Datetime(string='End Time', compute='_compute_end_time', store=True)
    actual_end_datetime = fields.Datetime(string='Actual End Date & Time', store=True)
    location_id = fields.Many2one('dw.location', string='Location')
    room_id = fields.Many2one('dw.room', string='Room')
    participant_ids = fields.One2many('dw.participant', 'meeting_planification_id', string='Participants')
    duration = fields.Float(string='Duration (H)', store=True, required=True, default=1.0)
    actual_duration = fields.Float(string='Duration (hours)', default=1.0, tracking=True)

    # specific to planification
    equipment_ids = fields.Many2many('dw.equipment', string='Equipements')
    meeting_id = fields.Many2one('dw.meeting', string='Meetings', ondelete='cascade')
    use_the_chat_room = fields.Boolean(string='Use the chat room', default=False)
    display_camera = fields.Boolean(string='Display the cameras in the meeting', default=False)
    is_current_user_host = fields.Boolean(string="Is Current User Host", compute="_compute_is_current_user_host")
    calendar_event_id = fields.Many2one('calendar.event', string='Calendar Event', readonly=True, copy=False)
    sync_with_calendar = fields.Boolean(string='Sync with Calendar', default=True)
    has_pv = fields.Boolean(string='PV', default=True)
    has_remote_participants = fields.Boolean(
        string='Has Remote Participants',
        compute='_compute_has_remote_participants',
        store=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('planned', 'Planned'),
        ('started', 'Started'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    @api.depends('participant_ids', 'participant_ids.is_remote')
    def _compute_has_remote_participants(self):
        """Check if meeting has any remote participants"""
        for meeting in self:
            meeting.has_remote_participants = any(meeting.participant_ids.mapped('is_remote'))

    def _compute_is_current_user_host(self):
        for rec in self:
            user = self.env.user

            # find participant linked to this user
            participant = rec.participant_ids.filtered(
                lambda p: p.user_id.id == user.id
            )

            # true if host
            rec.is_current_user_host = bool(participant and participant.is_host)

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

    @api.constrains('planned_start_datetime', 'planned_end_time', 'room_id', 'equipment_ids')
    def _check_availability(self):
        for rec in self:
            if not rec.planned_start_datetime or not rec.planned_end_time:
                continue

            # 1 Check room availability
            if rec.room_id:
                overlapping_rooms = self.env['dw.planification.meeting'].search([
                    ('id', '!=', rec.id),
                    ('room_id', '=', rec.room_id.id),
                    ('state', '=', 'planned'),
                    ('planned_start_datetime', '<', rec.planned_end_time),
                    ('planned_end_time', '>', rec.planned_start_datetime),
                ])
                if overlapping_rooms:
                    raise ValidationError(
                        f"La salle '{rec.room_id.name}' est déjà réservée pour cet intervalle de temps."
                    )

            # 2 Check equipment availability
            for equipment in rec.equipment_ids:
                overlapping_equipments = self.env['dw.planification.meeting'].search([
                    ('id', '!=', rec.id),
                    ('equipment_ids', 'in', equipment.id),
                    ('state', '=', 'planned'),
                    ('planned_start_datetime', '<', rec.planned_end_time),
                    ('planned_end_time', '>', rec.planned_start_datetime),
                ])
                if overlapping_equipments:
                    raise ValidationError(
                        f"L'équipement '{equipment.name}' est déjà réservé pour cet intervalle de temps."
                    )

    def action_plan(self):
        for rec in self:
            rec.state = 'planned'

            # Créer l'événement calendrier
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

            # Create separate reservations for each equipment
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

            if template:
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

                # 'name': rec.name,
                # 'objet': rec.objet,
                # 'is_external': rec.is_external,
                # 'meeting_type_id': rec.meeting_type_id.id,
                # 'client_ids': [(6, 0, rec.client_ids.ids)],
                # 'room_id': rec.room_id.id if rec.room_id else False,
                # 'planned_start_datetime': rec.planned_start_datetime,
                # 'end_datetime': rec.planned_end_time if hasattr(rec, 'planned_end_time') else False,
                # 'duration': rec.duration,
                # 'state': 'in_progress',
                # 'location_id': rec.location_id.id if rec.location_id else False,
                # 'agenda': rec.subject_order if hasattr(rec, 'subject_order') else False,
                # 'form_planification': True,
                # 'planification_id': rec.id,
                # 'jitsi_room_id': f"meeting-room-{rec.id}-{rec.env.cr.dbname}",
                # 'actual_start_time': fields.Datetime.now(),
                # 'use_the_chat_room': rec.is_off_site,

    def create_meeting_and_sessions(self):
        self.ensure_one()
        # TODO: change 6 with Command
        # 1) Create the MEETING record
        self.actual_start_datetime = fields.Datetime.now()
        meeting = self.env['dw.meeting'].create({
            'name': self.name,
            'planned_start_datetime': self.planned_start_datetime,
            'duration': self.duration,
            'subject_order': self.subject_order,
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
            'state': 'in_progress',
        })
        self.write({
            'state': 'started',
        })

        Session = self.env['dw.meeting.session']
        user_session = False

        for participant in self.participant_ids:
            if participant.user_id:
                session = Session.create({
                    'name': f"Session {meeting.name}, {participant.name}",
                    'meeting_id': meeting.id,
                    'user_id': participant.user_id.id,
                    'participant_id': participant.id,
                    'planification_id': self.id,
                    'is_host': participant.is_host,
                    'is_pv': participant.is_pv,
                    'actual_start_datetime': fields.Datetime.now(),
                    'display_camera': self.display_camera,
                    'subject_order': self.subject_order,
                    'has_remote_participants': self.has_remote_participants,
                })
                # Capture current user's session
                if participant.user_id.id == self.env.user.id:
                    user_session = session

        if user_session:
            return self.action_join()

        # Else open the main meeting
        return {
            'type': 'ir.actions.act_window',
            'name': 'Meeting',
            'res_model': 'dw.meeting',
            'view_mode': 'form',
            'res_id': meeting.id,
            'target': 'current',
        }

    # def open_meeting(self):
    #     self.ensure_one()
    #     Meeting = self.env['dw.meeting']
    #     meeting = Meeting.search([('planification_id', '=', self.id)], limit=1)
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': f'Meeting: {meeting.name}',
    #         'res_model': 'dw.meeting',
    #         'view_mode': 'form',
    #         'res_id': meeting.id,
    #         'target': 'current',
    #     }

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

        # 1911
        # if user_session:
        #     return {
        #         'type': 'ir.actions.act_window',
        #         'name': 'My Meeting Session',
        #         'res_model': 'dw.meeting.session',
        #         'view_mode': 'form',
        #         'res_id': user_session.id,
        #         'target': 'current',
        #     }

    # TODO: claude solution !!!
    # def action_join(self):
    #     self.ensure_one()
    #
    #     Session = self.env['dw.meeting.session']
    #     Meeting = self.env['dw.meeting']
    #     current_user = self.env.user
    #
    #     _logger.info(f"=== action_join called by user: {current_user.name} (ID: {current_user.id}) ===")
    #
    #     # Find meeting linked to this planification
    #     meeting = Meeting.search([('planification_id', '=', self.id)], limit=1)
    #
    #     if not meeting:
    #         raise ValidationError(_('No meeting found for this planification. Please start the meeting first.'))
    #
    #     _logger.info(f"Found meeting: {meeting.name} (ID: {meeting.id})")
    #
    #     # Find current user's participant record
    #     current_participant = self.participant_ids.filtered(
    #         lambda p: p.user_id and p.user_id.id == current_user.id
    #     )
    #
    #     if not current_participant:
    #         _logger.error(f"User {current_user.name} is not a participant of this meeting")
    #         raise ValidationError(_(
    #             'You are not a participant of this meeting. '
    #             'Please contact the meeting organizer.'
    #         ))
    #
    #     _logger.info(f"Found participant record: {current_participant.name} (ID: {current_participant.id})")
    #
    #     # Search for existing session
    #     user_session = Session.search([
    #         ('meeting_id', '=', meeting.id),
    #         ('participant_id', '=', current_participant.id),
    #         ('user_id', '=', current_user.id)
    #     ], limit=1)
    #
    #     # If no session exists, create one
    #     if not user_session:
    #         _logger.warning(f"No session found for user {current_user.name}. Creating new session...")
    #
    #         try:
    #             session_vals = {
    #                 'name': f"Session {meeting.name} - {current_participant.name}",
    #                 'meeting_id': meeting.id,
    #                 'user_id': current_user.id,
    #                 'participant_id': current_participant.id,
    #                 'planification_id': self.id,
    #                 'is_host': current_participant.is_host,
    #                 'is_pv': current_participant.is_pv,
    #                 'actual_start_datetime': fields.Datetime.now(),
    #                 'display_camera': self.display_camera,
    #                 'has_remote_participants': self.has_remote_participants,
    #                 'state': 'in_progress',
    #             }
    #
    #             user_session = Session.create(session_vals)
    #             _logger.info(f"Session created successfully: ID={user_session.id}")
    #
    #             # Copy agenda items to session
    #             if self.subject_order:
    #                 for agenda_item in self.subject_order:
    #                     self.env['dw.agenda'].create({
    #                         'name': agenda_item.name,
    #                         'session_id': user_session.id,
    #                     })
    #                 _logger.info(f"Copied {len(self.subject_order)} agenda items to session")
    #
    #             # Link session to participant
    #             current_participant.write({'session_id': user_session.id})
    #
    #         except Exception as e:
    #             _logger.error(f"Failed to create session: {str(e)}")
    #             raise ValidationError(_(
    #                 'Failed to create your meeting session: %s'
    #             ) % str(e))
    #     else:
    #         _logger.info(f"Found existing session: ID={user_session.id}")
    #
    #     # Final validation
    #     if not user_session or not user_session.id:
    #         _logger.error("user_session is still empty after creation attempt")
    #         raise ValidationError(_(
    #             'Failed to create or find your meeting session. '
    #             'Please contact the administrator.'
    #         ))
    #
    #     _logger.info(f"Returning action to open session {user_session.id}")
    #
    #     # Get user name safely
    #     user_name = user_session.user_id.name if user_session.user_id else current_user.name
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'name': f'Meeting: {meeting.name} - {user_name}',
    #         'tag': 'meeting_session_view_action',
    #         'params': {
    #             'planification_id': self.id,
    #         },
    #         'context': {
    #             'active_id': user_session.id,
    #             'default_session_id': user_session.id,
    #             'default_planification_id': self.id,
    #             'default_pv': meeting.pv if meeting.pv else '',
    #         },
    #     }
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
                # Capture current user's session
                if participant.user_id.id == self.env.user.id:
                    user_session = session

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

    def action_start(self):
        """Start meeting: ensure host, create meeting, link participants, update planification."""
        for rec in self:
            host_count = rec.participant_ids.filtered(lambda p: p.role_id.name == 'host')
            if not host_count:
                raise ValidationError(
                    _("At least one participant must be designated as host before starting the meeting.")
                )

            # Prepare meeting values
            meeting_vals = {
                'name': rec.name,
                'objet': rec.objet,
                'is_external': rec.is_external,
                'meeting_type_id': rec.meeting_type_id.id,
                'client_ids': [(6, 0, rec.client_ids.ids)],
                'room_id': rec.room_id.id if rec.room_id else False,
                'planned_start_datetime': rec.planned_start_datetime,
                'planned_end_time': rec.planned_end_time if hasattr(rec, 'planned_end_time') else False,
                'duration': rec.duration,
                'state': 'in_progress',
                'location_id': rec.location_id.id if rec.location_id else False,
                'subject_order': rec.subject_order if hasattr(rec, 'subject_order') else False,
                'form_planification': True,
                'planification_id': rec.id,
                'jitsi_room_id': f"meeting-room-{rec.id}-{rec.env.cr.dbname}",
                'actual_start_time': fields.Datetime.now(),
                'use_the_chat_room': rec.is_off_site,
            }

            # Create the meeting
            meeting = self.env['dw.meeting'].create(meeting_vals)

            # Link participants to meeting
            rec.participant_ids.write({'meeting_id': meeting.id})

            rec.write({
                'state': 'started',
                'meeting_id': meeting.id,
            })

            return rec.action_join()

            1911
            # Return action for dashboard
            # return {
            #     'type': 'ir.actions.client',
            #     'tag': 'meeting_dashboard_client',
            #     'name': f'Meeting: {meeting.name}',
            #     'params': {
            #         'meeting_id': meeting.id,
            #         'current_user': self.env.user.name,  # <-- pass user name
            #     }
            # }

    """
    # TODO : we have to check about this create for the calendar integration suggested by claude.
    """

    # @api.model_create_multi
    # def create(self, vals_list):
    #     """Créer l'événement calendrier lors de la création"""
    #     records = super().create(vals_list)
    #     for record in records:
    #         if record.sync_with_calendar and record.state in ['planned', 'confirmed']:
    #             record._create_calendar_event()
    #     return records

    def write(self, vals):
        """Mettre à jour l'événement calendrier lors de la modification"""
        result = super().write(vals)

        # Si on passe à l'état planned ou confirmed, créer l'événement
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
            rec.state = 'done'

    def action_confirm(self):
        for rec in self:
            host_count = self.participant_ids.filtered(lambda p: p.role_id.name == 'host')
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
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'

    @api.model
    def get_dashboard_kpis(self):
        """Get KPI data for dashboard"""
        now = fields.Datetime.now()  # Use Odoo's timezone-aware datetime
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Upcoming meetings (future planned/confirmed/started meetings)
        upcoming_count = self.search_count([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ])

        # Today's meetings
        today_meetings = self.search([
            ('planned_start_datetime', '>=', today_start),
            ('planned_start_datetime', '<', today_end),
            ('state', 'not in', ['cancelled', 'draft'])
        ])
        today_count = len(today_meetings)
        today_hours = sum(today_meetings.mapped('duration'))

        # Available rooms
        all_rooms = self.env['dw.room'].search([])
        rooms_free = sum(1 for room in all_rooms if room.status == 'free')

        # Total unique participants in upcoming meetings
        upcoming_meetings = self.search([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ])

        # Count unique participants across all upcoming meetings
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

        # Calculate trend (compare with last week)
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
        """Get upcoming planification meetings with details"""
        now = fields.Datetime.now()  # Use Odoo's timezone-aware datetime
        meetings = self.search([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ], limit=limit, order='planned_start_datetime asc')

        result = []
        for meeting in meetings:
            # Get organizer (from participants or creator)
            organizer_name = 'Unknown'
            host_participant = meeting.participant_ids.filtered(lambda p: p.is_host)
            if host_participant:
                organizer_name = host_participant[0].name
            elif meeting.create_uid:
                organizer_name = meeting.create_uid.name

            # Convert to user's timezone for display
            # Odoo stores in UTC, so we need to convert for display
            user_tz = self.env.user.tz or 'UTC'
            from pytz import timezone
            import pytz

            if meeting.planned_start_datetime:
                # Convert UTC to user timezone
                utc_dt = pytz.UTC.localize(meeting.planned_start_datetime.replace(tzinfo=None))
                user_dt = utc_dt.astimezone(timezone(user_tz))
                formatted_date = user_dt.strftime('%a, %b %d, %I:%M %p')
            else:
                formatted_date = ''

            # Determine priority based on duration and time to start
            priority = 'normal'
            if meeting.duration > 2:
                priority = 'high'
            time_to_start = (meeting.planned_start_datetime - now).total_seconds() / 3600
            if time_to_start < 1:  # Less than 1 hour away
                priority = 'urgent'

            # Count unique participants (avoid duplicates)
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
                'planned_start_datetime': meeting.planned_start_datetime.isoformat() if meeting.planned_start_datetime else None,
                'formatted_date': formatted_date,
                'duration': meeting.duration,
                'room_name': meeting.room_id.name if meeting.room_id else None,
                'organizer_name': organizer_name,
                'participant_count': len(unique_participants),  # Use unique count
                'state': meeting.state,
                'priority': priority,
                'is_recurring': False,  # Add recurring logic if needed
            })

        return result

    @api.model
    def quick_create_meeting(self, payload):
        """Quick create a planification meeting from dashboard"""
        # Validate required fields
        if not payload.get('name'):
            raise ValidationError("Meeting title is required")

        if not payload.get('planned_start_datetime'):
            raise ValidationError("Start date and time is required")

        # Convert string datetime to datetime object
        start_dt = fields.Datetime.to_datetime(payload['planned_start_datetime'])
        duration = float(payload.get('duration', 1))

        # Calculate end time
        end_dt = start_dt + timedelta(hours=duration)

        # Validate room availability if room is specified
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
                raise ValidationError(f"Room is already booked for this time period")

        # Create planification meeting
        meeting = self.create({
            'name': payload['name'],
            'planned_start_datetime': start_dt,
            'duration': duration,
            'room_id': room_id or False,
            'state': 'draft',
        })

        return {'id': meeting.id, 'name': meeting.name}

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
    def get_week_stats(self):
        """Get current week statistics"""
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

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
    def get_analytics_data(self):
        """Get data for analytics charts"""
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())

        # Meetings per day (last 7 days)
        daily_meetings = []
        for i in range(7):
            day_start = week_start + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            count = self.search_count([
                ('planned_start_datetime', '>=', day_start),
                ('planned_start_datetime', '<', day_end),
                ('state', 'not in', ['cancelled', 'draft'])
            ])
            daily_meetings.append(count)

        # Duration distribution
        all_meetings = self.search([
            ('planned_start_datetime', '>=', week_start),
            ('state', 'not in', ['cancelled', 'draft'])
        ])

        duration_dist = {
            'under_30': 0,
            '30_to_60': 0,
            '60_to_120': 0,
            'over_120': 0
        }

        for meeting in all_meetings:
            duration_minutes = meeting.duration * 60
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
