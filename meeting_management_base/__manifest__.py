{
    "name": "Meeting Management System base",
    "version": "18.0.1.0.0",
    "summary": "Manage meetings, schedules, and appointments efficiently.",
    "author": "DIGIWAVES - ALGERIA",
    "website": "https://digiwaves.io/",
    "category": "Management/Meetings",
    "depends": ['hr', 'contacts', 'calendar'],
    "data": [
        # data
        "data/dw_meeting_type_data.xml",
        "data/dw_participant_role_data.xml",
        # views
        "views/dw_actions_views.xml",
        "views/dw_equipment_type_views.xml",
        "views/dw_equipment_views.xml",
        "views/dw_location_views.xml",
        "views/dw_meeting_type_views.xml",
        "views/dw_meeting_views.xml",
        "views/dw_participant_role_views.xml",
        "views/dw_participant_views.xml",
        "views/dw_planification_meeting_views.xml",
        "views/dw_requirements_views.xml",
        "views/dw_room_views.xml",
        "views/dw_resevations.xml",
        "views/dw_meeting_session_view.xml",
        "views/res_config_settings_view.xml",
        "views/dw_meeting_summary.xml",
        # security
        "security/ir.model.access.csv",
        "security/dw_meeting_rules.xml",
        # menus
        "menus.xml",

    ],
    'assets': {
        'web.assets_backend': [
            'meeting_management_base/static/src/**/*.js',
            'meeting_management_base/static/src/**/*.xml',
            'meeting_management_base/static/src/**/*.scss',
            'meeting_management_base/static/src/**/*.css',
        ],
    },

    "license": "AGPL-3",
    "installable": True,
    "application": True,
}
