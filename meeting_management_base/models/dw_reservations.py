from smartdz import models, fields, api
from datetime import timedelta

class DwReservations(models.Model):
    _name = 'dw.reservations'
    _description = 'Reservations'

    name = fields.Char(string='Title',
                       tracking=True)

    start_time = fields.Datetime(string='Start Time')

    planned_end_time = fields.Datetime(string='End Time')

    room_id = fields.Many2one('dw.room',
                              string='Reserved Room')

    equipment_ids = fields.Many2many('dw.equipment',
                                     string='Reserved Equipments')

    meeting_plannification_id = fields.Many2one('dw.planification.meeting',
                                                string='Associated Meeting Planification')
