from smartdz import models, fields

class DwMeetingPostponeWizard(models.TransientModel):
    _name = 'dw.meeting.postpone.wizard'
    _description = 'Postpone Meeting Wizard'

    meeting_id = fields.Many2one('dw.planification.meeting', required=True, readonly=True)
    new_planned_start_datetime = fields.Datetime(
        string='New Start Date & Time',
        required=True
    )

    def _delete_reservations(self):
        """Delete all reservations when meeting is cancelled or done"""
        self.ensure_one()
        reservations = self.env['dw.reservations'].search([
            ('meeting_plannification_id', '=', self.meeting_id.id)
        ])
        if reservations:
            reservations.unlink()
            _logger.info(f"Deleted {len(reservations)} reservations for meeting {self.meeting_id.name}")

    def action_confirm_postpone(self):
        self.ensure_one()
        meeting = self.meeting_id
        self.meeting_id.write({'times_postponed': self.meeting_id.times_postponed + 1})
        new_meeting = meeting.copy({
            'name': self.meeting_id.name + " postponed " + str(self.meeting_id.times_postponed),
            'planned_start_datetime': self.new_planned_start_datetime,
            'state': 'planned',
            'times_postponed': self.meeting_id.times_postponed,
        })
        self.meeting_id.write({'state': 'cancelled'})

        self._delete_reservations()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dw.planification.meeting',
            'res_id': new_meeting.id,
            'view_mode': 'form',
            'target': 'current',
        }
