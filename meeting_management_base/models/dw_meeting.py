from smartdz import models, fields, api, _
from datetime import datetime, timedelta
from smartdz.exceptions import ValidationError


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
    actual_duration = fields.Float(string='Duration (hours)', default=1.0, tracking=True)


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
            },
        }


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
        room_id = f"odoo-meeting-{self.id}-{uuid.uuid4().hex[:8]}"

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

    @api.model
    def get_dashboard_kpis(self):
        """Get KPI data for dashboard"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Upcoming meetings (future meetings)
        upcoming_count = self.search_count([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done'])
        ])

        # Today's meetings
        today_meetings = self.search([
            ('planned_start_datetime', '>=', today_start),
            ('planned_start_datetime', '<', today_end),
            ('state', 'not in', ['cancelled'])
        ])
        today_count = len(today_meetings)
        today_hours = sum(today_meetings.mapped('duration'))

        # Available rooms
        all_rooms = self.env['dw.room'].search([])
        rooms_free = sum(1 for room in all_rooms if room.status == 'free')

        # Total participants (unique participants in upcoming meetings)
        upcoming_meetings = self.search([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done'])
        ])
        total_participants = sum(len(m.client_ids) for m in upcoming_meetings)

        # Calculate trend (compare with last week)
        last_week_start = now - timedelta(days=7)
        last_week_count = self.search_count([
            ('planned_start_datetime', '>=', last_week_start),
            ('planned_start_datetime', '<', now),
            ('state', 'not in', ['cancelled', 'done'])
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
        """Get upcoming meetings with details"""
        now = datetime.now()
        meetings = self.search([
            ('planned_start_datetime', '>=', now),
            ('state', 'not in', ['cancelled', 'done'])
        ], limit=limit, order='planned_start_datetime asc')

        result = []
        for meeting in meetings:
            # Get organizer (first participant or creator)
            organizer = meeting.client_ids[0] if meeting.client_ids else None
            organizer_name = organizer.name if organizer else (
                meeting.create_uid.name if meeting.create_uid else 'Unknown')

            # Format the date properly
            formatted_date = meeting.planned_start_datetime.strftime('%a, %b %d, %I:%M %p') if meeting.planned_start_datetime else ''

            result.append({
                'id': meeting.id,
                'name': meeting.name or 'Untitled Meeting',
                'planned_start_datetime': meeting.planned_start_datetime.isoformat() if meeting.planned_start_datetime else None,
                'formatted_date': formatted_date,
                'duration': meeting.duration,
                'room_name': meeting.room_id.name if meeting.room_id else None,
                'organizer_name': organizer_name,
                'participant_count': len(meeting.client_ids),
                'state': meeting.state,
                'priority': 'high' if meeting.duration > 2 else 'normal',
                'is_recurring': False,  # Add recurring logic if needed
            })

        return result

    @api.model
    def quick_create_meeting(self, payload):
        """Quick create a meeting from dashboard"""
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
                ('state', 'not in', ['cancelled', 'done']),
                '|',
                '&', ('planned_start_datetime', '<=', start_dt),
                ('planned_end_time', '>', start_dt),
                '&', ('planned_start_datetime', '<', end_dt),
                ('planned_end_time', '>=', end_dt),
            ], limit=1)

            if overlapping:
                raise ValidationError(f"Room is already booked for this time period")

        # Create meeting
        meeting = self.create({
            'name': payload['name'],
            'planned_start_datetime': start_dt,
            'planned_end_time': end_dt,
            'duration': duration,
            'room_id': room_id or False,
            'state': 'in_progress',
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
            ('state', 'not in', ['cancelled'])
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
                ('state', 'not in', ['cancelled'])
            ])
            daily_meetings.append(count)

        # Duration distribution
        all_meetings = self.search([
            ('planned_start_datetime', '>=', week_start),
            ('state', 'not in', ['cancelled'])
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
                ('state', 'not in', ['cancelled'])
            ])
            avg_participants = round(
                sum(len(m.client_ids) for m in day_meetings) / len(day_meetings)
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

