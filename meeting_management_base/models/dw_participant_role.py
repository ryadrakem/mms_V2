from smartdz import models, fields

class DwParticipantRole(models.Model):
    _name = 'dw.participant.role'
    _description = 'Participant Role'

    name = fields.Char(string='Role Name')

    description = fields.Text(string='Description')
