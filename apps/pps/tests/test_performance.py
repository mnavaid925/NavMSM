"""Query-budget tests — list pages must not regress on N+1."""
import pytest


@pytest.mark.django_db
class TestQueryBudget:
    def test_orders_list_query_budget(self, admin_client, django_assert_max_num_queries):
        with django_assert_max_num_queries(15):
            r = admin_client.get('/pps/orders/')
        assert r.status_code == 200

    def test_routings_list_query_budget(self, admin_client, django_assert_max_num_queries):
        with django_assert_max_num_queries(15):
            r = admin_client.get('/pps/routings/')
        assert r.status_code == 200

    def test_work_centers_list_query_budget(self, admin_client, django_assert_max_num_queries):
        with django_assert_max_num_queries(15):
            r = admin_client.get('/pps/work-centers/')
        assert r.status_code == 200
