from smartdz import models, fields

class DwRequirements(models.Model):
    _name = 'dw.requirements'
    _description = 'Requirements'

    name = fields.Char(string='Name')

    description = fields.Text(string='Description')

    seq = fields.Integer(string='Sequence')

    status = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed')
    ], string='Statut', default='open')
