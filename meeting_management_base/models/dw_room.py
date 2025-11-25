from smartdz import models, fields, api
from datetime import datetime, timedelta
import pytz
from pytz import timezone


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

    current_reservation_id = fields.Many2one('dw.planification.meeting', string='Current Meeting',
                                             compute='_compute_current_meeting')

    @api.depends('capacity_number')
    def _compute_capacity(self):
        """Ensure capacity is set"""
        for room in self:
            room.capacity = room.capacity_number

    def _compute_current_meeting(self):
        """Find current active planification meeting for the room"""
        now = datetime.now()

        for room in self:
            meeting = self.env['dw.planification.meeting'].search([
                ('room_id', '=', room.id),
                ('planned_start_datetime', '<=', now),
                ('planned_end_time', '>=', now),
                ('state', 'not in', ['cancelled', 'done', 'draft'])
            ], limit=1)
            room.current_reservation_id = meeting.id if meeting else False

    @api.depends('current_reservation_id')
    def _compute_status(self):
        """Compute room status based on current planification meetings - IMPROVED"""
        now = fields.Datetime.now()

        for room in self:
            # Check if there's an active meeting
            active_meeting = self.env['dw.planification.meeting'].search([
                ('room_id', '=', room.id),
                ('planned_start_datetime', '<=', now),
                ('planned_end_time', '>=', now),
                ('state', 'not in', ['cancelled', 'done', 'draft'])
            ], limit=1)

            if active_meeting:
                room.status = 'reserved'
            else:
                # Also check for maintenance status or other conditions
                room.status = 'free'

    @api.model
    def get_rooms_availability(self):
        """Get room availability status for dashboard - IMPROVED"""
        rooms = self.search([])
        now = fields.Datetime.now()

        # Get user's timezone
        user_tz = self.env.user.tz or 'UTC'
        user_timezone = timezone(user_tz)

        result = []
        Meeting = self.env['dw.meeting']

        for room in rooms:
            # Check for actual ongoing meetings
            current_actual_meeting = Meeting.search([
                ('room_id', '=', room.id),
                ('actual_start_datetime', '<=', now),
                ('state', '=', 'in_progress')
            ], limit=1)

            # Check planned meetings if no actual meeting
            if not current_actual_meeting:
                current_meeting = self.env['dw.planification.meeting'].search([
                    ('room_id', '=', room.id),
                    ('planned_start_datetime', '<=', now),
                    ('planned_end_time', '>=', now),
                    ('state', 'not in', ['cancelled', 'done', 'draft'])
                ], limit=1)
            else:
                current_meeting = None

            is_free = not (current_actual_meeting or current_meeting)

            # Get next meeting
            next_actual_meeting = Meeting.search([
                ('room_id', '=', room.id),
                ('actual_start_datetime', '>', now),
                ('state', 'in', ['in_progress', 'planned'])
            ], limit=1, order='actual_start_datetime asc')

            if not next_actual_meeting:
                next_meeting = self.env['dw.planification.meeting'].search([
                    ('room_id', '=', room.id),
                    ('planned_start_datetime', '>', now),
                    ('state', 'not in', ['cancelled', 'done'])
                ], limit=1, order='planned_start_datetime asc')
            else:
                next_meeting = None

            # Format times - FIXED FIELD NAMES
            free_until = None
            busy_until = None
            current_meeting_name = None

            if is_free:
                # Room is free - show when it will be busy
                target_meeting = next_actual_meeting or next_meeting
                if target_meeting:
                    dt = (target_meeting.actual_start_datetime
                          if hasattr(target_meeting, 'actual_start_datetime') and target_meeting.actual_start_datetime
                          else target_meeting.planned_start_datetime)
                    if dt:
                        utc_dt = pytz.UTC.localize(dt)
                        local_dt = utc_dt.astimezone(user_timezone)
                        free_until = local_dt.strftime('%I:%M %p')
            else:
                # Room is busy - show when it will be free
                active_meeting = current_actual_meeting or current_meeting
                if active_meeting:
                    if hasattr(active_meeting, 'actual_end_datetime') and active_meeting.actual_end_datetime:
                        dt = active_meeting.actual_end_datetime
                    elif hasattr(active_meeting, 'planned_end_time') and active_meeting.planned_end_time:
                        dt = active_meeting.planned_end_time
                    elif hasattr(active_meeting, 'actual_start_datetime') and active_meeting.actual_start_datetime:
                        # Calculate end time
                        duration = getattr(active_meeting, 'actual_duration', None) or getattr(active_meeting,
                                                                                               'duration', 1)
                        dt = active_meeting.actual_start_datetime + timedelta(hours=duration)
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
        """Quick book this room for 1 hour - creates planification meeting"""
        now = datetime.now()
        planned_end_time = now + timedelta(hours=1)

        # Check if room is available
        overlapping = self.env['dw.planification.meeting'].search([
            ('room_id', '=', self.id),
            ('planned_start_datetime', '<=', now),
            ('planned_end_time', '>', now),
            ('state', 'not in', ['cancelled', 'done', 'draft'])
        ], limit=1)

        if overlapping:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Room Not Available',
                    'message': f'Room is currently occupied by: {overlapping.name}',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        # Create quick booking as planification meeting
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