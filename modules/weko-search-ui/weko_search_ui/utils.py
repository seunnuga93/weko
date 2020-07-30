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

"""Weko Search-UI admin."""

import base64
import json
import os
import shutil
import sys
import tempfile
import traceback
import uuid
from collections import defaultdict
from datetime import datetime
from functools import reduce
from operator import getitem

import bagit
from flask import abort, current_app, request
from flask_babelex import gettext as _
from invenio_db import db
from invenio_files_rest.models import ObjectVersion
from invenio_i18n.ext import current_i18n
from invenio_pidstore.errors import PIDDoesNotExistError
from invenio_pidstore.models import PersistentIdentifier
from invenio_records.api import Record
from invenio_records.models import RecordMetadata
from invenio_search import RecordsSearch
from jsonschema import Draft4Validator
from weko_deposit.api import WekoDeposit, WekoIndexer, WekoRecord
from weko_index_tree.api import Indexes
from weko_indextree_journal.api import Journals
from weko_records.api import ItemTypes
from weko_workflow.api import Flow, WorkActivity
from weko_workflow.models import FlowDefine, WorkFlow

from .config import WEKO_FLOW_DEFINE, WEKO_FLOW_DEFINE_LIST_ACTION, \
    WEKO_REPO_USER, WEKO_SYS_USER
from .query import feedback_email_search_factory, item_path_search_factory


def get_tree_items(index_tree_id):
    """Get tree items."""
    records_search = RecordsSearch()
    records_search = records_search.with_preference_param().params(
        version=False)
    records_search._index[0] = current_app.config['SEARCH_UI_SEARCH_INDEX']
    search_instance, qs_kwargs = item_path_search_factory(
        None, records_search, index_id=index_tree_id)
    search_result = search_instance.execute()
    rd = search_result.to_dict()
    return rd.get('hits').get('hits')


def delete_records(index_tree_id):
    """Bulk delete records."""
    hits = get_tree_items(index_tree_id)
    for hit in hits:
        recid = hit.get('_id')
        record = Record.get_record(recid)
        if record is not None and record['path'] is not None:
            paths = record['path']
            if len(paths) > 0:
                # Remove the element which matches the index_tree_id
                removed_path = None
                for path in paths:
                    if path.endswith(str(index_tree_id)):
                        removed_path = path
                        paths.remove(path)
                        break

                # Do update the path on record
                record.update({'path': paths})
                record.commit()
                db.session.commit()

                # Indexing
                indexer = WekoIndexer()
                indexer.update_path(record, update_revision=False)

                if len(paths) == 0 and removed_path is not None:
                    from weko_deposit.api import WekoDeposit
                    WekoDeposit.delete_by_index_tree_id(removed_path)
                    Record.get_record(recid).delete()  # flag as deleted
                    db.session.commit()  # terminate the transaction


def get_journal_info(index_id=0):
    """Get journal information.

    :argument
        index_id -- {int} index id
    :return: The object.

    """
    result = {}
    try:
        if index_id == 0:
            return None
        schema_file = os.path.join(
            os.path.abspath(__file__ + "/../../../"),
            'weko-indextree-journal/weko_indextree_journal',
            current_app.config['WEKO_INDEXTREE_JOURNAL_FORM_JSON_FILE'])
        schema_data = json.load(open(schema_file))

        cur_lang = current_i18n.language
        journal = Journals.get_journal_by_index_id(index_id)
        if len(journal) <= 0 or journal.get('is_output') is False:
            return None

        for value in schema_data:
            title = value.get('title_i18n')
            if title is not None:
                data = journal.get(value['key'])
                if data is not None and len(str(data)) > 0:
                    data_map = value.get('titleMap')
                    if data_map is not None:
                        res = [x['name']
                               for x in data_map if x['value'] == data]
                        data = res[0]
                    val = title.get(cur_lang) + '{0}{1}'.format(': ', data)
                    result.update({value['key']: val})
        open_search_uri = request.host_url + journal.get('title_url')
        result.update({'openSearchUrl': open_search_uri})

    except BaseException:
        current_app.logger.error('Unexpected error: ', sys.exc_info()[0])
        abort(500)
    return result


