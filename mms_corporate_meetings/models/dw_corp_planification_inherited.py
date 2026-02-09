from smartdz import models, fields, api, _
from smartdz.exceptions import UserError, ValidationError

class DwCorpPlanification(models.Model):
    _inherit = 'dw.planification.meeting'
    _description = 'planification model for corporate meetings'

    is_ca = fields.Boolean(related='meeting_type_id.is_ca', string='CA')
    is_ag = fields.Boolean(related='meeting_type_id.is_ag', string='Ag')
    is_age = fields.Boolean(related='meeting_type_id.is_age', string='Age')
    meeting_number = fields.Integer(string="Meeting Number", compute="_compute_meeting_number", store=True)

    member_ids = fields.One2many(
        'dw.participant',
        'meeting_planification_id',
        string="Members",
        domain=[('is_member', '=', True)]
    )

    guest_ids = fields.One2many(
        'dw.participant',
        'meeting_planification_id',
        string="Guests",
        domain=[('is_member', '=', False)]
    )

    @api.depends('actual_start_datetime', 'is_ca', 'is_ag', 'is_age')
    def _compute_meeting_number(self):
        for rec in self:
            rec.meeting_number = 0

            if not rec.planned_start_datetime:
                continue

            meeting_date = rec.planned_start_datetime.date()
            year = meeting_date.year

            domain = [
                ('planned_start_datetime', '>=', f'{year}-01-01 00:00:00'),
                ('planned_start_datetime', '<=', f'{year}-12-31 23:59:59'),
            ]

            if rec.is_ca:
                domain.append(('meeting_type_id.is_ca', '=', True))
            elif rec.is_ag:
                domain.append(('meeting_type_id.is_ag', '=', True))
            elif rec.is_age:
                domain.append(('meeting_type_id.is_age', '=', True))

            meeting_model = self.env['dw.meeting']
            count = meeting_model.search_count(domain) + 1

            rec.meeting_number = count

    @api.depends('meeting_number', 'planned_start_datetime', 'is_ca', 'is_ag', 'is_age')
    def _compute_meeting_name(self):
        for rec in self:
            if not rec.planned_start_datetime:
                rec.meeting_name = False
                continue

            year = rec.planned_start_datetime.year

            if rec.is_ca:
                prefix = "CA"
            elif rec.is_ag:
                prefix = "AG"
            elif rec.is_age:
                prefix = "AGE"
            else:
                prefix = "MEETING"

            rec.meeting_name = f"{prefix}/N°{rec.meeting_number}/{year}"

    def action_print_convocations(self):
        return self.env.ref('mms_corporate_meetings.report_convocation').report_action(self)


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        is_ca = self.env.context.get('default_is_ca')
        is_ag = self.env.context.get('default_is_ag')
        is_age = self.env.context.get('default_is_age')
        today = fields.Date.today()
        year = today.year
        domain = [
            ('planned_start_datetime', '>=', f'{year}-01-01'),
            ('planned_start_datetime', '<=', f'{year}-12-31'),
        ]


        if is_ca:
            domain.append(('is_ca', '=', True))
            label = "Planification Réunion CA"
        elif is_ag:
            domain.append(('is_ag', '=', True))
            label = "Planification Réunion AG"
        elif is_age:
            domain.append(('is_age', '=', True))
            label = "Planification Réunion AGE"
        else:
            label = "Planification Réunion"

        count = self.search_count(domain) + 1
        number = str(count).zfill(2)

        res['name'] = f"{label} N° {number}/{year}"

        group_id = self.env.context.get('default_permanent_members_id')
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
                    'is_member': p.is_member,
                    'is_president': p.is_president,
                    'is_board_secretariat': p.is_board_secretariat,
                    'is_summoned': p.is_summoned,
                    'is_invited': p.is_invited,
                }))
            res['participant_ids'] = participants
        return res

    def _update_meeting_name(self):
        for record in self:
            if not record.planned_start_datetime:
                continue

            # Determine meeting label
            if record.is_ca:
                meeting_label = "Planification Réunion CA"
            elif record.is_ag:
                meeting_label = "Planification Réunion AG"
            elif record.is_age:
                meeting_label = "Planification Réunion AGE"
            else:
                meeting_label = "Planification Réunion"

            meeting_date = record.planned_start_datetime
            year = meeting_date.year

            domain = [
                ('id', '!=', record.id),
                ('planned_start_datetime', '>=', f'{year}-01-01'),
                ('planned_start_datetime', '<=', f'{year}-12-31'),
            ]
            if record.is_ca:
                domain.append(('is_ca', '=', True))
            elif record.is_ag:
                domain.append(('is_ag', '=', True))
            elif record.is_age:
                domain.append(('is_age', '=', True))

            count = self.search_count(domain) + 1
            number = str(count).zfill(2)

            formatted_date = meeting_date.strftime('%d %B %Y')

            record.name = f"{meeting_label} N° {number}/{year} du {formatted_date}"

    def write(self, vals):
        res = super().write(vals)
        if 'planned_start_datetime' in vals or 'meeting_type_id' in vals:
            self._update_meeting_name()
        return res

    @api.model
    def create(self, vals):
        record = super().create(vals)
        president_line = record.participant_ids.filtered(lambda p: p.is_president)
        if president_line:
            record.host_id = president_line[0].id
            record.pv_writer_id2 = president_line[0].id
        record._update_meeting_name()
        for participant in record.participant_ids:
            participant._compute_is_host()
        return record

