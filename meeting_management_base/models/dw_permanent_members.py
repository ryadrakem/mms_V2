from smartdz import models, fields, api, _
from datetime import datetime, timedelta
from smartdz.exceptions import ValidationError

class DwPermanentMembers(models.Model):
    _name = 'dw.permanent.members'
    _description = 'Permanent Members Group'

    name = fields.Char(string="Group Name", required=True)
    participant_ids = fields.One2many(
        'dw.participant',
        'permanent_members_id',
        string='Participants'
    )