def get_feedback_mail_list():
    """Get tree items."""
    records_search = RecordsSearch()
    records_search = records_search.with_preference_param().params(
        version=False)
    records_search._index[0] = current_app.config['SEARCH_UI_SEARCH_INDEX']
    search_instance = feedback_email_search_factory(None, records_search)
    search_result = search_instance.execute()
    rd = search_result.to_dict()
    return rd.get('aggregations').get('feedback_mail_list')\
        .get('email_list').get('buckets')


def parse_feedback_mail_data(data):
    """Parse data."""
    result = {}
    if data is not None and isinstance(data, list):
        for author in data:
            if author.get('doc_count'):
                email = author.get('key')
                hits = author.get('top_tag_hits').get('hits').get('hits')
                result[email] = {
                    'author_id': '',
                    'item': []
                }
                for index in hits:
                    if not result[email]['author_id']:
                        result[email]['author_id'] = index.get(
                            '_source').get('author_id')
                    result[email]['item'].append(index.get('_id'))
    return result


def check_permission():
    """Check user login is repo_user or sys_user."""
    from flask_security import current_user
    is_permission_user = False
    for role in list(current_user.roles or []):
        if role == WEKO_SYS_USER or role == WEKO_REPO_USER:
            is_permission_user = True

    return is_permission_user


def get_content_workflow(item):
    """Get content workflow.

    :argument
        item    -- {Object PostgreSql} list work flow

    :return
        result  -- {dictionary} content of work flow

    """
    result = dict()
    result['flows_name'] = item.flows_name
    result['id'] = item.id
    result['itemtype_id'] = item.itemtype_id
    result['flow_id'] = item.flow_id
    result['flow_name'] = item.flow_define.flow_name
    result['item_type_name'] = item.itemtype.item_type_name.name

    return result


def set_nested_item(data_dict, map_list, val):
    """Set item in nested dictionary."""
    reduce(getitem, map_list[:-1], data_dict)[map_list[-1]] = val

    return data_dict


def convert_nested_item_to_list(data_dict, map_list):
    """Set item in nested dictionary."""
    a = reduce(getitem, map_list[:-1], data_dict)[map_list[-1]]
    a = list(a.values())
    reduce(getitem, map_list[:-1], data_dict)[map_list[-1]] = a

    return data_dict


def define_default_dict():
    """Define nested dict.

    :return
       return       -- {dict}.
    """
    return defaultdict(define_default_dict)


def defaultify(d: dict) -> dict:
    """Create default dict.

    :argument
        d            -- {dict} current dict.
    :return
        return       -- {dict} default dict.

    """
    if not isinstance(d, dict):
        return d
    return defaultdict(
        define_default_dict,
        {k: defaultify(v) for k, v in d.items()}
    )


def handle_generate_key_path(key) -> list:
    """Handle generate key path.

    :argument
        key     -- {string} string key.
    :return
        return       -- {list} list key path after convert.

    """
    key = key.replace(
        '#.',
        '.'
    ).replace(
        '[',
        '.'
    ).replace(
        ']',
        ''
    ).replace(
        '#',
        '.'
    )
    key_path = key.split(".")
    if len(key_path) > 0 and not key_path[0]:
        del key_path[0]

    return key_path


def parse_to_json_form(data: list) -> dict:
    """Parse set argument to json object.

    :argument
        data    -- {list zip} argument if json object.
    :return
        return  -- {dict} dict after convert argument.

    """
    result = defaultify({})

    def convert_data(pro, path=None):
        """Convert data."""
        if path is None:
            path = []

        term_path = path
        if isinstance(pro, dict):
            list_pro = list(pro.keys())
            for pro_name in list_pro:
                term = list(term_path)
                term.append(pro_name)
                convert_data(pro[pro_name], term)
            if list_pro[0].isnumeric():
                convert_nested_item_to_list(result, term_path)
        else:
            return

    for key, name, value in data:
        key_path = handle_generate_key_path(key)
        name_path = handle_generate_key_path(name)
        if value:
            a = handle_check_identifier(name_path)
            if not a:
                set_nested_item(result, key_path, value)
            else:
                set_nested_item(result, key_path, value)
                a += ' key'
                set_nested_item(result, [a], key_path[1])

    convert_data(result)
    result = json.loads(json.dumps(result))
    return result


