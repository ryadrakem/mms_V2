from smartdz import models, fields, api, _
from smartdz.exceptions import UserError, ValidationError

class DwCorpPlanification(models.Model):
    _inherit = 'dw.meeting'
    _description = 'meeting model for corporate meetings'

    is_ca = fields.Boolean(related='meeting_type_id.is_ca', string='CA')
    is_ag = fields.Boolean(related='meeting_type_id.is_ag', string='Ag')
    is_agex = fields.Boolean(related='meeting_type_id.is_age', string='Age')


