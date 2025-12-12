from smartdz import models, fields, api

class DwRequirements(models.Model):
    _name = 'dw.requirements'
    _description = 'Requirements'

    name = fields.Char(string='Name')
    user_id = fields.Many2one(
        'res.users',
    )
    task_id = fields.Many2one(
        'dw.actions',
        string='Task',
    )
    description = fields.Text(string='Description', required=True)
    seq = fields.Integer(string='Sequence')
    is_done = fields.Boolean(string='Done')

    def _update_task_status(self):
        for requirement in self:
            task = requirement.task_id
            if not task:
                continue

            all_reqs = task.requirements
            done_reqs = all_reqs.filtered(lambda r: r.is_done)

            if done_reqs and task.status == 'todo':
                task.status = 'in_progress'

            if all_reqs and len(done_reqs) == len(all_reqs):
                if task.status not in ('done', 'blocked'):
                    task.status = 'done'

    @api.onchange('is_done')
    def _onchange_is_done(self):
        self._update_task_status()

    # Backend logic (create)
    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._update_task_status()
        return record

    # Backend logic (write)
    def write(self, vals):
        res = super().write(vals)
        self._update_task_status()
        return res