def check_import_items(file_content: str):
    """Validation importing zip file.

    :argument
        file_content -- contetn file's name.
    :return
        return       -- PID object if exist.

    """
    file_content_decoded = base64.b64decode(file_content)
    temp_path = tempfile.TemporaryDirectory()
    save_path = "/tmp"

    try:
        # Create temp dir for import data
        import_path = temp_path.name + '/' + \
            datetime.utcnow().strftime(r'%Y%m%d%H%M%S')
        data_path = save_path + '/' + \
            datetime.utcnow().strftime(r'%Y%m%d%H%M%S')
        os.mkdir(data_path)

        with open(import_path + '.zip', 'wb+') as f:
            f.write(file_content_decoded)
        shutil.unpack_archive(import_path + '.zip', extract_dir=data_path)
        bag = bagit.Bag(data_path)

        # Valid importing zip file format
        if bag.is_valid():
            data_path += '/data'
            list_record = []
            for tsv_entry in os.listdir(data_path):
                if tsv_entry.endswith('.tsv'):
                    list_record.extend(
                        unpackage_import_file(data_path, tsv_entry))
            list_record = handle_check_exist_record(list_record)
            return {
                'list_record': list_record,
                'data_path': data_path
            }
        else:
            return {
                'error': 'Zip file is not follow Bagit format.'
            }
    except Exception:
        current_app.logger.error('-' * 60)
        traceback.print_exc(file=sys.stdout)
        current_app.logger.error('-' * 60)
    finally:
        temp_path.cleanup()


def unpackage_import_file(data_path: str, tsv_file_name: str) -> list:
    """Getting record data from TSV file.

    :argument
        file_content -- Content files.
    :return
        return       -- PID object if exist.

    """
    tsv_file_path = '{}/{}'.format(data_path, tsv_file_name)
    data = read_stats_tsv(tsv_file_path)
    list_record = handle_validate_item_import(data.get('tsv_data'), data.get(
        'item_type_schema', {}
    ))
    return list_record


def read_stats_tsv(tsv_file_path: str) -> dict:
    """Read importing TSV file.

    :argument
        tsv_file_path -- tsv file's url.
    :return
        return       -- PID object if exist.

    """
    result = {
        'error': False,
        'error_code': 0,
        'tsv_data': [],
        'item_type_schema': {}
    }
    tsv_data = []
    item_path = []
    item_path_name = []
    check_item_type = {},
    schema = ''
    with open(tsv_file_path, 'r') as tsvfile:
        for num, row in enumerate(tsvfile, start=1):
            data_row = row.rstrip('\n').split('\t')
            if num == 1:
                if data_row[-1] and data_row[-1].split('/')[-1]:
                    item_type_id = data_row[-1].split('/')[-1]
                    check_item_type = get_item_type(int(item_type_id))
                    schema = data_row[-1]
                    if not check_item_type:
                        result['item_type_schema'] = {}
                    else:
                        result['item_type_schema'] = check_item_type['schema']

            elif num == 2:
                item_path = data_row
            elif num == 3:
                item_path_name = data_row
            else:
                data_parse_metadata = parse_to_json_form(
                    zip(item_path, item_path_name, data_row)
                )

                json_data_parse = parse_to_json_form(
                    zip(item_path_name, item_path, data_row)
                )
                if isinstance(check_item_type, dict):
                    item_type_name = check_item_type.get('name')
                    item_type_id = check_item_type.get('item_type_id')
                    tsv_item = dict(
                        **json_data_parse,
                        **data_parse_metadata,
                        **{
                            'item_type_name': item_type_name or '',
                            'item_type_id': item_type_id or '',
                            '$schema': schema if schema else ''
                        }
                    )
                else:
                    tsv_item = dict(**json_data_parse, **data_parse_metadata)
                tsv_data.append(tsv_item)

    result['tsv_data'] = tsv_data
    return result


def handle_validate_item_import(list_recond, schema) -> list:
    """Validate item import.

    :argument
        list_recond     -- {list} list recond import.
        schema     -- {dict} item_type schema.
    :return
        return       -- list_item_error.

    """
    result = []
    v2 = Draft4Validator(schema) if schema else None
    for record in list_recond:
        errors = []
        record_id = record.get("id")
        if record_id and (not represents_int(record_id)):
            errors.append("Incorrect Item id")
        if record.get('metadata'):
            if v2:
                a = v2.iter_errors(record.get('metadata'))
                errors = errors + [error.message for error in a]
            else:
                errors = errors = errors + ['ItemType is not exist']
            record['metadata']['path'] = handle_replace_new_index()

        item_error = dict(**record, **{
            'errors': errors if len(errors) else None
        })
        result.append(item_error)

    return result


