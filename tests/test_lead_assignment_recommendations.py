from app.services.lead_assignment_recommendations import recommend_lead_assignees


def test_recommendations_rank_lowest_workload_first_and_explain_reason():
    lead = {"id": 12, "assigned_user_id": None}
    candidates = [
        {"id": 1, "username": "Asha", "role": "TELECALLER", "is_active": True},
        {"id": 2, "username": "Bharat", "role": "SALES_EXECUTIVE", "is_active": True},
    ]

    result = recommend_lead_assignees(lead, candidates, {1: 9, 2: 2})

    assert [item["user_id"] for item in result] == [2, 1]
    assert result[0]["open_lead_count"] == 2
    assert any("approval required" in reason for reason in result[0]["reasons"])


def test_recommendations_exclude_inactive_ineligible_and_current_owner():
    lead = {"id": 12, "assigned_user_id": 1}
    candidates = [
        {"id": 1, "username": "Current", "role": "TELECALLER", "is_active": True},
        {"id": 2, "username": "Inactive", "role": "TELECALLER", "is_active": False},
        {"id": 3, "username": "Accountant", "role": "ACCOUNTANT", "is_active": True},
    ]

    assert recommend_lead_assignees(lead, candidates, {}) == []


def test_recommendations_are_deterministic_and_limit_is_respected():
    lead = {"id": 1, "assigned_user_id": None}
    candidates = [
        {"id": 4, "username": "Zara", "role": "TELECALLER", "is_active": True},
        {"id": 3, "username": "Aman", "role": "SALES_EXECUTIVE", "is_active": True},
        {"id": 2, "username": "Aman", "role": "TELECALLER", "is_active": True},
    ]

    result = recommend_lead_assignees(lead, candidates, {}, limit=2)

    assert [item["user_id"] for item in result] == [2, 3]
    assert recommend_lead_assignees(lead, candidates, {}, limit=0) == []
