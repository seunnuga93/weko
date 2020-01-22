from pytest_invenio.fixtures import database, app
from mock import mock, patch
from weko_workflow.models import WorkFlow,Action
from weko_records.api import ItemsMetadata
from helpers import login_user_via_session, insert_user_to_db

def side_effect_activity(*args, **kwargs):
    from weko_workflow.models import Activity
    from datetime import datetime

    activity_result = Activity()
    activity_result.workflow_id = '132'
    activity_result.activity_confirm_term_of_use = False

    action_item_registration = Action()
    action_item_registration.id = 8
    action_item_registration.action_endpoint = 'item_login'
    action_item_registration.action_is_need_agree = True

    activity_result.action = action_item_registration
    activity_result.activity_start = datetime.utcnow()
    activity_result.updated = datetime.utcnow()
    return activity_result


def side_effect_steps(*args, **kwargs):
    return [{'ActionEndpoint': 'begin_action', 'ActionName': 'Start', 'ActivityId': 'A-20191217-00004',
             'Author': 'info@inveniosoftware.org', 'Status': 'action_done', 'ActionId': 1, 'ActionVersion': '1.0.0'},
            {'ActionEndpoint': 'item_login', 'ActionName': 'Item Registration for Usage Application', 'ActivityId': 'A-20191217-00004',
             'Author': 'info@inveniosoftware.org', 'Status': 'action_done', 'ActionId': 8, 'ActionVersion': '1.0.1'},
            {'ActionEndpoint': 'approval_advisor', 'ActionName': 'Adivisor Approval', 'ActivityId': 'A-20191217-00004',
             'Author': '', 'Status': ' ', 'ActionId': 9, 'ActionVersion': '1.0.0'},
            {'ActionEndpoint': 'approval_guarantor', 'ActionName': 'Guarantor Approval',
             'ActivityId': 'A-20191217-00004clear', 'Author': '', 'Status': ' ', 'ActionId': 10,
             'ActionVersion': '1.0.0'}]



# def test_display_activity(app, database, client):
#     #login before making request
#     insert_user_to_db(database)
#     login_user_via_session(client, 1)

#     mock_workflow = mock.MagicMock()
#     temp_WF = WorkFlow()
#     temp_WF.index_tree_id = 'ABC123'
#     temp_WF.id = '123'
#     mock_workflow.return_value.get_workflow_by_id.return_value = temp_WF

#     mock_work_activity = mock.MagicMock()
#     mock_work_activity.return_value.get_activity_detail = side_effect_activity
#     mock_work_activity.return_value.get_activity_steps = side_effect_steps

#     steps = 'step_item_login_url', 'need_file', 'record', 'json_schema', 'schema_form', 'item_save_uri', 'files', 'endpoints', 'need_thumbnail', 'files_thumbnail','allow_multi_thumbnail'

#     with mock.patch('weko_workflow.views.WorkFlow', m), \
#          mock.patch('weko_workflow.views.WorkActivity', m2), \
#          patch.object(ItemsMetadata, 'get_record', return_value=None), \
#          mock.patch('weko_workflow.views.check_authority_action', return_value=1), \
#          mock.patch('weko_workflow.views.get_item_type_name', return_value='item_type_name'), \
#          mock.patch('weko_workflow.views.item_login', return_value=steps), \
#          mock.patch('weko_workflow.views.is_need_to_show_agreement_page', return_value=True), \
#          mock.patch('weko_workflow.views.get_term_and_condition_content', return_value="123"), \
#          mock.patch('weko_workflow.views.check_JGSS_item_type', return_value="123"), \
#          mock.patch('weko_workflow.views.get_index_id', return_value="123"):
#         res = client.post('/workflow/activity/detail/A-20191217-00001?status=ToDo')
#         assert res.status_code == 200

# def test_display_activity2(app, database, client):
#     #login before making request
#     insert_user_to_db(database)
#     login_user_via_session(client, 1)
#     insert_flow_activity_action(database)
#     res = client.post('/workflow/activity/detail/A-20200108-00100?status=ToDo')
#     assert res.status_code == 200

def insert_flow_activity_action(database):
    flow_id = "ed1fc1a1-db3d-450c-a093-b85e63d3d647"
    item_id = "f7ab31d0-f401-4e60-adc9-000000000111"
    record = {'item_1574156725144': {'subitem_usage_location': 'sage location', 'pubdate': '2019-12-08',
                                     '$schema': '/items/jsonschema/19', 'title': 'username'}}
    from helpers import insert_activity,insert_flow,insert_record_metadata,insert_workflow,insert_action_to_db,insert_flow_action,insert_item_type_name,insert_item_type
    insert_record_metadata(database,item_id,record)
    insert_flow(database,1,flow_id,"Flow Name",1,"A")
    insert_item_type_name(database,"Item_Type_Name",True,True)
    insert_item_type(database,1,{},{},{},1,1,True)
    insert_action_to_db(database)
    #Insert a flow contain 5 steps
    insert_flow_action(database,flow_id,1,1)
    insert_flow_action(database,flow_id,2,5)
    insert_flow_action(database,flow_id,8,2)
    insert_flow_action(database,flow_id,9,3)
    insert_flow_action(database,flow_id,11,4)
    insert_workflow(database,1,flow_id,"Flow Name",1,1,1)
    insert_activity(database,"A-20200108-00100",item_id,1,1,False)

def test_init_activity(app, database, client, es_clear):
    insert_user_to_db(database)
    login_user_via_session(client, 1)
    from weko_workflow.models import Activity
    item_title = "JGSS_Data"
    expect_result = b'JGSS_Data'
    post_data = Activity(
                activity_id='A-20200108-00100',
                item_id= 1,
                workflow_id= 1,
                flow_id= 1,
                action_id=1,
            )
    with mock.patch('weko_workflow.api.WorkActivity.init_activity', return_value= post_data):
        res = client.post('/workflow/activity/init?itemtitle='+item_title)
        assert expect_result in res.data
    