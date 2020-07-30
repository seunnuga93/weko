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

"""Views for weko-admin."""

import calendar
import json
import sys
from datetime import timedelta

from flask import Blueprint, Response, abort, current_app, flash, jsonify, \
    make_response, render_template, request
from flask_babelex import lazy_gettext as _
from flask_breadcrumbs import register_breadcrumb
from flask_login import current_user, login_required
from flask_menu import register_menu
from invenio_admin.proxies import current_admin
from invenio_oauth2server import require_api_auth, require_oauth_scopes
from invenio_stats.utils import QueryCommonReportsHelper
from sqlalchemy.orm import session
from weko_records.models import SiteLicenseInfo
from werkzeug.local import LocalProxy

from .api import send_site_license_mail
from .config import WEKO_HEADER_NO_CACHE
from .models import SessionLifetime, SiteInfo
from .utils import FeedbackMail, StatisticMail, format_site_info_data, \
    get_admin_lang_setting, get_api_certification_type, \
    get_current_api_certification, get_initial_stats_report, \
    get_search_setting, get_selected_language, get_unit_stats_report, \
    save_api_certification, update_admin_lang_setting, \
    validate_certification, validation_site_info

_app = LocalProxy(lambda: current_app.extensions['weko-admin'].app)


blueprint = Blueprint(
    'weko_admin',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/accounts/settings',
)

blueprint_api = Blueprint(
    'weko_admin',
    __name__,
    url_prefix='/admin',
    template_folder='templates',
    static_folder='static',
)


def _has_admin_access():
    """Use to check if a user has any admin access."""
    return current_user.is_authenticated and current_admin \
        .permission_factory(current_admin.admin.index_view).can()


@blueprint.route('/session/lifetime/<int:minutes>', methods=['GET'])
def set_lifetime(minutes):
    """Update session lifetime in db.

    :param minutes:
    :return: Session lifetime updated message.
    """
    try:
        db_lifetime = SessionLifetime.get_validtime()
        if db_lifetime is None:
            db_lifetime = SessionLifetime(lifetime=minutes)
        else:
            db_lifetime.lifetime = minutes
        db_lifetime.create()
        _app.permanent_session_lifetime = timedelta(
            minutes=db_lifetime.lifetime)
        return jsonify(code=0, msg='Session lifetime was updated.')
    except BaseException:
        current_app.logger.error('Unexpected error: ', sys.exc_info()[0])
        return abort(400)


@blueprint.route('/session', methods=['GET', 'POST'])
@blueprint.route('/session/', methods=['GET', 'POST'])
@register_menu(
    blueprint, 'settings.lifetime',
    _('%(icon)s Session', icon='<i class="fa fa-cogs fa-fw"></i>'),
    visible_when=_has_admin_access,
    order=14
)
@register_breadcrumb(
    blueprint, 'breadcrumbs.settings.session',
    _('Session')
)
@login_required
def lifetime():
    """Loading session setting page.

    :return: Lifetime in minutes.
    """
    if not _has_admin_access():
        return abort(403)
    try:
        db_lifetime = SessionLifetime.get_validtime()
        if db_lifetime is None:
            db_lifetime = SessionLifetime(lifetime=30)

        if request.method == 'POST':
            # Process forms
            form = request.form.get('submit', None)
            if form == 'lifetime':
                new_lifetime = request.form.get('lifetimeRadios', '30')
                db_lifetime.lifetime = int(new_lifetime)
                db_lifetime.create()
                _app.permanent_session_lifetime = timedelta(
                    minutes=db_lifetime.lifetime)
                flash(_('Session lifetime was updated.'), category='success')

        return render_template(
            current_app.config['WEKO_ADMIN_LIFETIME_TEMPLATE'],
            current_lifetime=str(db_lifetime.lifetime),
            map_lifetime=[('15', _('15 mins')),
                          ('30', _('30 mins')),
                          ('45', _('45 mins')),
                          ('60', _('60 mins')),
                          ('180', _('180 mins')),
                          ('360', _('360 mins')),
                          ('720', _('720 mins')),
                          ('1440', _('1440 mins'))]
        )
    except ValueError as valueErr:
        current_app.logger.error(
            'Could not convert data to an integer: {0}'.format(valueErr))
    except BaseException:
        current_app.logger.error('Unexpected error: ', sys.exc_info()[0])
        return abort(400)


@blueprint.route('/session/offline/info', methods=['GET'])
def session_info_offline():
    """Get session lifetime from app setting.

    :return: Session information offline in json.
    """
    current_app.logger.info('request session_info by offline')
    session_id = session.sid_s if hasattr(session, 'sid_s') else 'None'
    lifetime_str = str(current_app.config['PERMANENT_SESSION_LIFETIME'])
    return jsonify(user_id=current_user.get_id(),
                   session_id=session_id,
                   lifetime=lifetime_str,
                   _app_lifetime=str(_app.permanent_session_lifetime),
                   current_app_name=current_app.name)


