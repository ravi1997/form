"""
tests/test_analysis_engine.py
-----------------------------
Unit tests for the Flask Form Analyser query pipelines using mongomock.
"""

from __future__ import annotations
import mongomock
import pytest
from analysis_engine import run_analysis

@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    db = client.form_analyser_test
    
    # Seed mock form responses
    db.form_responses.insert_many([
        # Org 1 responses
        {
            "organization_id": "org_1",
            "satisfaction": "Very Satisfied",
            "score": 10,
            "region": "North",
            "data": {
                "preferred_features": ["Speed", "Ease"]
            }
        },
        {
            "organization_id": "org_1",
            "satisfaction": "Very Satisfied",
            "score": 9,
            "region": "North",
            "data": {
                "preferred_features": ["Speed"]
            }
        },
        {
            "organization_id": "org_1",
            "satisfaction": "Neutral",
            "score": 7,
            "region": "South",
            "data": {
                "preferred_features": ["Ease"]
            }
        },
        {
            "organization_id": "org_1",
            "satisfaction": "Very Dissatisfied",
            "score": 2,
            "region": "South",
            "data": {
                "preferred_features": []
            }
        },
        # Org 2 response (isolation check)
        {
            "organization_id": "org_2",
            "satisfaction": "Very Satisfied",
            "score": 10,
            "region": "North",
            "data": {
                "preferred_features": ["Speed"]
            }
        }
    ])
    return db


