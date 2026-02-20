from smartdz import models, fields, api, _
from smartdz.exceptions import UserError, ValidationError

class DwParticipantRole(models.Model):
    _name = 'dw.participant.role'
    _description = 'Participant Role'

    name = fields.Char(string='Role Name')

    description = fields.Text(string='Description')

    is_system = fields.Boolean(string='System Role', default=False, readonly=True,
                               help='System roles cannot be deleted or modified')

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Role name must be unique!')
    ]

    @api.constrains('name')
    def _check_duplicate_host(self):
        """Prevent creating multiple 'host' roles no duplication"""
        for record in self:
            if record.name and record.name.lower() == 'host':
                existing_host = self.search([
                    ('name', 'ilike', 'host'),
                    ('id', '!=', record.id)
                ], limit=1)
                if existing_host:
                    raise ValidationError(_('A host role already exists. Only one host role is allowed.'))

    def write(self, vals):
        """Prevent modification of system roles"""
        for record in self:
            if record.is_system and any(key in vals for key in ['name', 'is_system']):
                raise UserError(_('Cannot modify system role "%s"') % record.name)
        return super().write(vals)

    def unlink(self):
        """Prevent deletion of system roles and roles in use"""
        for record in self:
            # Check if it's a system role
            dw_participant = self.env['dw.participant']
            if record.is_system:
                raise UserError(_('Cannot delete system role "%s"') % record.name)

            # Check if role is in use
            participants_count = dw_participant.search_count([
                ('role_id', '=', record.id)
            ])

            if participants_count > 0:
                raise UserError(_(
                    'Cannot delete role "%s" because it is assigned to %d participant(s). '
                    'Please reassign these participants first.'
                ) % (record.name, participants_count))

        return super().unlink()