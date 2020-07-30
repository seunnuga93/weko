# -*- coding: utf-8 -*-
#
# This file is part of WEKO3.
# Copyright (C) 2017 National Institute of Informatics.
#
# WEKO3 is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# WEKO3 is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with WEKO3; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.

"""Configuration for weko-workflow."""

WEKO_WORKFLOW_BASE_TEMPLATE = 'weko_workflow/base.html'
"""Default base template for the demo page."""

WEKO_WORKFLOW_POP_PAGE = 'weko_workflow/admin/pop_page.html'
"""Default pop page template for the flow detail page."""

WEKO_WORKFLOW_OAPOLICY_SEARCH = 'oa_policy_{keyword}'
"""OA Policy cache."""

WEKO_WORKFLOW_OAPOLICY_CACHE_TTL = 24 * 60 * 60
""" cache default timeout 1 day"""

WEKO_WORKFLOW_ACTIVITY_ID_FORMAT = 'A-{}-{}'
"""Activity Id's format (A-YYYYMMDD-NNNNN with NNNNN starts from 00001)."""


WEKO_WORKFLOW_ACTION_ENDPOINTS = {
    'item_login': {
        'endpoint': 'weko_items_ui.index',
        'params': {}
    }
}

IDENTIFIER_GRANT_LIST = [(0, 'Not Grant', ''),
                         (1, 'JaLC DOI', 'https://doi.org'),
                         (2, 'JaLC CrossRef DOI', 'https://doi.org'),
                         (3, 'JaLC DataCite DOI', 'https://doi.org'),
                         (4, 'NDL JaLC DOI', 'https://doi.org')
                         ]
"""Options list for Identifier Grant action."""

IDENTIFIER_GRANT_SUFFIX_METHOD = 0
"""
    Suffix input method for Identifier Grant action

    :case 0: Automatic serial number
    :case 1: Semi-automatic input
    :case 2: Free input
"""

WEKO_WORKFLOW_IDENTIFIER_GRANT_CAN_WITHDRAW = -1
"""Identifier grant can withdraw."""

WEKO_WORKFLOW_IDENTIFIER_GRANT_IS_WITHDRAWING = -2
"""Identifier grant is withdrawing."""

WEKO_WORKFLOW_ITEM_REGISTRATION_ACTION_ID = 3
"""Item Registration action id default."""

"""Identifier grant is withdrawing."""

IDENTIFIER_GRANT_SELECT_DICT = {
    'NotGrant': '0',
    'JaLCDOI': '1',
    'CrossRefDOI': '2',
    'DataCiteDOI': '3',
    'NDLJaLCDOI': '4'
}
"""Identifier grant selected enum."""

WEKO_SERVER_CNRI_HOST_LINK = 'http://hdl.handle.net/'
"""Host server of CNRI"""

WEKO_WORKFLOW_SHOW_HARVESTING_ITEMS = False
"""Toggle display harvesting items in Workflow list."""

WEKO_WORKFLOW_ENABLE_FEEDBACK_MAIL = True
"""Enable showing function feed back mail"""

WEKO_WORKFLOW_ENABLE_CONTRIBUTOR = True
"""Enable Contributor"""

WEKO_WORKFLOW_TODO_TAB = 'todo'

WEKO_WORKFLOW_WAIT_TAB = 'wait'

WEKO_WORKFLOW_ALL_TAB = 'all'

WEKO_WORKFLOW_IDENTIFIER_GRANT_DOI = 0
"""Identifier grant was select."""

WEKO_WORKFLOW_IDENTIFIER_GRANT_WITHDRAWN = -3
"""Identifier grant was withdrawn."""
