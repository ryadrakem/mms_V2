import uuid
from smartdz import models, fields, api, _
from datetime import datetime, timedelta
from smartdz.exceptions import ValidationError
import logging
import base64

_logger = logging.getLogger(__name__)

class DwMeeting(models.Model):
    _name = 'dw.meeting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Meeting'
    _order = 'planned_start_datetime desc'

    # from planification meeting
    name= fields.Char(string='Meeting Title', required=True, tracking=True)
    objet = fields.Char(string='Objet')
    is_external = fields.Boolean(string='External')
    meeting_type_id = fields.Many2one('dw.meeting.type', string='Meeting Type')
    client_ids = fields.Many2many('res.partner', string='Client', domain=[('is_company', '=', True)])
    # subject_order = fields.Html(string='Agenda')
    subject_order = fields.One2many('dw.agenda', 'meeting_id', string='Agenda')
    planned_start_datetime = fields.Datetime(string='Start Date & Time', required=True, tracking=True)
    planned_end_time = fields.Datetime(string='End Date & Time', related="planification_id.planned_end_time",store=True)
    location_id = fields.Many2one('dw.location', string='Location')
    room_id = fields.Many2one('dw.room', string='Room')
    participant_ids = fields.One2many('dw.participant', 'meeting_id', string='Participants')
    duration = fields.Float(string='Duration (hours)', default=1.0, tracking=True)
    form_planification = fields.Boolean(string='Created from the planification meetings', default=False)
    planification_id = fields.Many2one('dw.planification.meeting', string='Associated Planifications')

    # from session
    actual_start_datetime = fields.Datetime(string='Actual Start Date & Time', tracking=True)
    actual_end_datetime = fields.Datetime(string='Actual End Date & Time', store=True)
    actual_duration = fields.Float(string='Duration (hours)', default=0.0, tracking=True)


    actions_ids = fields.One2many('dw.actions', 'meeting_id', string='Actions')
    summary = fields.Html(string='Summary')
    note_ids = fields.One2many('dw.meeting.note', 'meeting_id', string='Notes')
    decision_ids = fields.One2many('dw.meeting.decision', 'meeting_id', string='Decisions')
    pv = fields.Text(string='PV')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # jitsi code
    jitsi_room_id = fields.Char(string='Jitsi Room ID', readonly=True, copy=False)
    jitsi_room_created_by = fields.Many2one('res.users', string='Room Created By', readonly=True)
    jitsi_room_created_at = fields.Datetime(string='Room Created At', readonly=True)
    host_participant_id = fields.Many2one(
        'dw.participant',
        string='Meeting Host',
        compute='_compute_host_participant',
        store=True
    )

    @api.depends('participant_ids', 'participant_ids.role_id')
    def _compute_host_participant(self):
        """Find the host participant"""
        for meeting in self:
            host = meeting.participant_ids.filtered(lambda p: p.role_id.name == 'host')
            meeting.host_participant_id = host[0] if host else False

    def open_meeting(self):
        self.ensure_one()
        Planification = self.env['dw.planification.meeting']
        planification = Planification.search([('meeting_id', '=', self.id)], limit=1)
        return {
            'type': 'ir.actions.client',
            'name': f'Meeting: {self.name}',
            'tag': 'meetin_view_action',
            'context': {
                'active_id': self.id,
                'default_planification_id': planification.id,
                'uid': self.env.uid,
            },
        }

    def action_join_meeting(self):
        """Join the meeting - opens the user's session"""
        self.ensure_one()

        # Get current user
        current_user = self.env.user

        # Find the planification linked to this meeting
        planification = self.env['dw.planification.meeting'].search([
            ('meeting_id', '=', self.id)
        ], limit=1)

        if not planification:
            raise ValidationError(_("No planification found for this meeting."))

        # Find the session for the current user
        user_session = self.env['dw.meeting.session'].search([
            ('meeting_id', '=', self.id),
            ('user_id', '=', current_user.id)
        ], limit=1)

        if user_session and not user_session.flag_attendance:
            now = fields.Datetime.now()
            user_session.join_time = now
            if self.planification_id.actual_start_datetime and self.planification_id.tolerated_late:
                tolerated_limit = self.planification_id.actual_start_datetime + timedelta(minutes=self.planification_id.tolerated_late)
                if now <= tolerated_limit:
                    user_session.participant_id.attendance_status = "present"
                else:
                    user_session.participant_id.attendance_status = "late"
            user_session.flag_attendance = True


        if not user_session:
            raise ValidationError(_("You are not a participant in this meeting."))

        # Return the action to open the session
        return {
            'type': 'ir.actions.client',
            'name': f'Meeting: {self.name} - {current_user.name}',
            'tag': 'meeting_session_view_action',
            'params': {
                'planification_id': planification.id,
            },
            'context': {
                'active_id': user_session.id,
                'default_session_id': user_session.id,
                'default_planification_id': planification.id,
                'default_pv': self.pv,
            },
        }

    # def action_open_session(self):
    #     self.ensure_one()
    #     Session = self.env['dw.meeting.session']
    #     user_session = False
    #     Meeting = self.env['dw.meeting']
    #
    #     # find meeting linked to this planification
    #     meeting = Meeting.search([('id', '=', self.id)], limit=1)
    #
    #     for participant in self.participant_ids:
    #         if participant.user_id:
    #             session = Session.search([('meeting_id', '=', meeting.id), ('participant_id', '=', participant.id),
    #                                       ('user_id', '=', participant.user_id.id)], limit=1)
    #             # Capture current user's session
    #             if participant.user_id.id == self.env.user.id:
    #                 user_session = session
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'name': f'Meeting: {meeting.name}-{user_session.user_id.name}',
    #         'tag': 'meeting_session_view_action',
    #         'params': {
    #             'planification_id': meeting.planification.id,
    #         },
    #         'context': {
    #             'active_id': user_session.id,
    #             'default_session_id': user_session.id,
    #             'default_planification_id': meeting.planification.id,
    #             'default_pv': meeting.pv,
    #         },
    #     }


    # abderrahmane jitsi and dashboard methods
    def action_create_jitsi_room(self):
        """Create a Jitsi room - only host can do this"""
        self.ensure_one()

        # Check if user is the host
        current_user = self.env.user
        host_participant = self.participant_ids.filtered(
            lambda p: p.role_id.name == 'host' and (
                    p.partner_id.id == current_user.partner_id.id or
                    p.employee_id.user_id.id == current_user.id
            )
        )

        if not host_participant:
            raise ValidationError(_("Only the meeting host can create the video conference room."))

        if self.jitsi_room_id:
            raise ValidationError(_("A Jitsi room has already been created for this meeting."))

        # Generate unique room ID
        room_id = f"smartdz-meeting-{self.id}-{uuid.uuid4().hex[:8]}"

        self.write({
            'jitsi_room_id': room_id,
            'jitsi_room_created_by': current_user.id,
            'jitsi_room_created_at': fields.Datetime.now(),
        })

        # Send notification to all remote participants
        self._notify_room_created()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Video Room Created'),
                'message': _('The video conference room has been created successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _notify_room_created(self):
        """Notify all remote participants that the room is ready"""
        remote_participants = self.participant_ids.filtered(lambda p: p.is_remote)

        for participant in remote_participants:
            # You can send email or in-app notification here
            _logger.info(f"Notifying {participant.name} that Jitsi room is ready: {self.jitsi_room_id}")



    def action_generate_summary(self):
        """Generate AI-powered meeting summary"""
        self.ensure_one()

        if self.state != 'done':
            raise ValidationError(_("Only completed meetings can have summaries generated."))

        return {
            'type': 'ir.actions.client',
            'tag': 'generate_meeting_summary',
            'params': {
                'meeting_id': self.id,
                'meeting_name': self.name
            }
        }

    def action_view_summary(self):
        """View existing meeting summary"""
        self.ensure_one()

        summary = self.env['dw.meeting.summary'].search([
            ('meeting_id', '=', self.id)
        ], limit=1, order='create_date desc')

        if not summary:
            raise ValidationError(_("No summary found for this meeting."))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dw.meeting.summary',
            'res_id': summary.id,
            'views': [[False, 'form']],
            'target': 'current'
        }

    def _generate_pv_pdf(self):
        """Render the PV PDF using a QWeb report template."""
        self.ensure_one()

        try:
            # Get the report using the standard pattern
            report = self.env['ir.actions.report']._get_report_from_name(
                'meeting_management_base.meeting_pv_pdf_2'
            )

            if not report:
                raise ValueError("Report 'meeting_pv_pdf_2' not found")

            # Render the report
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf('meeting_management_base.meeting_pv_pdf_2', self.id)

            if not pdf_content:
                raise ValueError("PDF generation returned empty content")

            return pdf_content

        except Exception as e:
            _logger.error(f"Error generating PDF for meeting {self.name}: {e}", exc_info=True)
            raise ValidationError(
                _("Failed to generate the PV PDF. Please ensure the report is properly configured.")
            )
    def _send_pv_emails(self, pdf_b64):
        """Send PV emails to all participants with the PDF attachment."""
        self.ensure_one()

        template = self.env.ref(
            'meeting_management_base.email_template_meeting_pv',
            raise_if_not_found=False
        )

        if not template:
            _logger.error("Email template 'meeting_management_base.email_template_meeting_pv' not found")
            return

        for participant in self.participant_ids:
            participant_email = None
            if participant.partner_id and participant.partner_id.email:
                participant_email = participant.partner_id.email
            elif participant.employee_id and participant.employee_id.work_email:
                participant_email = participant.employee_id.work_email

            if not participant_email:
                _logger.warning(
                    f"No email address found for participant {participant.name}"
                )
                continue

            # Build attachment - create unique attachment for each participant
            attachment_name = f"PV_{self.name}_{participant.name}.pdf"
            attachment = self.env['ir.attachment'].create({
                'name': attachment_name,
                'type': 'binary',
                'datas': pdf_b64,
                'res_model': 'dw.meeting',
                'res_id': self.id,
                'mimetype': 'application/pdf',
            })

            # Send email
            try:
                template.send_mail(
                    participant.id,
                    email_values={
                        'email_to': participant_email,
                        'recipient_ids': [],
                        'attachment_ids': [attachment.id],
                    },
                    force_send=True,
                )
                _logger.info(f"PV sent to {participant.name} ({participant_email})")

            except Exception as e:
                _logger.error(f"Failed to send PV to {participant.name}: {e}", exc_info=True)
                # Clean up attachment if email fails
                attachment.unlink()

    def write(self, vals):
        """Override write to send PV emails when meeting is marked as done."""
        res = super(DwMeeting, self).write(vals)

        if 'state' in vals and vals['state'] == 'done':
            for rec in self:
                if rec.pv:
                    try:
                        _logger.info(f"Generating and sending PV for meeting: {rec.name}")
                        pdf_bytes = rec._generate_pv_pdf()
                        pdf_b64 = base64.b64encode(pdf_bytes)
                        # Send email to every participant
                        rec._send_pv_emails(pdf_b64)
                        _logger.info(f"PV successfully sent for meeting: {rec.name}")
                    except Exception as e:
                        _logger.error(f"Failed to generate or send PV for meeting {rec.name}: {e}", exc_info=True)
                        # Optionally, you can notify the user about the failure
                        # but don't block the state change

        return res

    def action_open_pv_wizard(self):
        """Open the popup allowing user to choose PDF or Word."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Download PV',
            'res_model': 'dw.meeting.pv.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_meeting_id': self.id,
            }
        }


class DwMeetingNote(models.Model):
    """Meeting Notes - real-time collaborative notes"""
    _name = 'dw.meeting.note'
    _description = 'Meeting Note'
    _order = 'create_date desc'

    meeting_id = fields.Many2one('dw.meeting', string='Meeting', required=True, ondelete='cascade')
    content = fields.Html(string='Content', required=True)
    author_id = fields.Many2one('res.users', string='Author', default=lambda self: self.env.user)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    is_action_item = fields.Boolean(string='Action Item')


class DwMeetingDecision(models.Model):
    """Meeting Decisions - track key decisions made"""
    _name = 'dw.meeting.decision'
    _description = 'Meeting Decision'
    _order = 'create_date desc'

    meeting_id = fields.Many2one('dw.meeting', string='Meeting', required=True, ondelete='cascade')
    title = fields.Char(string='Decision', required=True)
    description = fields.Text(string='Description')
    decided_by_id = fields.Many2one('res.users', string='Decided By', default=lambda self: self.env.user)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    impact = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Impact', default='medium')





    # def action_open_dashboard(self):
    #     return {
    #         'type': 'ir.actions.client',
    #
    #         'tag': 'meeting_dashboard_client',
    #         'name': 'Meeting Dashboard',
    #         'params': {
    #             'meeting_id': self.id,
    #         }
    #     }

