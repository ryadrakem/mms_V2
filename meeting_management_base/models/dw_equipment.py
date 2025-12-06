from smartdz import models, fields, api

class DwEquipment(models.Model):
    _name = 'dw.equipment'
    _description = 'Equipment'

    name = fields.Char(string='Name')

    description = fields.Html(string='Description')

    serial_number = fields.Char(string='Serial Number')

    status = fields.Selection([
        ('available', 'Available'),
        ('in_use', 'In use'),
        ('maintenance', 'Maintenance')
    ], string='Statut', default='available')

    equipment_type_id = fields.Many2one('dw.equipment.type',string='Equipment Type',required=True)

    reservation_ids = fields.One2many(
        'dw.reservations',
        'equipment_ids',
        string='Reservations',
        compute='_compute_reservations',
        store=True
    )

    @api.depends()
    def _compute_reservations(self):
        dw_reseravtions = self.env['dw.reservations']
        for eq in self:
            eq.reservation_ids = dw_reseravtions.search([
                ('equipment_ids', 'in', eq.id)
            ])
