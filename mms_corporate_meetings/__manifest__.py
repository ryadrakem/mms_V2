{
    "name": "Meeting Management System - Corporate meetings",
    "version": "18.0.1.0.0",
    "summary": "Extension of the meeting management base to manage corporate meetings.",
    "author": "DIGIWAVES - ALGERIA",
    "website": "https://digiwaves.io/",
    "maintainer": "MES-TEAM",
    "category": "Management/Meetings",
    "depends": ['meeting_management_base'],
    "data": [
        # data
        "data/dw_corporate_meeting_type_data.xml",
        "data/dw_corporate_role_data.xml",
        "data/dw_corp_permanent_members_data.xml",
        # views
        "views/dw_corp_participant_views.xml",
        "views/dw_corp_planification_views.xml",
        "views/dw_corp_permanent_members.xml",
        # menus
        "menus.xml",

    ],

    "license": "AGPL-3",
    "installable": True,
    "application": True,
}
