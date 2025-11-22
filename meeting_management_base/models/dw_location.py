from smartdz import models, fields

class DwLocation(models.Model):
    _name = 'dw.location'
    _description = 'Location'

    name = fields.Char(string='Name')

    adresse = fields.Char(string='Adresse')

    description = fields.Text(string='Description')

    room_ids = fields.One2many('dw.room',
                               'location_id',
                               string='Rooms')

    maps = fields.Char(string='Lien Google Maps')

    is_in_site = fields.Boolean(string='On Site')

