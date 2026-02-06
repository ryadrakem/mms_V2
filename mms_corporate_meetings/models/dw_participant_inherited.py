from smartdz import models, fields, api
from smartdz.exceptions import ValidationError
import secrets
import hashlib


class DwParticipant(models.Model):
    _inherit = 'dw.participant'
    _description = 'Participant'

    is_member = fields.Boolean(string='Is Member')
    is_president = fields.Boolean(string='Is President')
    is_board_secretariat = fields.Boolean(string='Is Secretariat')
    is_summoned = fields.Boolean(string='Is Summoned')
    is_invited = fields.Boolean(string='Is Invited')