def represents_int(s):
    """Handle check string is int.

    :argument
        s     -- {str} string number.
    :return
        return       -- true if is Int.

    """
    try:
        int(s)
        return True
    except ValueError:
        return False


def handle_check_index(list_index: list) -> bool:
    """Handle check index.

    :argument
        list_index     -- {list} list index id.
    :return
        return       -- true if exist.

    """
    result = True

    index_lst = []
    if list_index:
        index_id_lst = []
        for index in list_index:
            indexes = str(index).split('/')
            index_id_lst.append(indexes[len(indexes) - 1])
        index_lst = index_id_lst

    plst = Indexes.get_path_list(index_lst)
    if not plst or len(index_lst) != len(plst):
        result = False
    return result


def get_item_type(item_type_id=0) -> dict:
    """Get item type.

    :param item_type_id: Item type ID. (Default: 0).
    :return: The json object.
    """
    result = None
    if item_type_id > 0:
        itemtype = ItemTypes.get_by_id(item_type_id)
        if itemtype and itemtype.schema \
                and itemtype.item_type_name.name and item_type_id:
            result = {
                'schema': itemtype.schema,
                'name': itemtype.item_type_name.name,
                'item_type_id': item_type_id
            }

    if result is None:
        return {}

    return result


def handle_check_exist_record(list_recond) -> list:
    """Check record is exist in system.

    :argument
        list_recond -- {list} list recond import.
    :return
        return      -- list record has property status.

    """
    result = []
    for item in list_recond:
        if not item.get('errors'):
            item = dict(**item, **{
                'status': 'new'
            })
            try:
                item_id = item.get('id')
                if item_id:
                    item_exist = WekoRecord.get_record_by_pid(item_id)
                    if item_exist:
                        if item_exist.pid.is_deleted():
                            item['status'] = None
                            item['errors'] = [_('Item already DELETED'
                                                ' in the system')]
                            result.append(item)
                            continue
                        else:
                            exist_url = request.url_root + \
                                'records/' + item_exist.get('recid')
                            if item.get('uri') == exist_url:
                                item['status'] = 'update'
                            else:
                                item['errors'] = ['URI of items are not match']
                                item['status'] = None
                else:
                    item['id'] = None
                    if item.get('uri'):
                        item['errors'] = ['Item has no ID but non-empty URI']
                        item['status'] = None
            except PIDDoesNotExistError:
                pass
            except BaseException:
                current_app.logger.error(
                    'Unexpected error: ',
                    sys.exc_info()[0]
                )
        if item.get('status') == 'new':
            handle_remove_identifier(item)
        result.append(item)
    return result


def handle_check_identifier(name) -> str:
    """Check data is Identifier of Identifier Registration.

    :argument
        name_path     -- {list} list name path.
    :return
        return       -- Name of key if is Identifier.

    """
    result = ''
    if 'Identifier' in name or 'Identifier Registration' in name:
        result = name[0]
    return result


def handle_remove_identifier(item) -> dict:
    """Remove Identifier of Identifier Registration.

    :argument
        item         -- Item.
    :return
        return       -- Item had been removed property.

    """
    if item and item.get('Identifier key'):
        del item['metadata'][item.get('Identifier key')]
        del item['Identifier key']
        del item['Identifier']
    if item and item.get('Identifier Registration key'):
        del item['metadata'][item.get('Identifier Registration key')]
        del item['Identifier Registration key']
        del item['Identifier Registration']
    return item


