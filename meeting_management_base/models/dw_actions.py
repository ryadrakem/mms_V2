from smartdz import models, fields, api, _
from smartdz.exceptions import ValidationError
from datetime import date


class DwActions(models.Model):
    _name = 'dw.actions'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Actions'
    _order = 'priority desc, dead_line asc, id desc'

    name = fields.Char(string='Name', required=True, tracking=True)
    assignee = fields.Many2one('res.users', string='Assigned to', tracking=True, default=lambda self: self.env.user)
    requirements = fields.Many2many('dw.requirements', string='Requirements')
    task_ids = fields.One2many('dw.actions', 'parent_id', string='Sub-tasks')
    dead_line = fields.Date(string='Due Date', tracking=True)
    meeting_id = fields.Many2one('dw.meeting', string='Meeting', ondelete='cascade')
    session_id = fields.Many2one('dw.meeting.session', string='Meeting Session', ondelete='cascade')
    parent_id = fields.Many2one('dw.actions', string='Parent Action')
    description = fields.Text(string='Description')

    priority = fields.Selection([
        ('0', 'Normal'), ('1', 'Low'), ('2', 'High'), ('3', 'Urgent')
    ], string='Priority', default='0', tracking=True)

    status = fields.Selection([
        ('todo', 'To Do'), ('in_progress', 'In Progress'),
        ('done', 'Done'), ('blocked', 'Blocked')
    ], string='Status', default='todo', tracking=True, group_expand='_expand_states')

    color = fields.Integer(string='Color Index')
    completed_date = fields.Datetime(string='Completed Date', readonly=True)
    completed_by = fields.Many2one('res.users', string='Completed By', readonly=True)

    is_overdue = fields.Boolean(compute='_compute_deadline_status', store=True)
    days_until_deadline = fields.Integer(compute='_compute_deadline_status', store=True)
    deadline_status = fields.Selection([
        ('overdue', 'Overdue'), ('today', 'Due Today'),
        ('upcoming', 'Upcoming'), ('future', 'Future'),
        ('no_deadline', 'No Deadline')
    ], compute='_compute_deadline_status', store=True)

    subtask_count = fields.Integer(compute='_compute_subtask_progress', store=True)
    subtask_done_count = fields.Integer(compute='_compute_subtask_progress', store=True)
    subtask_progress = fields.Float(compute='_compute_subtask_progress', store=True)

    meeting_name = fields.Char(related='meeting_id.name', string='Meeting Name', readonly=True)
    is_my_action = fields.Boolean(compute='_compute_is_my_action', search='_search_is_my_action')


    @api.model
    def _expand_states(self, states, domain):
        return [key for key, val in type(self).status.selection]

    @api.depends('assignee')
    def _compute_is_my_action(self):
        current_user = self.env.user
        for action in self:
            action.is_my_action = action.assignee.id == current_user.id

    def _search_is_my_action(self, operator, value):
        current_user = self.env.user
        if operator == '=' and value:
            return [('assignee', '=', current_user.id)]
        elif operator == '=' and not value:
            return [('assignee', '!=', current_user.id)]
        return []

    @api.depends('dead_line')
    def _compute_deadline_status(self):
        today = date.today()
        for action in self:
            if not action.dead_line:
                action.is_overdue = False
                action.days_until_deadline = 0
                action.deadline_status = 'no_deadline'
            else:
                delta = (action.dead_line - today).days
                action.days_until_deadline = delta
                if delta < 0:
                    action.is_overdue = True
                    action.deadline_status = 'overdue'
                elif delta == 0:
                    action.is_overdue = False
                    action.deadline_status = 'today'
                elif delta <= 3:
                    action.is_overdue = False
                    action.deadline_status = 'upcoming'
                else:
                    action.is_overdue = False
                    action.deadline_status = 'future'

    @api.depends('task_ids', 'task_ids.status')
    def _compute_subtask_progress(self):
        for action in self:
            subtasks = action.task_ids
            action.subtask_count = len(subtasks)
            if subtasks:
                done_count = len(subtasks.filtered(lambda t: t.status == 'done'))
                action.subtask_done_count = done_count
                action.subtask_progress = (done_count / len(subtasks)) * 100
            else:
                action.subtask_done_count = 0
                action.subtask_progress = 0

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if not self._check_recursion():
            raise ValidationError('You cannot create recursive sub-tasks.')


    @api.model
    def create(self, vals):
        # Auto-link meeting
        if vals.get('session_id') and not vals.get('meeting_id'):
            session = self.env['dw.meeting.session'].browse(vals['session_id'])
            if session.meeting_id:
                vals['meeting_id'] = session.meeting_id.id

        record = super().create(vals)

        # Notify Assignee (Use OdooBot to force notification)
        if record.assignee:
            record._notify_new_assignee(record.assignee)

        return record

    def write(self, vals):
        assignee_changed = 'assignee' in vals

        # Completion tracking
        if vals.get('status') == 'done' and self.status != 'done':
            vals['completed_date'] = fields.Datetime.now()
            vals['completed_by'] = self.env.user.id
        elif vals.get('status') and vals['status'] != 'done':
            vals['completed_date'] = False
            vals['completed_by'] = False

        res = super().write(vals)

        for record in self:
            # Notify new assignee
            if assignee_changed and record.assignee:
                record._notify_new_assignee(record.assignee)

            # Notify if Blocked
            if vals.get('status') == 'blocked' and record.assignee:
                odoobot = self.env.ref('base.partner_root')
                record.message_post(
                    body=f"⚠️ <b>Action Blocked!</b> <br/>Please check the requirements.",
                    subject="Action Blocked",
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                    author_id=odoobot.id,
                    partner_ids=[record.assignee.partner_id.id]
                )

            # Auto-complete Parent
            if vals.get('status') == 'done' and record.parent_id:
                record._check_and_complete_parent()

        return res

    def _notify_new_assignee(self, user):
        """ Send notification from OdooBot to ensure it hits the Inbox """
        self.ensure_one()
        self.message_subscribe(partner_ids=[user.partner_id.id])

        odoobot = self.env.ref('base.partner_root')
        self.message_post(
            body=f"👋 You have been assigned to: <b>{self.name}</b>",
            subject="New Assignment",
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=odoobot.id,
            partner_ids=[user.partner_id.id]
        )

    def _check_and_complete_parent(self):
        parent = self.parent_id
        if parent:
            siblings = parent.task_ids
            if not any(t.status != 'done' for t in siblings):
                if parent.status != 'done':
                    parent.write({'status': 'done'})
                    parent.message_post(
                        body="✅ <b>Auto-Completed:</b> All sub-tasks are finished.",
                        message_type='notification',
                        subtype_xmlid='mail.mt_note'
                    )

    def action_set_todo(self):
        self.write({'status': 'todo'})

    def action_set_in_progress(self):
        self.write({'status': 'in_progress'})

    def action_set_done(self):
        self.write({'status': 'done'})

    def action_set_blocked(self):
        self.write({'status': 'blocked'})

    def action_open_meeting(self):
        self.ensure_one()
        if not self.meeting_id:
            raise ValidationError("No meeting associated with this action.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Meeting',
            'res_model': 'dw.meeting',
            'res_id': self.meeting_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