@blueprint_api.route('/load_lang', methods=['GET'])
def get_lang_list():
    """Get Language List."""
    results = dict()
    try:
        results['results'] = get_admin_lang_setting()
        results['msg'] = 'success'
    except Exception as e:
        results['msg'] = str(e)

    return jsonify(results)


@blueprint_api.route('/save_lang', methods=['POST'])
def save_lang_list():
    """Save Language List."""
    if request.headers['Content-Type'] != 'application/json':
        current_app.logger.debug(request.headers['Content-Type'])
        return jsonify(msg='Header Error')
    data = request.get_json()
    result = update_admin_lang_setting(data)

    return jsonify(msg=result)


@blueprint_api.route('/get_selected_lang', methods=['GET'])
def get_selected_lang():
    """Get selected language."""
    try:
        result = get_selected_language()
    except Exception as e:
        result = {'error': str(e)}
    return jsonify(result)


@blueprint_api.route('/get_api_cert_type', methods=['GET'])
def get_api_cert_type():
    """Get list of supported API, to display on the combobox on UI.

    :return: Example
    {
        'result':[
        {
            'api_code': 'DOI',
            'api_name': 'CrossRef API'
        },
        {
            'api_code': 'AMA',
            'api_name': 'Amazon'
        }],
        'error':''
    }
    """
    result = {
        'results': '',
        'error': ''
    }
    try:
        result['results'] = get_api_certification_type()
    except Exception as e:
        result['error'] = str(e)
    return jsonify(result)


@blueprint_api.route('/get_curr_api_cert/<string:api_code>', methods=['GET'])
def get_curr_api_cert(api_code=''):
    """Get current API certification data, to display on textbox on UI.

    :param api_code: API code
    :return:
    {
        'results':
        {
            'api_code': 'DOI',
            'api_name': 'CrossRef API',
            'cert_data':
            {
                'account': 'abc@xyz.com'
            }
        },
        'error':''
    }
    """
    result = {
        'results': '',
        'error': ''
    }
    try:
        result['results'] = get_current_api_certification(api_code)
    except Exception as e:
        result['error'] = str(e)
    return jsonify(result)


@blueprint_api.route('/save_api_cert_data', methods=['POST'])
def save_api_cert_data():
    """Save api certification data to database.

    :return: Example
    {
        'results': true // true if save successfully
        'error':''
    }
    """
    result = dict()

    if request.headers['Content-Type'] != 'application/json':
        result['error'] = _('Header Error')
        return jsonify(result)

    data = request.get_json()
    api_code = data.get('api_code', '')
    cert_data = data.get('cert_data', '')
    if not cert_data:
        result['error'] = _(
            'Account information is invalid. Please check again.')
    elif validate_certification(cert_data):
        result = save_api_certification(api_code, cert_data)
    else:
        result['error'] = _(
            'Account information is invalid. Please check again.')

    return jsonify(result)


@blueprint_api.route('/get_init_selection/<string:selection>', methods=['GET'])
def get_init_selection(selection=""):
    """Get initial data for unit and target.

    :param selection:
    """
    result = dict()
    try:
        if selection == 'target':
            result = get_initial_stats_report()
        elif selection == "":
            raise ValueError("Request URL is incorrectly")
        else:
            result = get_unit_stats_report(selection)
    except Exception as e:
        result['error'] = str(e)

    return jsonify(result)


@blueprint_api.route("/search_email", methods=['POST'])
@login_required
def get_email_author():
    """Get all authors."""
    data = request.get_json()
    result = FeedbackMail.search_author_mail(data)

    return jsonify(result)


@blueprint_api.route('/update_feedback_mail', methods=['POST'])
def update_feedback_mail():
    """API allow to save feedback mail setting.

    Returns:
        json -- response result

    """
    result = {
        'success': '',
        'error': ''
    }
    root_url = request.url_root
    root_url = str(root_url).replace('/api/', '')
    data = request.get_json()
    response = FeedbackMail.update_feedback_email_setting(
        data.get('data', ''),
        data.get('is_sending_feedback', False),
        root_url)

    if not response.get('error'):
        result['success'] = True
        return jsonify(result)
    else:
        result['error'] = response.get('error')
        result['success'] = False
        return jsonify(result)


@blueprint_api.route('/get_feedback_mail', methods=['GET'])
def get_feedback_mail():
    """API allow get feedback email setting.

    Returns:
        json -- email settings

    """
    result = {
        'data': '',
        'is_sending_feedback': '',
        'error': ''
    }

    data = FeedbackMail.get_feed_back_email_setting()
    if data.get('error'):
        result['error'] = data.get('error')
        return jsonify(result)
    result['data'] = data.get('data')
    result['is_sending_feedback'] = data.get('is_sending_feedback')
    return jsonify(result)


@blueprint_api.route('/get_send_mail_history', methods=['GET'])
def get_send_mail_history():
    """API allow to get send mail history.

    Returns:
        json -- response list mail data if no error occurs

    """
    try:
        data = request.args
        page = int(data.get('page'))
    except Exception as ex:
        current_app.logger.debug('Cannot convert parameter', ex)
        page = 1
    result = FeedbackMail.load_feedback_mail_history(page)
    return jsonify(result)


