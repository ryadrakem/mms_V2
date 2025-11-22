from smartdz import models, fields

class DwMeetingType(models.Model):
    _name = 'dw.meeting.type'
    _description = 'Meeting Type'

    name = fields.Char(string='Name')

    description = fields.Text(string='Description')
