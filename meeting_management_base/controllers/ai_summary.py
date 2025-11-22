# -*- coding: utf-8 -*-
import json
import logging
import os

import requests
from requests import RequestException

from smartdz import http, _
from smartdz.http import request
from smartdz.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MeetingSummaryAI(http.Controller):
    """
    Controller to generate meeting summaries using multiple free AI providers.
    Supports: Google Gemini, OpenRouter, Groq, Hugging Face
    """

    @http.route('/meeting/generate_summary', type='json', auth='user', methods=['POST'])
    def generate_ai_summary(self, meeting_id):
        """JSON route to generate and store an AI meeting summary."""
        try:
            # Basic validations & permission check
            meeting = request.env['dw.meeting'].sudo().browse(meeting_id)
            if not meeting.exists():
                return {'success': False, 'error': 'Meeting not found'}

            current_user = request.env.user
            is_participant = request.env['dw.participant'].sudo().search([
                ('meeting_id', '=', meeting_id),
                '|',
                ('employee_id.user_id', '=', current_user.id),
                ('partner_id.user_ids', 'in', current_user.id)
            ], limit=1)

            if not is_participant:
                return {'success': False, 'error': 'Only participants can generate summaries'}

            # Prepare data for AI
            summary_model = request.env['dw.meeting.summary'].sudo()
            meeting_data = summary_model.generate_summary_data(meeting_id)

            # Call AI with multiple provider support
            ai_result = self._generate_with_ai(meeting_data)

            if not ai_result.get('success'):
                return {'success': False, 'error': ai_result.get('error', 'AI generation failed')}

            # Create summary record
            summary_vals = {
                'meeting_id': meeting_id,
                'executive_summary': ai_result.get('executive_summary') or '',
                'key_decisions': ai_result.get('key_decisions') or '',
                'action_items_summary': ai_result.get('action_items_summary') or '',
                'discussion_points': ai_result.get('discussion_points') or '',
                'participants_summary': ', '.join(meeting_data['meeting']['participants']) if meeting_data[
                    'meeting'].get('participants') else '',
                'raw_notes': json.dumps(meeting_data.get('notes', [])),
                'raw_actions': json.dumps(meeting_data.get('actions', [])),
                'state': 'draft',
                'generated_by': request.env.uid,
                'ai_model_used': ai_result.get('model_used', 'Unknown'),
            }

            summary = summary_model.create(summary_vals)

            return {
                'success': True,
                'summary_id': summary.id,
                'summary_data': {
                    'executive_summary': summary.executive_summary,
                    'key_decisions': summary.key_decisions,
                    'action_items_summary': summary.action_items_summary,
                    'discussion_points': summary.discussion_points
                }
            }

        except Exception as e:
            _logger.exception("Failed to generate AI summary: %s", e)
            return {'success': False, 'error': str(e)}

    def _get_ai_config(self):
        """Get AI provider configuration."""
        config_param = request.env['ir.config_parameter'].sudo()

        # Get provider choice (default to gemini if not set)
        provider = config_param.get_param('meeting_management_base.ai_provider', default='gemini')

        # Get API keys for different providers
        configs = {
            'gemini': {
                'api_key': config_param.get_param('meeting_management_base.gemini_api_key') or os.environ.get(
                    'GEMINI_API_KEY'),
                'url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
            },
            'openrouter': {
                'api_key': config_param.get_param('meeting_management_base.openrouter_api_key') or os.environ.get(
                    'OPENROUTER_API_KEY'),
                'url': 'https://openrouter.ai/api/v1/chat/completions',
            },
            'groq': {
                'api_key': config_param.get_param('meeting_management_base.groq_api_key') or os.environ.get(
                    'GROQ_API_KEY'),
                'url': 'https://api.groq.com/openai/v1/chat/completions',
            },
            'huggingface': {
                'api_key': config_param.get_param('meeting_management_base.huggingface_api_key') or os.environ.get(
                    'HUGGINGFACE_API_KEY'),
                'url': 'https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1',
            }
        }

        return provider, configs.get(provider, configs['gemini'])

    def _generate_with_ai(self, meeting_data):
        """Generate summary using configured AI provider."""
        provider, config = self._get_ai_config()

        if not config.get('api_key'):
            _logger.error(f"{provider.upper()} API key not configured")
            return {'success': False,
                    'error': f'{provider.upper()} API key not configured. Get free key from documentation.'}

        prompt = self._build_summary_prompt(meeting_data)

        # Call appropriate provider
        if provider == 'gemini':
            return self._call_gemini(config, prompt)
        elif provider == 'openrouter':
            return self._call_openrouter(config, prompt)
        elif provider == 'groq':
            return self._call_groq(config, prompt)
        elif provider == 'huggingface':
            return self._call_huggingface(config, prompt)
        else:
            return {'success': False, 'error': 'Unknown AI provider'}

    def _call_gemini(self, config, prompt):
        """Call Google Gemini API (FREE - No credit card required)"""
        try:
            url = f"{config['url']}?key={config['api_key']}"
            headers = {'Content-Type': 'application/json'}

            payload = {
                'contents': [{
                    'parts': [{'text': prompt}]
                }],
                'generationConfig': {
                    'temperature': 0.7,
                    'maxOutputTokens': 4000,
                }
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=30)

            if resp.status_code >= 400:
                _logger.error("Gemini API error: %s - %s", resp.status_code, resp.text[:500])
                return {'success': False, 'error': f'Gemini API error: HTTP {resp.status_code}'}

            data = resp.json()

            # Extract text from Gemini response
            ai_text = ''
            if 'candidates' in data and data['candidates']:
                candidate = data['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    ai_text = ' '.join([part.get('text', '') for part in candidate['content']['parts']])

            if not ai_text:
                return {'success': False, 'error': 'Empty response from Gemini'}

            parsed = self._parse_ai_response(ai_text)
            parsed['model_used'] = 'Google Gemini Pro (Free)'
            return {'success': True, **parsed}

        except Exception as e:
            _logger.exception("Gemini API call failed: %s", e)
            return {'success': False, 'error': str(e)}

    def _call_openrouter(self, config, prompt):
        """Call OpenRouter API (FREE models available)"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {config['api_key']}",
                'HTTP-Referer': request.httprequest.url_root,
            }

            payload = {
                'model': 'deepseek/deepseek-chat',  # Free model
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 4000,
                'temperature': 0.7,
            }

            resp = requests.post(config['url'], headers=headers, json=payload, timeout=30)

            if resp.status_code >= 400:
                return {'success': False, 'error': f'OpenRouter error: HTTP {resp.status_code}'}

            data = resp.json()
            ai_text = data['choices'][0]['message']['content'] if 'choices' in data else ''

            if not ai_text:
                return {'success': False, 'error': 'Empty response from OpenRouter'}

            parsed = self._parse_ai_response(ai_text)
            parsed['model_used'] = 'DeepSeek via OpenRouter (Free)'
            return {'success': True, **parsed}

        except Exception as e:
            _logger.exception("OpenRouter API call failed: %s", e)
            return {'success': False, 'error': str(e)}

    def _call_groq(self, config, prompt):
        """Call Groq API (FREE tier available)"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {config['api_key']}",
            }

            payload = {
                'model': 'llama-3.3-70b-versatile',  # Fast and free
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 4000,
                'temperature': 0.7,
            }

            resp = requests.post(config['url'], headers=headers, json=payload, timeout=30)

            if resp.status_code >= 400:
                return {'success': False, 'error': f'Groq error: HTTP {resp.status_code}'}

            data = resp.json()
            ai_text = data['choices'][0]['message']['content'] if 'choices' in data else ''

            if not ai_text:
                return {'success': False, 'error': 'Empty response from Groq'}

            parsed = self._parse_ai_response(ai_text)
            parsed['model_used'] = 'Llama 3.3 via Groq (Free)'
            return {'success': True, **parsed}

        except Exception as e:
            _logger.exception("Groq API call failed: %s", e)
            return {'success': False, 'error': str(e)}

    def _call_huggingface(self, config, prompt):
        """Call Hugging Face Inference API (FREE tier available)"""
        try:
            headers = {
                'Authorization': f"Bearer {config['api_key']}",
                'Content-Type': 'application/json',
            }

            payload = {
                'inputs': prompt,
                'parameters': {
                    'max_new_tokens': 4000,
                    'temperature': 0.7,
                    'return_full_text': False,
                }
            }

            resp = requests.post(config['url'], headers=headers, json=payload, timeout=60)

            if resp.status_code >= 400:
                return {'success': False, 'error': f'Hugging Face error: HTTP {resp.status_code}'}

            data = resp.json()
            ai_text = data[0]['generated_text'] if isinstance(data, list) and data else ''

            if not ai_text:
                return {'success': False, 'error': 'Empty response from Hugging Face'}

            parsed = self._parse_ai_response(ai_text)
            parsed['model_used'] = 'Mixtral via Hugging Face (Free)'
            return {'success': True, **parsed}

        except Exception as e:
            _logger.exception("Hugging Face API call failed: %s", e)
            return {'success': False, 'error': str(e)}

    def _build_summary_prompt(self, meeting_data):
        """Build the prompt sent to the AI."""
        meeting = meeting_data.get('meeting', {})
        notes = meeting_data.get('notes', [])
        actions = meeting_data.get('actions', [])
        decisions = meeting_data.get('decisions', [])

        prompt = f"""You are a professional meeting secretary. Generate a comprehensive meeting summary based on the following information:

**MEETING DETAILS:**
- Title: {meeting.get('name', '')}
- Subject: {meeting.get('objet', '')}
- Date: {meeting.get('start_time', '')}
- Duration: {meeting.get('duration', '')} hours
- Participants: {', '.join(meeting.get('participants', []))}

**AGENDA:**
{meeting.get('agenda', '')}

**PARTICIPANT NOTES:**
"""

        for note in notes:
            participant = note.get('participant', 'Unknown')
            note_text = note.get('notes', '')
            prompt += f"\n{participant}:\n{note_text}\n"

        prompt += "\n**ACTION ITEMS:**\n"
        for action in actions:
            prompt += "- {title} (Assigned to: {assignee}, Due: {due_date}, Priority: {priority})\n".format(
                title=action.get('title', ''),
                assignee=action.get('assignee', 'Unassigned'),
                due_date=action.get('due_date', 'No deadline'),
                priority=action.get('priority', '')
            )

        if decisions:
            prompt += "\n**DECISIONS MADE:**\n"
            for decision in decisions:
                prompt += "- {title}: {description}\n".format(
                    title=decision.get('title', ''),
                    description=decision.get('description', '')
                )

        prompt += """

Please provide a structured summary with the following sections:

1. EXECUTIVE_SUMMARY: A brief 2-3 sentence overview of the meeting
2. KEY_DECISIONS: List all important decisions made (in HTML format with <ul><li>)
3. ACTION_ITEMS_SUMMARY: Organize action items by assignee with deadlines (in HTML format)
4. DISCUSSION_POINTS: Key topics discussed and outcomes (in HTML format with proper formatting)

Format your response EXACTLY like this:

[EXECUTIVE_SUMMARY]
Your executive summary here
[/EXECUTIVE_SUMMARY]

[KEY_DECISIONS]
<ul>
<li>Decision 1</li>
<li>Decision 2</li>
</ul>
[/KEY_DECISIONS]

[ACTION_ITEMS_SUMMARY]
<h4>John Doe:</h4>
<ul>
<li>Task 1 - Due: 2025-01-15</li>
<li>Task 2 - Due: 2025-01-20</li>
</ul>
[/ACTION_ITEMS_SUMMARY]

[DISCUSSION_POINTS]
<h4>Topic 1</h4>
<p>Discussion details...</p>
[/DISCUSSION_POINTS]
"""
        return prompt

    def _parse_ai_response(self, ai_text):
        """Parse tagged AI response into the four required sections."""
        import re

        def extract_section(text, section_name):
            pattern = r'\[' + re.escape(section_name) + r'\](.*?)\[/' + re.escape(section_name) + r'\]'
            m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else ''

        return {
            'executive_summary': extract_section(ai_text, 'EXECUTIVE_SUMMARY'),
            'key_decisions': extract_section(ai_text, 'KEY_DECISIONS'),
            'action_items_summary': extract_section(ai_text, 'ACTION_ITEMS_SUMMARY'),
            'discussion_points': extract_section(ai_text, 'DISCUSSION_POINTS')
        }