@blueprint_api.route('/get_failed_mail', methods=['GET'])
def get_failed_mail():
    """Get list failed mail.

    Returns:
        json -- List data if no error occurs

    """
    try:
        data = request.args
        page = int(data.get('page'))
        history_id = int(data.get('id'))
    except Exception as ex:
        current_app.logger.debug('Cannot convert parameter', ex)
        page = 1
        history_id = 1
    result = FeedbackMail.load_feedback_failed_mail(history_id, page)
    return jsonify(result)


@blueprint_api.route('/resend_failed_mail', methods=['POST'])
def resend_failed_mail():
    """Resend failed mail.

    :return:
    """
    data = request.get_json()
    history_id = data.get('history_id')
    result = {
        'success': True,
        'error': ''
    }
    try:
        mail_data = FeedbackMail.get_mail_data_by_history_id(history_id)
        StatisticMail.send_mail_to_all(
            mail_data.get('data'),
            mail_data.get('stats_date')
        )
        FeedbackMail.update_history_after_resend(history_id)
    except Exception as ex:
        current_app.logger.debug('Cannot resend mail', ex)
        result['success'] = False
        result['error'] = 'Request package is invalid'
    return jsonify(result)


@blueprint_api.route('/sitelicensesendmail/send/<start_month>/<end_month>',
                     methods=['POST'])
def manual_send_site_license_mail(start_month, end_month):
    """Send site license mail by manual."""
    send_list = SiteLicenseInfo.query.filter_by(receive_mail_flag='T').all()
    if send_list:
        start_date = start_month + '-01'
        _, lastday = calendar.monthrange(int(end_month[:4]),
                                         int(end_month[5:]))
        end_date = end_month + '-' + str(lastday).zfill(2)

        agg_date = start_month.replace('-', '.') + '-' + \
            end_month.replace('-', '.')
        res = QueryCommonReportsHelper.get(start_date=start_date,
                                           end_date=end_date,
                                           event='site_access')
        for s in send_list:
            mail_list = s.mail_address.split('\n')
            send_flag = False
            for r in res['institution_name']:
                if s.organization_name == r['name']:
                    send_site_license_mail(r['name'], mail_list, agg_date, r)
                    send_flag = True
                    break
            if not send_flag:
                data = {'file_download': 0,
                        'file_preview': 0,
                        'record_view': 0,
                        'search': 0,
                        'top_view': 0}
                send_site_license_mail(s.organization_name,
                                       mail_list, agg_date, data)

        return 'finished'


@blueprint_api.route('/update_site_info', methods=['POST'])
@login_required
def update_site_info():
    """Update site info.

    :return: result

    """
    site_info = request.get_json()
    format_data = format_site_info_data(site_info)
    validate = validation_site_info(format_data)
    if validate.get('error'):
        return jsonify(validate)
    else:
        SiteInfo.update(format_data)
        return jsonify(format_data)


@blueprint_api.route('/get_site_info', methods=['GET'])
@login_required
def get_site_info():
    """Get site info.

    :return: result

    """
    site_info = SiteInfo.get()
    result = dict()
    if not site_info:
        return jsonify({})
    result['copy_right'] = site_info.copy_right
    result['description'] = site_info.description
    result['keyword'] = site_info.keyword
    result['favicon'] = site_info.favicon
    result['favicon_name'] = site_info.favicon_name
    result['site_name'] = site_info.site_name
    result['notify'] = site_info.notify
    return jsonify(result)


@blueprint_api.route('/favicon', methods=['GET'])
def get_avatar():
    """Get favicon.

    :return: result

    """
    import base64
    import io
    from werkzeug import FileWrapper
    site_info = SiteInfo.get()
    if not site_info:
        return jsonify({})
    favicon = site_info.favicon.split(',')[1]
    favicon = base64.b64decode(favicon)
    b = io.BytesIO(favicon)
    w = FileWrapper(b)
    return Response(b, mimetype="image/x-icon", direct_passthrough=True)


@blueprint_api.route('/search_control/display_control', methods=['GET'])
def display_control_function():
    """Get display control.

    :return: display_control.
    """
    display_control = get_search_setting().get("display_control")
    r = make_response(json.dumps(display_control))

    r.headers["Cache-Control"] = current_app.config.get(
        "WEKO_HEADER_NO_CACHE",
        WEKO_HEADER_NO_CACHE
    ).get("Cache-Control")
    r.headers["Pragma"] = current_app.config.get(
        "WEKO_HEADER_NO_CACHE",
        WEKO_HEADER_NO_CACHE
    ).get("Pragma")
    r.headers["Expires"] = current_app.config.get(
        "WEKO_HEADER_NO_CACHE",
        WEKO_HEADER_NO_CACHE
    ).get("Expires")

    return r
