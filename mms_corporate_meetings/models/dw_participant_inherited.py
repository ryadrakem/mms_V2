from smartdz import models, fields, api
from smartdz.exceptions import ValidationError
import secrets
import hashlib


class DwParticipant(models.Model):
    _inherit = 'dw.participant'
    _description = 'Participant'

    is_member = fields.Boolean(related='role_id.is_member', string='Is Member')
    is_president = fields.Boolean(related='role_id.is_president', string='Is President')
    is_board_secretariat = fields.Boolean(related='role_id.is_board_secretariat', string='Is Secretariat')
    is_summoned = fields.Boolean(related='role_id.is_summoned', string='Is Summoned')
    is_invited = fields.Boolean(related='role_id.is_invited', string='Is Invited')

