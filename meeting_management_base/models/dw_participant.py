from smartdz import models, fields, api
from smartdz.exceptions import ValidationError
import secrets
import hashlib


class DwParticipant(models.Model):
    _name = 'dw.participant'
    _description = 'Participant'

    name = fields.Char(string='Name')
    is_external = fields.Boolean(string='External')
    is_remote = fields.Boolean(string='Remote')
    department = fields.Many2one('hr.department', string='Département')
    external_department = fields.Char(string='Département')
    job = fields.Many2one('hr.job', string='Job Position')
    external_job = fields.Char(string='Job Position')
    partner_id = fields.Many2one('res.partner', string='Partner')
    available_partner_ids = fields.Many2many('res.partner', compute='_compute_available_partner_ids',
                                             string='Available Partners')
    employee_id = fields.Many2one('hr.employee', string='Partner')
    meeting_planification_id = fields.Many2one('dw.planification.meeting', string='Meeting')
    meeting_id = fields.Many2one('dw.meeting', string='Meeting')
    role_id = fields.Many2one('dw.participant.role', string='Rôles')
    attachments = fields.Binary(string='Attachments')
    attachments_2 = fields.Binary(string='Attachments 2')
    attachments_3 = fields.Binary(string='Attachments 3')
    attachments_4 = fields.Binary(string='Attachments 4')
    is_attachments_2_visible = fields.Boolean(store=True, readonly=True)
    is_attachments_3_visible = fields.Boolean(store=True, readonly=True)
    is_attachments_4_visible = fields.Boolean(store=True, readonly=True)

    access_token = fields.Char(string='Access Token', copy=False, readonly=True)
    session_id = fields.Many2one('dw.meeting.session', string='Meeting Session')
    invitation_status = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined')
    ], string='Invitation Status', default='pending')
    is_host = fields.Boolean(string="Host", compute='_compute_is_host', store=True, readonly=True)
    is_pv = fields.Boolean(string="Rédacteur PV", store=True, readonly=False)
    user_id = fields.Many2one('res.users', string='User', compute='_compute_user_id', store=True, readonly=True)
    attendance_status = fields.Selection([
        ('default', 'Awaiting'),
        ('late', 'Late'),
        ('present', 'Present'),
        ('absent', 'absent'),
        ('excused', 'Excused'),
    ], string='Attendance', default='default')

    def set_attachment_2_visible(self):
        self.ensure_one()
        self.is_attachments_2_visible = True

    def set_attachment_3_visible(self):
        self.ensure_one()
        self.is_attachments_3_visible = True

    def set_attachment_4_visible(self):
        self.ensure_one()
        self.is_attachments_4_visible = True

    def set_attachment_2_invisible(self):
        self.ensure_one()
        self.is_attachments_2_visible = False
        self.attachments_2 = False

    def set_attachment_3_invisible(self):
        self.ensure_one()
        self.is_attachments_3_visible = False
        self.attachments_3 = False

    def set_attachment_4_invisible(self):
        self.ensure_one()
        self.is_attachments_4_visible = False
        self.attachments_4 = False



    @api.depends('is_external')
    def _compute_available_partner_ids(self):
        """Compute partners that are not linked to any employee"""
        for rec in self:
            if rec.is_external:
                # Get all partner IDs that ARE linked to employees
                employees = self.env['hr.employee'].search([
                    ('user_id', '!=', False),
                    ('user_id.partner_id', '!=', False)
                ])
                excluded_partner_ids = employees.mapped('user_id.partner_id.id')

                # Get ALL partners EXCEPT those linked to employees
                # This automatically includes:
                # - Partners without user_id
                # - Partners with user_id but no employee
                available_partners = self.env['res.partner'].search([
                    ('id', 'not in', excluded_partner_ids)
                ])
                rec.available_partner_ids = available_partners
            else:
                rec.available_partner_ids = self.env['res.partner'].search([])

    @api.depends('role_id')
    def _compute_is_host(self):
        for rec in self:
            rec.is_host = rec.role_id.name == "host"

    @api.depends('employee_id', 'partner_id')
    def _compute_user_id(self):
        for rec in self:
            if rec.employee_id and rec.employee_id.user_id:
                rec.user_id = rec.employee_id.user_id
            elif rec.partner_id and rec.partner_id.user_ids:
                # partners can have multiple users; we take the first one
                rec.user_id = rec.partner_id.user_ids[0]
            else:
                rec.user_id = False

    def _generate_access_token(self):
        """Generate a secure access token for the participant"""
        for record in self:
            if not record.access_token:
                # Create a unique token based on participant ID and secret
                secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
                token_string = f"{record.id}-{record.meeting_planification_id.id}-{secret}"
                record.access_token = hashlib.sha256(token_string.encode()).hexdigest()
        return True

    # TODO: this constraint is triggered once the whole record is being created, need to find a way to trigger it before
    @api.constrains('employee_id', 'partner_id', 'meeting_planification_id')
    def _check_unique_participant(self):
        for record in self:
            if record.meeting_planification_id:
                if record.employee_id:
                    duplicate = self.search([
                        ('meeting_planification_id', '=', record.meeting_planification_id.id),
                        ('employee_id', '=', record.employee_id.id),
                        ('id', '!=', record.id)
                    ])
                    if duplicate:
                        raise ValidationError('This employee is already a participant in this meeting!')

                if record.partner_id:
                    duplicate = self.search([
                        ('meeting_planification_id', '=', record.meeting_planification_id.id),
                        ('partner_id', '=', record.partner_id.id),
                        ('id', '!=', record.id)
                    ])
                    if duplicate:
                        raise ValidationError('This partner is already a participant in this meeting!')

    @api.onchange('is_external')
    def _onchange_is_external(self):
        for rec in self:
            rec.name = ""
            rec.department = {}
            rec.job = {}
            rec.employee_id = {}
            rec.partner_id = {}

    @api.onchange('partner_id', 'employee_id')
    @api.depends('partner_id', 'employee_id')
    def _compute_name(self):
        for rec in self:
            if rec.employee_id:
                rec.name = rec.employee_id.name
                rec.department = rec.employee_id.department_id
                rec.job = rec.employee_id.job_id
            elif rec.partner_id:
                rec.name = rec.partner_id.name
            else:
                rec.name = False

    @api.constrains('role_id', 'is_pv', 'user_id')
    def _check_user_required_for_roles(self):
        for record in self:
            if not record.user_id:
                if record.role_id and record.role_id.name == 'host':
                    raise ValidationError('Cannot be host without user account')
                if record.is_pv:
                    raise ValidationError('Cannot be PV writer without user account')
