from smartdz import models, fields, api, _
from datetime import datetime, timedelta
from smartdz.exceptions import ValidationError

class DwPermanentMembers(models.Model):
    _inherit = 'dw.permanent.members'
    _description = 'Permanent Members Group - Corporate extension'

    is_ca = fields.Boolean(default=False)
    is_ag = fields.Boolean(default=False)
    is_agex = fields.Boolean(default=False)

