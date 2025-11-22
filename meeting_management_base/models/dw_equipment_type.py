from smartdz import models, fields, api

class DwEquipmentType(models.Model):
    _name = 'dw.equipment.type'
    _description = 'Equipment Type'

    name = fields.Char(string='Name')

    description = fields.Html(string='Description')

    quantity = fields.Integer(string='Quantity',
                              compute='_compute_quantity')

    equipement_ids = fields.One2many('dw.equipment',
                                     'equipment_type_id',
                                     string='Equipments')

    @api.depends('equipement_ids')
    def _compute_quantity(self):
        for rec in self:
            rec.quantity = len(rec.equipement_ids)