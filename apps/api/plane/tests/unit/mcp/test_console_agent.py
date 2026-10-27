import base64

import pytest

from scripts.mcp_console import MAX_FILE_BYTES, _file_input, _response_text


def test_file_input_preserves_valid_data_url():
    encoded = base64.b64encode(b"hello plane").decode("ascii")

    result = _file_input(
        {
            "name": "notes.txt",
            "mimeType": "text/plain",
            "dataUrl": f"data:text/plain;base64,{encoded}",
        }
    )

    assert result == {
        "type": "input_file",
        "filename": "notes.txt",
        "file_data": f"data:text/plain;base64,{encoded}",
    }


def test_file_input_rejects_files_over_api_limit():
    oversized_base64 = "a" * (((MAX_FILE_BYTES + 1) * 4 // 3) + 4)

    with pytest.raises(ValueError, match="50 MB"):
        _file_input(
            {
                "name": "large.pdf",
                "mimeType": "application/pdf",
                "dataUrl": f"data:application/pdf;base64,{oversized_base64}",
            }
        )


def test_response_text_collects_output_message_parts():
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Đã tạo công việc."},
                    {"type": "refusal", "refusal": ""},
                ],
            }
        ]
    }

    assert _response_text(response) == "Đã tạo công việc."
