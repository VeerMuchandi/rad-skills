# a2ui_examples.py

GREETING_EXAMPLE = r"""
[
  { "beginRendering": { "surfaceId": "main", "root": "root_card" } },
  {
    "surfaceUpdate": {
      "surfaceId": "main",
      "components": [
        { "id": "root_card", "component": { "Card": { "child": "card_col" } } },
        { "id": "card_col", "component": { "Column": { "children": { "explicitList": ["greeting_txt", "specialty_tf", "zip_tf", "search_btn_row"] } } } },
        { "id": "greeting_txt", "component": { "Text": { "text": { "literalString": "Hello! I am your CareConnect Navigator. I can help you find doctors and book appointments in the Greater Atlanta area." }, "usageHint": "h2" } } },
        { "id": "specialty_tf", "component": { "TextField": { "label": { "literalString": "Specialty (e.g., Dermatology)" }, "text": {"path": "specialty"} } } },
        { "id": "zip_tf", "component": { "TextField": { "label": { "literalString": "Zip Code (e.g., 30303)" }, "text": {"path": "zip_code"} } } },
        { "id": "search_btn_row", "component": { "Row": { "children": { "explicitList": ["search_btn"] }, "distribution": "end" } } },
        { "id": "search_btn", "component": { "Button": { "child": "search_btn_txt", "primary": true, "action": { "name": "submit", "context": [{"key": "message", "value": {"literalString": "Search for doctors."}}, {"key": "specialty", "value": {"path": "specialty"}}, {"key": "zip_code", "value": {"path": "zip_code"}}] } } } },
        { "id": "search_btn_txt", "component": { "Text": { "text": { "literalString": "Find Doctors" } } } }
      ]
    }
  },
  { "dataModelUpdate": { "surfaceId": "main", "path": "/", "contents": [ { "key": "specialty", "valueString": "" }, { "key": "zip_code", "valueString": "" } ] } }
]
"""

PROVIDER_RESULTS_EXAMPLE = r"""
[
  { "beginRendering": { "surfaceId": "results", "root": "results_col" } },
  {
    "surfaceUpdate": {
      "surfaceId": "results",
      "components": [
        { "id": "results_col", "component": { "Column": { "children": { "explicitList": ["results_title", "provider_list"] } } } },
        { "id": "results_title", "component": { "Text": { "text": { "literalString": "Here are the providers I found:" }, "usageHint": "h3" } } },
        { "id": "provider_list", "component": { "List": { "direction": "vertical", "children": { "explicitList": ["p1_card", "p2_card"] } } } },
        
        { "id": "p1_card", "component": { "Card": { "child": "p1_col" } } },
        { "id": "p1_col", "component": { "Column": { "children": { "explicitList": ["p1_name", "p1_specialty", "p1_zip", "p1_book_btn"] } } } },
        { "id": "p1_name", "component": { "Text": { "text": { "literalString": "Dr. Smith" }, "usageHint": "h4" } } },
        { "id": "p1_specialty", "component": { "Text": { "text": { "literalString": "Dermatology" } } } },
        { "id": "p1_zip", "component": { "Text": { "text": { "literalString": "Zip: 30303" } } } },
        { "id": "p1_book_btn", "component": { "Button": { "child": "p1_book_txt", "action": { "name": "submit", "context": [{"key": "message", "value": {"literalString": "I want to book Dr. Smith."}}, {"key": "provider_id", "value": {"literalString": "p1"}}] } } } },
        { "id": "p1_book_txt", "component": { "Text": { "text": { "literalString": "Select & Book" } } } },

        { "id": "p2_card", "component": { "Card": { "child": "p2_col" } } },
        { "id": "p2_col", "component": { "Column": { "children": { "explicitList": ["p2_name", "p2_specialty", "p2_zip", "p2_book_btn"] } } } },
        { "id": "p2_name", "component": { "Text": { "text": { "literalString": "Dr. Jones" }, "usageHint": "h4" } } },
        { "id": "p2_specialty", "component": { "Text": { "text": { "literalString": "Dermatology" } } } },
        { "id": "p2_zip", "component": { "Text": { "text": { "literalString": "Zip: 30303" } } } },
        { "id": "p2_book_btn", "component": { "Button": { "child": "p2_book_txt", "action": { "name": "submit", "context": [{"key": "message", "value": {"literalString": "I want to book Dr. Jones."}}, {"key": "provider_id", "value": {"literalString": "p2"}}] } } } },
        { "id": "p2_book_txt", "component": { "Text": { "text": { "literalString": "Select & Book" } } } }
      ]
    }
  }
]
"""

BOOKING_CONFIRMATION_EXAMPLE = r"""
[
  { "beginRendering": { "surfaceId": "confirmation", "root": "confirm_card" } },
  {
    "surfaceUpdate": {
      "surfaceId": "confirmation",
      "components": [
        { "id": "confirm_card", "component": { "Card": { "child": "confirm_col" } } },
        { "id": "confirm_col", "component": { "Column": { "children": { "explicitList": ["confirm_title", "confirm_details", "final_book_btn"] } } } },
        { "id": "confirm_title", "component": { "Text": { "text": { "literalString": "Confirm Appointment" }, "usageHint": "h3" } } },
        { "id": "confirm_details", "component": { "Text": { "text": { "literalString": "Dr. Smith for Dermatology in 30303." } } } },
        { "id": "final_book_btn", "component": { "Button": { "child": "final_book_txt", "primary": true, "action": { "name": "submit", "context": [{"key": "message", "value": {"literalString": "Confirm booking."}}] } } } },
        { "id": "final_book_txt", "component": { "Text": { "text": { "literalString": "Confirm Booking" } } } }
      ]
    }
  }
]
"""
