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

"""Link Factory weko-deposit."""

from invenio_deposit.links import deposit_links_factory

from .pidstore import get_latest_version_id


def links_factory(pid, **kwargs):
    """Deposit links factory."""
    links = deposit_links_factory(pid)

    links.update(base_factory(pid, **kwargs))
    return links


def base_factory(pid, **kwargs):
    """Deposit links factory."""
    redirect_url = "/api/deposits/redirect/"
    iframe_index_url = "/items/iframe/index/"
    upgrade_pid_number = "{}.{}".format(
        pid.pid_value.split(".")[0],
        str(get_latest_version_id(pid.pid_value.split(".")[0])))

    links = dict()
    links['index'] = redirect_url + pid.pid_value
    links['r'] = "/items/index/" + pid.pid_value
    links['iframe_tree'] = iframe_index_url + pid.pid_value
    links['newversion'] = "/items/newversion/" + pid.pid_value
    links['edit'] = redirect_url + pid.pid_value
    links['iframe_tree_edit'] = iframe_index_url + pid.pid_value
    links['index_upgrade'] = redirect_url + upgrade_pid_number
    links['iframe_tree_upgrade'] = iframe_index_url + upgrade_pid_number

    return links
