from smartdz import models, fields, api
from smartdz.exceptions import ValidationError


class DwActions(models.Model):
    _name = 'dw.actions'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Actions'

    name = fields.Char(string='Name', required=True, tracking=True)
    assignee = fields.Many2one('res.users', string='Assigned to', tracking=True)
    requirements = fields.Many2many('dw.requirements', string='Requirements')
    task_ids = fields.One2many('dw.actions', 'parent_id', string='Sub-tasks')
    dead_line = fields.Date(string='Due Date', tracking=True)
    meeting_id = fields.Many2one('dw.meeting', string='Meeting', ondelete='cascade')
    session_id = fields.Many2one('dw.meeting.session', string='Meeting Session', ondelete='cascade')
    parent_id = fields.Many2one('dw.actions', string='Parent Action')

    # Add description for AI context
    description = fields.Text(string='Description')

    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ], string='Priority', default='medium', tracking=True)

    status = fields.Selection([
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('done', 'Done')
    ], string='Status', default='todo', tracking=True)

    # Add completion tracking
    completed_date = fields.Datetime(string='Completed Date', readonly=True)

    @api.model
    def create(self, vals):
        """Auto-link to meeting if session is provided"""
        if vals.get('session_id') and not vals.get('meeting_id'):
            session = self.env['dw.meeting.session'].browse(vals['session_id'])
            if session.meeting_id:
                vals['meeting_id'] = session.meeting_id.id
        return super().create(vals)

    def write(self, vals):
        """Track completion date"""
        if vals.get('status') == 'done' and self.status != 'done':
            vals['completed_date'] = fields.Datetime.now()
        return super().write(vals)