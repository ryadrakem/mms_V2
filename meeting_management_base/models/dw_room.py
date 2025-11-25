from smartdz import models, fields, api
from datetime import datetime, timedelta
import pytz
from pytz import timezone
from smartdz.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class DwRoom(models.Model):
    _name = 'dw.room'
    _description = 'Room'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    floor = fields.Integer(string='Floor')
    location_id = fields.Many2one('dw.location', string='Location')
    capacity = fields.Integer(string='Capacity', compute='_compute_capacity', store=True)
    capacity_number = fields.Integer(string='Capacity Number')
    equipments = fields.Many2many('dw.equipment', string='Equipments')
    status = fields.Selection([
        ('free', 'Free'),
        ('reserved', 'Reserved'),
        ('maintenance', 'Maintenance')
    ], string='Status', default='free', compute='_compute_status', store=False)

    current_reservation_id = fields.Many2one('dw.meeting', string='Current Meeting',
                                             compute='_compute_current_meeting')

    @api.depends('capacity_number')
    def _compute_capacity(self):
        """Ensure capacity is set"""
        for room in self:
            room.capacity = room.capacity_number

    def _compute_current_meeting(self):
        """Find current active ACTUAL meeting for the room - FIXED"""
        now = fields.Datetime.now()

        for room in self:
            # PRIORITY 1: Check for actual ongoing meetings (in_progress state)
            actual_meeting = self.env['dw.meeting'].search([
                ('room_id', '=', room.id),
                ('actual_start_datetime', '<=', now),
                ('state', '=', 'in_progress')
            ], limit=1)

            if actual_meeting:
                # Check if meeting has ended based on actual_end_datetime
                if actual_meeting.actual_end_datetime and actual_meeting.actual_end_datetime <= now:
                    room.current_reservation_id = False
                else:
                    room.current_reservation_id = actual_meeting.id
            else:
                # PRIORITY 2: Check planned meetings that haven't started yet
                planned_meeting = self.env['dw.planification.meeting'].search([
                    ('room_id', '=', room.id),
                    ('planned_start_datetime', '<=', now),
                    ('planned_end_time', '>=', now),
                    ('state', 'in', ['planned', 'confirmed']),
                    ('meeting_id', '=', False)  # Not yet converted to actual meeting
                ], limit=1)
                room.current_reservation_id = planned_meeting.id if planned_meeting else False

    @api.depends('current_reservation_id')
    def _compute_status(self):
        """Compute room status based on ACTUAL meetings - FIXED"""
        now = fields.Datetime.now()

        for room in self:
            # PRIORITY 1: Check if there's an actual ongoing meeting
            active_actual_meeting = self.env['dw.meeting'].search([
                ('room_id', '=', room.id),
                ('actual_start_datetime', '<=', now),
                ('state', '=', 'in_progress')
            ], limit=1)

            if active_actual_meeting:
                # Check if meeting has actually ended
                if active_actual_meeting.actual_end_datetime and active_actual_meeting.actual_end_datetime <= now:
                    room.status = 'free'
                else:
                    room.status = 'reserved'
            else:
                # PRIORITY 2: Check for planned meetings that haven't started yet
                upcoming_planned = self.env['dw.planification.meeting'].search([
                    ('room_id', '=', room.id),
                    ('planned_start_datetime', '<=', now),
                    ('planned_end_time', '>=', now),
                    ('state', 'in', ['planned', 'confirmed']),
                    ('meeting_id', '=', False)  # Not yet converted to actual meeting
                ], limit=1)

                room.status = 'reserved' if upcoming_planned else 'free'

    @api.model
    def get_rooms_availability(self):
        """Get room availability status for dashboard - FIXED TO USE ACTUAL TIMES"""
        rooms = self.search([])
        now = fields.Datetime.now()

        # Get user's timezone
        user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)

        result = []
        Meeting = self.env['dw.meeting']

        for room in rooms:
            # PRIORITY 1: Check for actual ongoing meetings (in_progress)
            current_actual_meeting = Meeting.search([
                ('room_id', '=', room.id),
                ('actual_start_datetime', '<=', now),
                ('state', '=', 'in_progress')
            ], limit=1)

            # Check if actual meeting has ended
            if current_actual_meeting:
                if current_actual_meeting.actual_end_datetime and current_actual_meeting.actual_end_datetime <= now:
                    current_actual_meeting = False  # Meeting has ended, room is free

            # PRIORITY 2: If no actual meeting, check planned meetings that haven't started
            current_planned_meeting = None
            if not current_actual_meeting:
                current_planned_meeting = self.env['dw.planification.meeting'].search([
                    ('room_id', '=', room.id),
                    ('planned_start_datetime', '<=', now),
                    ('planned_end_time', '>=', now),
                    ('state', 'in', ['planned', 'confirmed']),
                    ('meeting_id', '=', False)  # Not yet converted to actual meeting
                ], limit=1)

            is_free = not (current_actual_meeting or current_planned_meeting)

            # Get next meeting (actual or planned)
            next_actual_meeting = Meeting.search([
                ('room_id', '=', room.id),
                ('actual_start_datetime', '>', now),
                ('state', 'in', ['in_progress', 'planned'])
            ], limit=1, order='actual_start_datetime asc')

            next_planned_meeting = None
            if not next_actual_meeting:
                next_planned_meeting = self.env['dw.planification.meeting'].search([
                    ('room_id', '=', room.id),
                    ('planned_start_datetime', '>', now),
                    ('state', 'in', ['planned', 'confirmed']),
                    ('meeting_id', '=', False)
                ], limit=1, order='planned_start_datetime asc')

            # Format times
            free_until = None
            busy_until = None
            current_meeting_name = None

            if is_free:
                # Room is free - show when it will be busy next
                target_meeting = next_actual_meeting or next_planned_meeting
                if target_meeting:
                    dt = (target_meeting.actual_start_datetime
                          if hasattr(target_meeting, 'actual_start_datetime') and target_meeting.actual_start_datetime
                          else target_meeting.planned_start_datetime)
                    if dt:
                        utc_dt = pytz.UTC.localize(dt)
                        local_dt = utc_dt.astimezone(user_timezone)
                        free_until = local_dt.strftime('%I:%M %p')
            else:
                # Room is busy - show when it will be free (based on ACTUAL end time if available)
                active_meeting = current_actual_meeting or current_planned_meeting
                if active_meeting:
                    # For actual meetings, use actual_end_datetime if available
                    if hasattr(active_meeting, 'actual_end_datetime') and active_meeting.actual_end_datetime:
                        dt = active_meeting.actual_end_datetime
                    # For planned meetings not yet started, use planned_end_time
                    elif hasattr(active_meeting, 'planned_end_time') and active_meeting.planned_end_time:
                        dt = active_meeting.planned_end_time
                    else:
                        dt = None

                    if dt:
                        utc_dt = pytz.UTC.localize(dt)
                        local_dt = utc_dt.astimezone(user_timezone)
                        busy_until = local_dt.strftime('%I:%M %p')

                    current_meeting_name = active_meeting.name or 'Occupied'

            # Get equipment names
            amenities = [eq.name for eq in room.equipments[:3]]

            result.append({
                'id': room.id,
                'name': room.name,
                'is_free': is_free,
                'capacity': room.capacity_number or 0,
                'free_until': free_until,  # Only set when room is FREE
                'busy_until': busy_until,  # Only set when room is BUSY
                'current_meeting': current_meeting_name,  # Only set when BUSY
                'amenities': amenities,
                'floor': room.floor or 0,
            })

        return result

    def action_book_now(self):
        """Quick book this room for 1 hour - IMPROVED VALIDATION"""
        now = datetime.now()
        planned_end_time = now + timedelta(hours=1)

        # PRIORITY 1: Check for actual ongoing meetings first
        overlapping_actual = self.env['dw.meeting'].search([
            ('room_id', '=', self.id),
            ('actual_start_datetime', '<=', now),
            ('state', '=', 'in_progress')
        ], limit=1)

        if overlapping_actual:
            # Check if meeting has actually ended
            if not (overlapping_actual.actual_end_datetime and overlapping_actual.actual_end_datetime <= now):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Room Not Available',
                        'message': f'Room is currently occupied by: {overlapping_actual.name}',
                        'type': 'warning',
                        'sticky': False,
                    }
                }

        # PRIORITY 2: Check planned meetings
        overlapping_planned = self.env['dw.planification.meeting'].search([
            ('room_id', '=', self.id),
            ('planned_start_datetime', '<=', now),
            ('planned_end_time', '>', now),
            ('state', 'in', ['planned', 'confirmed']),
            ('meeting_id', '=', False)
        ], limit=1)

        if overlapping_planned:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Room Not Available',
                    'message': f'Room is reserved for: {overlapping_planned.name}',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        # Create quick booking
        meeting = self.env['dw.planification.meeting'].create({
            'name': f'Quick Booking - {self.name}',
            'planned_start_datetime': now,
            'duration': 1.0,
            'room_id': self.id,
            'state': 'draft',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dw.planification.meeting',
            'res_id': meeting.id,
            'views': [[False, 'form']],
            'target': 'current',
        }