def test_frequency_step(mock_db):
    analysis_def = {
        "name": "Satisfaction Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "sat_freq",
                "type": "frequency",
                "field": "satisfaction",
                "label": "Satisfaction breakdown"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    assert result["total_matching_responses"] == 4
    
    step_res = result["results"]["sat_freq"]
    assert step_res["type"] == "frequency"
    
    breakdown = {item["value"]: item["count"] for item in step_res["breakdown"]}
    assert breakdown["Very Satisfied"] == 2
    assert breakdown["Neutral"] == 1
    assert breakdown["Very Dissatisfied"] == 1


def test_aggregate_step(mock_db):
    analysis_def = {
        "name": "Score Avg Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "score_avg",
                "type": "aggregate",
                "field": "score",
                "operation": "avg"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["score_avg"]
    
    assert step_res["type"] == "aggregate"
    # Average score = (10 + 9 + 7 + 2) / 4 = 7.0
    assert step_res["result"] == 7.0


def test_nps_step(mock_db):
    analysis_def = {
        "name": "NPS Evaluation Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "score_nps",
                "type": "nps",
                "field": "score"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["score_nps"]
    
    assert step_res["type"] == "nps"
    # 2 Promoters (10, 9), 1 Passive (7), 1 Detractor (2)
    # Promoters = 50.0%, Detractors = 25.0%
    # NPS = 50.0 - 25.0 = 25.0
    assert step_res["nps_score"] == 25.0
    assert step_res["promoters"]["count"] == 2
    assert step_res["detractors"]["count"] == 1


def test_crosstab_step(mock_db):
    analysis_def = {
        "name": "Satisfaction by Region Crosstab Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "sat_by_region",
                "type": "crosstab",
                "row_field": "satisfaction",
                "col_field": "region"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["sat_by_region"]
    
    assert step_res["type"] == "crosstab"
    assert "North" in step_res["columns"]
    assert "South" in step_res["columns"]
    
    rows = {r["_row"]: r for r in step_res["rows"]}
    assert rows["Very Satisfied"]["North"] == 2
    assert rows["Neutral"]["South"] == 1
    assert rows["Very Dissatisfied"]["South"] == 1


def test_summarize_step(mock_db):
    analysis_def = {
        "name": "Summarize Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "score_summary",
                "type": "summarize",
                "field": "score"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["score_summary"]
    
    assert step_res["type"] == "summarize"
    assert step_res["count"] == 4
    assert step_res["mean"] == 7.0
    assert step_res["min"] == 2.0
    assert step_res["max"] == 10.0
    assert "percentiles" in step_res


def test_tabulate_chi2_step(mock_db):
    analysis_def = {
        "name": "Chi2 Tabulate Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "sat_by_region_chi2",
                "type": "tabulate_chi2",
                "row_field": "satisfaction",
                "col_field": "region"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["sat_by_region_chi2"]
    
    assert step_res["type"] == "tabulate_chi2"
    assert "chi2" in step_res
    assert step_res["chi2"]["df"] == 2


def test_regress_step(mock_db):
    # Seed extra data for regression (needs at least 3 distinct records)
    # The default mock_db already has 4 records matching org_1:
    # y = score (10, 9, 7, 2), x = score (can reg score on score for simple test)
    analysis_def = {
        "name": "Regression Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "score_on_score",
                "type": "regress",
                "field_y": "score",
                "field_x": "score"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["score_on_score"]
    
    assert step_res["type"] == "regress"
    assert step_res["observations"] == 4
    # Coefficient on itself should be 1.0
    assert step_res["coefficients"]["slope"]["coef"] == 1.0
    assert step_res["r_squared"] == 1.0


def test_ttest_step(mock_db):
    analysis_def = {
        "name": "ttest Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "score_by_region",
                "type": "ttest",
                "field": "score",
                "group_field": "region"
            }
        ]
    }
    
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["score_by_region"]
    
    assert step_res["type"] == "ttest"
    assert "welch_ttest" in step_res
    assert "North" in step_res["groups"]
    assert "South" in step_res["groups"]


def test_pwcorr_step(mock_db):
    analysis_def = {
        "name": "pwcorr Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "score_corr",
                "type": "pwcorr",
                "fields": ["score", "score"],
                "sig": True
            }
        ]
    }
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["score_corr"]
    
    assert step_res["type"] == "pwcorr"
    assert "matrix" in step_res
    assert step_res["matrix"]["score"]["score"]["coef"] == 1.0
    assert step_res["matrix"]["score"]["score"]["p_value"] == 0.0


def test_tabstat_step(mock_db):
    analysis_def = {
        "name": "tabstat Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "score_tabstat",
                "type": "tabstat",
                "fields": ["score"],
                "by": "region",
                "statistics": ["mean", "count", "sd", "min", "max"]
            }
        ]
    }
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["score_tabstat"]
    
    assert step_res["type"] == "tabstat"
    assert "North" in step_res["results"]
    assert "South" in step_res["results"]
    assert step_res["results"]["North"]["score"]["mean"] == 9.5
    assert step_res["results"]["North"]["score"]["count"] == 2
    assert step_res["results"]["South"]["score"]["mean"] == 4.5
    assert step_res["results"]["South"]["score"]["count"] == 2


def test_codebook_step(mock_db):
    analysis_def = {
        "name": "codebook Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "profile",
                "type": "codebook",
                "fields": ["score", "satisfaction"]
            }
        ]
    }
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["profile"]
    
    assert step_res["type"] == "codebook"
    assert "score" in step_res["fields"]
    assert "satisfaction" in step_res["fields"]
    
    assert step_res["fields"]["score"]["data_type"] == "numeric"
    assert step_res["fields"]["score"]["obs"] == 4
    assert step_res["fields"]["score"]["numeric_stats"]["mean"] == 7.0
    
    assert step_res["fields"]["satisfaction"]["data_type"] == "string"
    assert len(step_res["fields"]["satisfaction"]["frequencies"]) > 0


