from smartdz import models, fields, api, _
from smartdz.exceptions import UserError, ValidationError

class DwCorpPlanification(models.Model):
    _inherit = 'dw.planification.meeting'
    _description = 'planification model for corporate meetings'

    is_ca = fields.Boolean(related='meeting_type_id.is_ca', string='CA')
    is_ag = fields.Boolean(related='meeting_type_id.is_ag', string='Ag')
    is_age = fields.Boolean(related='meeting_type_id.is_age', string='Age')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        group_id = res.get('permanent_members_id')
        if group_id:
            group = self.env['dw.permanent.members'].browse(group_id)
            participants = []
            for p in group.participant_ids:
                participants.append((0, 0, {
                    'name': p.name,
                    'employee_id': p.employee_id.id,
                    'role_id': p.role_id.id,
                    'department': p.department.id,
                    'job': p.job.id,
                    'is_action_assigner': p.is_action_assigner,
                    'is_presence_required': p.is_presence_required,
                    'is_remote': p.is_remote,
                }))
            res['participant_ids'] = participants
        return res

