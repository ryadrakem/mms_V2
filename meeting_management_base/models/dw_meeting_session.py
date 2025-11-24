from smartdz import models, fields, api, _
from smartdz.exceptions import ValidationError
from datetime import timedelta
import logging

class DwMeetingSession(models.Model):
    _name = 'dw.meeting.session'
    _description = 'User Meeting Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # from planification meeting
    name = fields.Char(string="Session Name", required=True)
    objet = fields.Char(related="meeting_id.objet", readonly=True, store=True)
    meeting_type_id = fields.Many2one('dw.meeting.type', related="meeting_id.meeting_type_id", readonly=True,store=True)
    # subject_order = fields.Html(readonly=True, store=True)
    subject_order = fields.One2many('dw.agenda', 'session_id', string='Agenda')
    planned_start_datetime = fields.Datetime(related="meeting_id.planned_start_datetime", readonly=True, store=True)
    planned_end_time = fields.Datetime(related="meeting_id.planned_end_time", readonly=True, store=True)
    duration = fields.Float(string="Duration (hours)", related="planification_id.duration", store=True)
    meeting_id = fields.Many2one("dw.meeting", string="Meeting", required=True, ondelete="cascade")

    # from session
    actual_start_datetime = fields.Datetime(string='Actual Start Date & Time', tracking=True)
    actual_end_datetime = fields.Datetime(string='Actual End Date & Time', tracking=True)
    actual_duration = fields.Float(string='Duration (hours)', default=1.0, tracking=True)
    user_id = fields.Many2one("res.users", string="User", required=True)
    participant_id = fields.Many2one("dw.participant", string="Linked Participant")
    personal_actions_ids = fields.One2many("dw.actions", "session_id", string="Personal Actions")
    personal_notes = fields.Text(string="My Notes / MoM")
    requirements = fields.Html(string="My Requirements")
    has_remote_participants = fields.Boolean(string='Has Remote Participants',store=True)
    # specific to session
    is_connected = fields.Boolean(string="Currently Connected", default=False)
    is_host = fields.Boolean(string="Host User", related="participant_id.is_host", store=True)
    is_pv = fields.Boolean(string="Rédacteur PV", related="participant_id.is_pv", store=True)
    can_edit_agenda = fields.Boolean(string="Can Edit Agenda")
    can_edit_summary = fields.Boolean(string="Can Edit Summary")
    display_camera = fields.Boolean(string='Display the cameras in the meeting')
    planification_id = fields.Many2one("dw.planification.meeting", string="Origin Planification")
    leave_datetime = fields.Datetime(string="Leave Time")
    join_datetime = fields.Datetime(string="Join Time")
    view_state = fields.Json(string="User View State")

    state = fields.Selection([
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='in_progress', tracking=True)

    participant_ids = fields.One2many(
        'dw.participant',
        compute='_compute_participant_ids',
        string='Participants',
        # store=False
    )

    @api.depends('meeting_id', 'meeting_id.participant_ids')
    def _compute_participant_ids(self):
        for session in self:
            if session.meeting_id:
                session.participant_ids = session.meeting_id.participant_ids.filtered(
                    lambda p: p.meeting_id.id == session.meeting_id.id
                )
            else:
                session.participant_ids = self.env['dw.participant']