def compare_identifier(item, item_exist):
    """Compare data is Identifier.

    :argument
        item           -- {dict} item import.
        item_exist     -- {dict} item in system.
    :return
        return       -- Name of key if is Identifier.

    """
    if item.get('Identifier key'):
        item_iden = item.get('metadata', '').get(item.get('Identifier key'))
        item_exist_iden = item_exist.get(item.get(
            'Identifier key')).get('attribute_value_mlt')
        if len(item_iden) == len(item_exist_iden):
            list_dif = difference(item_iden, item_exist_iden)
            if list_dif:
                item['errors'] = ['Errors in Identifier']
                item['status'] = ''
        elif len(item_iden) > len(item_exist_iden):
            list_dif = difference(item_iden, item_exist_iden)
            for i in list_dif + item_iden:
                if i not in item_exist_iden:
                    try:
                        pids = [
                            k for k in i.values() if k != 'DOI' or k != 'HDL']
                        for pid in pids:
                            item_check = \
                                WekoRecord.get_record_by_pid(pid)
                            if item_check and item_check.id != item.id:
                                item['errors'] = ['Errors in Identifier']
                                item['status'] = ''
                    except BaseException:
                        current_app.logger.error('Unexpected error: ',
                                                 sys.exc_info()[0])
            if item['errors']:
                item['metadata'][item.get('Identifier key')] = list(set([
                    it for it in list_dif + item_iden
                ]))
        elif len(item_iden) < len(item_exist_iden):
            item['metadata'][item.get('Identifier key')] = item_exist_iden
    if item.get('uri'):
        pass
    return item


def make_stats_tsv(raw_stats, list_name):
    """Make TSV report file for stats."""
    import csv
    from io import StringIO
    tsv_output = StringIO()

    writer = csv.writer(tsv_output, delimiter='\t',
                        lineterminator="\n")

    writer.writerow(list_name)
    for item in raw_stats:
        term = []
        for name in list_name:
            term.append(item.get(name))
        writer.writerow(term)

    return tsv_output


def difference(list1, list2):
    """Make TSV report file for stats."""
    list_dif = [i for i in list1 + list2 if i not in list1 or i not in list2]
    return list_dif


def check_identifier_new(item):
    """Check data Identifier.

    :argument
        item           -- {dict} item import.
        item_exist     -- {dict} item in system.
    :return
        return       -- Name of key if is Identifier.

    """
    if item.get('Identifier key'):
        item_iden = item.get('metadata', '').get(item.get('Identifier key'))
        for it in item_iden:
            try:
                pids = [
                    k for k in it.values() if k != 'DOI' or k != 'HDL']
                for pid in pids:
                    item_check = \
                        WekoRecord.get_record_by_pid(pid)
                    if item_check and item_check.id != item.id:
                        item['errors'] = ['Errors in Identifier']
                        item['status'] = ''
            except BaseException:
                current_app.logger.error('Unexpected error: ',
                                         sys.exc_info()[0])
    return item


def create_deposit(item_id):
    """Create deposit.

    :argument
        item           -- {dict} item import.
        item_exist     -- {dict} item in system.

    """
    try:
        if item_id is not None:
            dep = WekoDeposit.create({}, recid=int(item_id))
            db.session.commit()
        else:
            dep = WekoDeposit.create({})
            db.session.commit()
        return dep['recid']
    except Exception:
        db.session.rollback()


def up_load_file_content(record, root_path):
    """Upload file content.

    :argument
        record         -- {dict} item import.
        root_path      -- {str} root_path.

    """
    try:
        file_path = record.get('file_path')
        if file_path:
            pid = PersistentIdentifier.query.filter_by(
                pid_type='recid',
                pid_value=record.get('id')).first()
            rec = RecordMetadata.query.filter_by(
                id=pid.object_uuid).first()
            bucket = rec.json['_buckets']['deposit']
            for file_name in file_path:
                with open(root_path + '/' + file_name, 'rb') as file:
                    obj = ObjectVersion.create(
                        bucket,
                        get_file_name(file_name)
                    )
                    obj.set_contents(file)
                    db.session.commit()
    except Exception:
        db.session.rollback()


def get_file_name(file_path):
    """Get file name.

    :argument
        file_path    -- {str} file_path.
    :returns         -- {str} file name

    """
    return file_path.split('/')[-1] if file_path.split('/')[-1] else ''


