try:
    from validator import build_question_index, minimal_form_snapshot, validate_response_payload
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from validator import build_question_index, minimal_form_snapshot, validate_response_payload
