from smartdz import http
from smartdz.http import request
import logging

_logger = logging.getLogger(__name__)


class MeetingResponseController(http.Controller):

    @http.route('/meeting/respond/<int:meeting_id>/<int:participant_id>/<string:token>/<string:response>',
                type='http',
                auth='public',
                methods=['GET'],
                website=True,
                csrf=False)
    def meeting_response_secure(self, meeting_id, participant_id, token, response, **kwargs):
        """
        Secure meeting invitation response handler with token validation

        Args:
            meeting_id: ID of the dw.planification.meeting record
            participant_id: ID of the dw.participant record
            token: Access token for authentication
            response: 'accept' or 'decline'
        """
        try:
            # Validate inputs
            if response not in ['accept', 'decline']:
                return request.render('meeting_management_base.meeting_response_error', {
                    'message': 'Invalid response type.'
                })

            # Get the participant
            participant = request.env['dw.participant'].sudo().browse(participant_id)

            if not participant.exists():
                return request.render('meeting_management_base.meeting_response_error', {
                    'message': 'Participant not found.'
                })

            # Verify the token
            if not participant.access_token or participant.access_token != token:
                _logger.warning(f"Invalid token attempt for participant {participant_id}")
                return request.render('meeting_management_base.meeting_response_error', {
                    'message': 'Invalid or expired link.'
                })

            # Verify meeting matches
            if participant.meeting_planification_id.id != meeting_id:
                return request.render('meeting_management_base.meeting_response_error', {
                    'message': 'Meeting and participant mismatch.'
                })

            meeting = participant.meeting_planification_id

            # Check if already responded
            if participant.invitation_status != 'pending':
                return request.render('meeting_management_base.meeting_response_already', {
                    'meeting': meeting,
                    'participant': participant,
                    'previous_status': participant.invitation_status
                })

            # Update invitation status
            new_status = 'accepted' if response == 'accept' else 'declined'
            participant.sudo().write({
                'invitation_status': new_status
            })

            # Log the response
            meeting.message_post(
                body=f"Participant {participant.name} has {new_status} the meeting invitation.",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

            _logger.info(f"Meeting {meeting_id} - Participant {participant.name} {new_status} invitation")

            # Render success page
            return request.render('meeting_management_base.meeting_response_success', {
                'meeting': meeting,
                'participant': participant,
                'response': response,
                'status': new_status
            })

        except Exception as e:
            _logger.error(f"Error processing meeting response: {str(e)}", exc_info=True)
            return request.render('meeting_management_base.meeting_response_error', {
                'message': 'An error occurred while processing your response.'
            })

    @http.route('/meeting/respond/<int:meeting_id>/<string:response>',
                type='http',
                auth='user',
                methods=['GET'],
                website=True)
    def meeting_response_simple(self, meeting_id, response, **kwargs):
        """
        Simple meeting invitation response handler (requires login)
        This is your original implementation for logged-in users

        Args:
            meeting_id: ID of the dw.planification.meeting record
            response: 'accept' or 'decline'
        """
        try:
            # Validate inputs
            if response not in ['accept', 'decline']:
                return request.render('meeting_management_base.meeting_response_error', {
                    'message': 'Invalid response type.'
                })

            # Get the meeting
            meeting = request.env['dw.planification.meeting'].sudo().browse(meeting_id)

            if not meeting.exists():
                return request.render('meeting_management_base.meeting_response_error', {
                    'message': 'Meeting not found.'
                })

            # Get the current user's partner
            partner = request.env.user.partner_id

            # Find the participant record for this user
            participant = request.env['dw.participant'].sudo().search([
                ('meeting_planification_id', '=', meeting_id),
                '|',
                ('partner_id', '=', partner.id),
                ('employee_id.user_id', '=', request.env.user.id)
            ], limit=1)

            if not participant:
                return request.render('meeting_management_base.meeting_response_error', {
                    'message': 'You are not a participant of this meeting.'
                })

            # Update invitation status
            new_status = 'accepted' if response == 'accept' else 'declined'
            participant.sudo().write({
                'invitation_status': new_status
            })

            # Log the response
            meeting.message_post(
                body=f"Participant {participant.name} has {new_status} the meeting invitation.",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

            _logger.info(f"Meeting {meeting_id} - Participant {participant.name} {new_status} invitation")

            # Render success page
            return request.render('meeting_management_base.meeting_response_success', {
                'meeting': meeting,
                'participant': participant,
                'response': response,
                'status': new_status
            })

        except Exception as e:
            _logger.error(f"Error processing meeting response: {str(e)}", exc_info=True)
            return request.render('meeting_management_base.meeting_response_error', {
                'message': 'An error occurred while processing your response.'
            })
