from smartdz import models, fields, api

class DwProject(models.Model):
    _name = "dw.project"
    _description = "Project"
    _order = "start_date desc, id desc"

    name = fields.Char(string="Project Name", required=True)
    description = fields.Text(string="Description")

    manager_ids = fields.Many2many(
        'res.users',
        'dw_project_manager_rel',
        'project_id',
        'user_id',
        string="Project Managers",
        help="Users responsible for supervising this project."
    )

    member_ids = fields.Many2many(
        'res.users',
        'dw_project_member_rel',
        'project_id',
        'user_id',
        string="Project Members",
        help="All users involved in this project."
    )

    users_allowed_to_see = fields.Many2many(
        'res.users',
        compute="_compute_users_allowed_to_see",
        string="Users Allowed to See",
        store=True,
    )

    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")

    status = fields.Selection([
        ('planning', "Planning"),
        ('ongoing', "Ongoing"),
        ('on_hold', "On Hold"),
        ('done', "Done"),
        ('cancelled', "Cancelled"),
    ], string="Status", default='planning', tracking=True, group_expand='_expand_states')

    action_ids = fields.One2many(
        'dw.actions',
        'project_id',
        string="Actions"
    )

    meeting_ids = fields.One2many(
        'dw.meeting',
        'project_id',
        string="Meetings"
    )

    meeting_planification_ids = fields.One2many(
        'dw.planification.meeting',
        'project_id',
        string="Meetings"
    )

    progress = fields.Float(
        string="Progress (%)",
        compute="_compute_progress",
        store=True,
    )

    color = fields.Integer("Color Index")

    _sql_constraints = [
        ('unique_project_name', 'unique(name)', 'A project with this name already exists. Please choose another name.')
    ]

    @api.depends('manager_ids', 'member_ids')
    def _compute_users_allowed_to_see(self):
        for project in self:
            project.users_allowed_to_see = project.manager_ids | project.member_ids

    @api.model
    def _expand_states(self, states, domain):
        return [key for key, val in type(self).status.selection]

    def action_set_ongoing(self):
        self.write({'status': 'ongoing'})

    def action_set_on_hold(self):
        self.write({'status': 'on_hold'})

    def action_set_done(self):
        self.write({'status': 'done'})

    def action_set_cancelled(self):
        self.write({'status': 'cancelled'})

    def action_view_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Project Actions',
            'res_model': 'dw.actions',
            'view_mode': 'kanban,form',
            'views': [(self.env.ref('meeting_management_base.dw_actions_view_kanban').id, 'kanban')],
            'domain': [('id', 'in', self.action_ids.ids)],
            'context': {'default_project_id': self.id},
        }

    @api.depends('action_ids.status')
    def _compute_progress(self):
        for project in self:
            actions = project.action_ids
            if not actions:
                project.progress = 0
            else:
                done_actions = actions.filtered(lambda t: t.status == 'done')
                project.progress = (len(done_actions) / len(actions)) * 100

class DwProjectStage(models.Model):
    _name = "dw.project.stage"
    _description = "Project Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=1)
