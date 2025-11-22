import jwt
import time
import logging
from smartdz import http
from smartdz.http import request

_logger = logging.getLogger(__name__)


class JitsiJaaSController(http.Controller):
    TOKEN_EXPIRATION = 3600 * 24

    def _get_jitsi_config(self):
        """Get Jitsi configuration from system parameters"""
        ICP = request.env['ir.config_parameter'].sudo()

        return {
            'app_id': ICP.get_param('jitsi.app_id', ''),
            'kid': ICP.get_param('jitsi.kid', ''),
            'private_key': ICP.get_param('jitsi.private_key', ''),
            'domain': ICP.get_param('jitsi.domain', '8x8.vc'),
        }

    def _fix_pem_format(self, pem_key):
        """Fix PEM format by ensuring proper line breaks"""
        try:
            pem_key = pem_key.strip()

            if '-----BEGIN RSA PRIVATE KEY-----' in pem_key:
                header = '-----BEGIN RSA PRIVATE KEY-----'
                footer = '-----END RSA PRIVATE KEY-----'
            elif '-----BEGIN PRIVATE KEY-----' in pem_key:
                header = '-----BEGIN PRIVATE KEY-----'
                footer = '-----END PRIVATE KEY-----'
            else:
                return None

            base64_content = pem_key.replace(header, '').replace(footer, '').replace('\n', '').replace('\r',
                                                                                                       '').replace(' ',
                                                                                                                   '')
            lines = [base64_content[i:i + 64] for i in range(0, len(base64_content), 64)]
            proper_pem = f"{header}\n" + '\n'.join(lines) + f"\n{footer}"

            return proper_pem
        except Exception as e:
            _logger.error("Failed to fix PEM format: %s", str(e))
            return None

    def _convert_pkcs8_to_pkcs1(self, pkcs8_key):
        """Convert PKCS#8 private key to PKCS#1 format"""
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend

            pkcs8_key = self._fix_pem_format(pkcs8_key)
            if not pkcs8_key:
                return None

            private_key = serialization.load_pem_private_key(
                pkcs8_key.encode('utf-8'),
                password=None,
                backend=default_backend()
            )

            pkcs1_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            return pkcs1_pem
        except Exception as e:
            _logger.error("Failed to convert key format: %s", str(e))
            return None

    def _validate_and_prepare_private_key(self, private_key):
        """Validate and prepare private key for JWT signing"""
        if not private_key:
            return None

        key = private_key.strip()

        if key.count('\n') < 3:
            key = self._fix_pem_format(key)
            if not key:
                return None

        if '-----BEGIN PRIVATE KEY-----' in key:
            converted_key = self._convert_pkcs8_to_pkcs1(key)
            if converted_key:
                return converted_key
            return None
        elif '-----BEGIN RSA PRIVATE KEY-----' in key:
            if key.count('\n') < 3:
                key = self._fix_pem_format(key)
            return key
        else:
            return None

    def _generate_jaas_jwt(self, user, room_name, is_moderator=False, meeting=None):
        """Generate a JaaS JWT token with RS256 algorithm"""
        config = self._get_jitsi_config()

        if not config['private_key']:
            _logger.error("JaaS private key not configured")
            return None

        private_key = self._validate_and_prepare_private_key(config['private_key'])
        if not private_key:
            _logger.error("Private key validation failed")
            return None

        now = int(time.time())

        if '/' in room_name:
            _, pure_room_name = room_name.rsplit('/', 1)
        else:
            pure_room_name = room_name

        pure_room_name = pure_room_name.lower()
        jwt_room_name = f"{config['app_id']}/{pure_room_name}"

        payload = {
            "aud": "jitsi",
            "iss": "chat",
            "sub": config['app_id'],
            "exp": now + self.TOKEN_EXPIRATION,
            "nbf": now - 10,
            "room": "*",
            "context": {
                "user": {
                    "id": str(user.id),
                    "name": user.name,
                    "email": user.email or f"user{user.id}@odoo.local",
                    "avatar": f"/web/image/res.users/{user.id}/image_128" if user.image_128 else "",
                    "moderator": "true" if is_moderator else "false",
                },
                "features": {
                    "livestreaming": "true" if is_moderator else "false",
                    "recording": "true" if is_moderator else "false",
                    "moderation": "true" if is_moderator else "false",
                }
            }
        }

        if meeting:
            payload["context"]["meeting"] = {
                "id": meeting.id,
                "name": meeting.name,
            }

        try:
            token = jwt.encode(
                payload,
                private_key,
                algorithm='RS256',
                headers={'kid': config['kid']}
            )

            _logger.info("JWT generated successfully for user %s", user.name)
            return token
        except Exception as e:
            _logger.error("Failed to generate JaaS JWT: %s", str(e))
            return None

    @http.route('/meeting/jitsi/token', type='json', auth='user', methods=['POST'], csrf=False)
    def generate_token(self, meeting_id, session_id=None):
        """Generate a JaaS JWT token for a meeting session"""
        try:
            # Get the meeting
            meeting = request.env['dw.meeting'].browse(meeting_id)

            if not meeting.exists():
                return {'error': 'Meeting not found', 'success': False}

            user = request.env.user

            # Check if user is moderator (host)
            participant = request.env['dw.participant'].search([
                ('meeting_id', '=', meeting_id),
                '|',
                ('employee_id.user_id', '=', user.id),
                ('partner_id.user_ids', 'in', user.id)
            ], limit=1)

            is_moderator = participant and participant.is_host

            # Generate room name
            config = self._get_jitsi_config()
            room_name = f"odoo-meeting-{meeting.id}".lower()
            full_room_name = f"{config['app_id']}/{room_name}"

            # Generate JWT token
            token = self._generate_jaas_jwt(
                user=user,
                room_name=full_room_name,
                is_moderator=is_moderator,
                meeting=meeting
            )

            if not token:
                return {'error': 'Failed to generate authentication token', 'success': False}

            return {
                'success': True,
                'token': token,
                'domain': config['domain'],
                'room_name': full_room_name,
                'user_name': user.name,
                'user_email': user.email or f"user{user.id}@odoo.local",
                'is_moderator': is_moderator,
                'app_id': config['app_id'],
            }
        except Exception as e:
            _logger.error("Failed to generate JaaS token: %s", str(e))
            return {'error': str(e), 'success': False}

    @http.route('/meeting/join', type='http', auth='user', website=True)
    def join_meeting_page(self, meeting_id=None, **kwargs):
        """
        Serve a clean join page for a meeting.
        Usage: /meeting/join?meeting_id=8
        The page will fetch the JWT token automatically via the existing /meeting/jitsi/token endpoint.
        """
        if not meeting_id:
            return "<h3>Error: Missing meeting_id parameter.</h3>"

        # Optional: verify meeting exists
        meeting = request.env['dw.meeting'].sudo().browse(meeting_id)
        if not meeting.exists():
            return f"<h3>Error: Meeting with ID {meeting_id} not found.</h3>"

        # Render the static join.html template
        # The template should be copied to: static/src/templates/jitsi/join.html
        return request.render('meeting_management_base.jitsi_join_template', {
            'meeting_id': meeting_id,
        })