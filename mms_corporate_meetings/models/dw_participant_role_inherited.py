from smartdz import models, fields, api, _
from smartdz.exceptions import UserError, ValidationError

class DwParticipantRole(models.Model):
    _inherit = 'dw.participant.role'
    _description = 'participant role model for corporate meetings'

    is_member = fields.Boolean(string='Is Member')
    is_president = fields.Boolean(string='Is President')
    is_board_secretariat = fields.Boolean(string='Is Secretariat')
    is_summoned = fields.Boolean(string='Is Summoned')
    is_invited = fields.Boolean(string='Is Invited')

