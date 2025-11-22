from smartdz import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    jitsi_domain = fields.Char(
        string='Jitsi Domain',
        config_parameter='jitsi.domain',
        default='8x8.vc',
        help='Your Jitsi server domain (8x8.vc for JaaS)'
    )

    jitsi_app_id = fields.Char(
        string='JaaS App ID',
        config_parameter='jitsi.app_id',
        help='Your JaaS AppID from 8x8 dashboard (e.g., vpaas-magic-cookie-xxx)'
    )

    jitsi_kid = fields.Char(
        string='JaaS Key ID (kid)',
        config_parameter='jitsi.kid',
        help='Format: {AppID}/{key_id} - Get from 8x8 API Keys page'
    )

    jitsi_private_key = fields.Char(
        string='Private Key (PEM)',
        config_parameter='jitsi.private_key',
        help='Your RSA private key in PEM format (keep this secret!)'
    )

    jitsi_public_key = fields.Char(
        string='Public Key (PEM)',
        config_parameter='jitsi.public_key',
        help='Your RSA public key (upload this to 8x8 dashboard)'
    )


    ai_provider = fields.Selection([
        ('gemini', 'Google Gemini (FREE - Recommended)'),
        ('openrouter', 'OpenRouter (FREE - Multiple Models)'),
        ('groq', 'Groq (FREE - Fast)'),
        ('huggingface', 'Hugging Face (FREE)'),
    ], string='AI Provider',
        default='gemini',
        config_parameter='meeting_management_base.ai_provider',
        help='Choose which AI provider to use for generating meeting summaries')

    gemini_api_key = fields.Char(
        string='Google Gemini API Key',
        config_parameter='meeting_management_base.gemini_api_key',
        help='Get free at: https://aistudio.google.com/app/apikey (No credit card required)'
    )

    openrouter_api_key = fields.Char(
        string='OpenRouter API Key',
        config_parameter='meeting_management_base.openrouter_api_key',
        help='Get free at: https://openrouter.ai/keys (Access 50+ models)'
    )

    groq_api_key = fields.Char(
        string='Groq API Key',
        config_parameter='meeting_management_base.groq_api_key',
        help='Get free at: https://console.groq.com/keys (Ultra-fast inference)'
    )

    huggingface_api_key = fields.Char(
        string='Hugging Face API Key',
        config_parameter='meeting_management_base.huggingface_api_key',
        help='Get free at: https://huggingface.co/settings/tokens'
    )

    @api.model
    def get_values(self):
        """Get the current settings values"""
        res = super(ResConfigSettings, self).get_values()

        ICP = self.env['ir.config_parameter'].sudo()

        # Get all our parameters
        private_key = ICP.get_param('jitsi.private_key', '')

        _logger.info("📥 Loading Jitsi configuration:")
        _logger.info("   - Domain: %s", ICP.get_param('jitsi.domain', '8x8.vc'))
        _logger.info("   - App ID: %s", ICP.get_param('jitsi.app_id', ''))
        _logger.info("   - Key ID: %s", ICP.get_param('jitsi.kid', ''))
        _logger.info("   - Private Key Length: %s", len(private_key))
        _logger.info("   - Private Key Preview: %s", private_key[:50] + "..." if private_key else "None")

        res.update({
            'jitsi_domain': ICP.get_param('jitsi.domain', '8x8.vc'),
            'jitsi_app_id': ICP.get_param('jitsi.app_id', ''),
            'jitsi_kid': ICP.get_param('jitsi.kid', ''),
            'jitsi_private_key': private_key,
        })

        return res

    def set_values(self):
        """Set the settings values"""
        super(ResConfigSettings, self).set_values()

        ICP = self.env['ir.config_parameter'].sudo()

        _logger.info("💾 Saving Jitsi configuration:")
        _logger.info("   - Domain: %s", self.jitsi_domain)
        _logger.info("   - App ID: %s", self.jitsi_app_id)
        _logger.info("   - Key ID: %s", self.jitsi_kid)
        _logger.info("   - Private Key Length: %s", len(self.jitsi_private_key or ''))
        _logger.info("   - Public Key Length: %s", len(self.jitsi_public_key or ''))

        # Set all our parameters
        ICP.set_param('jitsi.domain', self.jitsi_domain or '8x8.vc')
        ICP.set_param('jitsi.app_id', self.jitsi_app_id or '')
        ICP.set_param('jitsi.kid', self.jitsi_kid or '')
        ICP.set_param('jitsi.private_key', self.jitsi_private_key or '')

    # def action_generate_keys(self):
    #     """Generate RSA key pair for JaaS - ENHANCED VERSION"""
    #     _logger.info("🔑 Generating new RSA key pair...")
    #
    #     try:
    #         from cryptography.hazmat.primitives.asymmetric import rsa
    #         from cryptography.hazmat.primitives import serialization
    #         from cryptography.hazmat.backends import default_backend
    #
    #         # Generate private key
    #         _logger.info("   - Generating 4096-bit RSA private key...")
    #         private_key = rsa.generate_private_key(
    #             public_exponent=65537,
    #             key_size=4096,
    #             backend=default_backend()
    #         )
    #
    #         # Serialize private key to PEM (PKCS8 format)
    #         _logger.info("   - Serializing private key to PEM...")
    #         private_pem = private_key.private_bytes(
    #             encoding=serialization.Encoding.PEM,
    #             format=serialization.PrivateFormat.PKCS8,  # Use PKCS8 for better compatibility
    #             encryption_algorithm=serialization.NoEncryption()
    #         ).decode('utf-8')
    #
    #         # Serialize public key to PEM
    #         _logger.info("   - Serializing public key to PEM...")
    #         public_key = private_key.public_key()
    #         public_pem = public_key.public_bytes(
    #             encoding=serialization.Encoding.PEM,
    #             format=serialization.PublicFormat.SubjectPublicKeyInfo
    #         ).decode('utf-8')
    #
    #         # Update the current record
    #         _logger.info("   - Updating configuration with new keys...")
    #         self.write({
    #             'jitsi_private_key': private_pem,
    #             'jitsi_public_key': public_pem,
    #         })
    #
    #         _logger.info("✅ Key generation completed successfully!")
    #         _logger.info("   - Private Key Length: %s", len(private_pem))
    #         _logger.info("   - Public Key Length: %s", len(public_pem))
    #         _logger.info("   - Private Key Format: %s", private_pem.split('\n')[0])
    #         _logger.info("   - Public Key Format: %s", public_pem.split('\n')[0])
    #
    #         # Return reload action to refresh the view
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'reload',
    #         }
    #
    #     except ImportError as e:
    #         _logger.error("❌ Cryptography library not installed: %s", str(e))
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Error',
    #                 'message': 'cryptography library not installed. Run: pip install cryptography',
    #                 'type': 'danger',
    #                 'sticky': True,
    #             }
    #         }
    #     except Exception as e:
    #         _logger.error("❌ Failed to generate keys: %s", str(e))
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Error',
    #                 'message': f'Failed to generate keys: {str(e)}',
    #                 'type': 'danger',
    #                 'sticky': True,
    #             }
    #         }



    @api.onchange('ai_provider')
    def _onchange_ai_provider(self):
        """Show helper message when provider changes"""
        provider_urls = {
            'gemini': 'https://aistudio.google.com/app/apikey',
            'openrouter': 'https://openrouter.ai/keys',
            'groq': 'https://console.groq.com/keys',
            'huggingface': 'https://huggingface.co/settings/tokens',
        }

        if self.ai_provider:
            return {
                'warning': {
                    'title': 'Get Your Free API Key',
                    'message': f'Get your free {self.ai_provider.upper()} API key at:\n{provider_urls.get(self.ai_provider, "")}'
                }
            }