def test_oneway_anova_step(mock_db):
    analysis_def = {
        "name": "ANOVA Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "anova_res",
                "type": "oneway_anova",
                "field": "score",
                "group_field": "region"
            }
        ]
    }
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["anova_res"]
    
    assert step_res["type"] == "oneway_anova"
    assert "anova_table" in step_res
    # Between df = k-1 = 2-1 = 1
    assert step_res["anova_table"]["between"]["df"] == 1
    # Within df = N-k = 4-2 = 2
    assert step_res["anova_table"]["within"]["df"] == 2
    # Total df = N-1 = 3
    assert step_res["anova_table"]["total"]["df"] == 3
    # Check overall presence of statistic and p_value
    assert "f_statistic" in step_res
    assert "p_value" in step_res


def test_multiple_regression_and_hettest(mock_db):
    analysis_def = {
        "name": "Multiple Regression Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "multi_reg",
                "type": "regress",
                "field_y": "score",
                "fields_x": ["score"],
                "hettest": True
            }
        ]
    }
    result = run_analysis(mock_db, analysis_def)
    step_res = result["results"]["multi_reg"]
    
    assert step_res["type"] == "regress"
    assert "score" in step_res["coefficients"]
    assert "intercept" in step_res["coefficients"]
    assert "hettest" in step_res
    assert step_res["hettest"]["df"] == 1
    assert "lm_statistic" in step_res["hettest"]


def test_transformations_in_pipeline(mock_db):
    analysis_def = {
        "name": "Transformation Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "transformations": [
            {
                "field": "score_centered",
                "operation": "center",
                "source_field": "score"
            },
            {
                "field": "is_north",
                "operation": "recode",
                "source_field": "region",
                "map": {
                    "North": 1,
                    "South": 0
                },
                "default": 0
            }
        ],
        "steps": [
            {
                "id": "centered_summary",
                "type": "summarize",
                "field": "score_centered"
            },
            {
                "id": "north_freq",
                "type": "frequency",
                "field": "is_north"
            }
        ]
    }
    result = run_analysis(mock_db, analysis_def)
    
    # score values are 10, 9, 7, 2 -> mean is 7.0
    # centered values are 3.0, 2.0, 0.0, -5.0
    centered_res = result["results"]["centered_summary"]
    assert centered_res["type"] == "summarize"
    assert centered_res["mean"] == 0.0  # Centered mean is exactly 0
    assert centered_res["min"] == -5.0
    assert centered_res["max"] == 3.0
    
    # regions are North, North, South, South -> is_north is 1, 1, 0, 0
    freq_res = result["results"]["north_freq"]
    breakdown = {item["value"]: item["count"] for item in freq_res["breakdown"]}
    assert breakdown[1] == 2
    assert breakdown[0] == 2


def test_exports_csv_pdf(mock_db):
    from exporter import export_to_csv, export_to_pdf
    analysis_def = {
        "name": "Export Check",
        "source_collection": "form_responses",
        "filters": [
            {"field": "organization_id", "operator": "eq", "value": "org_1"}
        ],
        "steps": [
            {
                "id": "summarize",
                "type": "summarize",
                "field": "score"
            },
            {
                "id": "chi2",
                "type": "tabulate_chi2",
                "row_field": "satisfaction",
                "col_field": "region"
            },
            {
                "id": "regress",
                "type": "regress",
                "field_y": "score",
                "fields_x": ["score"],
                "hettest": True
            },
            {
                "id": "ttest",
                "type": "ttest",
                "field": "score",
                "group_field": "region"
            },
            {
                "id": "pwcorr",
                "type": "pwcorr",
                "fields": ["score", "score"]
            },
            {
                "id": "tabstat",
                "type": "tabstat",
                "fields": ["score"],
                "by": "region"
            },
            {
                "id": "codebook",
                "type": "codebook",
                "fields": ["score", "satisfaction"]
            },
            {
                "id": "oneway",
                "type": "oneway_anova",
                "field": "score",
                "group_field": "region"
            }
        ]
    }
    result = run_analysis(mock_db, analysis_def)
    csv_bytes = export_to_csv(result)
    assert len(csv_bytes) > 0
    pdf_bytes = export_to_pdf(result)
    assert len(pdf_bytes) > 0




