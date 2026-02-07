from smartdz import models, fields

class DwMeetingType(models.Model):
    _inherit = 'dw.meeting.type'
    _description = 'meeting type model for corporate meetings'

    is_ca = fields.Boolean(string='CA')
    is_ag = fields.Boolean(string='AG')
    is_age = fields.Boolean(string='AGE')
    is_corporate = fields.Boolean(string='Corporate')