def register_item_metadata(item):
    """Upload file content.

    :argument
        list_record    -- {list} list item import.
        file_path      -- {str} file path.
    """
    item_id = str(item.get('id'))
    try:
        pid = PersistentIdentifier.query.filter_by(
            pid_type='recid',
            pid_value=item_id
        ).first()

        record = WekoDeposit.get_record(pid.object_uuid)

        _deposit_data = record.dumps().get("_deposit")
        deposit = WekoDeposit(record, record.model)
        new_data = dict(
            **item.get('metadata'),
            **_deposit_data,
            **{
                '$schema': item.get('$schema'),
                'title': handle_get_title(item.get('Title')),
            }
        )
        item_status = {
            'index': new_data['path'],
            'actions': 'publish',
        }
        if not new_data.get('pid'):
            new_data = dict(**new_data, **{
                'pid': {
                    'revision_id': 0,
                    'type': 'recid',
                    'value': item_id
                }
            })
        deposit.update(item_status, new_data)
        deposit.commit()
        deposit.publish()
        with current_app.test_request_context():
            first_ver = deposit.newversion(pid)
            if first_ver:
                first_ver.publish()
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        current_app.logger.error('item id: %s update error.' % item_id)
        current_app.logger.error(ex)
        return {
            'success': False,
            'error': str(ex)
        }
    return {
        'success': True
    }


def handle_get_title(title) -> str:
    """Handle get title.

    :argument
        title           -- {dict or list} title.
    :return
        return       -- title string.

    """
    if isinstance(title, dict):
        return title.get('Title', '')
    elif isinstance(title, list):
        return title[0].get('Title') if title[0] \
            and isinstance(title[0], dict) else ''


def handle_workflow(item: dict):
    """Handle workflow.

    :argument
        title           -- {dict or list} title.
    :return
        return       -- title string.

    """
    pid = PersistentIdentifier.query.filter_by(
        pid_type='recid', pid_value=item.get('id')).first()
    if pid:
        activity = WorkActivity()
        wf_activity = activity.get_workflow_activity_by_item_id(
            pid.object_uuid)
        if wf_activity:
            return
    else:
        workflow = WorkFlow.query.filter_by(
            itemtype_id=item.get('item_type_id')).first()
        if workflow:
            return
        else:
            create_work_flow(item.get('item_type_id'))


def create_work_flow(item_type_id):
    """Handle create work flow.

    :argument
        item_type_id        -- {str} item_type_id.
    :return

    """
    flow_define = FlowDefine.query.filter_by(
        flow_name='Registration Flow').first()
    it = ItemTypes.get_by_id(item_type_id)

    if flow_define and it:
        try:
            data = WorkFlow()
            data.flows_id = uuid.uuid4()
            data.flows_name = it.item_type_name.name
            data.itemtype_id = it.id
            data.flow_id = flow_define.id
            db.session.add(data)
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            current_app.logger.error("create work flow error")
            current_app.logger.error(ex)


def create_flow_define():
    """Handle create flow_define."""
    flow_define = FlowDefine.query.filter_by(
        flow_name='Registration Flow').first()

    if not flow_define:
        the_flow = Flow()
        flow = the_flow.create_flow(WEKO_FLOW_DEFINE)

        if flow and flow.flow_id:
            the_flow.upt_flow_action(flow.flow_id,
                                     WEKO_FLOW_DEFINE_LIST_ACTION)


def import_items_to_system(item: dict):
    """Validation importing zip file.

    :argument
        item        -- Items Metadata.
    :return
        return      -- PID object if exist.

    """
    if not item:
        return None
    else:
        root_path = item.get('root_path', '')
        if item.get('status') == 'new':
            item_id = create_deposit(item.get('id'))
            item['id'] = item_id
        up_load_file_content(item, root_path)
        response = register_item_metadata(item)

        return response


def remove_temp_dir(path):
    """Validation importing zip file.

    :argument
        path     -- {string} path temp_dir.
    :return

    """
    shutil.rmtree(str(path.replace("/data", "")))


def handle_replace_new_index() -> list:
    """Validation importing zip file.

    :argument
    :return
        return       -- index id import item

    """
    from datetime import datetime
    now = datetime.now()
    index_import = Indexes.get_index_by_name("Index_import")
    if index_import:
        return [index_import.id]
    else:
        create_index = Indexes.create(
            pid=0,
            indexes={'id': int(datetime.timestamp(now) * 10 ** 3),
                     'value': 'Index_import'}
        )
        if create_index:
            index_import = Indexes.get_index_by_name("Index_import")
            if index_import:
                return [index_import.id]
        return []
