# -*- coding: utf-8 -*-
import json
import logging
import base64
import requests
import time
from smartdz import http  # ✅ CORRIGÉ
from smartdz.http import request  # ✅ CORRIGÉ
from smartdz.exceptions import ValidationError  # ✅ CORRIGÉ

_logger = logging.getLogger(__name__)


class VoiceToTextController(http.Controller):
    """
    Controller to handle voice recognition and convert speech to text
    for PV (Procès-Verbal) drafting during meetings
    """

    @http.route('/meeting/voice/transcribe', type='json', auth='user', methods=['POST'])
    def transcribe_audio(self, **kwargs):
        """
        Transcribe audio data to text using multiple providers
        """
        try:
            _logger.info("🎙️ Transcribe request received")

            # ✅ CORRECT: Les params viennent directement dans **kwargs
            audio_data = kwargs.get('audio_data')
            meeting_id = kwargs.get('meeting_id')
            format_audio = kwargs.get('format', 'webm')

            _logger.info("📋 Params: audio_size=%d, meeting_id=%s, format=%s",
                         len(audio_data) if audio_data else 0, meeting_id, format_audio)

            # Vérifier les paramètres
            if not audio_data:
                _logger.error("❌ No audio data provided")
                return {'success': False, 'error': 'No audio data provided'}

            if not meeting_id:
                _logger.error("❌ No meeting ID provided")
                return {'success': False, 'error': 'No meeting ID provided'}

            # Décoder le base64
            try:
                audio_bytes = base64.b64decode(audio_data)
                _logger.info("✅ Audio decoded: %d bytes", len(audio_bytes))
            except Exception as e:
                _logger.error("❌ Failed to decode audio: %s", e)
                return {'success': False, 'error': 'Invalid audio data'}

            # Validate meeting access
            meeting = request.env['dw.meeting'].sudo().browse(meeting_id)
            if not meeting.exists():
                _logger.error("❌ Meeting not found: %s", meeting_id)
                return {'success': False, 'error': 'Meeting not found'}

            _logger.info("✅ Meeting found: %s", meeting.name)

            # Get configured provider
            config = self._get_speech_config()
            _logger.info("📍 Speech provider: %s", config['provider'])

            # Try transcription with configured provider
            if config['provider'] == 'google_cloud':
                result = self._transcribe_with_google(audio_bytes, format_audio)
            elif config['provider'] == 'deepgram':
                result = self._transcribe_with_deepgram(audio_bytes, format_audio)
            elif config['provider'] == 'assembly':
                result = self._transcribe_with_assembly(audio_bytes, format_audio)
            else:
                _logger.error("❌ No speech provider configured")
                return {
                    'success': False,
                    'error': 'Please configure a speech-to-text provider in settings'
                }

            if result['success']:
                _logger.info("✅ Transcription successful for meeting %s: %s chars",
                             meeting_id, len(result.get('transcript', '')))
                return result
            else:
                _logger.error("❌ Transcription failed: %s", result.get('error'))
                return result

        except Exception as e:
            _logger.exception("❌ Transcription failed: %s", e)
            return {'success': False, 'error': str(e)}

    @http.route('/meeting/voice/enhance', type='json', auth='user', methods=['POST'])
    def enhance_transcript(self, **kwargs):
        """
        Use AI to improve/format the raw transcript
        """
        try:
            # ✅ CORRECT: Les params viennent directement dans **kwargs
            transcript = kwargs.get('transcript', '')
            meeting_id = kwargs.get('meeting_id')

            _logger.info("🤖 Enhancement request for meeting %s", meeting_id)

            meeting = request.env['dw.meeting'].sudo().browse(meeting_id)
            if not meeting.exists():
                return {'success': False, 'error': 'Meeting not found'}

            prompt = f"""Please improve and format this meeting transcript into a professional PV section.

Original Transcript:
{transcript}

Meeting: {meeting.name}
Date: {meeting.planned_start_datetime}

Please format it with proper punctuation, structure, and clarity while preserving all information.
Return only the formatted text without any preamble."""

            ai_result = self._call_ai_enhance(prompt)

            if ai_result['success']:
                return {
                    'success': True,
                    'enhanced_text': ai_result['text'],
                    'provider': ai_result.get('provider', 'AI Service')
                }
            else:
                # Return original if enhancement fails
                return {
                    'success': True,
                    'enhanced_text': transcript,
                    'provider': 'Original (Enhancement failed)'
                }

        except Exception as e:
            _logger.exception("❌ Enhancement failed: %s", e)
            return {'success': False, 'error': str(e)}

    def _get_speech_config(self):
        """Get speech-to-text configuration"""
        config_param = request.env['ir.config_parameter'].sudo()

        return {
            'provider': config_param.get_param('meeting_management_base.speech_provider', 'none'),
            'google_api_key': config_param.get_param('meeting_management_base.google_speech_key'),
            'deepgram_api_key': config_param.get_param('meeting_management_base.deepgram_key'),
            'assembly_api_key': config_param.get_param('meeting_management_base.assembly_key'),
        }

    def _transcribe_with_assembly(self, audio_bytes, format):
        """Transcribe using AssemblyAI"""
        try:
            config = self._get_speech_config()
            api_key = config['assembly_api_key']

            if not api_key:
                _logger.error("❌ AssemblyAI API key not configured")
                return {'success': False, 'error': 'AssemblyAI API key not configured'}

            _logger.info("🟣 Using AssemblyAI for transcription...")

            headers = {
                "Authorization": api_key,
                "Content-Type": f"audio/{format}"
            }

            # Upload audio file
            _logger.info("📤 Uploading audio to AssemblyAI...")
            response = requests.post(
                "https://api.assemblyai.com/v2/upload",
                headers={"Authorization": api_key},
                data=audio_bytes,
                timeout=60
            )

            if response.status_code >= 400:
                _logger.error("❌ Upload failed: %s", response.text[:200])
                return {'success': False, 'error': 'Failed to upload audio'}

            upload_url = response.json()['upload_url']
            _logger.info("✅ Audio uploaded: %s", upload_url)

            # Submit transcription request
            _logger.info("🔄 Requesting transcription...")
            transcription_data = {
                "audio_url": upload_url,
                "language_code": "fr"
            }

            response = requests.post(
                "https://api.assemblyai.com/v2/transcript",
                headers={"Authorization": api_key},
                json=transcription_data,
                timeout=60
            )

            if response.status_code >= 400:
                _logger.error("❌ Transcription request failed: %s", response.text[:200])
                return {'success': False, 'error': 'Transcription request failed'}

            transcript_id = response.json()['id']
            _logger.info("✅ Transcription ID: %s", transcript_id)

            # Poll for completion
            _logger.info("⏳ Waiting for transcription completion...")
            max_attempts = 300  # 5 minutes
            attempt = 0

            while attempt < max_attempts:
                response = requests.get(
                    f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                    headers={"Authorization": api_key},
                    timeout=10
                )

                if response.status_code >= 400:
                    _logger.error("❌ Failed to get transcript: %s", response.text[:200])
                    return {'success': False, 'error': 'Failed to get transcript'}

                data = response.json()
                status = data.get('status')
                _logger.info("Status: %s (attempt %d/%d)", status, attempt + 1, max_attempts)

                if status == 'completed':
                    transcript = data.get('text', '')
                    _logger.info("✅ Transcription completed: %d chars", len(transcript))
                    return {
                        'success': True,
                        'transcript': transcript,
                        'provider': 'AssemblyAI',
                        'confidence': 0.95,
                        'duration': data.get('audio_duration', 0)
                    }
                elif status == 'error':
                    error = data.get('error', 'Unknown error')
                    _logger.error("❌ AssemblyAI error: %s", error)
                    return {'success': False, 'error': f'Transcription error: {error}'}

                time.sleep(1)
                attempt += 1

            _logger.error("❌ Transcription timeout after %d seconds", max_attempts)
            return {'success': False, 'error': 'Transcription timeout'}

        except Exception as e:
            _logger.exception("❌ AssemblyAI error: %s", e)
            return {'success': False, 'error': str(e)}

    def _transcribe_with_deepgram(self, audio_bytes, format):
        """Transcribe using Deepgram"""
        try:
            config = self._get_speech_config()
            api_key = config['deepgram_api_key']

            if not api_key:
                return {'success': False, 'error': 'Deepgram API key not configured'}

            url = "https://api.deepgram.com/v1/listen?model=nova-2&language=fr&punctuate=true"

            headers = {
                "Authorization": f"Token {api_key}",
                "Content-Type": f"audio/{format}"
            }

            response = requests.post(url, data=audio_bytes, headers=headers, timeout=60)

            if response.status_code >= 400:
                _logger.error("❌ Deepgram error: %s", response.text[:200])
                return {'success': False, 'error': 'Deepgram API error'}

            data = response.json()

            if not data.get('results', {}).get('channels'):
                return {'success': False, 'error': 'No speech detected'}

            channel = data['results']['channels'][0]
            transcript = channel.get('alternatives', [{}])[0].get('transcript', '')
            confidence = channel.get('alternatives', [{}])[0].get('confidence', 0)

            return {
                'success': True,
                'transcript': transcript,
                'provider': 'Deepgram Nova-2',
                'confidence': confidence,
                'duration': data.get('metadata', {}).get('duration', 0)
            }

        except Exception as e:
            _logger.exception("❌ Deepgram error: %s", e)
            return {'success': False, 'error': str(e)}

    def _transcribe_with_google(self, audio_bytes, format):
        """Transcribe using Google Cloud Speech-to-Text"""
        try:
            config = self._get_speech_config()
            api_key = config['google_api_key']

            if not api_key:
                return {'success': False, 'error': 'Google API key not configured'}

            audio_content = base64.b64encode(audio_bytes).decode('utf-8')
            url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"

            payload = {
                "config": {
                    "encoding": "LINEAR16",
                    "sampleRateHertz": 16000,
                    "languageCode": "fr-FR",
                },
                "audio": {
                    "content": audio_content
                }
            }

            response = requests.post(url, json=payload, timeout=30)

            if response.status_code >= 400:
                _logger.error("❌ Google API error: %s", response.text[:200])
                return {'success': False, 'error': 'Google API error'}

            data = response.json()

            if 'results' not in data or not data['results']:
                return {'success': False, 'error': 'No speech detected'}

            transcript = ' '.join([
                r.get('alternatives', [{}])[0].get('transcript', '')
                for r in data['results']
            ])

            return {
                'success': True,
                'transcript': transcript,
                'provider': 'Google Cloud Speech-to-Text',
                'confidence': data['results'][0].get('alternatives', [{}])[0].get('confidence', 0)
            }

        except Exception as e:
            _logger.exception("❌ Google error: %s", e)
            return {'success': False, 'error': str(e)}

    def _call_ai_enhance(self, prompt):
        """Use existing AI infrastructure to enhance text"""
        try:
            config_param = request.env['ir.config_parameter'].sudo()
            provider = config_param.get_param('meeting_management_base.ai_provider', 'gemini')

            if provider == 'gemini':
                return self._enhance_with_gemini(prompt)
            else:
                return {'success': False, 'error': 'AI provider not configured'}

        except Exception as e:
            _logger.exception("❌ Enhancement failed: %s", e)
            return {'success': False, 'error': str(e)}

    def _enhance_with_gemini(self, prompt):
        """Enhance using Google Gemini"""
        try:
            config_param = request.env['ir.config_parameter'].sudo()
            api_key = config_param.get_param('meeting_management_base.gemini_api_key')

            if not api_key:
                return {'success': False, 'error': 'Gemini API key not configured'}

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

            payload = {
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {
                    'temperature': 0.7,
                    'maxOutputTokens': 2000,
                }
            }

            resp = requests.post(url, json=payload, timeout=30)

            if resp.status_code >= 400:
                _logger.error("❌ Gemini error: %s", resp.text[:200])
                return {'success': False, 'error': 'Gemini API error'}

            data = resp.json()

            if 'candidates' in data and data['candidates']:
                text = data['candidates'][0]['content']['parts'][0]['text']
                return {'success': True, 'text': text, 'provider': 'Google Gemini'}

            return {'success': False, 'error': 'No response from Gemini'}

        except Exception as e:
            _logger.exception("❌ Gemini error: %s", e)
            return {'success': False, 'error': str(e)}
