import uuid
from smartdz import models, fields, api, _, http
from datetime import datetime, timedelta
from smartdz.exceptions import ValidationError, UserError
import logging
import base64
from io import BytesIO
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

_logger = logging.getLogger(__name__)


class DwMeeting(models.Model):
    _name = 'dw.meeting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Meeting'
    _order = 'planned_start_datetime desc'

    # from planification meeting
    name = fields.Char(string='Meeting Title', required=True, tracking=True)
    objet = fields.Char(string='Objet')
    is_external = fields.Boolean(string='External')
    meeting_type_id = fields.Many2one('dw.meeting.type', string='Meeting Type')
    client_ids = fields.Many2many('res.partner', string='Client', domain=[('is_company', '=', True)])
    # subject_order = fields.Html(string='Agenda')
    subject_order = fields.One2many('dw.agenda', 'meeting_id', string='Calendar')
    planned_start_datetime = fields.Datetime(string='Start Date & Time', required=True, tracking=True)
    planned_end_time = fields.Datetime(string='End Date & Time', related="planification_id.planned_end_time",
                                       store=True)
    location_id = fields.Many2one('dw.location', string='Location')
    room_id = fields.Many2one('dw.room', string='Room')
    participant_ids = fields.One2many('dw.participant', 'meeting_id', string='Participants')
    duration = fields.Float(string='Duration (hours)', default=1.0, tracking=True)
    form_planification = fields.Boolean(string='Created from the planification meetings', default=False)
    planification_id = fields.Many2one('dw.planification.meeting', string='Associated Planifications')
    project_id = fields.Many2one('dw.project', string='Project')
    use_agenda_timer = fields.Boolean(
        string='Use Agenda Timer',
        related='planification_id.use_agenda_timer',
        store=True,
        readonly=True,
        help='Enable timer for each agenda item during the meeting'
    )
    # from session
    actual_start_datetime = fields.Datetime(string='Actual Start Date & Time', tracking=True)
    actual_end_datetime = fields.Datetime(string='Actual End Date & Time', store=True)
    actual_duration = fields.Float(string='Duration (hours)', default=0.0, tracking=True)

    actions_ids = fields.One2many('dw.actions', 'meeting_id', string='Actions')
    summary = fields.Html(string='Summary')
    note_ids = fields.One2many('dw.meeting.note', 'meeting_id', string='Notes')
    decision_ids = fields.One2many('dw.meeting.decision', 'meeting_id', string='Decisions')
    pv = fields.Html(
        string="Procès-Verbal",
        sanitize=False,
        sanitize_tags=False,
    )

    # NEW PV FIELDS
    pv_status = fields.Selection([
        ('draft', 'Brouillon'),
        ('final', 'Final'),
        ('signed', 'Signé'),
    ], string='PV Status', default='draft', tracking=True, help="Status of the meeting minutes")

    pv_signed_document = fields.Binary(string='Signed PV Document', attachment=True,
                                       help="Upload the signed PV document")
    pv_signed_document_name = fields.Char(string='Signed PV Filename')
    pv_can_edit = fields.Boolean(string='Can Edit PV', compute='_compute_pv_can_edit',
                                 help="Check if current user can edit PV")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # jitsi code
    jitsi_room_id = fields.Char(string='Jitsi Room ID', readonly=True, copy=False)
    jitsi_room_created_by = fields.Many2one('res.users', string='Room Created By', readonly=True)
    jitsi_room_created_at = fields.Datetime(string='Room Created At', readonly=True)
    host_participant_id = fields.Many2one(
        'dw.participant',
        string='Meeting Host',
        compute='_compute_host_participant',
        store=True
    )

    @api.depends('participant_ids', 'participant_ids.role_id')
    def _compute_host_participant(self):
        """Find the host participant"""
        for meeting in self:
            host = meeting.participant_ids.filtered(lambda p: p.is_host)
            meeting.host_participant_id = host[0] if host else False

    @api.depends('state', 'host_participant_id')
    def _compute_pv_can_edit(self):
        """Compute if current user can edit PV"""
        for meeting in self:
            current_user = self.env.user
            # Only host can edit PV after meeting is done
            if meeting.state == 'done':
                if meeting.host_participant_id:
                    # Check if current user is the host
                    is_host = meeting.host_participant_id.partner_id.id == current_user.partner_id.id or \
                              (
                                      meeting.host_participant_id.employee_id and meeting.host_participant_id.employee_id.user_id.id == current_user.id)
                    meeting.pv_can_edit = is_host
                else:
                    meeting.pv_can_edit = False
            else:
                # During meeting, PV writer can edit
                pv_participant = meeting.participant_ids.filtered(lambda p: p.is_pv)
                if pv_participant:
                    is_pv_writer = any(
                        p.partner_id.id == current_user.partner_id.id or
                        (p.employee_id and p.employee_id.user_id.id == current_user.id)
                        for p in pv_participant
                    )
                    meeting.pv_can_edit = is_pv_writer
                else:
                    meeting.pv_can_edit = False

    def action_generate_pv_template(self):
        """Generate PV template from Word document"""
        self.ensure_one()

        try:
            # Generate PV content based on meeting data
            pv_content = self._generate_pv_from_template()
            self.pv = pv_content

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('PV template generated successfully'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error(f"Error generating PV template: {e}", exc_info=True)
            raise UserError(_("Failed to generate PV template: %s") % str(e))

    def _generate_pv_from_template(self):
        """Generate PV HTML content based on the Word template structure"""
        self.ensure_one()

        # Format meeting date in French
        meeting_date = self.actual_start_datetime or self.planned_start_datetime
        if meeting_date:
            # Format: "30 avril 2025"
            months_fr = {
                1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
            }
            day = meeting_date.day
            month = months_fr[meeting_date.month]
            year = meeting_date.year
            date_str = f"{day} {month} {year}"
            time_str = meeting_date.strftime('%Hh %Mmn')
        else:
            date_str = datetime.now().strftime('%d %B %Y')
            time_str = datetime.now().strftime('%Hh %Mmn')

        # Get company name
        company_name = self.env.company.name or "SPA SMARTEST ALGERIA"

        # Get meeting type
        meeting_type = self.meeting_type_id.name if self.meeting_type_id else "Conseil d'administration"

        # Get president (host)
        president = None
        secretary = None
        members = []

        for participant in self.participant_ids:
            if participant.is_host:
                president = participant.name
            elif participant.is_pv:
                secretary = participant.name
            else:
                members.append(participant.name)

        if not president and self.participant_ids:
            president = self.participant_ids[0].name

        # Get agenda items
        agenda_items = []
        for item in self.subject_order:
            agenda_items.append(item.name)

        # Generate HTML template matching Word document
        html_content = f"""
<div style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
    <h1 style="text-align: center; text-transform: uppercase; margin-bottom: 10px;">
        PROCES VERBAL DU CONSEIL D'ADMINISTRATION
    </h1>
    <h2 style="text-align: center; margin-top: 5px; margin-bottom: 10px;">
        {company_name}
    </h2>
    <h3 style="text-align: center; margin-top: 5px; margin-bottom: 30px;">
        {self.name}
    </h3>

    <p style="text-align: justify; margin-top: 30px;">
        Le {date_str} à {time_str}, le Conseil d'administration de la société {company_name} 
        s'est réuni au siège de la société sur convocation du président du Conseil d'Administration 
        dont les copies sont jointes au présent procès-verbal.
    </p>

    <p style="text-align: justify;">
        Il a été établi une feuille de présence signée par les membres présents en leur nom propre. 
        Celle-ci figure en annexe du présent procès-verbal.
    </p>

    <p style="text-align: justify;">
        Le Conseil d'Administration est présidé par {president or '[PRÉSIDENT]'}, 
        en sa qualité de Président du Conseil d'Administration.
    </p>

    <h3 style="margin-top: 20px;"><u>Etaient présents :</u></h3>

    <h4 style="margin-left: 20px;">Membres du Conseil d'Administration :</h4>
    <ul style="margin-left: 40px;">
"""

        # Add participants
        if president:
            html_content += f"        <li>{president}, Président du Conseil d'Administration</li>\n"

        for member in members:
            html_content += f"        <li>{member}, Administrateur</li>\n"

        html_content += """    </ul>

"""

        if secretary:
            html_content += f"""    <p style="margin-left: 20px;">
        Le secrétariat du conseil d'administration est assuré par {secretary}.
    </p>

"""

        html_content += f"""    <p style="text-align: justify; margin-top: 20px;">
        Après avoir constaté que le conseil d'administration est en nombre pour siéger, 
        le président ouvre la séance à {time_str} et déclare que le conseil d'administration peut 
        valablement délibérer conformément à l'article 626 du code de commerce.
    </p>

    <p style="text-align: justify; margin-top: 15px;">
        Après avoir souhaité la bienvenue à l'ensemble des présents :
    </p>

    <p style="text-align: justify; margin-left: 20px;">
        Le président dépose sur le bureau les documents suivants :
    </p>

    <ul style="margin-left: 60px;">
        <li>Les convocations adressées aux membres du conseil d'administration</li>
    </ul>

    <h3 style="margin-top: 20px;"><u>Et rappelle l'ordre du jour ci-après :</u></h3>

    <div style="margin-left: 20px; margin-top: 10px; margin-bottom: 10px; border-top: 1px solid #000; border-bottom: 1px solid #000; padding: 5px 0;">
        <p style="margin: 0;">Ouverture de la séance</p>
        <ul style="margin: 5px 0 5px 20px;">
            <li>Approbation de l'ordre du jour</li>
"""

        # Add agenda items
        for idx, item in enumerate(agenda_items, 1):
            html_content += f"            <li>{item}</li>\n"

        html_content += """        </ul>
        <p style="margin: 0;">Divers</p>
        <ul style="margin: 5px 0 5px 20px;">
            <li>Questions diverses soulevées par les administrateurs</li>
        </ul>
    </div>

    <h3 style="margin-top: 20px;"><u>Approbation de l'ordre du jour :</u></h3>

    <p style="text-align: justify;">
        Après lecture et correction de l'ordre du jour, le président le met aux voix pour adoption.
    </p>

    <p style="text-align: justify;">
        <strong>Résolution N° 01 :</strong> Le conseil d'administration décide à l'unanimité des voix 
        des membres présents d'approuver l'ordre du jour de cette réunion.
    </p>

    <h3 style="margin-top: 20px;"><u>Déroulement de la réunion :</u></h3>

"""

        # Add numbered sections for each agenda item
        for idx, item in enumerate(agenda_items, 1):
            html_content += f"""    <p style="text-align: justify; margin-top: 15px;">
        <strong>({idx})</strong> <u>{item}</u>
    </p>

    <p style="text-align: justify; margin-left: 20px;">
        [À compléter]
    </p>

"""

        html_content += """    <h3 style="margin-top: 30px;"><u>Clôture de la séance :</u></h3>

    <p style="text-align: justify;">
        Plus aucune question n'étant à l'ordre du jour, la séance est levée à [HEURE].
    </p>
</div>
"""

        return html_content

    def action_download_pv_word(self):
        """Generate and download PV as Word document"""
        self.ensure_one()

        try:
            # Generate Word document
            doc = self._generate_pv_word_document()

            # Save to BytesIO
            doc_io = BytesIO()
            doc.save(doc_io)
            doc_io.seek(0)

            # Encode to base64
            doc_data = base64.b64encode(doc_io.read())

            # Create attachment
            filename = f"PV_{self.name}_{datetime.now().strftime('%Y%m%d')}.docx"
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': doc_data,
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            })

            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'new',
            }

        except Exception as e:
            _logger.error(f"Error generating Word PV: {e}", exc_info=True)
            raise UserError(_("Failed to generate Word document: %s") % str(e))

    def _generate_pv_word_document(self):
        """Generate Word document for PV from actual HTML content"""
        self.ensure_one()

        # If no PV content, use the template
        if not self.pv:
            return self._generate_pv_word_document_template()

        from html.parser import HTMLParser
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

        # Create new Document
        doc = Document()

        # Set document margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        # Parse HTML and convert to Word
        class HTMLToWordParser(HTMLParser):
            def __init__(self, document):
                super().__init__()
                self.doc = document
                self.current_paragraph = None
                self.current_run = None
                self.in_list = False
                self.list_style = None
                self.bold = False
                self.italic = False
                self.underline = False
                self.heading_level = 0
                self.in_table = False
                self.current_table = None
                self.current_row = None
                self.current_cell = None

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)

                if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    self.heading_level = int(tag[1])
                    self.current_paragraph = self.doc.add_paragraph()
                    self.current_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER if self.heading_level <= 2 else WD_PARAGRAPH_ALIGNMENT.LEFT
                    self.current_run = self.current_paragraph.add_run()
                    self.current_run.bold = True
                    if self.heading_level == 1:
                        self.current_run.font.size = Pt(16)
                    elif self.heading_level == 2:
                        self.current_run.font.size = Pt(14)
                    elif self.heading_level == 3:
                        self.current_run.font.size = Pt(12)

                elif tag == 'p':
                    self.current_paragraph = self.doc.add_paragraph()
                    style = attrs_dict.get('style', '')
                    if 'text-align: center' in style or 'text-align:center' in style:
                        self.current_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
                    elif 'text-align: justify' in style or 'text-align:justify' in style:
                        self.current_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
                    elif 'text-align: right' in style or 'text-align:right' in style:
                        self.current_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
                    self.current_run = self.current_paragraph.add_run()

                elif tag == 'div':
                    # Start a new paragraph for div
                    if self.current_paragraph is None or self.current_paragraph.text:
                        self.current_paragraph = self.doc.add_paragraph()
                        self.current_run = self.current_paragraph.add_run()

                elif tag in ['ul', 'ol']:
                    self.in_list = True
                    self.list_style = 'List Bullet' if tag == 'ul' else 'List Number'

                elif tag == 'li':
                    if self.in_list:
                        self.current_paragraph = self.doc.add_paragraph(style=self.list_style)
                        self.current_run = self.current_paragraph.add_run()

                elif tag == 'br':
                    if self.current_run:
                        self.current_run.add_break()

                elif tag in ['strong', 'b']:
                    self.bold = True
                    if self.current_run:
                        self.current_run = self.current_paragraph.add_run()
                        self.current_run.bold = True

                elif tag in ['em', 'i']:
                    self.italic = True
                    if self.current_run:
                        self.current_run = self.current_paragraph.add_run()
                        self.current_run.italic = True

                elif tag == 'u':
                    self.underline = True
                    if self.current_run:
                        self.current_run = self.current_paragraph.add_run()
                        self.current_run.underline = True

                elif tag == 'table':
                    self.in_table = True
                    # We'll add table support if needed

            def handle_endtag(self, tag):
                if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    self.heading_level = 0
                    self.current_paragraph = None
                    self.current_run = None

                elif tag == 'p':
                    self.current_paragraph = None
                    self.current_run = None

                elif tag in ['ul', 'ol']:
                    self.in_list = False
                    self.list_style = None

                elif tag == 'li':
                    self.current_paragraph = None
                    self.current_run = None

                elif tag in ['strong', 'b']:
                    self.bold = False
                    if self.current_paragraph:
                        self.current_run = self.current_paragraph.add_run()

                elif tag in ['em', 'i']:
                    self.italic = False
                    if self.current_paragraph:
                        self.current_run = self.current_paragraph.add_run()

                elif tag == 'u':
                    self.underline = False
                    if self.current_paragraph:
                        self.current_run = self.current_paragraph.add_run()

                elif tag == 'table':
                    self.in_table = False

            def handle_data(self, data):
                # Clean up whitespace
                data = data.strip()
                if not data:
                    return

                # If no current paragraph, create one
                if self.current_paragraph is None:
                    self.current_paragraph = self.doc.add_paragraph()
                    self.current_run = self.current_paragraph.add_run()

                # If no current run, create one
                if self.current_run is None:
                    self.current_run = self.current_paragraph.add_run()

                # Add the text
                self.current_run.add_text(data)

        # Parse the HTML content
        parser = HTMLToWordParser(doc)

        # Clean HTML (remove div wrapper if present)
        html_content = self.pv
        if html_content.startswith('<div'):
            # Extract content between first div
            import re
            match = re.search(r'<div[^>]*>(.*)</div>', html_content, re.DOTALL)
            if match:
                html_content = match.group(1)

        try:
            parser.feed(html_content)
        except Exception as e:
            _logger.warning(f"Error parsing HTML: {e}. Using template instead.")
            return self._generate_pv_word_document_template()

        return doc

    def _generate_pv_word_document_template(self):
        """Generate static Word document template (fallback)"""
        self.ensure_one()

        # Create new Document
        doc = Document()

        # Set document margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        # Format meeting date
        meeting_date = self.actual_start_datetime or self.planned_start_datetime
        if meeting_date:
            date_str = meeting_date.strftime('%d %B %Y')
            time_str = meeting_date.strftime('%Hh %Mmn')
        else:
            date_str = datetime.now().strftime('%d %B %Y')
            time_str = datetime.now().strftime('%Hh %Mmn')

        company_name = self.env.company.name or "COMPANY NAME"

        # Title
        title = doc.add_paragraph()
        title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = title.add_run("PROCES VERBAL DU CONSEIL D'ADMINISTRATION")
        run.bold = True
        run.font.size = Pt(14)

        # Company name
        company = doc.add_paragraph()
        company.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = company.add_run(company_name)
        run.bold = True
        run.font.size = Pt(12)

        # Meeting name
        meeting_name = doc.add_paragraph()
        meeting_name.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = meeting_name.add_run(self.name)
        run.font.size = Pt(12)

        doc.add_paragraph()  # Spacing

        # Introduction paragraph
        intro = doc.add_paragraph()
        intro.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        intro.add_run(
            f"Le {date_str} à {time_str}, le Conseil d'administration de la société {company_name} "
            f"s'est réuni au siège de la société sur convocation du président du Conseil d'Administration "
            f"dont les copies sont jointes au présent procès-verbal."
        )

        # Attendance sheet mention
        attendance = doc.add_paragraph()
        attendance.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        attendance.add_run(
            "Il a été établi une feuille de présence signée par les membres présents en leur nom propre. "
            "Celle-ci figure en annexe du présent procès-verbal."
        )

        # President mention
        participants = self.participant_ids.filtered(lambda p: p.is_host)
        president_name = participants[0].name if participants else "[PRÉSIDENT]"

        president = doc.add_paragraph()
        president.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        president.add_run(
            f"Le Conseil d'Administration est présidé par {president_name}, "
            f"en sa qualité de Président du Conseil d'Administration."
        )

        doc.add_paragraph()  # Spacing

        # Present members
        present_title = doc.add_paragraph()
        run = present_title.add_run("Etaient présents :")
        run.bold = True

        members_title = doc.add_paragraph()
        run = members_title.add_run("    Membres du Conseil d'Administration :")
        run.bold = True

        # Add participants
        for participant in self.participant_ids:
            role = ""
            if participant.is_host:
                role = "Président du Conseil d'Administration"
            elif participant.is_pv:
                role = "Secrétaire"
            else:
                role = "Administrateur"

            p = doc.add_paragraph(style='List Bullet')
            p.add_run(f"{participant.name}, {role}")

        doc.add_paragraph()  # Spacing

        # Quorum paragraph
        quorum = doc.add_paragraph()
        quorum.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        quorum.add_run(
            "Après avoir constaté que le conseil d'administration est en nombre pour siéger, "
            "le président ouvre la séance et déclare que le conseil d'administration peut "
            "valablement délibérer conformément à l'article 626 du code de commerce."
        )

        doc.add_paragraph()  # Spacing

        # Agenda
        agenda_title = doc.add_paragraph()
        run = agenda_title.add_run("Ordre du jour :")
        run.bold = True

        for item in self.subject_order:
            agenda_item = doc.add_paragraph(style='List Bullet')
            agenda_item.add_run(item.name)

        doc.add_paragraph()  # Spacing

        # Agenda approval
        approval_title = doc.add_paragraph()
        run = approval_title.add_run("Approbation de l'ordre du jour :")
        run.bold = True

        approval_text = doc.add_paragraph()
        approval_text.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        approval_text.add_run(
            "Après lecture de l'ordre du jour, le président le met aux voix pour adoption."
        )

        resolution = doc.add_paragraph()
        resolution.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        run = resolution.add_run("Résolution N° 01 : ")
        run.bold = True
        resolution.add_run(
            "Le conseil d'administration décide à l'unanimité des voix des membres présents "
            "d'approuver l'ordre du jour de cette réunion."
        )

        doc.add_paragraph()  # Spacing

        # Meeting proceedings
        proceedings_title = doc.add_paragraph()
        run = proceedings_title.add_run("Déroulement de la réunion :")
        run.bold = True

        proceedings_text = doc.add_paragraph()
        proceedings_text.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        proceedings_text.add_run("[À compléter avec le déroulement détaillé de la réunion]")

        doc.add_paragraph()  # Spacing

        # Closing
        closing_title = doc.add_paragraph()
        run = closing_title.add_run("Clôture de la séance :")
        run.bold = True

        closing_text = doc.add_paragraph()
        closing_text.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
        closing_text.add_run(
            "Plus aucune question n'étant à l'ordre du jour, la séance est levée à [HEURE]."
        )

        return doc

    def action_download_pv_pdf(self):
        """Download PV as PDF"""
        self.ensure_one()

        try:
            pdf_content = self._generate_pv_pdf()
            pdf_b64 = base64.b64encode(pdf_content)

            # Create attachment
            filename = f"PV_{self.name}_{datetime.now().strftime('%Y%m%d')}.pdf"
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': pdf_b64,
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/pdf',
            })

            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'new',
            }

        except Exception as e:
            _logger.error(f"Error downloading PDF: {e}", exc_info=True)
            raise UserError(_("Failed to download PDF: %s") % str(e))

    def action_send_pv_emails(self):
        """Send PV emails to all participants"""
        self.ensure_one()

        if not self.pv:
            raise UserError(_("Cannot send PV: No PV content available"))

        try:
            pdf_bytes = self._generate_pv_pdf()
            pdf_b64 = base64.b64encode(pdf_bytes)
            self._send_pv_emails(pdf_b64)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('PV sent to all participants successfully'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error(f"Error sending PV emails: {e}", exc_info=True)
            raise UserError(_("Failed to send PV emails: %s") % str(e))

    def action_upload_signed_pv(self):
        """Close the meeting record after uploading signed PV"""
        self.ensure_one()

        if not self.pv_signed_document:
            raise UserError(_("Please upload the signed PV document first"))

        self.write({
            'pv_status': 'signed',
            'state': 'done'
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Signed PV uploaded and meeting closed successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_set_pv_final(self):
        """Set PV status to final"""
        self.ensure_one()

        if not self.pv:
            raise UserError(_("Cannot finalize PV: No PV content available"))

        self.pv_status = 'final'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('PV status set to Final'),
                'type': 'success',
                'sticky': False,
            }
        }

    def open_meeting(self):
        self.ensure_one()
        Planification = self.env['dw.planification.meeting']
        planification = Planification.search([('meeting_id', '=', self.id)], limit=1)
        return {
            'type': 'ir.actions.client',
            'name': f'Meeting: {self.name}',
            'tag': 'meetin_view_action',
            'context': {
                'active_id': self.id,
                'default_planification_id': planification.id,
                'uid': self.env.uid,
            },
        }

    def action_join_meeting(self):
        """Join the meeting - opens the user's session"""
        self.ensure_one()

        # Get current user
        current_user = self.env.user

        # Find the planification linked to this meeting
        planification = self.env['dw.planification.meeting'].search([
            ('meeting_id', '=', self.id)
        ], limit=1)

        if not planification:
            raise ValidationError(_("No planification found for this meeting."))

        # Find the session for the current user
        user_session = self.env['dw.meeting.session'].search([
            ('meeting_id', '=', self.id),
            ('user_id', '=', current_user.id)
        ], limit=1)

        if user_session:
            user_session.participant_id.attendance_status = "present"

            if not user_session.flag_attendance:
                now = fields.Datetime.now()
                user_session.join_time = now
                if self.planification_id.actual_start_datetime and self.planification_id.tolerated_late:
                    tolerated_limit = self.planification_id.actual_start_datetime + timedelta(
                        minutes=self.planification_id.tolerated_late)
                    if now <= tolerated_limit:
                        user_session.participant_id.is_late = False
                    else:
                        user_session.participant_id.is_late = True
                elif self.planification_id.actual_start_datetime and self.planification_id.tolerated_late == 0:
                    if now <= self.planification_id.actual_start_datetime + timedelta(minutes=1):
                        user_session.participant_id.is_late = False
                    else:
                        user_session.participant_id.is_late = True
                user_session.flag_attendance = True

        if not user_session:
            raise ValidationError(_("You are not a participant in this meeting."))

        # Return the action to open the session
        return {
            'type': 'ir.actions.client',
            'name': f'Meeting: {self.name} - {current_user.name}',
            'tag': 'meeting_session_view_action',
            'params': {
                'planification_id': planification.id,
            },
            'context': {
                'active_id': user_session.id,
                'default_session_id': user_session.id,
                'default_planification_id': planification.id,
                'default_pv': self.pv,
            },
        }

    # abderrahmane jitsi and dashboard methods
    def action_create_jitsi_room(self):
        """Create a Jitsi room - only host can do this"""
        self.ensure_one()

        # Check if user is the host
        current_user = self.env.user
        host_participant = self.participant_ids.filtered(
            lambda p: p.is_host and (
                    p.partner_id.id == current_user.partner_id.id or
                    p.employee_id.user_id.id == current_user.id
            )
        )

        if not host_participant:
            raise ValidationError(_("Only the meeting host can create a Jitsi room"))

        # Check if room already exists
        if self.jitsi_room_id:
            raise ValidationError(_("A Jitsi room already exists for this meeting"))

        # Generate unique room ID
        room_id = f"meeting-{self.id}-{uuid.uuid4().hex[:8]}"

        self.write({
            'jitsi_room_id': room_id,
            'jitsi_room_created_by': current_user.id,
            'jitsi_room_created_at': fields.Datetime.now()
        })

        # Notify all remote participants
        self._notify_room_created()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('The video conference room has been created successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def _notify_room_created(self):
        """Notify all remote participants that the room is ready"""
        remote_participants = self.participant_ids.filtered(lambda p: p.is_remote)

        for participant in remote_participants:
            # You can send email or in-app notification here
            _logger.info(f"Notifying {participant.name} that Jitsi room is ready: {self.jitsi_room_id}")

    def action_generate_summary(self):
        """Generate AI-powered meeting summary"""
        self.ensure_one()

        if self.state != 'done':
            raise ValidationError(_("Only completed meetings can have summaries generated."))

        return {
            'type': 'ir.actions.client',
            'tag': 'generate_meeting_summary',
            'params': {
                'meeting_id': self.id,
                'meeting_name': self.name
            }
        }

    def action_view_summary(self):
        """View existing meeting summary"""
        self.ensure_one()

        summary = self.env['dw.meeting.summary'].search([
            ('meeting_id', '=', self.id)
        ], limit=1, order='create_date desc')

        if not summary:
            raise ValidationError(_("No summary found for this meeting."))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dw.meeting.summary',
            'res_id': summary.id,
            'views': [[False, 'form']],
            'target': 'current'
        }

    def _generate_pv_pdf(self):
        """Render the PV PDF using a QWeb report template."""
        self.ensure_one()

        try:
            # Get the report using the standard pattern
            report = self.env['ir.actions.report']._get_report_from_name(
                'meeting_management_base.meeting_pv_pdf_2'
            )

            if not report:
                raise ValueError("Report 'meeting_pv_pdf_2' not found")

            # Render the report
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf('meeting_management_base.meeting_pv_pdf_2',
                                                                            self.id)

            if not pdf_content:
                raise ValueError("PDF generation returned empty content")

            return pdf_content

        except Exception as e:
            _logger.error(f"Error generating PDF for meeting {self.name}: {e}", exc_info=True)
            raise ValidationError(
                _("Failed to generate the PV PDF. Please ensure the report is properly configured.")
            )

    def _send_pv_emails(self, pdf_b64):
        """Send PV emails to all participants with the PDF attachment."""
        self.ensure_one()

        template = self.env.ref(
            'meeting_management_base.email_template_meeting_pv',
            raise_if_not_found=False
        )

        if not template:
            _logger.error("Email template 'meeting_management_base.email_template_meeting_pv' not found")
            return

        for participant in self.participant_ids:
            participant_email = None
            if participant.partner_id and participant.partner_id.email:
                participant_email = participant.partner_id.email
            elif participant.employee_id and participant.employee_id.work_email:
                participant_email = participant.employee_id.work_email

            if not participant_email:
                _logger.warning(
                    f"No email address found for participant {participant.name}"
                )
                continue

            # Build attachment - create unique attachment for each participant
            attachment_name = f"PV_{self.name}_{participant.name}.pdf"
            attachment = self.env['ir.attachment'].create({
                'name': attachment_name,
                'type': 'binary',
                'datas': pdf_b64,
                'res_model': 'dw.meeting',
                'res_id': self.id,
                'mimetype': 'application/pdf',
            })

            # Send email
            try:
                template.send_mail(
                    participant.id,
                    email_values={
                        'email_to': participant_email,
                        'recipient_ids': [],
                        'attachment_ids': [attachment.id],
                    },
                    force_send=True,
                )
                _logger.info(f"PV sent to {participant.name} ({participant_email})")

            except Exception as e:
                _logger.error(f"Failed to send PV to {participant.name}: {e}", exc_info=True)
                # Clean up attachment if email fails
                attachment.unlink()

    def write(self, vals):
        """Override write - Remove automatic PV sending"""
        res = super(DwMeeting, self).write(vals)
        # Automatic PV sending removed - now done manually via button
        return res


class DwMeetingNote(models.Model):
    """Meeting Notes - real-time collaborative notes"""
    _name = 'dw.meeting.note'
    _description = 'Meeting Note'
    _order = 'create_date desc'

    meeting_id = fields.Many2one('dw.meeting', string='Meeting', required=True, ondelete='cascade')
    content = fields.Html(string='Content', required=True)
    author_id = fields.Many2one('res.users', string='Author', default=lambda self: self.env.user)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    is_action_item = fields.Boolean(string='Action Item')


class DwMeetingDecision(models.Model):
    """Meeting Decisions - track key decisions made"""
    _name = 'dw.meeting.decision'
    _description = 'Meeting Decision'
    _order = 'create_date desc'

    meeting_id = fields.Many2one('dw.meeting', string='Meeting', required=True, ondelete='cascade')
    title = fields.Char(string='Decision', required=True)
    description = fields.Text(string='Description')
    decided_by_id = fields.Many2one('res.users', string='Decided By', default=lambda self: self.env.user)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    impact = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ], string='Impact', default='medium')