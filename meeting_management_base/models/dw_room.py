from smartdz import models, fields, api
from datetime import datetime, timedelta


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
        """Find current active meeting for the room"""
        now = datetime.now()

        for room in self:
            meeting = self.env['dw.meeting'].search([
                ('room_id', '=', room.id),
                ('planned_start_datetime', '<=', now),
                ('planned_end_time', '>=', now),
                ('state', 'not in', ['cancelled', 'done'])
            ], limit=1)
            room.current_reservation_id = meeting.id if meeting else False

    @api.depends('current_reservation_id')
    def _compute_status(self):
        """Compute room status based on current meetings"""
        now = datetime.now()

        for room in self:
            # Check if there's an active meeting
            active_meeting = self.env['dw.meeting'].search([
                ('room_id', '=', room.id),
                ('planned_start_datetime', '<=', now),
                ('planned_end_time', '>=', now),
                ('state', 'not in', ['cancelled', 'done'])
            ], limit=1)

            if active_meeting:
                room.status = 'reserved'
            else:
                room.status = 'free'

    @api.model
    def get_rooms_availability(self):
        """Get room availability status for dashboard"""
        rooms = self.search([])
        now = datetime.now()

        result = []
        for room in rooms:
            # Check current status
            current_meeting = self.env['dw.meeting'].search([
                ('room_id', '=', room.id),
                ('planned_start_datetime', '<=', now),
                ('planned_end_time', '>=', now),
                ('state', 'not in', ['cancelled', 'done'])
            ], limit=1)

            is_free = not current_meeting

            # Get next meeting
            next_meeting = self.env['dw.meeting'].search([
                ('room_id', '=', room.id),
                ('planned_start_datetime', '>', now),
                ('state', 'not in', ['cancelled', 'done'])
            ], limit=1, order='planned_start_datetime asc')

            # Format times
            if is_free:
                if next_meeting:
                    free_until = next_meeting.planned_start_datetime.isoformat()
                else:
                    free_until = None
                busy_until = None
                current_meeting_name = None
            else:
                free_until = None
                busy_until = current_meeting.planned_end_time.isoformat()
                current_meeting_name = current_meeting.name or 'Occupied'

            # Get amenities (equipment names)
            amenities = [eq.name for eq in room.equipments[:3]]

            result.append({
                'id': room.id,
                'name': room.name,
                'is_free': is_free,
                'capacity': room.capacity_number or 0,
                'free_until': free_until,
                'busy_until': busy_until,
                'current_meeting': current_meeting_name,
                'amenities': amenities,
                'floor': room.floor or 0,
            })

        return result

    def action_book_now(self):
        """Quick book this room for 1 hour"""
        now = datetime.now()
        planned_end_time = now + timedelta(hours=1)

        # Check if room is available
        overlapping = self.env['dw.meeting'].search([
            ('room_id', '=', self.id),
            ('planned_start_datetime', '<=', now),
            ('planned_end_time', '>', now),
            ('state', 'not in', ['cancelled', 'done'])
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

        # Create quick booking
        meeting = self.env['dw.meeting'].create({
            'name': f'Quick Booking - {self.name}',
            'planned_start_datetime': now,
            'planned_end_time': planned_end_time,
            'duration': 1.0,
            'room_id': self.id,
            'state': 'confirmed',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dw.meeting',
            'res_id': meeting.id,
            'views': [[False, 'form']],
            'target': 'current',
        }